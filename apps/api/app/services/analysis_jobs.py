import logging
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import UTC, datetime

from app.schemas.analysis import (
    AnalysisJobResponse,
    AnalysisProgress,
    AnalysisResponse,
    RepositoryInfo,
)
from app.services.github_analysis_service import analyze_github_repository
from app.services.github_repository import GitHubRepository, RepositoryLimits


logger = logging.getLogger(__name__)
_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="repo-analysis")
_registry_lock = threading.Lock()
_jobs: dict[str, "AnalysisJob"] = {}
_max_active_jobs = 2
_max_retained_jobs = 20


class AnalysisJobCapacityError(Exception):
    pass


class AnalysisJobNotFoundError(Exception):
    pass


@dataclass
class AnalysisJob:
    analysis_id: str
    status: str = "created"
    progress: dict[str, int] = field(default_factory=dict)
    repository: RepositoryInfo | None = None
    result: AnalysisResponse | None = None
    error: str | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def update(
        self,
        status: str,
        progress: dict[str, int],
        result: AnalysisResponse | None = None,
    ) -> None:
        with self.lock:
            self.status = status
            self.progress.update(progress)
            if result is not None:
                self.result = result
                self.repository = result.repository

    def snapshot(self) -> AnalysisJobResponse:
        with self.lock:
            return AnalysisJobResponse(
                analysis_id=self.analysis_id,
                status=self.status,
                progress=AnalysisProgress(
                    files_discovered=self.progress.get("files_discovered", 0),
                    files_analyzed=self.progress.get("files_analyzed", 0),
                    files_skipped=self.progress.get("files_skipped", 0),
                    percent=self.progress.get("percent", 0),
                ),
                repository=self.repository,
                result=self.result,
                error=self.error,
            )


def start_analysis_job(
    repository: GitHubRepository,
    limits: RepositoryLimits,
) -> AnalysisJobResponse:
    with _registry_lock:
        active_jobs = [
            job
            for job in _jobs.values()
            if job.status not in {"complete", "failed"}
        ]
        if len(active_jobs) >= _max_active_jobs:
            raise AnalysisJobCapacityError(
                "The local analyzer is busy. Wait for a running analysis to finish."
            )

        _prune_jobs()
        job = AnalysisJob(analysis_id=uuid.uuid4().hex)
        _jobs[job.analysis_id] = job
        _executor.submit(_run_job, job, repository, limits)
        return job.snapshot()


def _prune_jobs() -> None:
    finished_jobs = sorted(
        (
            job
            for job in _jobs.values()
            if job.status in {"complete", "failed"}
        ),
        key=lambda job: job.created_at,
    )
    while len(_jobs) >= _max_retained_jobs and finished_jobs:
        oldest = finished_jobs.pop(0)
        _jobs.pop(oldest.analysis_id, None)


def _run_job(
    job: AnalysisJob,
    repository: GitHubRepository,
    limits: RepositoryLimits,
) -> None:
    try:
        result = analyze_github_repository(repository, job.update, limits)
    except Exception as error:
        logger.exception("GitHub repository analysis failed")
        with job.lock:
            job.status = "failed"
            job.error = (
                str(error)
                if error.__class__.__module__.startswith("app.services")
                else "Repository analysis failed. Check the URL and API logs."
            )
        return

    with job.lock:
        job.result = result
        job.repository = result.repository
        job.progress["files_analyzed"] = result.metrics.files
        job.status = "complete"


def get_analysis_job(analysis_id: str) -> AnalysisJobResponse:
    with _registry_lock:
        job = _jobs.get(analysis_id)
    if job is None:
        raise AnalysisJobNotFoundError("Analysis job was not found or has expired.")
    return job.snapshot()
