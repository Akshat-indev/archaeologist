# Archaeologist API

FastAPI service that runs the existing Tree-sitter engine against a local
repository. Analysis is deterministic and held in the response; no database is
used.

From this directory in WSL:

```bash
uv sync
uv run uvicorn app.main:app --reload --env-file ../../.env
```

The API listens at `http://localhost:8000`. The analyze screen is served by the
web app on `http://localhost:3000`; the API allows that origin for local CORS.
The API also allows `http://localhost:3001`, which Next.js may select when port
3000 is already occupied.

## GitHub sign-in

Create a GitHub OAuth App with callback URL
`http://localhost:8000/api/auth/github/callback`. Add its client ID and secret
to the repository `.env` file. Generate a session signing secret with
`openssl rand -hex 32` and set `AUTH_SESSION_SECRET` as well. `API_PUBLIC_URL`
and `WEB_APP_URL` default to the local addresses above. Restart the API after
changing `.env`.

Sign-in establishes identity only; repository analysis requires a valid signed-in
session and currently supports public repositories and local API paths. The OAuth
access token is used only to read the GitHub profile, then discarded. The browser
receives a signed, HTTP-only identity session cookie, never the provider token.

Endpoints:

- `GET /api/health`
- `GET /api/auth/github` to begin GitHub sign-in
- `GET /api/auth/github/callback` OAuth callback
- `GET /api/auth/me` to read the current signed-in identity
- `POST /api/auth/logout` to clear the identity session
- `POST /api/analyze` with `{"source": {"type": "github", "url": "https://github.com/owner/repository"}}` (requires sign-in)
- `GET /api/analyses/{analysis_id}` to poll a GitHub analysis job (requires sign-in)
- `POST /api/analyze` with `{"path": "/absolute/path/to/repository"}` for local development (requires sign-in)

GitHub analysis accepts public repository URLs only. It clones a shallow snapshot
without checking out repository files, reads the Git archive as data, ignores
symlinks, and removes the temporary workspace after analysis. Repository code is
never installed, imported, built, or executed. The in-process job registry is
intended for local experiments; jobs are lost when the API process restarts.

Limits can be configured in `.env` (see the repository's `.env.example`):

- `MAX_REPOSITORY_SIZE_MB` (default 1000)
- `MAX_FILE_COUNT` (default 20000)
- `MAX_FILE_SIZE_MB` (default 5)
- `MAX_ANALYSIS_FILES` (default 10000)
- `GITHUB_CLONE_TIMEOUT_SECONDS` (default 180)
- `MAX_FLOW_DEPTH` (default 20)
- `MAX_CANDIDATE_FLOWS` (default 200)

Exceeding a configured limit fails the job with a clear error; the engine does
not silently truncate a repository. JavaScript/TypeScript files are analyzed.
Other tracked files are reported as skipped with their paths and extension.

The analyze response includes:

- `architecture.nodes`: one stable-ID node per analyzed file, including isolated
  files, with language, symbol count, and dependency/dependent counts.
- `architecture.edges`: deduplicated resolved local imports, with imported and
  local symbol names when the declaration exposes them.
- `files`: raw import statements and structured symbol metadata.
- `entry_points` and `metrics`: detected common entry filenames and repository
  dependency statistics.
- `entities`, evidence-backed `relationships`, and candidate `flows`: behavior
  reconstructed from statically recognized calls, React events/rendering,
  HTTP requests, and Express-style routes.

External packages and unresolved imports remain parser evidence in each file's
`imports` list; they do not become architecture edges.
Behavior relationships include their source file, line, and categorical
confidence. Only statically resolved local calls and exact method/path matches
are connected; unknown calls and ambiguous routes are omitted.

Run API tests with:

```bash
uv run pytest
```
