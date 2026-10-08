import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from analyzer.behavior import build_behavior_graph
from parser.analyze import analyze_repository
from parser.models import BehaviorFact, FileInfo, RepositoryModel, SymbolInfo


FIXTURE = Path(__file__).parent / "fixtures" / "login_app"


class BehaviorAnalysisTests(unittest.TestCase):
    def test_flow_ids_are_unique_for_distinct_handlers_on_same_event(self):
        model = RepositoryModel(
            repository="duplicate-flow-ids",
            files=[
                FileInfo(
                    path="Panel.tsx",
                    language="tsx",
                    symbol_details=[
                        SymbolInfo("Panel", "react_component"),
                        SymbolInfo("saveFirst", "function"),
                        SymbolInfo("saveSecond", "function"),
                    ],
                    behavior_facts=[
                        BehaviorFact(
                            kind="event",
                            line=4,
                            caller="Panel",
                            name="onClick",
                            target="saveFirst",
                        ),
                        BehaviorFact(
                            kind="event",
                            line=5,
                            caller="Panel",
                            name="onClick",
                            target="saveSecond",
                        ),
                    ],
                )
            ],
        )

        graph = build_behavior_graph(model)

        self.assertEqual(2, len(graph.flows))
        self.assertEqual(2, len({flow.id for flow in graph.flows}))

    def test_reconstructs_full_login_flow_from_static_evidence(self):
        model = analyze_repository(str(FIXTURE))
        graph = build_behavior_graph(model)

        relationships = {
            (edge.from_id, edge.type, edge.to_id)
            for edge in graph.relationships
        }
        self.assertIn(
            (
                "frontend/LoginForm.tsx::handleSubmit",
                "calls",
                "frontend/LoginForm.tsx::validateForm",
            ),
            relationships,
        )
        self.assertIn(
            (
                "frontend/LoginForm.tsx::handleSubmit",
                "calls",
                "frontend/auth.ts::loginUser",
            ),
            relationships,
        )
        self.assertIn(
            (
                "frontend/LoginForm.tsx::LoginForm",
                "handles_event",
                "frontend/LoginForm.tsx::handleSubmit",
            ),
            relationships,
        )
        self.assertIn(
            (
                "frontend/App.tsx::App",
                "renders",
                "frontend/LoginForm.tsx::LoginForm",
            ),
            relationships,
        )
        self.assertIn(
            (
                "frontend/auth.ts::loginUser",
                "http_request",
                "http:POST:/api/login",
            ),
            relationships,
        )
        self.assertIn(
            (
                "http:POST:/api/login",
                "matches_route",
                "route:POST:/api/login",
            ),
            relationships,
        )
        self.assertIn(
            (
                "route:POST:/api/login",
                "handled_by",
                "backend/controllers/auth.ts::loginController",
            ),
            relationships,
        )
        self.assertIn(
            (
                "backend/controllers/auth.ts::loginController",
                "calls",
                "backend/services/auth.ts::authService.login",
            ),
            relationships,
        )
        self.assertNotIn(
            "unresolvedCall",
            {edge.to_id.rsplit("::", 1)[-1] for edge in graph.relationships},
        )

        self.assertEqual(1, len(graph.flows))
        flow = graph.flows[0]
        self.assertEqual("LoginForm submit flow", flow.name)
        self.assertEqual("onSubmit", flow.trigger.label)
        self.assertTrue(
            {
                "frontend/LoginForm.tsx::LoginForm",
                "frontend/LoginForm.tsx::handleSubmit",
                "frontend/auth.ts::loginUser",
                "http:POST:/api/login",
                "route:POST:/api/login",
                "backend/controllers/auth.ts::loginController",
                "backend/services/auth.ts::authService.login",
            }
            <= {node.id for node in flow.nodes}
        )
        self.assertTrue(
            all(
                relationship.evidence.file and relationship.evidence.line > 0
                for relationship in graph.relationships
            )
        )

    def test_extracts_axios_method_and_dynamic_path_without_guessing(self):
        with TemporaryDirectory() as temporary_directory:
            repository = Path(temporary_directory)
            (repository / "client.ts").write_text(
                "export async function loadItems(url: string) {\n"
                "  return axios.post(url, {});\n"
                "}\n",
                encoding="utf-8",
            )
            graph = build_behavior_graph(analyze_repository(str(repository)))

        requests = [entity for entity in graph.entities if entity.kind == "http_request"]
        self.assertEqual(
            [("POST", "<dynamic>")],
            [(request.method, request.path) for request in requests],
        )

    def test_detects_static_axios_requests_and_inline_express_routes(self):
        with TemporaryDirectory() as temporary_directory:
            repository = Path(temporary_directory)
            (repository / "client.ts").write_text(
                "export function load() { return axios.get('/items'); }\n"
                "export function remove() { return axios.delete('/items/1'); }\n",
                encoding="utf-8",
            )
            (repository / "routes.ts").write_text(
                'app.get("/health", (req, res) => res.send("ok"));\n',
                encoding="utf-8",
            )
            graph = build_behavior_graph(analyze_repository(str(repository)))

        self.assertEqual(
            {("GET", "/items"), ("DELETE", "/items/1")},
            {
                (entity.method, entity.path)
                for entity in graph.entities
                if entity.kind == "http_request"
            },
        )
        self.assertIn(
            ("GET", "/health"),
            {
                (entity.method, entity.path)
                for entity in graph.entities
                if entity.kind == "api_route"
            },
        )

    def test_resolves_aliased_imported_arrow_function_calls(self):
        with TemporaryDirectory() as temporary_directory:
            repository = Path(temporary_directory)
            (repository / "caller.ts").write_text(
                'import { run as execute } from "./service";\n'
                "export function task() { execute(); }\n",
                encoding="utf-8",
            )
            (repository / "service.ts").write_text(
                "export const run = () => true;\n",
                encoding="utf-8",
            )
            graph = build_behavior_graph(analyze_repository(str(repository)))

        self.assertIn(
            (
                "caller.ts::task",
                "calls",
                "service.ts::run",
            ),
            {
                (edge.from_id, edge.type, edge.to_id)
                for edge in graph.relationships
            },
        )

    def test_links_inline_react_event_handlers_to_local_calls(self):
        with TemporaryDirectory() as temporary_directory:
            repository = Path(temporary_directory)
            (repository / "Button.tsx").write_text(
                "export function Button() {\n"
                "  return <button onClick={() => save()} />;\n"
                "}\n"
                "function save() { return true; }\n",
                encoding="utf-8",
            )
            graph = build_behavior_graph(analyze_repository(str(repository)))

        self.assertIn(
            (
                "Button.tsx::Button",
                "handles_event",
                "Button.tsx::$onClick@2",
            ),
            {
                (edge.from_id, edge.type, edge.to_id)
                for edge in graph.relationships
            },
        )
        self.assertIn(
            (
                "Button.tsx::$onClick@2",
                "calls",
                "Button.tsx::save",
            ),
            {
                (edge.from_id, edge.type, edge.to_id)
                for edge in graph.relationships
            },
        )

    def test_omits_request_route_links_when_route_is_ambiguous(self):
        with TemporaryDirectory() as temporary_directory:
            repository = Path(temporary_directory)
            (repository / "client.ts").write_text(
                'export function login() { return fetch("/login", { method: "POST" }); }\n',
                encoding="utf-8",
            )
            (repository / "routes-a.ts").write_text(
                'router.post("/login", firstHandler);\n',
                encoding="utf-8",
            )
            (repository / "routes-b.ts").write_text(
                'router.post("/login/", secondHandler);\n',
                encoding="utf-8",
            )
            graph = build_behavior_graph(analyze_repository(str(repository)))

        self.assertFalse(
            any(edge.type == "matches_route" for edge in graph.relationships)
        )
        self.assertFalse(
            any(edge.type == "handled_by" for edge in graph.relationships)
        )


if __name__ == "__main__":
    unittest.main()
