import sys
import json
import os
import re
from collections.abc import Mapping
from pathlib import Path

from tree_sitter import Language, Parser
import tree_sitter_javascript
import tree_sitter_typescript

ENGINE_ROOT = Path(__file__).resolve().parents[1]
if str(ENGINE_ROOT) not in sys.path:
    sys.path.insert(0, str(ENGINE_ROOT))

from analyzer.resolver import resolve_imports
from parser.behavior import extract_behavior_facts
from parser.models import FileInfo, RepositoryModel, SymbolInfo
from parser.traversal import walk_syntax_tree


# ---------------------------------------------------------
# Language configuration
# ---------------------------------------------------------

EXTENSION_TO_LANGUAGE = {
    ".js": "javascript",
    ".jsx": "javascript",
    ".ts": "typescript",
    ".tsx": "tsx",
}


LANGUAGES = {
    "javascript": Language(tree_sitter_javascript.language()),
    "typescript": Language(tree_sitter_typescript.language_typescript()),
    "tsx": Language(tree_sitter_typescript.language_tsx()),
}


# ---------------------------------------------------------
# Directories we don't want to analyze
# ---------------------------------------------------------

IGNORED_DIRECTORIES = {
    "node_modules",
    ".git",
    "dist",
    "build",
    ".next",
    ".nuxt",
    ".output",
    "coverage",
    ".cache",
    ".turbo",
    "out",
    "target",
    "vendor",
    "Pods",
    "DerivedData",
    "__pycache__",
    ".venv",
    "venv",
    "env",
}


# ---------------------------------------------------------
# Find source files
# ---------------------------------------------------------

def find_source_files(repo_path: Path):
    for current_directory, directories, filenames in os.walk(
        repo_path,
        topdown=True,
        followlinks=False,
    ):
        current_path = Path(current_directory)
        directories[:] = sorted(
            directory
            for directory in directories
            if directory not in IGNORED_DIRECTORIES
            and not (current_path / directory).is_symlink()
        )
        for filename in sorted(filenames):
            path = current_path / filename
            if path.is_symlink():
                continue
            if path.suffix.lower() in EXTENSION_TO_LANGUAGE:
                yield path


# ---------------------------------------------------------
# Extract imports
# ---------------------------------------------------------

def _node_text(node, source: bytes) -> str:
    try:
        return source[node.start_byte : node.end_byte].decode("utf-8")
    except (UnicodeDecodeError, IndexError, TypeError):
        return ""


def extract_imports(root_node, source: bytes):
    return [
        _node_text(node, source)
        for node in _walk_nodes(root_node)
        if node.type == "import_statement"
    ]


def _contains_jsx(node):
    jsx_node_types = {
        "jsx_element",
        "jsx_self_closing_element",
        "jsx_fragment",
    }
    return any(
        descendant.type in jsx_node_types
        for descendant in _walk_nodes(node)
    )


def _walk_nodes(node):
    for current, _depth in walk_syntax_tree(node):
        yield current


def extract_symbol_details(root_node, source: bytes):
    symbols = []
    re_exported_names = set()
    for node in _walk_nodes(root_node):
        if node.type != "export_statement":
            continue
        statement = _node_text(node, source)
        clause = re.search(r"\bexport\s*\{([^}]*)\}", statement)
        if clause is not None:
            for item in clause.group(1).split(","):
                local_name = item.strip().removeprefix("type ").split(" as ", 1)[0]
                if re.fullmatch(r"[A-Za-z_$][\w$]*", local_name):
                    re_exported_names.add(local_name)
        default_export = re.match(
            r"\s*export\s+default\s+([A-Za-z_$][\w$]*)\b",
            statement,
        )
        if default_export is not None:
            re_exported_names.add(default_export.group(1))

    def append_symbol(name, kind, exported, declaration, container=None):
        if (
            kind != "hook"
            and kind in {"function", "constant", "variable"}
            and name[:1].isupper()
            and _contains_jsx(declaration)
        ):
            kind = "react_component"

        symbols.append(
            SymbolInfo(
                name=name,
                kind=kind,
                exported=exported or name in re_exported_names,
                line=declaration.start_point.row + 1,
                container=container,
            )
        )

    contexts = [(False, None)]
    parent_types: list[str] = []
    for node, depth in walk_syntax_tree(root_node):
        while len(contexts) <= depth:
            contexts.append((False, None))
        exported, container = contexts[depth]
        parent_type = parent_types[depth - 1] if depth else None
        is_exported = exported or node.type == "export_statement"
        name_node = node.child_by_field_name("name")

        declaration_kinds = {
            "function_declaration": "function",
            "class_declaration": "class",
            "method_definition": "method",
            "interface_declaration": "interface",
            "type_alias_declaration": "type",
        }
        kind = declaration_kinds.get(node.type)
        if kind is not None and name_node is not None:
            name = _node_text(name_node, source)
            if kind == "function" and name.startswith("use"):
                kind = "hook"
            append_symbol(name, kind, is_exported, node, container)
            if kind == "class":
                container = name
            elif kind == "function":
                container = None

        if node.type == "lexical_declaration":
            declaration_text = source[node.start_byte : node.end_byte].lstrip()
            variable_kind = (
                "constant" if declaration_text.startswith(b"const") else "variable"
            )
            for child in node.named_children:
                if child.type != "variable_declarator":
                    continue
                variable_name = child.child_by_field_name("name")
                if (
                    variable_name is None
                    or variable_name.type not in {"identifier", "property_identifier"}
                ):
                    continue
                name = _node_text(variable_name, source)
                value = child.child_by_field_name("value")
                kind = variable_kind
                value_is_function = value is not None and any(
                    descendant.type in {"arrow_function", "function_expression"}
                    for descendant in _walk_nodes(value)
                )
                if name.startswith("use") and value_is_function:
                    kind = "hook"
                elif (
                    name[:1].isupper()
                    and value is not None
                    and _contains_jsx(value)
                ):
                    kind = "react_component"
                elif value_is_function:
                    kind = "function"
                append_symbol(
                    name,
                    kind,
                    is_exported,
                    value if value is not None else child,
                )

        if node.type == "method_definition":
            container = None

        if node.type == "variable_declarator" and parent_type == "lexical_declaration":
            variable_name = node.child_by_field_name("name")
            if variable_name is not None:
                container = _node_text(variable_name, source)

        declaration_node = node.type in declaration_kinds or node.type == "lexical_declaration"
        if len(contexts) <= depth + 1:
            contexts.append((False, None))
        contexts[depth + 1] = (
            False if declaration_node else is_exported,
            container,
        )
        if len(parent_types) <= depth:
            parent_types.append(node.type)
        else:
            parent_types[depth] = node.type

    return symbols


# ---------------------------------------------------------
# Analyze one file
# ---------------------------------------------------------

def analyze_file(file_path: Path, repo_path: Path):

    extension = file_path.suffix.lower()

    language = EXTENSION_TO_LANGUAGE[extension]

    parser = Parser(LANGUAGES[language])

    source = file_path.read_bytes()

    tree = parser.parse(source)
    symbol_details = extract_symbol_details(tree.root_node, source)

    relative_path = file_path.relative_to(repo_path)

    return FileInfo(
        path=str(relative_path).replace("\\", "/"),
        language=language,
        imports=extract_imports(tree.root_node, source),
        symbols=[symbol.name for symbol in symbol_details],
        symbol_details=symbol_details,
        behavior_facts=extract_behavior_facts(tree.root_node, source),
    )


# ---------------------------------------------------------
# Analyze entire repository
# ---------------------------------------------------------

def analyze_repository(
    repo_path: str,
    aliases: Mapping[str, str] | None = None,
):

    repo = Path(repo_path).resolve()

    if not repo.exists():
        raise FileNotFoundError(
            f"Repository not found: {repo}"
        )

    if not repo.is_dir():
        raise NotADirectoryError(
            f"Not a directory: {repo}"
        )

    files = []

    for file_path in sorted(
        find_source_files(repo),
        key=lambda path: path.relative_to(repo).as_posix(),
    ):

        file_info = analyze_file(file_path, repo)
        files.append(file_info)

    return RepositoryModel(
        repository=repo.name,
        files=files,
        relationships=resolve_imports(files, aliases),
    )


# ---------------------------------------------------------
# Convert model to JSON
# ---------------------------------------------------------

def model_to_dict(model: RepositoryModel):

    return {
        "repository": model.repository,

        "files": [
            {
                "path": file.path,
                "language": file.language,
                "imports": file.imports,
                "symbols": file.symbols,
            }
            for file in model.files
        ],
        "relationships": [
            {
                "from": relationship.from_path,
                "to": relationship.to_path,
                "type": relationship.type,
            }
            for relationship in model.relationships
        ],
    }


# ---------------------------------------------------------
# CLI
# ---------------------------------------------------------

def main():

    if len(sys.argv) != 2:

        print(
            "Usage: python analyze.py <repository-path>"
        )

        sys.exit(1)

    repo_path = sys.argv[1]

    model = analyze_repository(repo_path)

    output = model_to_dict(model)

    print(
        json.dumps(
            output,
            indent=2
        )
    )


if __name__ == "__main__":
    main()