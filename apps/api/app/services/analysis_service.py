import sys
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Callable

ENGINE_ROOT = Path(__file__).resolve().parents[4] / "engine"
if str(ENGINE_ROOT) not in sys.path:
    sys.path.insert(0, str(ENGINE_ROOT))

from analyzer.architecture import build_architecture
from analyzer.behavior import build_behavior_graph
from analyzer.resolver import resolve_imports
from parser.analyze import analyze_file, analyze_repository, find_source_files
from parser.models import RepositoryModel

from app.schemas.analysis import (
    AnalysisMetrics,
    AnalysisResponse,
    Architecture,
    ArchitectureEdge,
    ArchitectureNode,
    BehaviorEntity as BehaviorEntityResponse,
    BehaviorFlow as BehaviorFlowResponse,
    BehaviorRelationship as BehaviorRelationshipResponse,
    Evidence as EvidenceResponse,
    EntryPoint,
    FileAnalysis,
    FileFrequency,
    FileSymbol,
    FlowTrigger as FlowTriggerResponse,
    ImportedSymbol,
    RepositoryInfo,
    SymbolAnalysis,
)


ENTRY_POINT_NAMES = {
    "src/main.tsx",
    "src/main.ts",
    "src/index.tsx",
    "src/index.ts",
    "src/App.tsx",
    "src/App.ts",
}


class RepositoryNotFoundError(Exception):
    pass


class RepositoryPathError(Exception):
    pass


class UnsupportedRepositoryError(Exception):
    pass


class RepositoryAnalysisError(Exception):
    pass


def _analysis_response_for_model(
    model,
    resolved_path: Path,
    graph,
    behavior,
) -> AnalysisResponse:
    language_summary = Counter(file.language for file in model.files)
    entry_points = [
        EntryPoint(path=file.path)
        for file in model.files
        if file.path in ENTRY_POINT_NAMES
    ]
    symbols = [
        SymbolAnalysis(
            id=f"{file.path}::{symbol.container + '.' if symbol.container else ''}{symbol.name}",
            name=symbol.name,
            kind=symbol.kind,
            file=file.path,
            exported=symbol.exported,
            line=symbol.line,
        )
        for file in model.files
        for symbol in file.symbol_details
    ]
    total_symbols = len(symbols)
    component_count = sum(symbol.kind == "react_component" for symbol in symbols)
    behavior_relationships = [
        BehaviorRelationshipResponse(
            id=(
                f"relationship:{relationship.from_id}:{relationship.type}:"
                f"{relationship.to_id}:{relationship.evidence.file}:"
                f"{relationship.evidence.line}"
            ),
            **{
                "from": relationship.from_id,
                "to": relationship.to_id,
            },
            type=relationship.type,
            confidence=relationship.confidence,
            evidence=EvidenceResponse(
                file=relationship.evidence.file,
                line=relationship.evidence.line,
            ),
            label=relationship.label,
        )
        for relationship in behavior.relationships
    ]
    behavior_relationship_by_id = {
        relationship.id: relationship for relationship in behavior_relationships
    }
    return AnalysisResponse(
        repository=RepositoryInfo(
            name=model.repository,
            path=str(resolved_path),
            language_summary=dict(sorted(language_summary.items())),
            analysis_timestamp=datetime.now(UTC).isoformat(),
        ),
        entry_points=entry_points,
        metrics=AnalysisMetrics(
            total_files=len(model.files),
            total_symbols=total_symbols,
            total_relationships=len(graph.edges),
            typescript_files=language_summary["typescript"] + language_summary["tsx"],
            javascript_files=language_summary["javascript"],
            react_components=component_count,
            files_without_dependencies=sum(
                node.imports_count == 0 for node in graph.nodes
            ),
            files_without_dependents=sum(
                node.imported_by_count == 0 for node in graph.nodes
            ),
            most_imported_files=[
                FileFrequency(path=node.path, count=node.imported_by_count)
                for node in sorted(
                    graph.nodes,
                    key=lambda item: (-item.imported_by_count, item.path),
                )
                if node.imported_by_count > 0
            ][:5],
            files=len(model.files),
            symbols=total_symbols,
            relationships=len(behavior_relationships),
            components=component_count,
            functions=sum(
                symbol.kind in {"function", "method", "hook"}
                for symbol in symbols
            ),
            routes=sum(entity.kind == "api_route" for entity in behavior.entities),
            http_requests=sum(
                entity.kind == "http_request" for entity in behavior.entities
            ),
            flows=len(behavior.flows),
        ),
        architecture=Architecture(
            nodes=[
                ArchitectureNode(
                    id=node.id,
                    path=node.path,
                    name=node.name,
                    language=node.language,
                    symbol_count=node.symbol_count,
                    imports_count=node.imports_count,
                    imported_by_count=node.imported_by_count,
                    exported_symbols=node.exported_symbols,
                )
                for node in graph.nodes
            ],
            edges=[
                ArchitectureEdge(
                    id=edge.id,
                    source=edge.source,
                    target=edge.target,
                    type=edge.type,
                    symbols=[
                        ImportedSymbol(imported=symbol.imported, local=symbol.local)
                        for symbol in edge.symbols
                    ],
                )
                for edge in graph.edges
            ],
        ),
        files=[
            FileAnalysis(
                path=file.path,
                language=file.language,
                imports=file.imports,
                symbols=[
                    FileSymbol(
                        name=symbol.name,
                        kind=symbol.kind,
                        exported=symbol.exported,
                        line=symbol.line,
                    )
                    for symbol in file.symbol_details
                ],
            )
            for file in model.files
        ],
        symbols=symbols,
        entities=[
            BehaviorEntityResponse(
                id=entity.id,
                name=entity.name,
                kind=entity.kind,
                file=entity.file,
                line=entity.line,
                method=entity.method,
                path=entity.path,
            )
            for entity in behavior.entities
        ],
        relationships=behavior_relationships,
        flows=[
            BehaviorFlowResponse(
                id=flow.id,
                name=flow.name,
                trigger=FlowTriggerResponse(
                    type=flow.trigger.type,
                    source=flow.trigger.source,
                    label=flow.trigger.label,
                ),
                nodes=[
                    BehaviorEntityResponse(
                        id=entity.id,
                        name=entity.name,
                        kind=entity.kind,
                        file=entity.file,
                        line=entity.line,
                        method=entity.method,
                        path=entity.path,
                    )
                    for entity in flow.nodes
                ],
                relationships=[
                    behavior_relationship_by_id[
                        (
                            f"relationship:{relationship.from_id}:{relationship.type}:"
                            f"{relationship.to_id}:{relationship.evidence.file}:"
                            f"{relationship.evidence.line}"
                        )
                    ]
                    for relationship in flow.relationships
                ],
            )
            for flow in behavior.flows
        ],
    )


def analyze_repository_path(
    repository_path: str,
    progress_callback: Callable[..., None] | None = None,
    allow_unsupported_only: bool = False,
    max_flow_depth: int = 20,
    max_flows: int = 200,
) -> AnalysisResponse:
    requested_path = Path(repository_path).expanduser()
    try:
        resolved_path = requested_path.resolve(strict=True)
    except FileNotFoundError as error:
        raise RepositoryNotFoundError("Repository path does not exist.") from error
    except OSError as error:
        raise RepositoryPathError("Repository path is not accessible.") from error

    if not resolved_path.is_dir():
        raise RepositoryPathError("Repository path must be a directory.")

    try:
        source_files = sorted(
            find_source_files(resolved_path),
            key=lambda path: path.relative_to(resolved_path).as_posix(),
        )
        total_files = len(source_files)
        if total_files == 0:
            if not allow_unsupported_only:
                raise UnsupportedRepositoryError(
                    "No supported JavaScript or TypeScript source files were found."
                )
            return AnalysisResponse(
                repository=RepositoryInfo(
                    name=resolved_path.name,
                    path=str(resolved_path),
                    language_summary={},
                    analysis_timestamp=datetime.now(UTC).isoformat(),
                ),
                entry_points=[],
                metrics=AnalysisMetrics(
                    total_files=0,
                    total_symbols=0,
                    total_relationships=0,
                    typescript_files=0,
                    javascript_files=0,
                    react_components=0,
                    files_without_dependencies=0,
                    files_without_dependents=0,
                    most_imported_files=[],
                    files=0,
                    symbols=0,
                    relationships=0,
                    components=0,
                    functions=0,
                    routes=0,
                    http_requests=0,
                    flows=0,
                ),
                architecture=Architecture(nodes=[], edges=[]),
                files=[],
                symbols=[],
                entities=[],
                relationships=[],
                flows=[],
            )

        files: list = []
        chunk_size = max(1, total_files // 4)

        for index, file_path in enumerate(source_files, start=1):
            files.append(analyze_file(file_path, resolved_path))
            if progress_callback is not None and index < total_files and (
                index % chunk_size == 0 or index == total_files - 1
            ):
                partial_model = RepositoryModel(
                    repository=resolved_path.name,
                    files=files,
                    relationships=resolve_imports(files),
                )
                partial_graph = build_architecture(partial_model)
                partial_behavior = build_behavior_graph(
                    partial_model,
                    max_flow_depth=max_flow_depth,
                    max_flows=max_flows,
                )
                percent = min(100, int((index / total_files) * 100))
                partial_result = _analysis_response_for_model(
                    partial_model,
                    resolved_path,
                    partial_graph,
                    partial_behavior,
                )
                try:
                    progress_callback(
                        "parsing",
                        {
                            "files_discovered": total_files,
                            "files_analyzed": index,
                            "files_skipped": 0,
                            "percent": percent,
                        },
                        partial_result,
                    )
                except TypeError:
                    progress_callback(
                        "parsing",
                        {
                            "files_discovered": total_files,
                            "files_analyzed": index,
                            "files_skipped": 0,
                            "percent": percent,
                        },
                    )

        model = RepositoryModel(
            repository=resolved_path.name,
            files=files,
            relationships=resolve_imports(files),
        )
    except (OSError, UnicodeError, ValueError, RuntimeError) as error:
        raise RepositoryAnalysisError(
            "The repository could not be analyzed."
        ) from error

    if not model.files:
        if not allow_unsupported_only:
            raise UnsupportedRepositoryError(
                "No supported JavaScript or TypeScript source files were found."
            )

    if progress_callback is not None:
        progress_callback("analyzing", {"files_analyzed": len(model.files), "percent": 100})

    try:
        graph = build_architecture(model)
        if progress_callback is not None:
            progress_callback("building_flows", {"files_analyzed": len(model.files), "percent": 100})
        behavior = build_behavior_graph(
            model,
            max_flow_depth=max_flow_depth,
            max_flows=max_flows,
        )
    except (OSError, UnicodeError, ValueError, RuntimeError) as error:
        raise RepositoryAnalysisError(
            "The repository could not be analyzed."
        ) from error

    return _analysis_response_for_model(model, resolved_path, graph, behavior)
