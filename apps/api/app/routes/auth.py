import base64
import hashlib
import hmac
import json
import os
import secrets
import time
from typing import Any
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, Cookie, HTTPException, Request, Response
from fastapi.responses import RedirectResponse


router = APIRouter(prefix="/api/auth", tags=["authentication"])
_SESSION_COOKIE = "archaeologist_session"
_STATE_COOKIE = "github_oauth_state"
_SESSION_MAX_AGE = 60 * 60 * 24 * 7


def _configuration() -> dict[str, str] | None:
    client_id = os.environ.get("GITHUB_CLIENT_ID", "").strip()
    client_secret = os.environ.get("GITHUB_CLIENT_SECRET", "").strip()
    signing_secret = os.environ.get("AUTH_SESSION_SECRET", "").strip()
    if not client_id or not client_secret or len(signing_secret) < 32:
        return None

    api_url = os.environ.get("API_PUBLIC_URL", "http://localhost:8000").rstrip("/")
    return {
        "client_id": client_id,
        "client_secret": client_secret,
        "signing_secret": signing_secret,
        "redirect_uri": os.environ.get(
            "GITHUB_REDIRECT_URI",
            f"{api_url}/api/auth/github/callback",
        ),
        "web_url": os.environ.get("WEB_APP_URL", "http://localhost:3000").rstrip("/"),
    }


def _cookie_secure(request: Request) -> bool:
    configured = os.environ.get("AUTH_COOKIE_SECURE")
    if configured is not None:
        return configured.lower() in {"1", "true", "yes"}
    return request.url.scheme == "https"


def _cookie_samesite() -> str:
    value = os.environ.get("AUTH_COOKIE_SAMESITE", "lax").strip().lower()
    if value not in {"lax", "strict", "none"}:
        return "lax"
    return value


def _trusted_origins() -> set[str]:
    configured = os.environ.get("CORS_ALLOWED_ORIGINS", "")
    origins = {
        origin.strip().rstrip("/")
        for origin in configured.split(",")
        if origin.strip()
    }
    origins.add(
        os.environ.get("WEB_APP_URL", "http://localhost:3000").strip().rstrip("/")
    )
    if not configured:
        origins.add("http://localhost:3001")
    return origins


def _validate_request_origin(request: Request) -> None:
    origin = request.headers.get("origin")
    if origin and origin.rstrip("/") not in _trusted_origins():
        raise HTTPException(status_code=403, detail="Request origin is not allowed.")


def _encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def _create_session(user: dict[str, str], signing_secret: str) -> str:
    payload = json.dumps(
        {"user": user, "expires": int(time.time()) + _SESSION_MAX_AGE},
        separators=(",", ":"),
    ).encode("utf-8")
    encoded_payload = _encode(payload)
    signature = hmac.new(
        signing_secret.encode("utf-8"),
        encoded_payload.encode("ascii"),
        hashlib.sha256,
    ).digest()
    return f"{encoded_payload}.{_encode(signature)}"


def _read_session(cookie: str | None) -> dict[str, str] | None:
    configuration = _configuration()
    if not cookie or configuration is None:
        return None
    try:
        encoded_payload, encoded_signature = cookie.split(".", 1)
        expected_signature = hmac.new(
            configuration["signing_secret"].encode("utf-8"),
            encoded_payload.encode("ascii"),
            hashlib.sha256,
        ).digest()
        if not hmac.compare_digest(_decode(encoded_signature), expected_signature):
            return None
        payload: Any = json.loads(_decode(encoded_payload))
        user = payload.get("user")
        if payload.get("expires", 0) < int(time.time()) or not isinstance(user, dict):
            return None
        if not isinstance(user.get("login"), str):
            return None
        return {
            "login": user["login"],
            "name": user.get("name") or user["login"],
            "avatar_url": user.get("avatar_url", ""),
        }
    except (ValueError, TypeError, json.JSONDecodeError):
        return None


def _frontend_redirect(configuration: dict[str, str], result: str) -> RedirectResponse:
    return RedirectResponse(f"{configuration['web_url']}/?auth={result}", status_code=303)


@router.get("/github")
def start_github_login(request: Request) -> RedirectResponse:
    configuration = _configuration()
    if configuration is None:
        raise HTTPException(
            status_code=503,
            detail=(
                "GitHub sign-in is not configured. Set GITHUB_CLIENT_ID, "
                "GITHUB_CLIENT_SECRET, and a 32-character AUTH_SESSION_SECRET."
            ),
        )

    state = secrets.token_urlsafe(32)
    authorize_url = "https://github.com/login/oauth/authorize?" + urlencode(
        {
            "client_id": configuration["client_id"],
            "redirect_uri": configuration["redirect_uri"],
            "scope": "read:user",
            "state": state,
        }
    )
    response = RedirectResponse(authorize_url, status_code=302)
    response.set_cookie(
        _STATE_COOKIE,
        state,
        max_age=600,
        httponly=True,
        secure=_cookie_secure(request),
        samesite="lax",
        path="/api/auth/github",
    )
    return response


@router.get("/github/callback")
async def finish_github_login(
    request: Request,
    response: Response,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
    oauth_state: str | None = Cookie(default=None, alias=_STATE_COOKIE),
) -> RedirectResponse:
    configuration = _configuration()
    if configuration is None:
        raise HTTPException(status_code=503, detail="GitHub sign-in is not configured.")
    if error:
        redirect = _frontend_redirect(configuration, "cancelled")
    elif (
        not code
        or not state
        or not oauth_state
        or not secrets.compare_digest(state, oauth_state)
    ):
        redirect = _frontend_redirect(configuration, "invalid_state")
    else:
        try:
            async with httpx.AsyncClient(timeout=12.0) as client:
                token_response = await client.post(
                    "https://github.com/login/oauth/access_token",
                    headers={"Accept": "application/json"},
                    data={
                        "client_id": configuration["client_id"],
                        "client_secret": configuration["client_secret"],
                        "code": code,
                        "redirect_uri": configuration["redirect_uri"],
                        "state": state,
                    },
                )
                token_response.raise_for_status()
                token_data = token_response.json()
                access_token = token_data.get("access_token")
                if not isinstance(access_token, str) or not access_token:
                    raise ValueError("GitHub did not return an access token.")

                user_response = await client.get(
                    "https://api.github.com/user",
                    headers={
                        "Accept": "application/vnd.github+json",
                        "Authorization": f"Bearer {access_token}",
                        "X-GitHub-Api-Version": "2022-11-28",
                    },
                )
                user_response.raise_for_status()
                github_user = user_response.json()

            login = github_user.get("login")
            if not isinstance(login, str) or not login:
                raise ValueError("GitHub did not return a valid account.")
            user = {
                "login": login,
                "name": github_user.get("name") or login,
                "avatar_url": github_user.get("avatar_url") or "",
            }
            redirect = _frontend_redirect(configuration, "connected")
            redirect.set_cookie(
                _SESSION_COOKIE,
                _create_session(user, configuration["signing_secret"]),
                max_age=_SESSION_MAX_AGE,
                httponly=True,
                secure=_cookie_secure(request),
                samesite=_cookie_samesite(),
                path="/",
            )
        except (httpx.HTTPError, ValueError, KeyError):
            redirect = _frontend_redirect(configuration, "failed")

    redirect.delete_cookie(
        _STATE_COOKIE,
        path="/api/auth/github",
        secure=_cookie_secure(request),
        httponly=True,
        samesite=_cookie_samesite(),
    )
    return redirect


@router.get("/me")
def read_github_session(
    session: str | None = Cookie(default=None, alias=_SESSION_COOKIE),
) -> dict[str, Any]:
    user = _read_session(session)
    return {
        "authenticated": user is not None,
        "configured": _configuration() is not None,
        "user": user,
    }


def require_github_user(
    request: Request,
    session: str | None = Cookie(default=None, alias=_SESSION_COOKIE),
) -> dict[str, str]:
    _validate_request_origin(request)
    user = _read_session(session)
    if user is None:
        raise HTTPException(
            status_code=401,
            detail="Sign in with GitHub before analyzing a repository.",
        )
    return user


@router.post("/logout", status_code=204)
def logout(request: Request, response: Response) -> Response:
    _validate_request_origin(request)
    response.status_code = 204
    response.delete_cookie(
        _SESSION_COOKIE,
        path="/",
        secure=_cookie_secure(request),
        httponly=True,
        samesite="lax",
    )
    return response