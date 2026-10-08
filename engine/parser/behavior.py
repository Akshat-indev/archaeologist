from parser.models import BehaviorFact
from parser.traversal import walk_syntax_tree


EVENT_NAMES = {
    "onClick",
    "onSubmit",
    "onChange",
    "onBlur",
    "onFocus",
    "onKeyDown",
}
HTTP_METHODS = {"get", "post", "put", "patch", "delete"}
ROUTE_METHODS = HTTP_METHODS | {"all"}


def _text(node, source: bytes) -> str:
    return source[node.start_byte : node.end_byte].decode("utf-8")


def _identifier(node, source: bytes) -> str | None:
    if node is None:
        return None
    if node.type in {
        "identifier",
        "property_identifier",
        "type_identifier",
        "jsx_identifier",
    }:
        return _text(node, source)
    return None


def _string_value(node, source: bytes) -> str | None:
    if node is None or node.type not in {"string", "template_string"}:
        return None
    text = _text(node, source)
    if node.type == "template_string" and "${" in text:
        return None
    if len(text) < 2:
        return None
    return text[1:-1]


def _call_target(node, source: bytes) -> tuple[str | None, str | None]:
    if node is None:
        return None, None
    if node.type == "identifier":
        return None, _text(node, source)
    if node.type == "member_expression":
        return _text(node.child_by_field_name("object"), source), _identifier(
            node.child_by_field_name("property"), source
        )
    return None, None


def _http_request(node, caller: str | None, source: bytes) -> BehaviorFact | None:
    function = node.child_by_field_name("function")
    receiver, name = _call_target(function, source)
    if name is None:
        return None

    arguments_node = node.child_by_field_name("arguments")
    arguments = arguments_node.named_children if arguments_node is not None else []
    if not arguments:
        return None

    method = "GET"
    path = _string_value(arguments[0], source)
    if name == "fetch" and receiver is None:
        if len(arguments) > 1 and arguments[1].type == "object":
            for pair in arguments[1].named_children:
                if pair.type != "pair":
                    continue
                key = pair.child_by_field_name("key")
                value = pair.child_by_field_name("value")
                if _identifier(key, source) == "method":
                    method = (_string_value(value, source) or "GET").upper()
                    break
    elif receiver is not None and receiver.split(".")[-1] == "axios":
        method = name.upper()
    else:
        return None

    return BehaviorFact(
        kind="http_request",
        caller=caller,
        method=method,
        path=path or "<dynamic>",
        line=node.start_point.row + 1,
    )


def _route_fact(node, source: bytes) -> BehaviorFact | None:
    function = node.child_by_field_name("function")
    receiver, name = _call_target(function, source)
    if (
        receiver is None
        or name is None
        or name.lower() not in ROUTE_METHODS
        or not (
            receiver == "app"
            or receiver.lower().endswith("router")
        )
    ):
        return None

    arguments_node = node.child_by_field_name("arguments")
    arguments = arguments_node.named_children if arguments_node is not None else []
    if len(arguments) < 2:
        return None

    path = _string_value(arguments[0], source)
    if path is None:
        return None

    handler_receiver, handler = _call_target(arguments[-1], source)
    if handler is None:
        handler = _identifier(arguments[-1], source)
    return BehaviorFact(
        kind="route",
        method=name.upper(),
        path=path,
        target=handler,
        receiver=handler_receiver,
        line=node.start_point.row + 1,
    )


def extract_behavior_facts(root_node, source: bytes) -> list[BehaviorFact]:
    facts: list[BehaviorFact] = []
    contexts: list[tuple[str | None, str | None]] = [(None, None)]
    skip_subtree_depth: int | None = None
    for node, depth in walk_syntax_tree(root_node):
        if skip_subtree_depth is not None:
            if depth > skip_subtree_depth:
                continue
            skip_subtree_depth = None
        while len(contexts) <= depth:
            contexts.append((None, None))
        caller, component = contexts[depth]
        if not node.is_named:
            if len(contexts) <= depth + 1:
                contexts.append((caller, component))
            contexts[depth + 1] = (caller, component)
            continue

        node_type = node.type
        active_caller = caller
        active_component = component

        if node_type == "function_declaration":
            name = _identifier(node.child_by_field_name("name"), source)
            if name:
                active_caller = name
                if name[:1].isupper():
                    active_component = name
        elif node_type == "method_definition":
            name = _identifier(node.child_by_field_name("name"), source)
            if name:
                active_caller = f"{component}.{name}" if component else name
        elif node_type == "variable_declarator":
            name = _identifier(node.child_by_field_name("name"), source)
            value = node.child_by_field_name("value")
            if (
                name
                and value is not None
                and value.type in {"arrow_function", "function_expression"}
            ):
                active_caller = name
                if name[:1].isupper():
                    active_component = name

        if node_type == "call_expression":
            receiver, name = _call_target(
                node.child_by_field_name("function"), source
            )
            if name:
                facts.append(
                    BehaviorFact(
                        kind="call",
                        caller=active_caller,
                        name=name,
                        receiver=receiver,
                        line=node.start_point.row + 1,
                    )
                )
            request = _http_request(node, active_caller, source)
            if request is not None:
                facts.append(request)
            route = _route_fact(node, source)
            if route is not None:
                facts.append(route)

        if node_type in {"jsx_element", "jsx_self_closing_element"}:
            opening = (
                node.child_by_field_name("open_tag")
                if node_type == "jsx_element"
                else node
            )
            name_node = opening.child_by_field_name("name") if opening else None
            child_name = _identifier(name_node, source)
            if (
                active_component
                and child_name
                and child_name[:1].isupper()
                and child_name != active_component
            ):
                facts.append(
                    BehaviorFact(
                        kind="render",
                        caller=active_component,
                        name=child_name,
                        line=node.start_point.row + 1,
                    )
                )

        if node_type == "jsx_attribute":
            named_children = node.named_children
            event_node = node.child_by_field_name("name") or (
                named_children[0] if named_children else None
            )
            event_name = _identifier(event_node, source)
            value = node.child_by_field_name("value") or (
                named_children[-1] if len(named_children) > 1 else None
            )
            if active_component and event_name in EVENT_NAMES and value is not None:
                expression = (
                    value.named_children[0]
                    if value.type == "jsx_expression" and value.named_children
                    else value
                )
                target = _identifier(expression, source)
                inline_handler = (
                    expression.type in {"arrow_function", "function_expression"}
                )
                if target or inline_handler:
                    handler_name = target or f"${event_name}@{node.start_point.row + 1}"
                    facts.append(
                        BehaviorFact(
                            kind="event",
                            caller=active_component,
                            name=event_name,
                            target=handler_name,
                            line=node.start_point.row + 1,
                        )
                    )
                    if inline_handler:
                        for descendant in _walk(expression):
                            if descendant.type != "call_expression":
                                continue
                            receiver, called_name = _call_target(
                                descendant.child_by_field_name("function"), source
                            )
                            if called_name:
                                facts.append(
                                    BehaviorFact(
                                        kind="call",
                                        caller=handler_name,
                                        name=called_name,
                                        receiver=receiver,
                                        line=descendant.start_point.row + 1,
                                    )
                                )
                    skip_subtree_depth = depth

        if len(contexts) <= depth + 1:
            contexts.append((active_caller, active_component))
        contexts[depth + 1] = (active_caller, active_component)

    return facts


def _walk(node):
    for current, _depth in walk_syntax_tree(node):
        if current.is_named:
            yield current
