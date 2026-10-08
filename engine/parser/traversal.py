from collections.abc import Iterator

from tree_sitter import Node


def walk_syntax_tree(root_node: Node) -> Iterator[tuple[Node, int]]:
    cursor = root_node.walk()
    while True:
        yield cursor.node, cursor.depth
        if cursor.goto_first_child():
            continue
        while not cursor.goto_next_sibling():
            if not cursor.goto_parent():
                return
