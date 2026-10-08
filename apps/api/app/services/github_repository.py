import os
import re
import shutil
import subprocess
import tarfile
import threading
from dataclasses import dataclass
from pathlib import Path, PurePosixPath


class GitHubRepositoryError(Exception):
    pass


class RepositoryLimitError(Exception):
    pass


@dataclass(frozen=True)
class GitHubRepository:
    owner: str
    name: str
    full_name: str
    url: str


@dataclass(frozen=True)
class RepositoryLimits:
    max_repository_size: int
    max_file_count: int
    max_file_size: int
    max_analysis_files: int
    clone_timeout: int
    max_flow_depth: int
    max_flows: int

    @classmethod
    def from_environment(cls) -> "RepositoryLimits":
        return cls(
            max_repository_size=_positive_environment_int(
                "MAX_REPOSITORY_SIZE_MB", 1000
            )
            * 1024
            * 1024,
            max_file_count=_positive_environment_int("MAX_FILE_COUNT", 20000),
            max_file_size=_positive_environment_int("MAX_FILE_SIZE_MB", 5)
            * 1024
            * 1024,
            max_analysis_files=_positive_environment_int(
                "MAX_ANALYSIS_FILES", 10000
            ),
            clone_timeout=_positive_environment_int(
                "GITHUB_CLONE_TIMEOUT_SECONDS", 180
            ),
            max_flow_depth=_positive_environment_int("MAX_FLOW_DEPTH", 20),
            max_flows=_positive_environment_int("MAX_CANDIDATE_FLOWS", 200),
        )


@dataclass
class SnapshotSummary:
    files_discovered: int
    files_analyzed: int
    files_skipped: int
    skipped_files: list[dict[str, str]]
    unsupported_languages: dict[str, int]


def _positive_environment_int(name: str, default: int) -> int:
    value = os.environ.get(name)
    if value is None:
        return default
    try:
        parsed = int(value)
    except ValueError as error:
        raise ValueError(f"{name} must be a positive integer.") from error
    if parsed <= 0:
        raise ValueError(f"{name} must be a positive integer.")
    return parsed


def parse_github_repository_url(value: str) -> GitHubRepository:
    match = re.fullmatch(
        r"https://github\.com/([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+)/?",
        value.strip(),
        re.IGNORECASE,
    )
    if match is None:
        raise ValueError(
            "Enter a public GitHub repository URL like "
            "https://github.com/owner/repository."
        )

    owner, name = match.groups()
    if owner in {".", ".."} or name in {".", ".."}:
        raise ValueError("The GitHub repository URL is invalid.")
    if name.lower().endswith(".git"):
        name = name[:-4]
    if not name or name in {".", ".."}:
        raise ValueError("The GitHub repository URL is invalid.")

    return GitHubRepository(
        owner=owner,
        name=name,
        full_name=f"{owner}/{name}",
        url=f"https://github.com/{owner}/{name}",
    )


def _git_environment() -> dict[str, str]:
    environment = os.environ.copy()
    environment["GIT_TERMINAL_PROMPT"] = "0"
    environment["GIT_CONFIG_NOSYSTEM"] = "1"
    environment["GIT_CONFIG_GLOBAL"] = os.devnull
    return environment


def _git_output(
    arguments: list[str],
    cwd: Path,
    timeout: int = 15,
    allow_missing: bool = False,
) -> str:
    try:
        result = subprocess.run(
            ["git", *arguments],
            cwd=cwd,
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout,
            env=_git_environment(),
        )
    except FileNotFoundError as error:
        raise GitHubRepositoryError("Git is required to analyze GitHub URLs.") from error
    except subprocess.TimeoutExpired as error:
        raise GitHubRepositoryError("GitHub repository acquisition timed out.") from error
    if allow_missing and result.returncode != 0:
        return ""
    if result.returncode != 0:
        raise GitHubRepositoryError("Could not read cloned repository metadata.")
    return result.stdout.strip()


def clone_and_extract_repository(
    repository: GitHubRepository,
    workspace: Path,
    limits: RepositoryLimits,
) -> tuple[Path, str, str | None, SnapshotSummary]:
    """Clone repository objects without checkout, then safely extract source files."""
    git_directory = workspace / "git"
    source_directory = workspace / "source"
    workspace.mkdir(parents=True, exist_ok=True)

    try:
        result = subprocess.run(
            [
                "git",
                "clone",
                "--depth",
                "1",
                "--no-checkout",
                "--no-recurse-submodules",
                f"{repository.url}.git",
                str(git_directory),
            ],
            check=False,
            capture_output=True,
            text=True,
            timeout=limits.clone_timeout,
            env=_git_environment(),
        )
    except FileNotFoundError as error:
        raise GitHubRepositoryError("Git is required to analyze GitHub URLs.") from error
    except subprocess.TimeoutExpired as error:
        raise GitHubRepositoryError("GitHub repository clone timed out.") from error
    if result.returncode != 0:
        raise GitHubRepositoryError(
            "Could not clone the public GitHub repository. Confirm the URL is "
            "public and try again."
        )

    commit = _git_output(["rev-parse", "--verify", "HEAD"], git_directory)
    branch_ref = _git_output(
        ["symbolic-ref", "--quiet", "--short", "refs/remotes/origin/HEAD"],
        git_directory,
        allow_missing=True,
    )
    default_branch = branch_ref.removeprefix("origin/") if branch_ref else None

    source_directory.mkdir(parents=True)
    process = subprocess.Popen(
        ["git", "archive", "--format=tar", "HEAD"],
        cwd=git_directory,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        env=_git_environment(),
    )
    if process.stdout is None:
        process.kill()
        process.wait()
        raise GitHubRepositoryError("Could not read the repository snapshot.")

    archive_timed_out = threading.Event()

    def terminate_timed_out_archive() -> None:
        archive_timed_out.set()
        if process.poll() is None:
            process.kill()

    archive_timer = threading.Timer(limits.clone_timeout, terminate_timed_out_archive)
    archive_timer.start()
    files_discovered = 0
    files_analyzed = 0
    files_skipped = 0
    repository_bytes = 0
    skipped: list[dict[str, str]] = []
    unsupported_languages: dict[str, int] = {}
    supported_extensions = {".js", ".jsx", ".ts", ".tsx"}

    try:
        with tarfile.open(fileobj=process.stdout, mode="r|") as archive:
            for member in archive:
                if member.isdir():
                    continue
                if not (member.isfile() or member.issym() or member.islnk()):
                    continue

                files_discovered += 1
                if files_discovered > limits.max_file_count:
                    raise RepositoryLimitError(
                        "Repository exceeds current MVP analysis limits "
                        f"(maximum {limits.max_file_count} files)."
                    )
                relative_path = PurePosixPath(member.name)
                if (
                    relative_path.is_absolute()
                    or ".." in relative_path.parts
                    or "\\" in member.name
                    or not relative_path.parts
                ):
                    raise GitHubRepositoryError(
                        "Repository contains an unsafe file path."
                    )

                suffix = relative_path.suffix.lower()
                if member.issym() or member.islnk():
                    files_skipped += 1
                    if len(skipped) < 1000:
                        skipped.append(
                            {
                                "path": member.name,
                                "language": suffix.lstrip(".") or "unknown",
                                "status": "skipped_symlink",
                            }
                        )
                    continue
                if suffix not in supported_extensions:
                    files_skipped += 1
                    language = suffix.lstrip(".") or "unknown"
                    unsupported_languages[language] = (
                        unsupported_languages.get(language, 0) + 1
                    )
                    if len(skipped) < 1000:
                        skipped.append(
                            {
                                "path": member.name,
                                "language": language,
                                "status": "unsupported",
                            }
                        )
                    continue

                repository_bytes += member.size
                if repository_bytes > limits.max_repository_size:
                    limit_mb = limits.max_repository_size // (1024 * 1024)
                    raise RepositoryLimitError(
                        "Repository exceeds current MVP analysis limits "
                        f"(maximum {limit_mb} MB uncompressed source size)."
                    )
                if member.size > limits.max_file_size:
                    limit_mb = limits.max_file_size // (1024 * 1024)
                    raise RepositoryLimitError(
                        f"Repository file '{member.name}' exceeds the current "
                        f"MVP limit of {limit_mb} MB."
                    )

                files_analyzed += 1
                if files_analyzed > limits.max_analysis_files:
                    raise RepositoryLimitError(
                        "Repository exceeds current MVP analysis limits "
                        f"(maximum {limits.max_analysis_files} supported source files)."
                    )

                extracted = archive.extractfile(member)
                if extracted is None:
                    raise GitHubRepositoryError(
                        f"Could not read repository file '{member.name}'."
                    )
                destination = source_directory.joinpath(*relative_path.parts)
                resolved_destination = destination.resolve()
                if not resolved_destination.is_relative_to(source_directory.resolve()):
                    raise GitHubRepositoryError(
                        "Repository contains an unsafe file path."
                    )
                destination.parent.mkdir(parents=True, exist_ok=True)
                with extracted, destination.open("xb") as output:
                    shutil.copyfileobj(extracted, output)
    except Exception as error:
        process.stdout.close()
        if process.poll() is None:
            process.kill()
        process.wait()
        if archive_timed_out.is_set():
            raise GitHubRepositoryError(
                "Creating the repository snapshot timed out."
            ) from error
        raise
    finally:
        archive_timer.cancel()

    process.stdout.close()
    try:
        process.wait(timeout=15)
    except subprocess.TimeoutExpired as error:
        process.terminate()
        process.wait()
        raise GitHubRepositoryError(
            "Creating the repository snapshot timed out."
        ) from error

    if archive_timed_out.is_set():
        raise GitHubRepositoryError("Creating the repository snapshot timed out.")
    if process.returncode != 0:
        raise GitHubRepositoryError("Could not create a safe repository snapshot.")

    return (
        source_directory,
        commit,
        default_branch,
        SnapshotSummary(
            files_discovered=files_discovered,
            files_analyzed=files_analyzed,
            files_skipped=files_skipped,
            skipped_files=skipped,
            unsupported_languages=dict(sorted(unsupported_languages.items())),
        ),
    )
