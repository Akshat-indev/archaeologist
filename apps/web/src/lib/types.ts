export type SymbolKind =
  | "react_component"
  | "function"
  | "class"
  | "method"
  | "interface"
  | "type"
  | "constant"
  | "variable"
  | "hook";

export interface FileSymbol {
  name: string;
  kind: SymbolKind;
  exported: boolean;
  line: number;
}

export interface SymbolAnalysis extends FileSymbol {
  id: string;
  file: string;
}

export interface FileAnalysis {
  path: string;
  language: string;
  imports: string[];
  symbols: FileSymbol[];
}

export interface ImportedSymbol {
  imported: string;
  local: string;
}

export interface ArchitectureNode {
  id: string;
  path: string;
  name: string;
  language: string;
  symbol_count: number;
  imports_count: number;
  imported_by_count: number;
  exported_symbols: string[];
}

export interface ArchitectureEdge {
  id: string;
  source: string;
  target: string;
  type: string;
  symbols: ImportedSymbol[];
}

export interface EntryPoint {
  path: string;
  reason: string;
}

export interface BehaviorEntity {
  id: string;
  name: string;
  kind: string;
  file: string | null;
  line: number | null;
  method: string | null;
  path: string | null;
}

export interface BehaviorRelationship {
  id: string;
  from: string;
  to: string;
  type: string;
  confidence: string;
  evidence: {
    file: string;
    line: number;
  };
  label: string | null;
}

export interface BehaviorFlow {
  id: string;
  name: string;
  trigger: {
    type: string;
    source: string;
    label: string;
  };
  nodes: BehaviorEntity[];
  relationships: BehaviorRelationship[];
}

export interface AnalysisResponse {
  repository: {
    name: string;
    path: string;
    language_summary: Record<string, number>;
    provider: string | null;
    owner: string | null;
    full_name: string | null;
    url: string | null;
    default_branch: string | null;
    commit: string | null;
    analysis_timestamp: string | null;
  };
  entry_points: EntryPoint[];
  metrics: {
    total_files: number;
    total_symbols: number;
    total_relationships: number;
    typescript_files: number;
    javascript_files: number;
    react_components: number;
    files_without_dependencies: number;
    files_without_dependents: number;
    most_imported_files: { path: string; count: number }[];
    files: number;
    symbols: number;
    relationships: number;
    components: number;
    functions: number;
    routes: number;
    http_requests: number;
    flows: number;
    unsupported_files: number;
    files_discovered: number;
    files_skipped: number;
  };
  architecture: {
    nodes: ArchitectureNode[];
    edges: ArchitectureEdge[];
  };
  files: FileAnalysis[];
  symbols: SymbolAnalysis[];
  entities: BehaviorEntity[];
  relationships: BehaviorRelationship[];
  flows: BehaviorFlow[];
  skipped_files: { path: string; language: string; status: string }[];
  warnings: string[];
}

export interface GitHubUser {
  login: string;
  name: string;
  avatar_url: string;
}

export interface GitHubSession {
  authenticated: boolean;
  configured: boolean;
  user: GitHubUser | null;
}

export interface AnalysisJobResponse {
  analysis_id: string;
  status:
    | "created"
    | "cloning"
    | "scanning"
    | "parsing"
    | "analyzing"
    | "building_flows"
    | "complete"
    | "failed";
  progress: {
    files_discovered: number;
    files_analyzed: number;
    files_skipped: number;
  };
  repository: AnalysisResponse["repository"] | null;
  result: AnalysisResponse | null;
  error: string | null;
}
