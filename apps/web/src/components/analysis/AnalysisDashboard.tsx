"use client";

import { useMemo, useRef, useState } from "react";
import Link from "next/link";

import {
  ArchitectureGraph,
  selectArchitectureNodes,
} from "@/components/analysis/ArchitectureGraph";
import { FileTable } from "@/components/analysis/FileTable";
import { FlowGraph } from "@/components/analysis/FlowGraph";
import { MetricCard } from "@/components/analysis/MetricCard";
import type {
  AnalysisResponse,
  BehaviorEntity,
  BehaviorFlow,
  BehaviorRelationship,
  ArchitectureEdge,
  ArchitectureNode,
  FileAnalysis,
  GitHubUser,
} from "@/lib/types";

type View = "overview" | "flows" | "architecture" | "files";
type GraphSelection =
  | { type: "node"; value: ArchitectureNode }
  | { type: "edge"; value: ArchitectureEdge }
  | null;
type FlowSelection =
  | { type: "node"; value: BehaviorEntity }
  | { type: "relationship"; value: BehaviorRelationship }
  | null;

const navigation: { id: View; label: string; icon: string }[] = [
  { id: "overview", label: "Overview", icon: "◫" },
  { id: "flows", label: "Flows", icon: "↳" },
  { id: "architecture", label: "Architecture", icon: "⌘" },
  { id: "files", label: "Files", icon: "▤" },
];

interface AnalysisDashboardProps {
  analysis: AnalysisResponse;
  githubUser: GitHubUser | null;
  onSignOut: () => void;
  onNewAnalysis: () => void;
}

export function AnalysisDashboard({
  analysis,
  githubUser,
  onSignOut,
  onNewAnalysis,
}: AnalysisDashboardProps) {
  const [view, setView] = useState<View>("overview");
  const [search, setSearch] = useState("");
  const [selectedFilePath, setSelectedFilePath] = useState<string | null>(null);
  const [graphSelection, setGraphSelection] = useState<GraphSelection>(null);
  const [selectedFlowId, setSelectedFlowId] = useState<string | null>(null);
  const [flowSelection, setFlowSelection] = useState<FlowSelection>(null);
  const [clipboardNotice, setClipboardNotice] = useState<{
    kind: "success" | "error";
    title: string;
    message: string;
  } | null>(null);
  const promptTimeout = useRef<number | null>(null);
  const [architectureSearch, setArchitectureSearch] = useState("");
  const [hideDisconnected, setHideDisconnected] = useState(false);
  const [visibleNodeLimit, setVisibleNodeLimit] = useState(60);
  const [directoryFilter, setDirectoryFilter] = useState("");
  const [languageFilter, setLanguageFilter] = useState("");
  const filteredFiles = useMemo(
    () =>
      analysis.files.filter((file) =>
        file.path.toLowerCase().includes(search.toLowerCase()) &&
        (!directoryFilter || file.path.split("/")[0] === directoryFilter) &&
        (!languageFilter || file.language === languageFilter),
      ),
    [analysis.files, directoryFilter, languageFilter, search],
  );
  const directories = useMemo(
    () => [...new Set(analysis.files.map((file) => file.path.split("/")[0]))].sort(),
    [analysis.files],
  );
  const languages = useMemo(
    () => [...new Set(analysis.files.map((file) => file.language))].sort(),
    [analysis.files],
  );
  const visibleArchitectureNodes = useMemo(
    () =>
      selectArchitectureNodes(
        analysis,
        architectureSearch,
        hideDisconnected,
        visibleNodeLimit,
      ),
    [analysis, architectureSearch, hideDisconnected, visibleNodeLimit],
  );
  const fileByPath = useMemo(
    () => new Map(analysis.files.map((file) => [file.path, file])),
    [analysis.files],
  );
  const selectedFile = selectedFilePath
    ? (fileByPath.get(selectedFilePath) ?? null)
    : null;
  const selectedFlow =
    analysis.flows.find((flow) => flow.id === selectedFlowId) ??
    analysis.flows[0] ??
    null;
  const pageTitle = navigation.find((item) => item.id === view)?.label ?? "Flows";

  function selectFile(path: string) {
    setSelectedFilePath(path);
    setView("files");
  }

  async function copyBrief(text: string, successMessage: string) {
    if (promptTimeout.current !== null) {
      window.clearTimeout(promptTimeout.current);
    }

    try {
      await navigator.clipboard.writeText(text);
      setClipboardNotice({
        kind: "success",
        title: successMessage,
        message: "Ready to paste into your AI assistant.",
      });
    } catch {
      setClipboardNotice({
        kind: "error",
        title: "Could not copy brief",
        message: "Check browser clipboard permissions and try again.",
      });
    }

    promptTimeout.current = window.setTimeout(() => {
      setClipboardNotice(null);
      promptTimeout.current = null;
    }, 3200);
  }

  function buildProjectBrief() {
    const repository = analysis.repository.full_name ?? analysis.repository.name;
    const revision = analysis.repository.commit
      ? ` (${analysis.repository.commit.slice(0, 7)})`
      : "";
    const languages = Object.entries(analysis.repository.language_summary)
      .sort((left, right) => right[1] - left[1])
      .map(([language, count]) => `${language} (${count} files)`);
    const directories = new Map<string, number>();
    for (const file of analysis.files) {
      const directory = file.path.includes("/") ? file.path.split("/")[0] : ".";
      directories.set(directory, (directories.get(directory) ?? 0) + 1);
    }
    const structure = [...directories.entries()]
      .sort((left, right) => right[1] - left[1])
      .slice(0, 12)
      .map(([directory, count]) => `- \`${directory}/\` — ${count} analyzed files`);
    const entryPoints = analysis.entry_points.length
      ? analysis.entry_points.map((entry) => `- \`${entry.path}\` — ${entry.reason}`)
      : ["- No conventional entry points were identified by the scan."];
    const hotspots = analysis.metrics.most_imported_files.slice(0, 8).map(
      (file) => `- \`${file.path}\` — imported by ${file.count} files`,
    );
    const flowBriefs = analysis.flows.slice(0, 8).map((flow) => {
      const steps = flow.relationships.map((relationship) => {
        const source = flow.nodes.find((node) => node.id === relationship.from);
        const target = flow.nodes.find((node) => node.id === relationship.to);
        const relation = relationship.label ?? relationship.type.replaceAll("_", " ");
        return `  - ${source?.name ?? relationship.from} ${relation} ${target?.name ?? relationship.to} (\`${relationship.evidence.file}:${relationship.evidence.line}\`)`;
      });
      return [
        `- **${flow.name}** starts at ${flow.trigger.label} in \`${flow.trigger.source}\`.`,
        ...(steps.length ? steps : ["  - No connected steps were resolved."]),
      ].join("\n");
    });

    return [
      `# Project context: ${repository}${revision}`,
      analysis.repository.url ? `Repository: ${analysis.repository.url}` : "",
      "",
      "You are helping make a change in this existing project. Treat the repository source as authoritative; this brief is a map for orientation, not a substitute for reading the relevant files.",
      "",
      "## Repository snapshot",
      `- ${analysis.metrics.total_files} source files analyzed; ${analysis.metrics.total_symbols} symbols and ${analysis.metrics.total_relationships} relationships identified.`,
      `- ${analysis.metrics.routes} routes and ${analysis.metrics.http_requests} outgoing HTTP requests detected; ${analysis.metrics.flows} candidate behavior flows reconstructed.`,
      `- Languages: ${languages.length ? languages.join(", ") : "not reported"}.`,
      "",
      "## Project layout",
      ...(structure.length ? structure : ["- No directory structure was available."]),
      "",
      "## Entry points",
      ...entryPoints,
      "",
      "## Architecture signals",
      ...(hotspots.length ? hotspots : ["- No high-traffic imported files were identified."]),
      "",
      "## Reconstructed behavior",
      ...(flowBriefs.length ? flowBriefs : ["- No end-to-end application flows were connected by static analysis."]),
      analysis.flows.length > 8 ? `- ${analysis.flows.length - 8} additional flows are available in the analysis UI.` : "",
      "",
      "## Coverage and cautions",
      "- These are static-analysis findings. Verify each cited file and line in source before relying on an inferred behavior.",
      "- This scan focuses on JavaScript and TypeScript source. Dynamic behavior, external packages, and unsupported files may not be represented.",
      ...analysis.warnings.map((warning) => `- Scan warning: ${warning}`),
      "",
      "## How to work in this project",
      "1. First inspect the relevant implementation and nearby tests; preserve the repository's existing conventions.",
      "2. Explain the smallest useful change before making it, and avoid unrelated refactors.",
      "3. Add or update focused tests, run the narrowest relevant checks, and report any remaining uncertainty.",
      "",
      "My task: [Describe the change or question here]",
    ].filter(Boolean).join("\n");
  }

  async function copyProjectBrief() {
    await copyBrief(buildProjectBrief(), "Project brief copied");
  }

  async function copyFlowPrompt(flow: BehaviorFlow) {
    const entitiesById = new Map(flow.nodes.map((entity) => [entity.id, entity]));
    const repository = analysis.repository.full_name ?? analysis.repository.name;
    const revision = analysis.repository.commit
      ? ` at commit ${analysis.repository.commit.slice(0, 7)}`
      : "";
    const relationships = flow.relationships.map((relationship, index) => {
      const source = entitiesById.get(relationship.from);
      const target = entitiesById.get(relationship.to);
      const relation = relationship.label ?? relationship.type.replaceAll("_", " ");
      return `${index + 1}. ${source?.name ?? relationship.from} --${relation}--> ${target?.name ?? relationship.to} (${relationship.evidence.file}:${relationship.evidence.line})`;
    });
    const prompt = [
      `# Behavior brief: ${flow.name}`,
      `Project: ${repository}${revision}`,
      "",
      `This candidate flow begins when ${flow.trigger.label} is activated in \`${flow.trigger.source}\`. Use the evidence below as a navigation guide, then verify the implementation in source before drawing conclusions.`,
      "",
      "## Connected steps",
      "",
      ...relationships,
      "",
      "## What to investigate",
      "Explain the user-visible behavior end to end, identify relevant state changes and error paths, and call out gaps or assumptions. Suggest practical edge cases. Keep claims tied to source evidence; distinguish confirmed behavior from inference.",
      "",
      "My question about this flow: [Describe what you want to understand or change]",
    ].join("\n");
    await copyBrief(prompt, "Flow brief copied");
  }

  return (
    <main className="workspace">
      <header className="topbar">
        <Link className="brand" href="/" aria-label="Archaeologist home">
          <span className="brand-mark">
            <span />
            <span />
            <span />
            <span />
          </span>
          <span>archaeologist</span>
        </Link>
        <div className="topbar-divider" />
        <div className="repo-crumb">
          <span className="repo-status-dot" />
          <span>
            {analysis.repository.full_name ?? analysis.repository.name}
          </span>
          <span className="crumb-separator">/</span>
          <code title={analysis.repository.path}>
            {analysis.repository.provider === "github"
              ? `${analysis.repository.default_branch ?? "default branch"} · ${analysis.repository.commit?.slice(0, 7) ?? "commit unknown"}`
              : analysis.repository.path}
          </code>
        </div>
        <div className="topbar-actions">
          {githubUser && (
            <span className="workspace-account">GitHub · {githubUser.login}</span>
          )}
          <span className="analysis-status"><span /> Static analysis</span>
          {githubUser && (
            <button className="button button-quiet" onClick={onSignOut} type="button">
              Sign out
            </button>
          )}
          <button className="button button-quiet" onClick={onNewAnalysis} type="button">
            New analysis
          </button>
        </div>
      </header>

      <div className="workspace-body">
        <aside className="sidebar">
          <div className="sidebar-label">Workspace</div>
          <nav aria-label="Analysis views" className="side-nav">
            {navigation.map((item) => (
              <button
                key={item.id}
                className={`nav-item${view === item.id ? " active" : ""}`}
                onClick={() => {
                  setView(item.id);
                  setSearch("");
                }}
                type="button"
              >
                <span className="nav-icon">{item.icon}</span>
                <span>{item.label}</span>
                {item.id === "files" && (
                  <span className="nav-count">{analysis.metrics.total_files}</span>
                )}
              </button>
            ))}
          </nav>
          <div className="sidebar-bottom">
            <div className="sidebar-label">Analysis mode</div>
            <div className="mode-card">
              <span className="mode-indicator" />
              <div>
                <strong>Static scan</strong>
                <span>Code-grounded facts</span>
              </div>
            </div>
            <p className="sidebar-footnote">No AI guesses. Just your code.</p>
          </div>
        </aside>

        <section className="main-content">
          {analysis.warnings.length > 0 && (
            <div className="analysis-warning" role="status">
              <strong>
                {analysis.metrics.files_skipped} files skipped
              </strong>
              <div>
                {analysis.warnings.map((warning) => (
                  <p key={warning}>{warning}</p>
                ))}
              </div>
            </div>
          )}
          <div className="page-heading">
            <div>
              <div className="eyebrow">REPOSITORY ANALYSIS</div>
              <h1>{pageTitle}</h1>
              <p>
                {view === "overview" &&
                  "A deterministic snapshot of the structure in this repository."}
                {view === "flows" &&
                  "Follow evidence-backed behavior from user interactions to application responses."}
                {view === "architecture" &&
                  "Explore every source file and its resolved import relationships."}
                {view === "files" &&
                  "Browse source files, their symbols, and dependency counts."}
              </p>
            </div>
            <div className="scan-meta">
              <span className="scan-check">✓</span>
              <span>Analysis complete</span>
            </div>
          </div>

          {view === "overview" && (
            <Overview
              analysis={analysis}
              onCopyProjectBrief={copyProjectBrief}
              onCopyPrompt={copyFlowPrompt}
              onSelectFile={selectFile}
              onSelectFlow={(flow) => {
                setSelectedFlowId(flow.id);
                setFlowSelection(null);
                setView("flows");
              }}
              onNavigate={setView}
            />
          )}

          {view === "flows" && (
            <section className="surface flow-surface">
              <div className="surface-header">
                <div>
                  <h2>Detected application flows</h2>
                  <p>
                    {analysis.flows.length} candidate{" "}
                    {analysis.flows.length === 1 ? "flow" : "flows"} built from
                    static code evidence
                  </p>
                </div>
                <span className="flow-evidence-badge">STATIC EVIDENCE</span>
              </div>
              {analysis.flows.length > 0 && selectedFlow ? (
                <div className="flow-workspace">
                  <nav className="flow-list" aria-label="Detected flows">
                    {analysis.flows.map((flow) => (
                      <button
                        className={`flow-list-item${flow.id === selectedFlow.id ? " selected" : ""}`}
                        key={flow.id}
                        onClick={() => {
                          setSelectedFlowId(flow.id);
                          setFlowSelection(null);
                        }}
                        type="button"
                      >
                        <span className="flow-trigger-icon">↳</span>
                        <span className="flow-list-copy">
                          <strong>{flow.name}</strong>
                          <span>{flow.trigger.label} · {flow.nodes.length} entities</span>
                        </span>
                      </button>
                    ))}
                  </nav>
                  <div className="flow-content">
                    <div className="flow-heading">
                      <div>
                        <h3>{selectedFlow.name}</h3>
                        <p>
                          Triggered by {selectedFlow.trigger.label} in{" "}
                          <code>{selectedFlow.trigger.source}</code>
                        </p>
                      </div>
                      <div className="flow-heading-actions">
                        <span>{selectedFlow.relationships.length} connections</span>
                        <button
                          className="button button-quiet prompt-button"
                          onClick={() => void copyFlowPrompt(selectedFlow)}
                          type="button"
                        >
                          Copy flow brief
                        </button>
                      </div>
                    </div>
                    <div className="flow-graph-layout">
                      <FlowGraph
                        flow={selectedFlow}
                        onSelectNode={(entity) =>
                          setFlowSelection({ type: "node", value: entity })
                        }
                        onSelectRelationship={(relationship) =>
                          setFlowSelection({
                            type: "relationship",
                            value: relationship,
                          })
                        }
                      />
                      <FlowDetails
                        selection={flowSelection}
                        flow={selectedFlow}
                      />
                    </div>
                  </div>
                </div>
              ) : (
                <div className="empty-flow">
                  <div className="detail-placeholder-icon">↳</div>
                  <strong>No application flows detected yet</strong>
                  <p>
                    Flows appear when static analysis can connect a React event
                    handler to calls or an HTTP request.
                  </p>
                </div>
              )}
            </section>
          )}

          {view === "architecture" && (
            <section className="surface graph-surface architecture-surface">
              <div className="surface-header">
                <div>
                  <h2>Repository map</h2>
                  <p>
                    Showing {visibleArchitectureNodes.length} of{" "}
                    {analysis.architecture.nodes.length} files · up to 200 import links
                  </p>
                </div>
                <div className="architecture-controls">
                  <SearchBox
                    value={architectureSearch}
                    onChange={(value) => {
                      setArchitectureSearch(value);
                      setVisibleNodeLimit(60);
                    }}
                    placeholder="Search files..."
                  />
                  <label className="graph-filter-toggle">
                    <input
                      checked={hideDisconnected}
                      onChange={(event) =>
                        setHideDisconnected(event.target.checked)
                      }
                      type="checkbox"
                    />
                    Connected only
                  </label>
                  <div className="graph-legend"><span /> A → B imports</div>
                </div>
              </div>
              <div className="architecture-layout">
                <ArchitectureGraph
                  analysis={analysis}
                  search={architectureSearch}
                  hideDisconnected={hideDisconnected}
                  visibleNodeLimit={visibleNodeLimit}
                  visibleEdgeLimit={200}
                  onSelectNode={(node) =>
                    setGraphSelection({ type: "node", value: node })
                  }
                  onSelectEdge={(edge) =>
                    setGraphSelection({ type: "edge", value: edge })
                  }
                />
                <GraphDetails
                  analysis={analysis}
                  selection={graphSelection}
                  onSelectNode={(node) =>
                    setGraphSelection({ type: "node", value: node })
                  }
                  onSelectEdge={(edge) =>
                    setGraphSelection({ type: "edge", value: edge })
                  }
                />
              </div>
              {visibleArchitectureNodes.length <
                analysis.architecture.nodes.filter((node) => {
                  const query = architectureSearch.trim().toLowerCase();
                  const matches =
                    !query ||
                    node.path.toLowerCase().includes(query) ||
                    node.name.toLowerCase().includes(query);
                  return (
                    matches &&
                    (!hideDisconnected ||
                      node.imports_count + node.imported_by_count > 0)
                  );
                }).length && (
                <button
                  className="show-more-nodes"
                  onClick={() => setVisibleNodeLimit((limit) => limit + 60)}
                  type="button"
                >
                  Show 60 more files
                </button>
              )}
            </section>
          )}

          {view === "files" && (
            <section className="surface list-surface">
              <div className="surface-header">
                <div>
                  <h2>Source files</h2>
                  <p>{analysis.files.length} files found in this repository</p>
                </div>
                <SearchBox
                  value={search}
                  onChange={setSearch}
                  placeholder="Filter files..."
                />
                <select
                  aria-label="Filter by directory"
                  className="filter-select"
                  onChange={(event) => setDirectoryFilter(event.target.value)}
                  value={directoryFilter}
                >
                  <option value="">All directories</option>
                  {directories.map((directory) => (
                    <option key={directory} value={directory}>
                      {directory}
                    </option>
                  ))}
                </select>
                <select
                  aria-label="Filter by language"
                  className="filter-select"
                  onChange={(event) => setLanguageFilter(event.target.value)}
                  value={languageFilter}
                >
                  <option value="">All languages</option>
                  {languages.map((language) => (
                    <option key={language} value={language}>
                      {language}
                    </option>
                  ))}
                </select>
              </div>
              <div className="data-layout">
                <FileTable
                  files={filteredFiles}
                  nodes={analysis.architecture.nodes}
                  selectedPath={selectedFile?.path ?? null}
                  onSelect={setSelectedFilePath}
                />
                <FileDetails
                  file={selectedFile}
                  analysis={analysis}
                  onSelectFile={selectFile}
                />
              </div>
            </section>
          )}
        </section>
      </div>
      {clipboardNotice && (
        <div
          className={`clipboard-toast ${clipboardNotice.kind}`}
          role="status"
          aria-live="polite"
        >
          <span aria-hidden="true" className="clipboard-toast-icon">
            {clipboardNotice.kind === "success" ? "✓" : "!"}
          </span>
          <span className="clipboard-toast-copy">
            <strong>{clipboardNotice.title}</strong>
            <span>{clipboardNotice.message}</span>
          </span>
        </div>
      )}
    </main>
  );
}

function Overview({
  analysis,
  onCopyProjectBrief,
  onCopyPrompt,
  onSelectFile,
  onSelectFlow,
  onNavigate,
}: {
  analysis: AnalysisResponse;
  onCopyProjectBrief: () => void;
  onCopyPrompt: (flow: BehaviorFlow) => void;
  onSelectFile: (path: string) => void;
  onSelectFlow: (flow: BehaviorFlow) => void;
  onNavigate: (view: View) => void;
}) {
  const featuredFlow = analysis.flows[0];
  const entitiesById = new Map(featuredFlow?.nodes.map((entity) => [entity.id, entity]));

  return (
    <div className="overview-content">
      {featuredFlow ? (
        <section className="featured-flow surface">
          <div className="featured-flow-heading">
            <div>
              <span className="section-kicker">RECONSTRUCTED BEHAVIOR</span>
              <h2>{featuredFlow.name}</h2>
              <p>
                Starts at <strong>{featuredFlow.trigger.label}</strong> in{" "}
                <code>{featuredFlow.trigger.source}</code>
              </p>
            </div>
            <div className="featured-flow-actions">
              <button
                className="button button-quiet prompt-button"
                onClick={() => void onCopyProjectBrief()}
                type="button"
              >
                Copy project brief
              </button>
              <button
                className="button button-quiet prompt-button"
                onClick={() => void onCopyPrompt(featuredFlow)}
                type="button"
              >
                Copy flow brief
              </button>
              <button
                className="button button-primary featured-flow-action"
                onClick={() => onSelectFlow(featuredFlow)}
                type="button"
              >
                Open flow graph <span aria-hidden="true">→</span>
              </button>
            </div>
          </div>
          <div className="relationship-list" aria-label="Evidence-backed relationships">
            {featuredFlow.relationships.map((relationship, index) => {
              const source = entitiesById.get(relationship.from);
              const target = entitiesById.get(relationship.to);
              return (
                <div className="relationship-row" key={relationship.id}>
                  <span className="relationship-index">{String(index + 1).padStart(2, "0")}</span>
                  <div className="relationship-endpoint">
                    <strong>{source?.name ?? relationship.from}</strong>
                    <span>{source?.kind.replaceAll("_", " ")}</span>
                  </div>
                  <span className="relationship-type">
                    {relationship.label ?? relationship.type.replaceAll("_", " ")}
                  </span>
                  <div className="relationship-endpoint">
                    <strong>{target?.name ?? relationship.to}</strong>
                    <span>{target?.kind.replaceAll("_", " ")}</span>
                  </div>
                  <code className="relationship-evidence">
                    {relationship.evidence.file}:{relationship.evidence.line}
                  </code>
                </div>
              );
            })}
          </div>
        </section>
      ) : (
        <section className="featured-flow surface no-featured-flow">
          <span className="section-kicker">REPOSITORY BEHAVIOR</span>
          <h2>No end-to-end flow was reconstructed</h2>
          <p>
            The scan found {analysis.metrics.http_requests} HTTP requests and{" "}
            {analysis.metrics.routes} API routes, but could not connect them to a
            user-triggered flow with current static evidence.
          </p>
          <button
            className="text-button"
            onClick={() => onNavigate("architecture")}
            type="button"
          >
            Explore repository map <span>↗</span>
          </button>
        </section>
      )}

      <div className="metric-grid">
        <MetricCard
          label="Files"
          value={analysis.metrics.total_files}
          note="JavaScript and TypeScript"
          accent="blue"
        />
        <MetricCard
          label="Flows"
          value={analysis.metrics.flows}
          note="Connected behavior paths"
          accent="green"
        />
        <MetricCard
          label="Routes"
          value={analysis.metrics.routes}
          note="API endpoints found"
          accent="green"
        />
        <MetricCard
          label="HTTP requests"
          value={analysis.metrics.http_requests}
          note="Outgoing requests found"
          accent="blue"
        />
      </div>

      <section className="surface overview-graph">
        <div className="surface-header">
          <div>
            <h2>Repository map</h2>
            <p>Arrows point from a file to the files it imports</p>
          </div>
          <button
            className="text-button"
            onClick={() => onNavigate("architecture")}
            type="button"
          >
            Explore map <span>↗</span>
          </button>
        </div>
        <ArchitectureGraph
          analysis={analysis}
          compact
          hideDisconnected
          visibleNodeLimit={10}
          onSelectNode={(node) => onSelectFile(node.path)}
        />
      </section>
    </div>
  );
}

function SearchBox({
  value,
  onChange,
  placeholder,
}: {
  value: string;
  onChange: (value: string) => void;
  placeholder: string;
}) {
  return (
    <label className="search-box">
      <svg viewBox="0 0 20 20" aria-hidden="true">
        <circle cx="8.5" cy="8.5" r="5.5" />
        <path d="m13 13 4 4" />
      </svg>
      <input
        value={value}
        onChange={(event) => onChange(event.target.value)}
        placeholder={placeholder}
      />
    </label>
  );
}

function FlowDetails({
  selection,
  flow,
}: {
  selection: FlowSelection;
  flow: BehaviorFlow;
}) {
  if (!selection) {
    return (
      <aside className="flow-details detail-empty">
        <div className="detail-placeholder-icon">⌁</div>
        <strong>Select a flow node or connection</strong>
        <p>Inspect the entity or source-code evidence for a relationship.</p>
      </aside>
    );
  }

  if (selection.type === "node") {
    const entity = selection.value;
    return (
      <aside className="flow-details">
        <div className="detail-heading">
          <span className="eyebrow">FLOW ENTITY</span>
          <span className="language-chip">
            {entity.kind.replaceAll("_", " ")}
          </span>
        </div>
        <strong className="flow-detail-name">{entity.name}</strong>
        <code className="detail-path">{entity.id}</code>
        {entity.path && (
          <div className="detail-section">
            <div className="detail-section-title">Endpoint</div>
            <code className="flow-endpoint">
              {entity.method} {entity.path}
            </code>
          </div>
        )}
        {entity.file && (
          <div className="detail-section">
            <div className="detail-section-title">Source</div>
            <code className="flow-evidence-file">
              {entity.file}
              {entity.line ? `:${entity.line}` : ""}
            </code>
          </div>
        )}
        <div className="detail-section">
          <div className="detail-section-title">Flow relationships</div>
          <span className="detail-muted">
            {flow.relationships.filter(
              (relationship) =>
                relationship.from === entity.id ||
                relationship.to === entity.id,
            ).length}{" "}
            connected steps
          </span>
        </div>
      </aside>
    );
  }

  const relationship = selection.value;
  const source = flow.nodes.find((node) => node.id === relationship.from);
  const target = flow.nodes.find((node) => node.id === relationship.to);
  return (
    <aside className="flow-details">
      <div className="detail-heading">
        <span className="eyebrow">BEHAVIOR RELATIONSHIP</span>
        <span className="language-chip">{relationship.confidence}</span>
      </div>
      <div className="flow-relation-ends">
        <code>{source?.name ?? relationship.from}</code>
        <span>{relationship.label ?? relationship.type.replaceAll("_", " ")}</span>
        <code>{target?.name ?? relationship.to}</code>
      </div>
      <div className="detail-section">
        <div className="detail-section-title">Static evidence</div>
        <code className="flow-evidence-file">
          {relationship.evidence.file}:{relationship.evidence.line}
        </code>
      </div>
      <span className="detail-muted">
        This relationship is connected from explicit syntax at the evidence
        location.
      </span>
    </aside>
  );
}

function GraphDetails({
  analysis,
  selection,
  onSelectNode,
  onSelectEdge,
}: {
  analysis: AnalysisResponse;
  selection: GraphSelection;
  onSelectNode: (node: ArchitectureNode) => void;
  onSelectEdge: (edge: ArchitectureEdge) => void;
}) {
  if (!selection) {
    return (
      <aside className="detail-panel detail-empty">
        <div className="detail-placeholder-icon">⌁</div>
        <strong>Select a node or edge</strong>
        <p>Inspect file symbols and the names imported across a relationship.</p>
      </aside>
    );
  }

  if (selection.type === "edge") {
    const edge = selection.value;
    const source = analysis.architecture.nodes.find(
      (node) => node.id === edge.source,
    );
    const target = analysis.architecture.nodes.find(
      (node) => node.id === edge.target,
    );
    return (
      <aside className="detail-panel graph-detail-panel">
        <div className="detail-heading">
          <span className="eyebrow">IMPORT RELATIONSHIP</span>
          <span className="language-chip">{edge.type}</span>
        </div>
        <code className="detail-path">{edge.source}</code>
        <div className="detail-section">
          <div className="detail-section-title">Imports from</div>
          <button
            className="detail-list-row detail-link"
            onClick={() => source && onSelectNode(source)}
            type="button"
          >
            <span className="relationship-arrow">↓</span>
            <code>{edge.target}</code>
          </button>
        </div>
        <div className="detail-section">
          <div className="detail-section-title">Imported symbols</div>
          <div className="detail-section-content">
            {edge.symbols.length > 0 ? (
              edge.symbols.map((symbol) => (
                <div
                  className="detail-list-row"
                  key={`${symbol.imported}:${symbol.local}`}
                >
                  <span className="symbol-bullet">ƒ</span>
                  <code>
                    {symbol.imported}
                    {symbol.local !== symbol.imported &&
                      ` as ${symbol.local}`}
                  </code>
                </div>
              ))
            ) : (
              <span className="detail-muted">
                Binding names are unavailable for this import.
              </span>
            )}
          </div>
        </div>
        {target && (
          <button
            className="detail-link graph-open-file"
            onClick={() => onSelectNode(target)}
            type="button"
          >
            Inspect target file
          </button>
        )}
      </aside>
    );
  }

  const node = selection.value;
  const file = analysis.files.find((item) => item.path === node.path);
  const imports = analysis.architecture.edges.filter(
    (edge) => edge.source === node.id,
  );
  const importedBy = analysis.architecture.edges.filter(
    (edge) => edge.target === node.id,
  );

  return (
    <aside className="detail-panel graph-detail-panel">
      <div className="detail-heading">
        <span className="eyebrow">FILE NODE</span>
        <span className="language-chip">{node.language}</span>
      </div>
      <code className="detail-path">{node.path}</code>
      <div className="detail-stats">
        <div><strong>{node.symbol_count}</strong><span>Symbols</span></div>
        <div><strong>{node.imports_count}</strong><span>Imports</span></div>
        <div><strong>{node.imported_by_count}</strong><span>Imported by</span></div>
      </div>
      <div className="detail-section">
        <div className="detail-section-title">Declarations</div>
        <div className="detail-section-content">
          {file && file.symbols.length > 0 ? (
            file.symbols.map((symbol) => (
              <div className="detail-list-row" key={`${symbol.name}:${symbol.kind}`}>
                <span className="symbol-bullet">ƒ</span>
                <code>{symbol.name}</code>
                <span className="detail-muted">{symbol.kind}</span>
                {symbol.exported && <span className="exported">exported</span>}
              </div>
            ))
          ) : (
            <span className="detail-muted">No declarations detected.</span>
          )}
        </div>
      </div>
      <GraphRelationshipList
        title="Imports"
        edges={imports}
        direction="target"
        onSelectEdge={onSelectEdge}
      />
      <GraphRelationshipList
        title="Imported by"
        edges={importedBy}
        direction="source"
        onSelectEdge={onSelectEdge}
      />
    </aside>
  );
}

function GraphRelationshipList({
  title,
  edges,
  direction,
  onSelectEdge,
}: {
  title: string;
  edges: ArchitectureEdge[];
  direction: "source" | "target";
  onSelectEdge: (edge: ArchitectureEdge) => void;
}) {
  return (
    <div className="detail-section">
      <div className="detail-section-title">{title}</div>
      <div className="detail-section-content">
        {edges.length > 0 ? (
          edges.map((edge) => (
            <button
              className="detail-list-row detail-link"
              key={edge.id}
              onClick={() => onSelectEdge(edge)}
              type="button"
            >
              <span className="relationship-arrow">↔</span>
              <code>{direction === "target" ? edge.target : edge.source}</code>
            </button>
          ))
        ) : (
          <span className="detail-muted">No relationships.</span>
        )}
      </div>
    </div>
  );
}

function FileDetails({
  file,
  analysis,
  onSelectFile,
}: {
  file: FileAnalysis | null;
  analysis: AnalysisResponse;
  onSelectFile: (path: string) => void;
}) {
  if (!file) {
    return (
      <aside className="detail-panel detail-empty">
        <div className="detail-placeholder-icon">⌁</div>
        <strong>Select a file</strong>
        <p>Choose a source file to inspect its dependencies and symbols.</p>
      </aside>
    );
  }

  const node = analysis.architecture.nodes.find(
    (item) => item.path === file.path,
  );
  const imports = analysis.architecture.edges.filter(
    (edge) => edge.source === file.path,
  );
  const importedBy = analysis.architecture.edges.filter(
    (edge) => edge.target === file.path,
  );
  const detectedBehavior = analysis.relationships.filter(
    (relationship) => relationship.evidence.file === file.path,
  );
  const detectedFlows = analysis.flows.filter((flow) =>
    flow.nodes.some((entity) => entity.file === file.path),
  );

  return (
    <aside className="detail-panel">
      <div className="detail-heading">
        <span className="eyebrow">SOURCE FILE</span>
        <span className="language-chip">{file.language}</span>
      </div>
      <code className="detail-path">{file.path}</code>
      <div className="detail-stats">
        <div><strong>{file.symbols.length}</strong><span>Symbols</span></div>
        <div><strong>{node?.imports_count ?? 0}</strong><span>Imports</span></div>
        <div><strong>{node?.imported_by_count ?? 0}</strong><span>Imported by</span></div>
      </div>
      <div className="detail-section">
        <div className="detail-section-title">Declarations</div>
        <div className="detail-section-content">
          {file.symbols.length > 0 ? (
            file.symbols.map((symbol) => (
              <div className="detail-list-row" key={`${symbol.name}:${symbol.kind}`}>
                <span className="symbol-bullet">ƒ</span>
                <code>{symbol.name}</code>
                <span className="detail-muted">{symbol.kind}</span>
                {symbol.exported && <span className="exported">exported</span>}
              </div>
            ))
          ) : (
            <span className="detail-muted">No declarations detected.</span>
          )}
        </div>
      </div>
      <div className="detail-section">
        <div className="detail-section-title">Imports</div>
        <div className="detail-section-content">
          {imports.length > 0 ? (
            imports.map((edge) => (
              <button
                className="detail-list-row detail-link"
                key={edge.id}
                onClick={() => onSelectFile(edge.target)}
                type="button"
              >
                <span className="relationship-arrow">↓</span>
                <code>{edge.target}</code>
              </button>
            ))
          ) : (
            <span className="detail-muted">No resolved dependencies.</span>
          )}
        </div>
      </div>
      <div className="detail-section">
        <div className="detail-section-title">Imported by</div>
        <div className="detail-section-content">
          {importedBy.length > 0 ? (
            importedBy.map((edge) => (
              <button
                className="detail-list-row detail-link"
                key={edge.id}
                onClick={() => onSelectFile(edge.source)}
                type="button"
              >
                <span className="relationship-arrow">↑</span>
                <code>{edge.source}</code>
              </button>
            ))
          ) : (
            <span className="detail-muted">No files depend on this file.</span>
          )}
        </div>
      </div>
      <div className="detail-section">
        <div className="detail-section-title">Detected behavior</div>
        <div className="detail-section-content">
          {detectedBehavior.length > 0 ? (
            detectedBehavior.map((relationship) => (
              <div className="file-behavior-row" key={relationship.id}>
                <span>{relationship.type.replaceAll("_", " ")}</span>
                <code title={`${relationship.from} → ${relationship.to}`}>
                  {relationship.to.split("::").at(-1)}
                </code>
                <span className="detail-muted">
                  :{relationship.evidence.line}
                </span>
              </div>
            ))
          ) : (
            <span className="detail-muted">No behavior relationships detected.</span>
          )}
        </div>
      </div>
      <div className="detail-section">
        <div className="detail-section-title">Detected flows</div>
        <div className="detail-section-content">
          {detectedFlows.length > 0 ? (
            detectedFlows.map((flow) => (
              <div className="detail-list-row" key={flow.id}>
                <span className="relationship-arrow">↳</span>
                <code>{flow.name}</code>
              </div>
            ))
          ) : (
            <span className="detail-muted">No detected flows include this file.</span>
          )}
        </div>
      </div>
    </aside>
  );
}
