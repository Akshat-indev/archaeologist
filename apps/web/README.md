# Archaeologist Web

Next.js frontend for the local static-analysis MVP. It submits a repository
path to the API, then presents overview metrics, an import graph, files, and
statically detected symbols.

From this directory:

```bash
npm ci --include=optional
npm run dev
```

In WSL, make sure the shell uses Linux Node before installing or starting the
frontend. WSL can find Windows `npm` on its `PATH` even when Linux Node is not
installed:

```bash
source "$HOME/.nvm/nvm.sh"
nvm install --lts
nvm use --lts
node -p process.platform
command -v node
```

The platform check must print `linux`, and `node` should resolve under
`/home/<user>/.nvm/`. If it prints `win32` or resolves under `/mnt/c/Program
Files/nodejs`, stop: Next.js and Lightning CSS will load Windows native
binaries from the WSL process. Keep the web app's `node_modules` for one
platform at a time; do not alternate Windows and WSL installs in the same
directory.

The API defaults to `http://localhost:8000/api`. Set `NEXT_PUBLIC_API_URL` to
override it. The API must be running and able to access the repository path.
