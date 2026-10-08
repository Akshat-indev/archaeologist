# Archaeologist

Archaeologist statically analyzes JavaScript/TypeScript repositories and
reconstructs evidence-backed application behavior: React events, local function
calls, HTTP requests, backend routes, and candidate flows. The file import graph
remains supporting structural evidence; parsing and resolution are the source of
truth, with no LLM or database required.

The deterministic full-stack login fixture in `engine/tests/fixtures/login_app`
verifies the reconstructed chain from a React form submission through its
frontend request and backend route to the service method.

## Local development (WSL)

Start the API from `apps/api/`:

```bash
uv sync
uv run uvicorn app.main:app --reload --env-file ../../.env
```

Start the web app from `apps/web/`:

```bash
npm install
npm run dev
```

Open `http://localhost:3000` and paste a public GitHub repository URL such as
`https://github.com/withastro/astro`.
The API clones it into a temporary workspace and removes that workspace after
the result is built. It never executes repository code. The API is at
`http://localhost:8000`; API docs are at `/docs`.

## Tests

```bash
(cd engine && uv run python -m unittest discover -s tests -v)
(cd apps/api && uv run pytest)
(cd apps/web && npm run lint && npx tsc --noEmit)
```

## Deployment

See [DEPLOYMENT.md](DEPLOYMENT.md) for deploying the web app to Vercel and the
API to Render, including OAuth and production cookie configuration.