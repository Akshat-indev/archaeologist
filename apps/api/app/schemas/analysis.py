from typing import Literal

from pydantic import BaseModel, Field, model_validator


SymbolKind = Literal[
    "react_component",
    "function",
    "class",
    "method",
    "interface",
    "type",
    "constant",
    "variable",
    "hook",
]


class AnalysisSource(BaseModel):
    type: Literal["github"]
    url: str = Field(min_length=1)


class AnalyzeRequest(BaseModel):
    path: str | None = Field(default=None, min_length=1)
    source: AnalysisSource | None = None

    @model_validator(mode="after")
    def require_exactly_one_source(self) -> "AnalyzeRequest":
        if (self.path is None) == (self.source is None):
            raise ValueError("Provide exactly one of 'path' or 'source'.")
        return self


class RepositoryInfo(BaseModel):
    name: str
    path: str
    language_summary: dict[str, int]
    provider: str | None = None
    owner: str | None = None
    full_name: str | None = None
    url: str | None = None
    default_branch: str | None = None
    commit: str | None = None
    analysis_timestamp: str | None = None


class EntryPoint(BaseModel):
    path: str
    reason: str = "common_entry_filename"


class FileSymbol(BaseModel):
    name: str
    kind: SymbolKind
    exported: bool
    line: int


class SymbolAnalysis(FileSymbol):
    id: str
    file: str


class FileAnalysis(BaseModel):
    path: str
    language: str
    imports: list[str]
    symbols: list[FileSymbol]


class ImportedSymbol(BaseModel):
    imported: str
    local: str


class ArchitectureNode(BaseModel):
    id: str
    path: str
    name: str
    language: str
    symbol_count: int
    imports_count: int
    imported_by_count: int
    exported_symbols: list[str]


class ArchitectureEdge(BaseModel):
    id: str
    source: str
    target: str
    type: str
    symbols: list[ImportedSymbol]


class Architecture(BaseModel):
    nodes: list[ArchitectureNode]
    edges: list[ArchitectureEdge]


class Evidence(BaseModel):
    file: str
    line: int


class BehaviorEntity(BaseModel):
    id: str
    name: str
    kind: str
    file: str | None = None
    line: int | None = None
    method: str | None = None
    path: str | None = None


class BehaviorRelationship(BaseModel):
    id: str
    from_id: str = Field(alias="from")
    to_id: str = Field(alias="to")
    type: str
    confidence: str
    evidence: Evidence
    label: str | None = None


class FlowTrigger(BaseModel):
    type: str
    source: str
    label: str


class BehaviorFlow(BaseModel):
    id: str
    name: str
    trigger: FlowTrigger
    nodes: list[BehaviorEntity]
    relationships: list[BehaviorRelationship]


class FileFrequency(BaseModel):
    path: str
    count: int


class AnalysisMetrics(BaseModel):
    total_files: int
    total_symbols: int
    total_relationships: int
    typescript_files: int
    javascript_files: int
    react_components: int
    files_without_dependencies: int
    files_without_dependents: int
    most_imported_files: list[FileFrequency]
    files: int
    symbols: int
    relationships: int
    components: int
    functions: int
    routes: int
    http_requests: int
    flows: int
    unsupported_files: int = 0
    files_discovered: int = 0
    files_skipped: int = 0


class AnalysisResponse(BaseModel):
    repository: RepositoryInfo
    entry_points: list[EntryPoint]
    metrics: AnalysisMetrics
    architecture: Architecture
    files: list[FileAnalysis]
    symbols: list[SymbolAnalysis]
    entities: list[BehaviorEntity]
    relationships: list[BehaviorRelationship]
    flows: list[BehaviorFlow]
    skipped_files: list[dict[str, str]] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class AnalysisProgress(BaseModel):
    files_discovered: int = 0
    files_analyzed: int = 0
    files_skipped: int = 0
    percent: int = 0


class AnalysisJobResponse(BaseModel):
    analysis_id: str
    status: Literal[
        "created",
        "cloning",
        "scanning",
        "parsing",
        "analyzing",
        "building_flows",
        "complete",
        "failed",
    ]
    progress: AnalysisProgress
    repository: RepositoryInfo | None = None
    result: AnalysisResponse | None = None
    error: str | None = None
