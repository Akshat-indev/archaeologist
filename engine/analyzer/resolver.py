import posixpath
import re
from collections.abc import Mapping, Sequence

from parser.models import FileInfo, ImportedSymbol, Relationship


DEFAULT_ALIASES = {"@/": "src/"}
SOURCE_EXTENSIONS = (".ts", ".tsx", ".js", ".jsx")
INDEX_FILES = tuple(f"index{extension}" for extension in SOURCE_EXTENSIONS)

FROM_IMPORT_PATTERN = re.compile(r"\bfrom\s*(['\"])([^'\"]+)\1")
SIDE_EFFECT_IMPORT_PATTERN = re.compile(r"^\s*import\s*(['\"])([^'\"]+)\1")
IMPORT_CLAUSE_PATTERN = re.compile(
    r"^\s*import\s+(.*?)\s+from\s*['\"]",
    re.DOTALL,
)


def _import_source(statement: str) -> str | None:
    match = FROM_IMPORT_PATTERN.search(statement)
    if match is None:
        match = SIDE_EFFECT_IMPORT_PATTERN.search(statement)
    return match.group(2) if match is not None else None


def _imported_symbols(statement: str) -> list[ImportedSymbol]:
    match = IMPORT_CLAUSE_PATTERN.search(statement)
    if match is None:
        return []

    clause = match.group(1).strip()
    if clause.startswith("type "):
        clause = clause[5:].strip()

    symbols: list[ImportedSymbol] = []
    named_clause = re.search(r"\{([^}]*)\}", clause)
    if named_clause is not None:
        for item in named_clause.group(1).split(","):
            item = re.sub(r"^\s*type\s+", "", item).strip()
            if not item:
                continue
            parts = re.split(r"\s+as\s+", item, maxsplit=1)
            imported = parts[0].strip()
            local = parts[1].strip() if len(parts) == 2 else imported
            symbols.append(ImportedSymbol(imported=imported, local=local))

    namespace_clause = re.search(r"\*\s+as\s+([A-Za-z_$][\w$]*)", clause)
    if namespace_clause is not None:
        symbols.append(
            ImportedSymbol(imported="*", local=namespace_clause.group(1))
        )

    default_clause = clause.split(",", 1)[0].strip()
    if "{" not in default_clause and not default_clause.startswith("*"):
        default_clause = re.sub(r"^type\s+", "", default_clause)
        if re.fullmatch(r"[A-Za-z_$][\w$]*", default_clause):
            symbols.insert(
                0,
                ImportedSymbol(imported="default", local=default_clause),
            )

    return symbols


def _local_import_path(
    source_path: str,
    specifier: str,
    aliases: Mapping[str, str],
) -> str | None:
    for prefix in sorted(aliases, key=len, reverse=True):
        if specifier.startswith(prefix):
            return posixpath.normpath(
                posixpath.join(aliases[prefix], specifier[len(prefix) :])
            )

    if specifier.startswith(("./", "../")):
        return posixpath.normpath(
            posixpath.join(posixpath.dirname(source_path), specifier)
        )

    return None


def _candidate_paths(base_path: str) -> Sequence[str]:
    if base_path.endswith(SOURCE_EXTENSIONS):
        return (base_path,)

    return (
        *(f"{base_path}{extension}" for extension in SOURCE_EXTENSIONS),
        *(posixpath.join(base_path, index_file) for index_file in INDEX_FILES),
    )


def resolve_imports(
    files: Sequence[FileInfo],
    aliases: Mapping[str, str] | None = None,
) -> list[Relationship]:
    """Resolve local import declarations to repository-relative file paths."""
    alias_paths = DEFAULT_ALIASES if aliases is None else aliases
    available_paths = {file.path.replace("\\", "/") for file in files}
    relationships: list[Relationship] = []
    edges_by_pair: dict[tuple[str, str], Relationship] = {}

    for file in files:
        source_path = file.path.replace("\\", "/")
        for statement in file.imports:
            specifier = _import_source(statement)
            if specifier is None:
                continue

            base_path = _local_import_path(source_path, specifier, alias_paths)
            if base_path is None:
                continue

            target_path = next(
                (
                    candidate
                    for candidate in _candidate_paths(base_path)
                    if candidate in available_paths
                ),
                None,
            )
            if target_path is None:
                continue

            edge_key = (source_path, target_path)
            relationship = edges_by_pair.get(edge_key)
            if relationship is None:
                relationship = Relationship(
                    from_path=source_path,
                    to_path=target_path,
                )
                edges_by_pair[edge_key] = relationship
                relationships.append(relationship)

            for symbol in _imported_symbols(statement):
                if symbol not in relationship.symbols:
                    relationship.symbols.append(symbol)

    return relationships
