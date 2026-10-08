from collections import Counter
from dataclasses import dataclass, field
from pathlib import PurePosixPath

from parser.models import RepositoryModel


@dataclass(frozen=True)
class ArchitectureSymbol:
    imported: str
    local: str


@dataclass
class ArchitectureNode:
    id: str
    path: str
    name: str
    language: str
    symbol_count: int
    imports_count: int = 0
    imported_by_count: int = 0
    exported_symbols: list[str] = field(default_factory=list)


@dataclass
class ArchitectureEdge:
    id: str
    source: str
    target: str
    type: str = "imports"
    symbols: list[ArchitectureSymbol] = field(default_factory=list)


@dataclass
class ArchitectureGraph:
    nodes: list[ArchitectureNode]
    edges: list[ArchitectureEdge]


def build_architecture(model: RepositoryModel) -> ArchitectureGraph:
    """Build a deterministic file graph from parser evidence and resolved imports."""
    nodes_by_path = {
        file.path: ArchitectureNode(
            id=file.path,
            path=file.path,
            name=PurePosixPath(file.path).name,
            language=file.language,
            symbol_count=len(file.symbol_details) or len(file.symbols),
            exported_symbols=[
                symbol.name for symbol in file.symbol_details if symbol.exported
            ],
        )
        for file in model.files
    }

    edges_by_pair: dict[tuple[str, str], ArchitectureEdge] = {}
    for relationship in sorted(
        model.relationships,
        key=lambda item: (item.from_path, item.to_path, item.type),
    ):
        if (
            relationship.from_path not in nodes_by_path
            or relationship.to_path not in nodes_by_path
        ):
            continue

        pair = (relationship.from_path, relationship.to_path)
        edge = edges_by_pair.get(pair)
        if edge is None:
            edge = ArchitectureEdge(
                id=f"{relationship.from_path}->{relationship.to_path}",
                source=relationship.from_path,
                target=relationship.to_path,
                type=relationship.type,
            )
            edges_by_pair[pair] = edge

        for symbol in relationship.symbols:
            metadata = ArchitectureSymbol(
                imported=symbol.imported,
                local=symbol.local,
            )
            if metadata not in edge.symbols:
                edge.symbols.append(metadata)

    for edge in edges_by_pair.values():
        edge.symbols.sort(key=lambda symbol: (symbol.imported, symbol.local))
        nodes_by_path[edge.source].imports_count += 1
        nodes_by_path[edge.target].imported_by_count += 1

    return ArchitectureGraph(
        nodes=sorted(nodes_by_path.values(), key=lambda node: node.path),
        edges=sorted(
            edges_by_pair.values(),
            key=lambda edge: (edge.source, edge.target, edge.type),
        ),
    )
