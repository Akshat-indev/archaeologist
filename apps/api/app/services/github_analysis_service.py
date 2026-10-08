import tempfile
from collections import Counter
from collections.abc import Callable
from pathlib import Path

from app.schemas.analysis import AnalysisResponse
from app.services.analysis_service import analyze_repository_path
from app.services.github_repository import (
    GitHubRepository,
    RepositoryLimits,
    clone_and_extract_repository,
)


ProgressCallback = Callable[..., None]


def analyze_github_repository(
    repository: GitHubRepository,
    progress_callback: ProgressCallback,
    limits: RepositoryLimits | None = None,
) -> AnalysisResponse:
    effective_limits = limits or RepositoryLimits.from_environment()
    progress_callback("cloning", {})

    with tempfile.TemporaryDirectory(prefix="archaeologist-") as workspace:
        progress_callback("scanning", {})
        source_path, commit, branch, snapshot = clone_and_extract_repository(
            repository,
            Path(workspace),
            effective_limits,
        )
        progress_callback(
            "parsing",
            {
                "files_discovered": snapshot.files_discovered,
                "files_analyzed": 0,
                "files_skipped": snapshot.files_skipped,
            },
        )
        result = analyze_repository_path(
            str(source_path),
            progress_callback=progress_callback,
            allow_unsupported_only=True,
            max_flow_depth=effective_limits.max_flow_depth,
            max_flows=effective_limits.max_flows,
        )

    language_summary = Counter(result.repository.language_summary)
    for language, count in snapshot.unsupported_languages.items():
        language_summary[language] += count
    warnings: list[str] = []
    if snapshot.files_skipped:
        warnings.append(
            f"{snapshot.files_skipped} files were skipped; "
            f"{sum(snapshot.unsupported_languages.values())} use unsupported languages."
        )
    if snapshot.files_skipped > len(snapshot.skipped_files):
        warnings.append("The skipped-file list is limited to the first 1000 files.")
    if not result.files:
        warnings.append(
            "No JavaScript or TypeScript files were found; only repository metadata "
            "and unsupported-file statistics are available."
        )

    return result.model_copy(
        update={
            "repository": result.repository.model_copy(
                update={
                    "provider": "github",
                    "owner": repository.owner,
                    "name": repository.name,
                    "full_name": repository.full_name,
                    "url": repository.url,
                    "path": repository.url,
                    "default_branch": branch,
                    "commit": commit,
                    "language_summary": dict(sorted(language_summary.items())),
                }
            ),
            "metrics": result.metrics.model_copy(
                update={
                    "unsupported_files": sum(
                        snapshot.unsupported_languages.values()
                    ),
                    "files_discovered": snapshot.files_discovered,
                    "files_skipped": snapshot.files_skipped,
                }
            ),
            "skipped_files": snapshot.skipped_files,
            "warnings": warnings,
        }
    )
