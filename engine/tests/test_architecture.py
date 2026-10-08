import unittest

from analyzer.architecture import build_architecture
from parser.models import FileInfo, ImportedSymbol, Relationship, RepositoryModel


class BuildArchitectureTests(unittest.TestCase):
    def test_includes_isolated_files_and_counts_unique_relationships(self):
        model = RepositoryModel(
            repository="sample",
            files=[
                FileInfo(path="src/App.tsx", language="tsx", symbols=["App"]),
                FileInfo(path="src/Card.tsx", language="tsx"),
                FileInfo(path="src/Orphan.ts", language="typescript"),
                FileInfo(path="src/Disconnected.ts", language="typescript"),
            ],
            relationships=[
                Relationship(
                    from_path="src/App.tsx",
                    to_path="src/Card.tsx",
                    symbols=[ImportedSymbol(imported="Card", local="Card")],
                ),
                Relationship(
                    from_path="src/App.tsx",
                    to_path="src/Card.tsx",
                    symbols=[ImportedSymbol(imported="Button", local="Action")],
                ),
                Relationship(
                    from_path="src/Orphan.ts",
                    to_path="src/Card.tsx",
                ),
                Relationship(
                    from_path="src/missing.ts",
                    to_path="src/Card.tsx",
                ),
            ],
        )

        graph = build_architecture(model)

        self.assertEqual(
            [
                "src/App.tsx",
                "src/Card.tsx",
                "src/Disconnected.ts",
                "src/Orphan.ts",
            ],
            [node.id for node in graph.nodes],
        )
        self.assertEqual(2, len(graph.edges))
        self.assertEqual(
            ("src/App.tsx", "src/Card.tsx"),
            (graph.edges[0].source, graph.edges[0].target),
        )
        self.assertEqual(
            [("Button", "Action"), ("Card", "Card")],
            [
                (symbol.imported, symbol.local)
                for symbol in graph.edges[0].symbols
            ],
        )
        self.assertEqual(
            ("src/Orphan.ts", "src/Card.tsx", []),
            (
                graph.edges[1].source,
                graph.edges[1].target,
                graph.edges[1].symbols,
            ),
        )
        self.assertEqual(
            [
                ("src/App.tsx", 1, 0),
                ("src/Card.tsx", 0, 2),
                ("src/Disconnected.ts", 0, 0),
                ("src/Orphan.ts", 1, 0),
            ],
            [
                (node.path, node.imports_count, node.imported_by_count)
                for node in graph.nodes
            ],
        )


if __name__ == "__main__":
    unittest.main()
