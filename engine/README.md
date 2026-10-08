# Archaeologist Engine

The engine scans JavaScript and TypeScript repositories with Tree-sitter and
adds code-grounded file relationships to the structured repository model.
Import resolution is separate from parsing: the parser records import
statements, and `analyzer/resolver.py` maps local imports to discovered files.
`analyzer/architecture.py` builds a deterministic graph with one node per file,
deduplicated import edges, imported symbol bindings, and per-file dependency
counts. `analyzer/behavior.py` resolves supported local calls and constructs
evidence-backed React event/render, HTTP request, Express-style route, and
candidate-flow relationships. Unknown calls and ambiguous route matches are
omitted rather than guessed.

From the `engine/` directory in WSL, scan a repository with:

```bash
uv run python parser/analyze.py /mnt/c/Users/Akshat/Code/Orvex
```

The JSON output retains each file's raw `imports` and adds resolved edges:

```json
{
  "from": "src/App.tsx",
  "to": "src/components/Navbar.tsx",
  "type": "imports"
}
```

File symbols retain their name list and also have structured metadata inside the
engine model: a deterministic kind, plus whether the declaration is exported.
React components are identified from uppercase declarations containing JSX;
this is a static heuristic, not semantic inference.

Relative imports, `@/` imports (initially mapped to `src/`), supported source
extensions, and directory `index` files are resolved. Unresolved and external
package imports do not create relationships. Call `analyze_repository` with an
`aliases` mapping to configure other prefixes.

Run the engine tests from `engine/`:

```bash
uv run python -m unittest discover -s tests -v
```