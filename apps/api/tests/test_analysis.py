from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.routes.auth import _create_session

client = TestClient(app)
LOGIN_FIXTURE = Path(__file__).resolve().parents[3] / "engine" / "tests" / "fixtures" / "login_app"
_TEST_SESSION_SECRET = "test-session-secret-" + "x" * 40


@pytest.fixture(autouse=True)
def authenticated_test_session(monkeypatch) -> None:
    monkeypatch.setenv("GITHUB_CLIENT_ID", "test-client-id")
    monkeypatch.setenv("GITHUB_CLIENT_SECRET", "test-client-secret")
    monkeypatch.setenv("AUTH_SESSION_SECRET", _TEST_SESSION_SECRET)
    client.cookies.set(
        "archaeologist_session",
        _create_session(
            {"login": "test-user", "name": "Test User", "avatar_url": ""},
            _TEST_SESSION_SECRET,
        ),
    )
    yield
    client.cookies.clear()


def test_analyze_returns_complete_architecture_graph(tmp_path) -> None:
    source = tmp_path / "src"
    components = source / "components"
    components.mkdir(parents=True)
    (source / "main.tsx").write_text(
        "import { App } from './App';\n"
        "import React from 'react';\n"
        "createRoot(document.getElementById('root')!).render(<App />);\n",
        encoding="utf-8",
    )
    (source / "App.tsx").write_text(
        "import { Card as UiCard } from './components/Card';\n"
        "import { CardMeta } from './components/Card';\n"
        "import { Missing } from './missing';\n"
        "export function App() { return <UiCard />; }\n",
        encoding="utf-8",
    )
    (components / "Card.tsx").write_text(
        "export const Card = () => <article />;\n",
        encoding="utf-8",
    )
    (source / "Orphan.ts").write_text("export type Orphan = string;\n", encoding="utf-8")

    response = client.post("/api/analyze", json={"path": str(tmp_path)})

    assert response.status_code == 200
    result = response.json()
    assert result["repository"]["name"] == tmp_path.name
    assert result["repository"]["language_summary"] == {"tsx": 3, "typescript": 1}
    assert result["entry_points"] == [
        {"path": "src/App.tsx", "reason": "common_entry_filename"},
        {"path": "src/main.tsx", "reason": "common_entry_filename"},
    ]
    assert result["metrics"]["total_files"] == 4
    assert result["metrics"]["total_relationships"] == 2
    assert result["metrics"]["files_without_dependencies"] == 2
    assert result["metrics"]["files_without_dependents"] == 2
    assert result["metrics"]["most_imported_files"] == [
        {"path": "src/App.tsx", "count": 1},
        {"path": "src/components/Card.tsx", "count": 1},
    ]

    nodes = result["architecture"]["nodes"]
    assert [node["id"] for node in nodes] == [
        "src/App.tsx",
        "src/Orphan.ts",
        "src/components/Card.tsx",
        "src/main.tsx",
    ]
    assert nodes[0]["imports_count"] == 1
    assert nodes[0]["imported_by_count"] == 1
    assert nodes[1]["imports_count"] == 0
    assert nodes[1]["imported_by_count"] == 0
    assert result["architecture"]["edges"] == [
        {
            "id": "src/App.tsx->src/components/Card.tsx",
            "source": "src/App.tsx",
            "target": "src/components/Card.tsx",
            "type": "imports",
            "symbols": [
                {"imported": "Card", "local": "UiCard"},
                {"imported": "CardMeta", "local": "CardMeta"},
            ],
        },
        {
            "id": "src/main.tsx->src/App.tsx",
            "source": "src/main.tsx",
            "target": "src/App.tsx",
            "type": "imports",
            "symbols": [{"imported": "App", "local": "App"}],
        },
    ]
    assert result["files"][0]["symbols"] == [
        {
            "name": "App",
            "kind": "react_component",
            "exported": True,
            "line": 4,
        }
    ]
    assert any(edge["type"] == "renders" for edge in result["relationships"])
    assert result["flows"] == []


def test_analyze_returns_evidence_backed_login_flow() -> None:
    response = client.post(
        "/api/analyze",
        json={"path": str(LOGIN_FIXTURE)},
    )

    assert response.status_code == 200
    result = response.json()
    assert result["metrics"]["components"] == 2
    assert result["metrics"]["routes"] == 1
    assert result["metrics"]["http_requests"] == 1
    assert result["metrics"]["flows"] == 1
    assert {
        (entity["kind"], entity["method"], entity["path"])
        for entity in result["entities"]
        if entity["kind"] in {"api_route", "http_request"}
    } == {
        ("api_route", "POST", "/api/login"),
        ("http_request", "POST", "/api/login"),
    }
    flow = result["flows"][0]
    assert flow["name"] == "LoginForm submit flow"
    assert flow["trigger"] == {
        "type": "event",
        "source": "frontend/LoginForm.tsx::handleSubmit",
        "label": "onSubmit",
    }
    flow_nodes = {node["id"] for node in flow["nodes"]}
    assert {
        "frontend/LoginForm.tsx::LoginForm",
        "frontend/LoginForm.tsx::handleSubmit",
        "frontend/auth.ts::loginUser",
        "http:POST:/api/login",
        "route:POST:/api/login",
        "backend/controllers/auth.ts::loginController",
        "backend/services/auth.ts::authService.login",
    } <= flow_nodes
    assert any(
        edge["type"] == "matches_route"
        and edge["evidence"] == {"file": "frontend/auth.ts", "line": 2}
        for edge in flow["relationships"]
    )
    assert all(
        relationship["confidence"] == "confirmed"
        and relationship["evidence"]["line"] > 0
        for relationship in result["relationships"]
    )


def test_analyze_returns_404_for_missing_path(tmp_path) -> None:
    response = client.post(
        "/api/analyze",
        json={"path": str(tmp_path / "missing")},
    )

    assert response.status_code == 404
    assert response.json() == {"detail": "Repository path does not exist."}


def test_analyze_returns_400_for_file_path(tmp_path) -> None:
    file_path = tmp_path / "not-a-repository"
    file_path.write_text("content", encoding="utf-8")

    response = client.post("/api/analyze", json={"path": str(file_path)})

    assert response.status_code == 400


def test_analyze_returns_422_for_unsupported_repository(tmp_path) -> None:
    response = client.post("/api/analyze", json={"path": str(tmp_path)})

    assert response.status_code == 422


def test_analyze_rejects_invalid_github_repository_urls() -> None:
    response = client.post(
        "/api/analyze",
        json={
            "source": {
                "type": "github",
                "url": "https://github.com/owner/repo/issues",
            }
        },
    )

    assert response.status_code == 400
    assert "public GitHub repository URL" in response.json()["detail"]


def test_analyze_requires_exactly_one_source() -> None:
    response = client.post("/api/analyze", json={})

    assert response.status_code == 422


def test_github_analysis_returns_pollable_job(monkeypatch) -> None:
    import time

    from app.services import analysis_jobs

    def analyze_fixture(repository, progress_callback, limits):
        progress_callback("parsing", {"files_discovered": 6})
        from app.services.analysis_service import analyze_repository_path

        return analyze_repository_path(str(LOGIN_FIXTURE))

    monkeypatch.setattr(
        analysis_jobs,
        "analyze_github_repository",
        analyze_fixture,
    )
    response = client.post(
        "/api/analyze",
        json={
            "source": {
                "type": "github",
                "url": "https://github.com/example/login-app",
            }
        },
    )

    assert response.status_code == 202
    initial = response.json()
    assert initial["analysis_id"]
    assert initial["status"] in {
        "created",
        "cloning",
        "parsing",
        "complete",
    }

    for _ in range(50):
        status_response = client.get(
            f"/api/analyses/{initial['analysis_id']}"
        )
        assert status_response.status_code == 200
        status = status_response.json()
        if status["status"] in {"complete", "failed"}:
            break
        time.sleep(0.02)

    assert status["status"] == "complete"
    assert status["result"]["metrics"]["flows"] == 1
    assert status["progress"]["files_discovered"] == 6


def test_analysis_job_not_found() -> None:
    response = client.get("/api/analyses/not-a-real-job")

    assert response.status_code == 404
