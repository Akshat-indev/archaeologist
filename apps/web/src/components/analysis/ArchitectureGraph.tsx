"use client";

import { useMemo } from "react";
import {
  Background,
  BackgroundVariant,
  Controls,
  Handle,
  MarkerType,
  MiniMap,
  Position,
  ReactFlow,
  type Edge,
  type Node,
  type NodeProps,
} from "@xyflow/react";

import type {
  AnalysisResponse,
  ArchitectureEdge,
  ArchitectureNode,
} from "@/lib/types";

interface FileNodeData extends Record<string, unknown> {
  file: ArchitectureNode;
}

interface ArchitectureGraphProps {
  analysis: AnalysisResponse;
  compact?: boolean;
  search?: string;
  hideDisconnected?: boolean;
  visibleNodeLimit?: number;
  visibleEdgeLimit?: number;
  onSelectNode?: (node: ArchitectureNode) => void;
  onSelectEdge?: (edge: ArchitectureEdge) => void;
}

function FileNode({
  data,
}: NodeProps<Node<FileNodeData, "fileCard">>) {
  const file = data.file;

  return (
    <div className="graph-node">
      <Handle
        type="target"
        position={Position.Left}
        className="graph-handle"
      />

      <div className="graph-node-header">
        <span className="graph-node-icon">
          {file.language.slice(0, 1)}
        </span>

        <div className="graph-node-title">
          <strong title={file.name}>{file.name}</strong>
          <span title={file.path}>{file.path}</span>
        </div>

        <span className="graph-node-language">
          {file.language}
        </span>
      </div>

      <div className="graph-node-footer">
        <span>
          {file.imports_count} imports
        </span>

        <span className="graph-node-separator">·</span>

        <span>
          {file.imported_by_count} dependents
        </span>
      </div>

      <Handle
        type="source"
        position={Position.Right}
        className="graph-handle"
      />
    </div>
  );
}

const nodeTypes = {
  fileCard: FileNode,
};

export function selectArchitectureNodes(
  analysis: AnalysisResponse,
  search = "",
  hideDisconnected = false,
  visibleNodeLimit = Number.POSITIVE_INFINITY,
): ArchitectureNode[] {
  const query = search.trim().toLowerCase();

  const matches = analysis.architecture.nodes.filter((node) => {
    const matchesQuery =
      !query ||
      node.path.toLowerCase().includes(query) ||
      node.name.toLowerCase().includes(query);

    const isConnected =
      node.imports_count + node.imported_by_count > 0;

    return (
      matchesQuery &&
      (!hideDisconnected || isConnected)
    );
  });

  if (matches.length <= visibleNodeLimit) {
    return matches;
  }

  return matches
    .slice()
    .sort(
      (left, right) =>
        right.imports_count +
          right.imported_by_count -
          (left.imports_count +
            left.imported_by_count) ||
        left.path.localeCompare(right.path),
    )
    .slice(0, visibleNodeLimit)
    .sort((left, right) =>
      left.path.localeCompare(right.path),
    );
}

function createGraph(
  analysis: AnalysisResponse,
  visibleNodes: ArchitectureNode[],
  compact: boolean,
  visibleEdgeLimit: number,
) {
  const visibleIds = new Set(
    visibleNodes.map((node) => node.id),
  );

  const architecture = {
    nodes: visibleNodes,
    edges: analysis.architecture.edges.filter(
      (edge) =>
        visibleIds.has(edge.source) &&
        visibleIds.has(edge.target),
    ),
  };

  const outgoing = new Map<string, string[]>();

  const incomingCounts = new Map(
    architecture.nodes.map((node) => [node.id, 0]),
  );

  for (const edge of architecture.edges) {
    outgoing.set(edge.source, [
      ...(outgoing.get(edge.source) ?? []),
      edge.target,
    ]);

    incomingCounts.set(
      edge.target,
      (incomingCounts.get(edge.target) ?? 0) + 1,
    );
  }

  for (const targets of outgoing.values()) {
    targets.sort();
  }

  const depths = new Map<string, number>();

  const assignDepths = (root: string) => {
    if (depths.has(root)) return;

    const queue = [root];
    depths.set(root, 0);

    for (
      let cursor = 0;
      cursor < queue.length;
      cursor += 1
    ) {
      const source = queue[cursor];
      const depth = depths.get(source) ?? 0;

      for (const target of outgoing.get(source) ?? []) {
        if (depths.has(target)) continue;

        depths.set(target, depth + 1);
        queue.push(target);
      }
    }
  };

  architecture.nodes
    .filter(
      (node) =>
        (incomingCounts.get(node.id) ?? 0) === 0,
    )
    .map((node) => node.id)
    .sort()
    .forEach(assignDepths);

  architecture.nodes
    .map((node) => node.id)
    .sort()
    .forEach(assignDepths);

  const rowsAtDepth = new Map<number, number>();

  const nodes: Node<FileNodeData, "fileCard">[] =
    architecture.nodes
      .slice()
      .sort(
        (left, right) =>
          (depths.get(left.id) ?? 0) -
            (depths.get(right.id) ?? 0) ||
          left.id.localeCompare(right.id),
      )
      .map((file) => {
        const depth = depths.get(file.id) ?? 0;
        const row = rowsAtDepth.get(depth) ?? 0;

        rowsAtDepth.set(depth, row + 1);

        return {
          id: file.id,
          type: "fileCard",
          position: {
            x: depth * 360,
            y: row * 150,
          },
          data: { file },
        };
      });

  const edges: Edge<{
    architecture: ArchitectureEdge;
  }>[] = architecture.edges
    .slice(0, visibleEdgeLimit)
    .map((edge) => ({
      id: edge.id,
      source: edge.source,
      target: edge.target,
      type: "smoothstep",
      markerEnd: {
        type: MarkerType.ArrowClosed,
        color: "#64748b",
      },
      data: {
        architecture: edge,
      },
      style: {
        stroke: "#526174",
        strokeWidth: compact ? 1.5 : 1.8,
      },
    }));

  return {
    nodes,
    edges,
  };
}

export function ArchitectureGraph({
  analysis,
  compact = false,
  search,
  hideDisconnected = false,
  visibleNodeLimit,
  visibleEdgeLimit = Number.POSITIVE_INFINITY,
  onSelectNode,
  onSelectEdge,
}: ArchitectureGraphProps) {
  const visibleNodes = useMemo(
    () =>
      selectArchitectureNodes(
        analysis,
        search,
        hideDisconnected,
        visibleNodeLimit,
      ),
    [
      analysis,
      hideDisconnected,
      search,
      visibleNodeLimit,
    ],
  );

  const graph = useMemo(
    () =>
      createGraph(
        analysis,
        visibleNodes,
        compact,
        visibleEdgeLimit,
      ),
    [
      analysis,
      compact,
      visibleEdgeLimit,
      visibleNodes,
    ],
  );

  return (
    <div
      className={`architecture-canvas${
        compact ? " compact" : ""
      }`}
    >
      <ReactFlow
        nodes={graph.nodes}
        edges={graph.edges}
        nodeTypes={nodeTypes}
        fitView
        fitViewOptions={{
          padding: compact ? 0.18 : 0.28,
        }}
        nodesDraggable={false}
        nodesConnectable={false}
        elementsSelectable
        onNodeClick={(_, node) =>
          onSelectNode?.(node.data.file)
        }
        onEdgeClick={(_, edge) => {
          const data = edge.data as
            | { architecture: ArchitectureEdge }
            | undefined;

          if (data) {
            onSelectEdge?.(data.architecture);
          }
        }}
        minZoom={0.25}
        maxZoom={1.4}
      >
        <Background
          color="#202936"
          gap={24}
          size={1}
          variant={BackgroundVariant.Dots}
        />

        {!compact && (
          <>
            <Controls showInteractive={false} />

            <MiniMap
              pannable
              zoomable
              nodeColor="#53657c"
              maskColor="rgba(7, 10, 15, 0.8)"
            />
          </>
        )}
      </ReactFlow>
    </div>
  );
}