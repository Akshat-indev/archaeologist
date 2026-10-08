import io
import subprocess
import tarfile
from pathlib import Path
from unittest.mock import patch

import pytest

from app.services.github_repository import (
    GitHubRepository,
    RepositoryLimitError,
    RepositoryLimits,
    clone_and_extract_repository,
    parse_github_repository_url,
)
from app.services.github_analysis_service import analyze_github_repository
from app.services.github_repository import SnapshotSummary


def _archive(files: dict[str, bytes], symlinks: dict[str, str] | None = None) -> bytes:
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w") as archive:
        for name, contents in files.items():
            member = tarfile.TarInfo(name)
            member.size = len(contents)
            archive.addfile(member, io.BytesIO(contents))
        for name, target in (symlinks or {}).items():
            member = tarfile.TarInfo(name)
            member.type = tarfile.SYMTYPE
            member.linkname = target
            archive.addfile(member)
    return buffer.getvalue()


class FakeArchiveProcess:
    def __init__(self, data: bytes) -> None:
        self.stdout = io.BytesIO(data)
        self.returncode = 0

    def poll(self):
        return self.returncode

    def wait(self, timeout=None):
        return self.returncode

    def terminate(self):
        self.returncode = -15

    def kill(self):
        self.returncode = -9


def _successful_git_result(stdout: str = "") -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess(args=["git"], returncode=0, stdout=stdout, stderr="")


def test_parses_public_repository_url_variants() -> None:
    assert parse_github_repository_url(
        "https://github.com/fastapi/fastapi/"
    ) == GitHubRepository(
        owner="fastapi",
        name="fastapi",
        full_name="fastapi/fastapi",
        url="https://github.com/fastapi/fastapi",
    )
    assert parse_github_repository_url(
        "https://github.com/withastro/astro.git"
    ).name == "astro"


@pytest.mark.parametrize(
    "url",
    [
        "http://github.com/owner/repo",
        "https://github.com/owner/repo/issues",
        "https://github.com/owner/repo/tree/main",
        "https://github.com/owner/repo/blob/main/file.ts",
        "https://github.com.evil.example/owner/repo",
        "https://user:password@github.com/owner/repo",
        "https://github.com/owner/repo?tab=readme",
        "https://github.com/../repo",
        "https://gitlab.com/owner/repo",
    ],
)
def test_rejects_non_repository_github_urls(url: str) -> None:
    with pytest.raises(ValueError):
        parse_github_repository_url(url)


def test_clones_without_checkout_and_extracts_only_supported_files(tmp_path) -> None:
    repository = parse_github_repository_url("https://github.com/example/project")
    archive = _archive(
        {
            "src/App.tsx": b"export function App() { return <main />; }\n",
            "README.md": b"project",
            "src/main.py": b"print('not executed')",
        },
        {"src/link.ts": "../outside.ts"},
    )
    process = FakeArchiveProcess(archive)
    git_results = [
        _successful_git_result(),
        _successful_git_result("abc123\n"),
        _successful_git_result("origin/main\n"),
    ]
    limits = RepositoryLimits(
        max_repository_size=1024 * 1024,
        max_file_count=20,
        max_file_size=1024,
        max_analysis_files=10,
        clone_timeout=5,
        max_flow_depth=20,
        max_flows=200,
    )

    with (
        patch("app.services.github_repository.subprocess.run", side_effect=git_results) as run,
        patch("app.services.github_repository.subprocess.Popen", return_value=process),
    ):
        source, commit, branch, summary = clone_and_extract_repository(
            repository,
            tmp_path / "workspace",
            limits,
        )

    assert "--no-checkout" in run.call_args_list[0].args[0]
    assert "--depth" in run.call_args_list[0].args[0]
    assert commit == "abc123"
    assert branch == "main"
    assert (source / "src" / "App.tsx").read_text(encoding="utf-8").startswith("export")
    assert not (source / "src" / "link.ts").exists()
    assert not (source / "README.md").exists()
    assert summary.files_discovered == 4
    assert summary.files_analyzed == 1
    assert summary.files_skipped == 3
    assert summary.unsupported_languages == {"md": 1, "py": 1}
    assert any(item["status"] == "skipped_symlink" for item in summary.skipped_files)


def test_rejects_repository_size_limit_before_extracting_files(tmp_path) -> None:
    repository = parse_github_repository_url("https://github.com/example/project")
    archive = _archive({"large.ts": b"content larger than limit"})
    git_results = [
        _successful_git_result(),
        _successful_git_result("abc123\n"),
        _successful_git_result("origin/main\n"),
    ]
    limits = RepositoryLimits(
        max_repository_size=5,
        max_file_count=20,
        max_file_size=100,
        max_analysis_files=10,
        clone_timeout=5,
        max_flow_depth=20,
        max_flows=200,
    )

    with (
        patch("app.services.github_repository.subprocess.run", side_effect=git_results),
        patch(
            "app.services.github_repository.subprocess.Popen",
            return_value=FakeArchiveProcess(archive),
        ),
        pytest.raises(RepositoryLimitError, match="Repository exceeds current MVP"),
    ):
        clone_and_extract_repository(repository, tmp_path / "workspace", limits)


def test_skips_large_unsupported_files_without_failing_scan(tmp_path) -> None:
    repository = parse_github_repository_url("https://github.com/example/project")
    archive = _archive(
        {
            "src/App.tsx": b"export function App() { return 'ok'; }\n",
            "fixtures/penguin.png": b"x" * (1024 * 1024 * 6),
        }
    )
    git_results = [
        _successful_git_result(),
        _successful_git_result("abc123\n"),
        _successful_git_result("origin/main\n"),
    ]
    limits = RepositoryLimits(
        max_repository_size=1024 * 1024,
        max_file_count=20,
        max_file_size=1024 * 1024,
        max_analysis_files=10,
        clone_timeout=5,
        max_flow_depth=20,
        max_flows=200,
    )

    with (
        patch("app.services.github_repository.subprocess.run", side_effect=git_results),
        patch(
            "app.services.github_repository.subprocess.Popen",
            return_value=FakeArchiveProcess(archive),
        ),
    ):
        source, commit, branch, summary = clone_and_extract_repository(
            repository,
            tmp_path / "workspace",
            limits,
        )

    assert commit == "abc123"
    assert branch == "main"
    assert (source / "src" / "App.tsx").exists()
    assert summary.files_discovered == 2
    assert summary.files_analyzed == 1
    assert summary.files_skipped == 1
    assert summary.unsupported_languages == {"png": 1}


def test_analyzes_extracted_snapshot_and_reports_unsupported_files(
    tmp_path,
) -> None:
    (tmp_path / "App.tsx").write_text(
        "export function App() { return <main />; }\n",
        encoding="utf-8",
    )
    snapshot = SnapshotSummary(
        files_discovered=2,
        files_analyzed=1,
        files_skipped=1,
        skipped_files=[
            {"path": "README.md", "language": "md", "status": "unsupported"}
        ],
        unsupported_languages={"md": 1},
    )
    progress: list[str] = []

    with patch(
        "app.services.github_analysis_service.clone_and_extract_repository",
        return_value=(tmp_path, "abc123", "main", snapshot),
    ):
        result = analyze_github_repository(
            parse_github_repository_url("https://github.com/example/project"),
            lambda status, counts: progress.append(status),
            RepositoryLimits(
                max_repository_size=1024,
                max_file_count=20,
                max_file_size=1024,
                max_analysis_files=10,
                clone_timeout=5,
                max_flow_depth=20,
                max_flows=200,
            ),
        )

    assert result.repository.provider == "github"
    assert result.repository.owner == "example"
    assert result.repository.full_name == "example/project"
    assert result.repository.commit == "abc123"
    assert result.repository.default_branch == "main"
    assert result.repository.language_summary == {"md": 1, "tsx": 1}
    assert result.metrics.unsupported_files == 1
    assert result.metrics.files_discovered == 2
    assert result.metrics.files_skipped == 1
    assert result.skipped_files == snapshot.skipped_files
    assert result.warnings
    assert progress == ["cloning", "scanning", "parsing", "analyzing", "building_flows"]


def test_analyzes_repository_with_only_unsupported_languages(tmp_path) -> None:
    snapshot = SnapshotSummary(
        files_discovered=1,
        files_analyzed=0,
        files_skipped=1,
        skipped_files=[
            {"path": "main.py", "language": "py", "status": "unsupported"}
        ],
        unsupported_languages={"py": 1},
    )

    with patch(
        "app.services.github_analysis_service.clone_and_extract_repository",
        return_value=(tmp_path, "abc123", None, snapshot),
    ):
        result = analyze_github_repository(
            parse_github_repository_url("https://github.com/example/python"),
            lambda status, counts: None,
            RepositoryLimits(1024, 20, 1024, 10, 5, 20, 200),
        )

    assert result.files == []
    assert result.metrics.unsupported_files == 1
    assert result.metrics.files_discovered == 1
    assert "No JavaScript or TypeScript files" in result.warnings[-1]
