# Deployment

The web app deploys to Vercel; the FastAPI service deploys to Render using the
repository-root Dockerfile. The API image includes both `apps/api` and the
sibling `engine` package.

## 1. Push the repository

Create an empty GitHub repository, then add it as this workspace's `origin` and
push the `master` branch. The root `.gitignore` excludes `.env`; never force-add
the local environment file. Review `git status` before committing.

## 2. Deploy the API to Render

Create a Render Blueprint from the GitHub repository and use `render.yaml`.
Keep the Docker build context at the repository root so the image can copy the
engine. After Render assigns the API hostname, set these environment values in
the Render service dashboard:

- `API_PUBLIC_URL`: the full API origin, such as `https://your-api.onrender.com`
- `WEB_APP_URL`: the Vercel production origin, such as `https://your-app.vercel.app`
- `CORS_ALLOWED_ORIGINS`: comma-separated exact web origins allowed to call the
  API. Include the production URL and any Vercel preview origins you intend to use.
- `GITHUB_CLIENT_ID` and `GITHUB_CLIENT_SECRET`: from a GitHub OAuth App
- `AUTH_SESSION_SECRET`: a fresh random secret generated with `openssl rand -hex 32`

The blueprint enables secure cookies and `SameSite=None` for separate Vercel and
Render hosts. These hosts are cross-site; browsers that block third-party cookies
may still reject the identity cookie. For reliable production sign-in, use
custom domains under the same registrable domain, for example
`app.example.com` and `api.example.com`, and configure exact origins accordingly.

## 3. Deploy the web app to Vercel

Import the same GitHub repository into Vercel and set the project Root Directory
to `apps/web`. Add this environment variable for Production (and Preview if
needed):

- `NEXT_PUBLIC_API_URL`: `https://your-api.onrender.com/api`

Redeploy after setting it. The frontend uses this value for auth and analysis
requests; the browser never receives the GitHub OAuth client secret or provider
access token.

## 4. Configure GitHub OAuth

In GitHub Developer Settings, create an OAuth App with:

- Homepage URL: the Vercel production origin
- Authorization callback URL: `https://your-api.onrender.com/api/auth/github/callback`

Enter its client ID and secret in Render, not Vercel. The OAuth scope remains
identity-only (`read:user`); repository permissions are not requested.

The API health check is `https://your-api.onrender.com/api/health`. Render's free
service can sleep when idle, so initial requests may be delayed after inactivity.