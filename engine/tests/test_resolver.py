import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from analyzer.resolver import resolve_imports
from parser.analyze import analyze_file, analyze_repository, model_to_dict
from parser.models import FileInfo


class ResolveImportsTests(unittest.TestCase):
    def test_resolves_relative_alias_and_directory_imports(self):
        files = [
            FileInfo(
                path="src/App.tsx",
                language="tsx",
                imports=[
                    "import { Navbar } from './components/Navbar'",
                    "import { helper } from '@/lib/utils'",
                    "import { Button } from './components/ui'",
                ],
            ),
            FileInfo(path="src/components/Navbar.tsx", language="tsx"),
            FileInfo(path="src/lib/utils.ts", language="typescript"),
            FileInfo(path="src/components/ui/index.tsx", language="tsx"),
        ]

        relationships = resolve_imports(files)

        self.assertEqual(
            [
                ("src/App.tsx", "src/components/Navbar.tsx", "imports"),
                ("src/App.tsx", "src/lib/utils.ts", "imports"),
                ("src/App.tsx", "src/components/ui/index.tsx", "imports"),
            ],
            [
                (edge.from_path, edge.to_path, edge.type)
                for edge in relationships
            ],
        )

    def test_resolves_parent_and_explicit_extension_imports(self):
        files = [
            FileInfo(
                path="src/pages/Home.tsx",
                language="tsx",
                imports=[
                    "import { helper } from '../../shared/helper.js'",
                    "import './components/Widget.tsx'",
                ],
            ),
            FileInfo(path="shared/helper.js", language="javascript"),
            FileInfo(path="src/pages/components/Widget.tsx", language="tsx"),
        ]

        relationships = resolve_imports(files)

        self.assertEqual(
            ["shared/helper.js", "src/pages/components/Widget.tsx"],
            [edge.to_path for edge in relationships],
        )
        self.assertEqual([], relationships[1].symbols)

    def test_supports_custom_aliases_and_skips_external_or_unresolved_imports(self):
        files = [
            FileInfo(
                path="app/main.ts",
                language="typescript",
                imports=[
                    "import { item } from '~/item'",
                    "import React from 'react'",
                    "import missing from './missing'",
                ],
            ),
            FileInfo(path="shared/item.tsx", language="tsx"),
        ]

        relationships = resolve_imports(files, aliases={"~/": "shared/"})

        self.assertEqual(
            [("app/main.ts", "shared/item.tsx")],
            [(edge.from_path, edge.to_path) for edge in relationships],
        )

    def test_deduplicates_edges_to_the_same_file(self):
        files = [
            FileInfo(
                path="src/App.tsx",
                language="tsx",
                imports=[
                    "import { A } from './Widget'",
                    "import { B } from './Widget.tsx'",
                ],
            ),
            FileInfo(path="src/Widget.tsx", language="tsx"),
        ]

        relationships = resolve_imports(files)

        self.assertEqual(1, len(relationships))
        self.assertEqual(
            [("A", "A"), ("B", "B")],
            [(symbol.imported, symbol.local) for symbol in relationships[0].symbols],
        )

    def test_extracts_default_namespace_and_aliased_import_names(self):
        files = [
            FileInfo(
                path="src/App.tsx",
                language="tsx",
                imports=[
                    "import Card, { Button as PrimaryButton } from './Card'",
                    "import * as utilities from './utils'",
                ],
            ),
            FileInfo(path="src/Card.tsx", language="tsx"),
            FileInfo(path="src/utils.ts", language="typescript"),
        ]

        relationships = resolve_imports(files)

        self.assertEqual(
            [
                [("default", "Card"), ("Button", "PrimaryButton")],
                [("*", "utilities")],
            ],
            [
                [(symbol.imported, symbol.local) for symbol in edge.symbols]
                for edge in relationships
            ],
        )

    def test_extracts_bindings_from_multiline_imports(self):
        files = [
            FileInfo(
                path="src/App.ts",
                language="typescript",
                imports=[
                    "import {\n"
                    "  run as execute,\n"
                    "} from './service'"
                ],
            ),
            FileInfo(path="src/service.ts", language="typescript"),
        ]

        relationship = resolve_imports(files)[0]

        self.assertEqual(
            [("run", "execute")],
            [(symbol.imported, symbol.local) for symbol in relationship.symbols],
        )

    def test_repository_analysis_includes_resolved_relationships(self):
        with TemporaryDirectory() as temporary_directory:
            repository = Path(temporary_directory)
            source_directory = repository / "src"
            (source_directory / "components").mkdir(parents=True)
            (source_directory / "App.tsx").write_text(
                "import { Card } from '@/components/Card';\n"
                "import './theme';\n",
                encoding="utf-8",
            )
            (source_directory / "components" / "Card.tsx").write_text(
                "export function Card() { return null; }\n",
                encoding="utf-8",
            )
            (source_directory / "theme.js").write_text(
                "export const theme = {};\n",
                encoding="utf-8",
            )

            result = model_to_dict(analyze_repository(str(repository)))

        self.assertEqual(
            [
                {
                    "from": "src/App.tsx",
                    "to": "src/components/Card.tsx",
                    "type": "imports",
                },
                {
                    "from": "src/App.tsx",
                    "to": "src/theme.js",
                    "type": "imports",
                },
            ],
            result["relationships"],
        )

    def test_extracts_deterministic_symbol_kinds_and_exports(self):
        with TemporaryDirectory() as temporary_directory:
            repository = Path(temporary_directory)
            source = repository / "Feature.tsx"
            source.write_text(
                "export const LIMIT = 3;\n"
                "export function Feature() { return <main />; }\n"
                "function useValue() { return 1; }\n"
                "function Shared() { return null; }\n"
                "export { Shared };\n"
                "class Store { get() { return 1; } }\n"
                "export class PublicStore { method() { return 1; } }\n"
                "const useCount = 1;\n"
                "export interface Props {}\n"
                "export type Mode = string;\n",
                encoding="utf-8",
            )

            file_info = analyze_file(source, repository)

        self.assertEqual(
            [
                ("LIMIT", "constant", True),
                ("Feature", "react_component", True),
                ("useValue", "hook", False),
                ("Shared", "function", True),
                ("Store", "class", False),
                ("get", "method", False),
                ("PublicStore", "class", True),
                ("method", "method", False),
                ("useCount", "constant", False),
                ("Props", "interface", True),
                ("Mode", "type", True),
            ],
            [
                (symbol.name, symbol.kind, symbol.exported)
                for symbol in file_info.symbol_details
            ],
        )

    def test_analyzes_deeply_nested_syntax_without_python_recursion(self):
        with TemporaryDirectory() as temporary_directory:
            repository = Path(temporary_directory)
            source = repository / "nested.ts"
            source.write_text(
                "const value = " + "[" * 1200 + "0" + "]" * 1200 + ";\n",
                encoding="utf-8",
            )

            file_info = analyze_file(source, repository)

        self.assertEqual(["value"], file_info.symbols)


if __name__ == "__main__":
    unittest.main()
