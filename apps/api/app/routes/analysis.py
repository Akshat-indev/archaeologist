from fastapi import APIRouter, Depends, HTTPException, Response

from app.schemas.analysis import (
    AnalysisJobResponse,
    AnalysisResponse,
    AnalyzeRequest,
)
from app.routes.auth import require_github_user
from app.services.analysis_jobs import (
    AnalysisJobCapacityError,
    AnalysisJobNotFoundError,
    get_analysis_job,
    start_analysis_job,
)
from app.services.analysis_service import (
    RepositoryAnalysisError,
    RepositoryNotFoundError,
    RepositoryPathError,
    UnsupportedRepositoryError,
    analyze_repository_path,
)
from app.services.github_repository import (
    RepositoryLimits,
    parse_github_repository_url,
)

router = APIRouter(prefix="/api", tags=["analysis"])


@router.post("/analyze", response_model=AnalysisResponse | AnalysisJobResponse)
def analyze(
    request: AnalyzeRequest,
    response: Response,
    user: dict[str, str] = Depends(require_github_user),
) -> AnalysisResponse | AnalysisJobResponse:
    if request.source is not None:
        try:
            repository = parse_github_repository_url(request.source.url)
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        try:
            limits = RepositoryLimits.from_environment()
        except ValueError as error:
            raise HTTPException(status_code=500, detail=str(error)) from error
        try:
            response.status_code = 202
            return start_analysis_job(repository, limits)
        except AnalysisJobCapacityError as error:
            raise HTTPException(status_code=429, detail=str(error)) from error

    if request.path is None:
        raise HTTPException(
            status_code=422,
            detail="Provide exactly one of 'path' or 'source'.",
        )
    try:
        return analyze_repository_path(request.path)
    except RepositoryNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except RepositoryPathError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    except UnsupportedRepositoryError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    except RepositoryAnalysisError as error:
        raise HTTPException(status_code=500, detail=str(error)) from error


@router.get("/analyses/{analysis_id}", response_model=AnalysisJobResponse)
def read_analysis_job(
    analysis_id: str,
    user: dict[str, str] = Depends(require_github_user),
) -> AnalysisJobResponse:
    try:
        return get_analysis_job(analysis_id)
    except AnalysisJobNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
