"use client";

import { useMemo } from "react";
import {
  Background,
  BackgroundVariant,
  Controls,
  Handle,
  MarkerType,
  Position,
  ReactFlow,
  type Edge,
  type Node,
  type NodeProps,
} from "@xyflow/react";

import type {
  BehaviorEntity,
  BehaviorFlow,
  BehaviorRelationship,
} from "@/lib/types";

interface FlowNodeData extends Record<string, unknown> {
  entity: BehaviorEntity;
}

interface FlowGraphProps {
  flow: BehaviorFlow;
  onSelectNode: (entity: BehaviorEntity) => void;
  onSelectRelationship: (
    relationship: BehaviorRelationship,
  ) => void;
}

function BehaviorNode({
  data,
}: NodeProps<Node<FlowNodeData, "behavior">>) {
  const entity = data.entity;

  return (
    <div
      className={`behavior-node ${entity.kind}`}
    >
      <Handle
        type="target"
        position={Position.Left}
        className="graph-handle"
      />

      <div className="behavior-node-kind">
        {entity.kind.replaceAll("_", " ")}
      </div>

      <strong title={entity.name}>
        {entity.name}
      </strong>

      {entity.file && (
        <code title={entity.file}>
          {entity.file}
        </code>
      )}

      <Handle
        type="source"
        position={Position.Right}
        className="graph-handle"
      />
    </div>
  );
}

const nodeTypes = {
  behavior: BehaviorNode,
};

const EDGE_LABELS: Record<string, string> = {
  renders: "renders",
  handles_event: "handles",
  calls: "calls",
  http_request: "HTTP",
  matches_route: "matches route",
  handled_by: "handled by",
};

function createFlowElements(
  flow: BehaviorFlow,
) {
  const outgoing = new Map<string, string[]>();

  const incoming = new Map(
    flow.nodes.map((node) => [node.id, 0]),
  );

  for (const relationship of flow.relationships) {
    outgoing.set(relationship.from, [
      ...(outgoing.get(relationship.from) ?? []),
      relationship.to,
    ]);

    incoming.set(
      relationship.to,
      (incoming.get(relationship.to) ?? 0) + 1,
    );
  }

  for (const targets of outgoing.values()) {
    targets.sort();
  }

  const depth = new Map<string, number>();

  const roots = flow.nodes
    .filter(
      (node) =>
        (incoming.get(node.id) ?? 0) === 0,
    )
    .map((node) => node.id)
    .sort();

  const queue = [...roots];

  roots.forEach((id) => depth.set(id, 0));

  for (
    let cursor = 0;
    cursor < queue.length;
    cursor += 1
  ) {
    const source = queue[cursor];
    const nextDepth =
      (depth.get(source) ?? 0) + 1;

    for (const target of outgoing.get(source) ?? []) {
      if (depth.has(target)) continue;

      depth.set(target, nextDepth);
      queue.push(target);
    }
  }

  for (const node of flow.nodes) {
    if (!depth.has(node.id)) {
      depth.set(node.id, 0);
    }
  }

  const rowByDepth = new Map<number, number>();

  const nodes: Node<
    FlowNodeData,
    "behavior"
  >[] = flow.nodes
    .slice()
    .sort(
      (left, right) =>
        (depth.get(left.id) ?? 0) -
          (depth.get(right.id) ?? 0) ||
        left.id.localeCompare(right.id),
    )
    .map((entity) => {
      const layer = depth.get(entity.id) ?? 0;
      const row = rowByDepth.get(layer) ?? 0;

      rowByDepth.set(layer, row + 1);

      return {
        id: entity.id,
        type: "behavior",
        position: {
          x: layer * 300,
          y: row * 145,
        },
        data: { entity },
      };
    });

  const edges: Edge<{
    relationship: BehaviorRelationship;
  }>[] = flow.relationships.map(
    (relationship) => ({
      id: relationship.id,
      source: relationship.from,
      target: relationship.to,
      label:
        relationship.label ??
        EDGE_LABELS[relationship.type] ??
        relationship.type,
      data: {
        relationship,
      },
      type: "smoothstep",
      markerEnd: {
        type: MarkerType.ArrowClosed,
        color: "#718198",
      },
      style: {
        stroke: "#65748a",
        strokeWidth: 1.8,
      },
      labelStyle: {
        fill: "#aeb9c8",
        fontSize: 11,
        fontWeight: 600,
      },
      labelBgStyle: {
        fill: "#0d1219",
        fillOpacity: 0.96,
      },
    }),
  );

  return {
    nodes,
    edges,
  };
}

export function FlowGraph({
  flow,
  onSelectNode,
  onSelectRelationship,
}: FlowGraphProps) {
  const graph = useMemo(
    () => createFlowElements(flow),
    [flow],
  );

  return (
    <div className="flow-canvas">
      <ReactFlow
        nodes={graph.nodes}
        edges={graph.edges}
        nodeTypes={nodeTypes}
        fitView
        fitViewOptions={{
          padding: 0.24,
        }}
        nodesDraggable={false}
        nodesConnectable={false}
        elementsSelectable
        onNodeClick={(_, node) =>
          onSelectNode(node.data.entity)
        }
        onEdgeClick={(_, edge) => {
          const relationship =
            edge.data?.relationship;

          if (relationship) {
            onSelectRelationship(relationship);
          }
        }}
        minZoom={0.2}
        maxZoom={1.4}
      >
        <Background
          color="#202936"
          gap={24}
          size={1}
          variant={BackgroundVariant.Dots}
        />

        <Controls showInteractive={false} />
      </ReactFlow>
    </div>
  );
}