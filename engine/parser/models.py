from dataclasses import dataclass, field
from typing import List


@dataclass
class FileInfo:
    path: str
    language: str
    imports: List[str] = field(default_factory=list)
    symbols: List[str] = field(default_factory=list)
    symbol_details: List["SymbolInfo"] = field(default_factory=list)
    behavior_facts: List["BehaviorFact"] = field(default_factory=list)


@dataclass(frozen=True)
class SymbolInfo:
    name: str
    kind: str
    exported: bool = False
    line: int = 1
    container: str | None = None


@dataclass(frozen=True)
class BehaviorFact:
    kind: str
    line: int
    caller: str | None = None
    name: str | None = None
    receiver: str | None = None
    method: str | None = None
    path: str | None = None
    target: str | None = None


@dataclass(frozen=True)
class BehaviorEntity:
    id: str
    name: str
    kind: str
    file: str | None = None
    line: int | None = None
    method: str | None = None
    path: str | None = None


@dataclass(frozen=True)
class Evidence:
    file: str
    line: int


@dataclass(frozen=True)
class BehaviorRelationship:
    from_id: str
    to_id: str
    type: str
    evidence: Evidence
    confidence: str = "confirmed"
    label: str | None = None


@dataclass(frozen=True)
class ImportedSymbol:
    imported: str
    local: str


@dataclass
class Relationship:
    from_path: str
    to_path: str
    type: str = "imports"
    symbols: List[ImportedSymbol] = field(default_factory=list)


@dataclass
class RepositoryModel:
    repository: str
    files: List[FileInfo] = field(default_factory=list)
    relationships: List[Relationship] = field(default_factory=list)
    behavior_entities: List[BehaviorEntity] = field(default_factory=list)
    behavior_relationships: List[BehaviorRelationship] = field(default_factory=list)