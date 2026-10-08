from collections import defaultdict, deque
from dataclasses import dataclass
import os

from parser.models import (
    BehaviorEntity,
    BehaviorRelationship,
    Evidence,
    RepositoryModel,
    SymbolInfo,
)


@dataclass(frozen=True)
class FlowTrigger:
    type: str
    source: str
    label: str


@dataclass
class BehaviorFlow:
    id: str
    name: str
    trigger: FlowTrigger
    nodes: list[BehaviorEntity]
    relationships: list[BehaviorRelationship]


@dataclass
class BehaviorGraph:
    entities: list[BehaviorEntity]
    relationships: list[BehaviorRelationship]
    flows: list[BehaviorFlow]


def _symbol_id(file_path: str, symbol: SymbolInfo) -> str:
    name = f"{symbol.container}.{symbol.name}" if symbol.container else symbol.name
    return f"{file_path}::{name}"


def _normalize_path(path: str) -> str:
    return path.rstrip("/") or "/"


def _build_behavior(model: RepositoryModel) -> tuple[
    list[BehaviorEntity], list[BehaviorRelationship]
]:
    files = {file.path: file for file in model.files}
    entities: dict[str, BehaviorEntity] = {}
    symbols_by_file: dict[str, list[tuple[SymbolInfo, BehaviorEntity]]] = {}

    for file in model.files:
        file_symbols: list[tuple[SymbolInfo, BehaviorEntity]] = []
        for symbol in file.symbol_details:
            entity = BehaviorEntity(
                id=_symbol_id(file.path, symbol),
                name=symbol.name,
                kind=symbol.kind,
                file=file.path,
                line=symbol.line,
            )
            entities[entity.id] = entity
            file_symbols.append((symbol, entity))
        symbols_by_file[file.path] = file_symbols

    imported_bindings: dict[str, dict[str, tuple[str, str]]] = defaultdict(dict)
    for relationship in model.relationships:
        for symbol in relationship.symbols:
            imported_bindings[relationship.from_path][symbol.local] = (
                relationship.to_path,
                symbol.imported,
            )

    def resolve_symbol(
        file_path: str,
        name: str | None,
        receiver: str | None = None,
    ) -> BehaviorEntity | None:
        if not name or file_path not in files:
            return None

        same_file = symbols_by_file.get(file_path, [])
        if receiver == "this":
            candidates = [
                entity
                for symbol, entity in same_file
                if symbol.name == name and symbol.kind == "method"
            ]
            return candidates[0] if len(candidates) == 1 else None

        binding = imported_bindings[file_path].get(receiver or name)
        if binding is not None:
            target_path, imported_name = binding
            target_symbols = symbols_by_file.get(target_path, [])
            if receiver is None:
                candidates = [
                    entity
                    for symbol, entity in target_symbols
                    if (
                        symbol.name == imported_name
                        and symbol.exported
                        and symbol.kind
                        in {
                            "function",
                            "hook",
                            "method",
                            "react_component",
                            "class",
                        }
                    )
                    or (
                        imported_name == "default"
                        and symbol.exported
                        and symbol.kind in {"function", "hook", "class", "react_component"}
                    )
                ]
            else:
                imported_owner = imported_name
                if imported_name == "default":
                    imported_owner = next(
                        (
                            symbol.name
                            for symbol, _ in target_symbols
                            if symbol.exported
                            and symbol.kind in {"class", "react_component"}
                        ),
                        imported_name,
                    )
                candidates = [
                    entity
                    for symbol, entity in target_symbols
                    if symbol.name == name
                    and symbol.kind == "method"
                    and symbol.container in {receiver, imported_owner}
                    and any(
                        owner.name == symbol.container and owner.exported
                        for owner, _ in target_symbols
                    )
                ]
            return candidates[0] if len(candidates) == 1 else None

        candidates = [
            entity
            for symbol, entity in same_file
            if symbol.name == name
            and (
                receiver is None
                or symbol.container == receiver
            )
            and symbol.kind
            in {"function", "hook", "method", "react_component", "class"}
        ]
        if len(candidates) == 1:
            return candidates[0]

        if receiver is None:
            imported = imported_bindings[file_path].get(name)
            if imported is not None:
                target_path, imported_name = imported
                candidates = [
                    entity
                    for symbol, entity in symbols_by_file.get(target_path, [])
                    if (
                        symbol.name == imported_name
                        and symbol.exported
                        and symbol.kind
                        in {
                            "function",
                            "hook",
                            "method",
                            "react_component",
                            "class",
                        }
                    )
                    or (
                        imported_name == "default"
                        and symbol.exported
                        and symbol.kind in {"function", "class", "react_component"}
                    )
                ]
                if len(candidates) == 1:
                    return candidates[0]
        return None

    relationships: dict[tuple[str, str, str, str, int], BehaviorRelationship] = {}

    def add_relationship(
        source: BehaviorEntity,
        target: BehaviorEntity,
        relation_type: str,
        file_path: str,
        line: int,
        label: str | None = None,
    ) -> None:
        key = (source.id, target.id, relation_type, file_path, line)
        relationships[key] = BehaviorRelationship(
            from_id=source.id,
            to_id=target.id,
            type=relation_type,
            evidence=Evidence(file=file_path, line=line),
            label=label,
        )

    route_entities: dict[tuple[str, str], BehaviorEntity] = {}
    request_entities: dict[tuple[str, str], BehaviorEntity] = {}
    route_declaration_counts: dict[tuple[str, str], int] = defaultdict(int)

    for file in model.files:
        for fact in file.behavior_facts:
            if fact.kind == "route" and fact.method and fact.path:
                route_key = (fact.method.upper(), _normalize_path(fact.path))
                route_declaration_counts[route_key] += 1
                route_id = f"route:{route_key[0]}:{route_key[1]}"
                route_entities.setdefault(
                    route_key,
                    BehaviorEntity(
                        id=route_id,
                        name=f"{route_key[0]} {route_key[1]}",
                        kind="api_route",
                        file=file.path,
                        line=fact.line,
                        method=route_key[0],
                        path=route_key[1],
                    ),
                )
            if fact.kind == "http_request" and fact.method and fact.path:
                request_key = (fact.method.upper(), fact.path)
                request_id = f"http:{request_key[0]}:{request_key[1]}"
                request_entities.setdefault(
                    request_key,
                    BehaviorEntity(
                        id=request_id,
                        name=f"{request_key[0]} {request_key[1]}",
                        kind="http_request",
                        file=file.path,
                        line=fact.line,
                        method=request_key[0],
                        path=fact.path,
                    ),
                )

    entities.update({item.id: item for item in route_entities.values()})
    entities.update({item.id: item for item in request_entities.values()})

    for file in model.files:
        for fact in file.behavior_facts:
            if fact.kind == "render" and fact.caller and fact.name:
                source = resolve_symbol(file.path, fact.caller)
                target = resolve_symbol(file.path, fact.name)
                if (
                    source is not None
                    and source.kind == "react_component"
                    and target is not None
                    and target.kind == "react_component"
                ):
                    add_relationship(source, target, "renders", file.path, fact.line)
            elif fact.kind == "event" and fact.caller and fact.target:
                source = resolve_symbol(file.path, fact.caller)
                target = resolve_symbol(file.path, fact.target)
                if target is None and fact.target.startswith("$"):
                    target = BehaviorEntity(
                        id=f"{file.path}::{fact.target}",
                        name=fact.target,
                        kind="function",
                        file=file.path,
                        line=fact.line,
                    )
                    entities[target.id] = target
                if (
                    source is not None
                    and source.kind == "react_component"
                    and target is not None
                ):
                    add_relationship(
                        source,
                        target,
                        "handles_event",
                        file.path,
                        fact.line,
                        fact.name,
                    )
            elif fact.kind == "call" and fact.caller and fact.name:
                source = resolve_symbol(file.path, fact.caller)
                if source is None and fact.caller.startswith("$"):
                    source = entities.get(f"{file.path}::{fact.caller}")
                target = resolve_symbol(file.path, fact.name, fact.receiver)
                if source is not None and target is not None:
                    add_relationship(source, target, "calls", file.path, fact.line)
            elif fact.kind == "http_request" and fact.caller and fact.method and fact.path:
                source = resolve_symbol(file.path, fact.caller)
                target = request_entities[(fact.method.upper(), fact.path)]
                if source is not None:
                    add_relationship(
                        source,
                        target,
                        "http_request",
                        file.path,
                        fact.line,
                    )
            elif fact.kind == "route" and fact.method and fact.path:
                route_key = (fact.method.upper(), _normalize_path(fact.path))
                route = route_entities[route_key]
                if route_declaration_counts[route_key] != 1:
                    continue
                if fact.target:
                    target = resolve_symbol(
                        file.path,
                        fact.target,
                        fact.receiver,
                    )
                    if target is not None:
                        add_relationship(
                            route,
                            target,
                            "handled_by",
                            file.path,
                            fact.line,
                        )

    routes_by_key: dict[tuple[str, str], list[BehaviorEntity]] = defaultdict(list)
    for key, route in route_entities.items():
        routes_by_key[key].append(route)
    for file in model.files:
        for fact in file.behavior_facts:
            if fact.kind != "http_request" or not fact.method or not fact.path:
                continue
            request_key = (fact.method.upper(), fact.path)
            route_key = (request_key[0], _normalize_path(request_key[1]))
            routes = routes_by_key.get(route_key, [])
            if len(routes) != 1 or route_declaration_counts[route_key] != 1:
                continue
            add_relationship(
                request_entities[request_key],
                routes[0],
                "matches_route",
                file.path,
                fact.line,
            )

    return (
        sorted(entities.values(), key=lambda entity: entity.id),
        sorted(
            relationships.values(),
            key=lambda relationship: (
                relationship.evidence.file,
                relationship.evidence.line,
                relationship.from_id,
                relationship.type,
                relationship.to_id,
            ),
        ),
    )


def build_behavior_graph(
    model: RepositoryModel,
    max_flow_depth: int = 20,
    max_flows: int = 200,
) -> BehaviorGraph:
    entities, relationships = _build_behavior(model)
    entity_by_id = {entity.id: entity for entity in entities}
    outgoing: dict[str, list[BehaviorRelationship]] = defaultdict(list)
    for relationship in relationships:
        outgoing[relationship.from_id].append(relationship)

    flows: list[BehaviorFlow] = []
    for trigger_edge in relationships:
        if trigger_edge.type != "handles_event":
            continue
        if len(flows) >= max_flows:
            break

        start_id = trigger_edge.from_id
        reachable = {start_id, trigger_edge.to_id}
        queue = deque([(trigger_edge.to_id, 0)])
        reached_relationships: list[BehaviorRelationship] = []
        while queue:
            source_id, depth = queue.popleft()
            if depth >= max_flow_depth:
                continue
            for relationship in outgoing[source_id]:
                if relationship.type in {"renders", "handles_event"}:
                    continue
                reached_relationships.append(relationship)
                if relationship.to_id not in reachable:
                    reachable.add(relationship.to_id)
                    queue.append((relationship.to_id, depth + 1))

        flow_relationships = [
            trigger_edge,
            *(
                relationship for relationship in reached_relationships
            ),
        ]
        if not flow_relationships:
            continue
        used_ids = {start_id}
        for relationship in flow_relationships:
            used_ids.add(relationship.from_id)
            used_ids.add(relationship.to_id)

        component = entity_by_id[start_id]
        event_label = trigger_edge.label or "event"
        handler = entity_by_id[trigger_edge.to_id]
        flows.append(
            BehaviorFlow(
                id=(
                    f"flow:{start_id}:{event_label}:{handler.id}:"
                    f"{trigger_edge.evidence.file}:{trigger_edge.evidence.line}"
                ),
                name=f"{component.name} {event_label.removeprefix('on').lower()} flow",
                trigger=FlowTrigger(
                    type="event",
                    source=handler.id,
                    label=event_label,
                ),
                nodes=sorted(
                    (entity_by_id[item] for item in used_ids),
                    key=lambda entity: entity.id,
                ),
                relationships=flow_relationships,
            )
        )

    return BehaviorGraph(
        entities=entities,
        relationships=relationships,
        flows=sorted(flows, key=lambda flow: flow.id),
    )
