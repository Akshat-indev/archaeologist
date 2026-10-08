from fastapi.testclient import TestClient

from app.main import app
from app.routes.auth import _create_session
import app.routes.auth as auth_routes


client = TestClient(app)


def test_github_session_is_anonymous_when_not_signed_in(monkeypatch) -> None:
    monkeypatch.delenv("GITHUB_CLIENT_ID", raising=False)
    monkeypatch.delenv("GITHUB_CLIENT_SECRET", raising=False)
    monkeypatch.delenv("AUTH_SESSION_SECRET", raising=False)

    response = client.get("/api/auth/me")

    assert response.status_code == 200
    assert response.json() == {
        "authenticated": False,
        "configured": False,
        "user": None,
    }


def test_github_login_explains_missing_oauth_configuration(monkeypatch) -> None:
    monkeypatch.delenv("GITHUB_CLIENT_ID", raising=False)
    monkeypatch.delenv("GITHUB_CLIENT_SECRET", raising=False)
    monkeypatch.delenv("AUTH_SESSION_SECRET", raising=False)

    response = client.get("/api/auth/github")

    assert response.status_code == 503
    assert "GITHUB_CLIENT_ID" in response.json()["detail"]


def test_analysis_and_job_results_require_github_sign_in() -> None:
    anonymous_client = TestClient(app)

    analyze_response = anonymous_client.post(
        "/api/analyze",
        json={"path": "/tmp/repository"},
    )
    job_response = anonymous_client.get("/api/analyses/unknown-job")

    assert analyze_response.status_code == 401
    assert job_response.status_code == 401
    assert analyze_response.json()["detail"] == (
        "Sign in with GitHub before analyzing a repository."
    )


def test_cookie_authenticated_mutations_reject_untrusted_origins(monkeypatch) -> None:
    monkeypatch.setenv("GITHUB_CLIENT_ID", "client-id")
    monkeypatch.setenv("GITHUB_CLIENT_SECRET", "client-secret")
    monkeypatch.setenv("AUTH_SESSION_SECRET", "a" * 48)
    csrf_client = TestClient(app)
    csrf_client.cookies.set(
        "archaeologist_session",
        _create_session(
            {"login": "octocat", "name": "Octocat", "avatar_url": ""},
            "a" * 48,
        ),
    )

    analyze_response = csrf_client.post(
        "/api/analyze",
        headers={"Origin": "https://attacker.example"},
        json={"path": "/tmp/repository"},
    )
    logout_response = csrf_client.post(
        "/api/auth/logout",
        headers={"Origin": "https://attacker.example"},
    )

    assert analyze_response.status_code == 403
    assert logout_response.status_code == 403


def test_github_login_redirects_with_csrf_state(monkeypatch) -> None:
    monkeypatch.setenv("GITHUB_CLIENT_ID", "client-id")
    monkeypatch.setenv("GITHUB_CLIENT_SECRET", "client-secret")
    monkeypatch.setenv("AUTH_SESSION_SECRET", "a" * 48)

    response = client.get("/api/auth/github", follow_redirects=False)

    assert response.status_code == 302
    assert response.headers["location"].startswith(
        "https://github.com/login/oauth/authorize?"
    )
    assert "state=" in response.headers["location"]
    assert "scope=read%3Auser" in response.headers["location"]
    assert "repo" not in response.headers["location"]
    assert "httponly" in response.headers["set-cookie"].lower()


def test_github_callback_keeps_provider_token_server_side(monkeypatch) -> None:
    monkeypatch.setenv("GITHUB_CLIENT_ID", "client-id")
    monkeypatch.setenv("GITHUB_CLIENT_SECRET", "client-secret")
    monkeypatch.setenv("AUTH_SESSION_SECRET", "a" * 48)
    monkeypatch.setenv("AUTH_COOKIE_SECURE", "true")
    monkeypatch.setenv("AUTH_COOKIE_SAMESITE", "none")

    class MockResponse:
        def __init__(self, body: dict[str, str]) -> None:
            self.body = body

        def raise_for_status(self) -> None:
            pass

        def json(self) -> dict[str, str]:
            return self.body

    class MockClient:
        def __init__(self, *args, **kwargs) -> None:
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args) -> None:
            pass

        async def post(self, *args, **kwargs) -> MockResponse:
            return MockResponse({"access_token": "provider-secret-token"})

        async def get(self, *args, **kwargs) -> MockResponse:
            return MockResponse(
                {
                    "login": "octocat",
                    "name": "Octocat",
                    "avatar_url": "https://example.test/avatar",
                }
            )

    monkeypatch.setattr(auth_routes.httpx, "AsyncClient", MockClient)
    secure_client = TestClient(app, base_url="https://testserver")
    secure_client.get("/api/auth/github", follow_redirects=False)
    state = secure_client.cookies.get("github_oauth_state")

    callback = secure_client.get(
        "/api/auth/github/callback",
        params={"code": "one-time-code", "state": state},
        follow_redirects=False,
    )

    assert callback.status_code == 303
    assert "auth=connected" in callback.headers["location"]
    session_cookie = callback.headers["set-cookie"]
    assert "provider-secret-token" not in session_cookie
    assert "httponly" in session_cookie.lower()
    assert "secure" in session_cookie.lower()
    assert "samesite=none" in session_cookie.lower()
    assert secure_client.get("/api/auth/me").json()["user"]["login"] == "octocat"


def test_signed_github_session_is_returned_but_tampering_is_rejected(monkeypatch) -> None:
    monkeypatch.setenv("GITHUB_CLIENT_ID", "client-id")
    monkeypatch.setenv("GITHUB_CLIENT_SECRET", "client-secret")
    monkeypatch.setenv("AUTH_SESSION_SECRET", "a" * 48)
    session = _create_session(
        {
            "login": "octocat",
            "name": "Octocat",
            "avatar_url": "https://example.test/avatar",
        },
        "a" * 48,
    )
    client.cookies.set("archaeologist_session", session)

    authenticated = client.get("/api/auth/me")
    client.cookies.set("archaeologist_session", session + "tampered")
    tampered = client.get("/api/auth/me")

    assert authenticated.json() == {
        "authenticated": True,
        "configured": True,
        "user": {
            "login": "octocat",
            "name": "Octocat",
            "avatar_url": "https://example.test/avatar",
        },
    }
    assert tampered.json()["authenticated"] is False


def test_logout_clears_the_session_cookie() -> None:
    response = client.post("/api/auth/logout")

    assert response.status_code == 204
    assert "max-age=0" in response.headers["set-cookie"].lower()