"use client";

import "@xyflow/react/dist/style.css";


import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState, type DragEvent, type ReactNode } from "react";
import {
  Background,
  BaseEdge,
  EdgeLabelRenderer,
  Handle,
  Panel,
  Position,
  ReactFlow,
  applyEdgeChanges,
  applyNodeChanges,
  getSmoothStepPath,
  useReactFlow,
  type Connection,
  type Edge,
  type EdgeChange,
  type EdgeProps,
  type Node,
  type NodeChange,
  type NodeProps,
} from "@xyflow/react";
import { AlertTriangle, Maximize, Minus, Plus, Trash2, X } from "lucide-react";
import { toast } from "sonner";

import { Field } from "@/components/crm/bits";
import { Button } from "@/components/ui/button";
import { NativeSelect, NativeSelectOption } from "@/components/ui/native-select";
import {
  BLOCKS,
  BLOCK_BY_KIND,
  connectionProblem,
  newNodeId,
  pathOrder,
  subjectOf,
  type BlockConfig,
  type BlockKind,
  type Graph,
  type Problem,
} from "@/lib/automation";
import { formatNumber } from "@/lib/format";
import { cn } from "@/lib/utils";
import { BlockSettings } from "./block-settings";
import { BlockSummary } from "./parts";
import { useResolvedTheme } from "@/lib/theme";

type BlockData = { kind: BlockKind; config: BlockConfig; step: number; problems: string[] };
type BlockNode = Node<BlockData, "block">;
type FlowEdge = Edge<Record<string, never>, "removable">;

const DRAG_TYPE = "application/x-crm-block";
const ROW = 150;

function toFlow(graph: Graph): { nodes: BlockNode[]; edges: FlowEdge[] } {
  return {
    nodes: graph.nodes.map((n) => ({
      id: n.id,
      type: "block",
      position: n.position ?? { x: 0, y: 0 },
      data: { kind: n.kind, config: n.config ?? {}, step: -1, problems: [] },
    })),
    edges: graph.edges.map((e) => ({ id: e.id, source: e.source, target: e.target, type: "removable" })),
  };
}

function toGraph(nodes: BlockNode[], edges: FlowEdge[]): Graph {
  return {
    nodes: nodes.map((n) => ({
      id: n.id,
      kind: n.data.kind,
      config: n.data.config,
      position: { x: Math.round(n.position.x), y: Math.round(n.position.y) },
    })),
    edges: edges.map((e) => ({ id: e.id, source: e.source, target: e.target })),
  };
}

// -- canvas pieces -------------------------------------------------------------------

function BlockCard({ data, selected }: NodeProps<BlockNode>) {
  const def = BLOCK_BY_KIND[data.kind];
  const Icon = def.icon;
  const invalid = data.problems.length > 0;
  return (
    <div
      dir="rtl"
      className={cn(
        "w-60 rounded-xl border bg-card p-3 text-start shadow-sm transition-shadow",
        selected && "ring-2 ring-primary",
        invalid && "border-destructive",
      )}
    >
      {data.kind !== "trigger" ? (
        <Handle type="target" position={Position.Top} className="!size-3 !border-2 !border-card !bg-primary" />
      ) : null}
      <div className="flex items-center gap-2">
        <span className={cn("grid size-7 shrink-0 place-items-center rounded-md", def.tone)}>
          <Icon className="size-4" aria-hidden />
        </span>
        <span className="text-sm font-semibold">{def.label}</span>
        <span className="ms-auto text-[11px] text-muted-foreground">
          {data.kind === "trigger" ? "شروع" : data.step > 0 ? `قدم ${formatNumber(data.step)}` : "جدا از مسیر"}
        </span>
      </div>
      <div className="mt-2">
        <BlockSummary kind={data.kind} config={data.config} />
      </div>
      {invalid ? (
        <ul className="mt-2 space-y-1 border-t pt-2 text-[11px] leading-4 text-destructive">
          {data.problems.map((p) => (
            <li key={p} className="flex gap-1">
              <AlertTriangle className="mt-px size-3 shrink-0" aria-hidden />
              {p}
            </li>
          ))}
        </ul>
      ) : null}
      <Handle type="source" position={Position.Bottom} className="!size-3 !border-2 !border-card !bg-primary" />
    </div>
  );
}

function RemovableEdge({ id, sourceX, sourceY, targetX, targetY, sourcePosition, targetPosition, selected }: EdgeProps<FlowEdge>) {
  const { deleteElements } = useReactFlow();
  const [path, labelX, labelY] = getSmoothStepPath({ sourceX, sourceY, targetX, targetY, sourcePosition, targetPosition });
  return (
    <>
      <BaseEdge
        id={id}
        path={path}
        markerEnd="url(#crm-arrow)"
        style={{ strokeWidth: 2, stroke: selected ? "var(--primary)" : "var(--muted-foreground)" }}
      />
      <EdgeLabelRenderer>
        <button
          type="button"
          aria-label="حذف اتصال"
          title="حذف اتصال"
          onClick={() => void deleteElements({ edges: [{ id }] })}
          className="nodrag nopan pointer-events-auto absolute grid size-5 place-items-center rounded-full border bg-card text-muted-foreground shadow-sm hover:text-destructive"
          style={{ transform: `translate(-50%, -50%) translate(${labelX}px, ${labelY}px)` }}
        >
          <X className="size-3" />
        </button>
      </EdgeLabelRenderer>
    </>
  );
}

const nodeTypes = { block: BlockCard };
const edgeTypes = { removable: RemovableEdge };

function ZoomControls() {
  const { zoomIn, zoomOut, fitView } = useReactFlow();
  return (
    <Panel position="bottom-left" className="flex gap-1 rounded-lg border bg-card p-1 shadow-sm">
      <Button variant="ghost" size="icon-sm" aria-label="بزرگ‌نمایی" title="بزرگ‌نمایی" onClick={() => void zoomIn()}>
        <Plus />
      </Button>
      <Button variant="ghost" size="icon-sm" aria-label="کوچک‌نمایی" title="کوچک‌نمایی" onClick={() => void zoomOut()}>
        <Minus />
      </Button>
      <Button variant="ghost" size="icon-sm" aria-label="نمایش همه بلوک‌ها" title="نمایش همه بلوک‌ها" onClick={() => void fitView({ padding: 0.2 })}>
        <Maximize />
      </Button>
    </Panel>
  );
}

const ARIA_LABELS = {
  "node.a11yDescription.default": "برای انتخاب Enter یا فاصله را بزنید؛ با کلیدهای جهت جابه‌جا و با Delete حذف می‌شود.",
  "node.a11yDescription.keyboardDisabled": "برای انتخاب Enter یا فاصله را بزنید.",
  "node.a11yDescription.ariaLiveMessage": ({ x, y }: { direction: string; x: number; y: number }) =>
    `بلوک به موقعیت ${Math.round(x)}، ${Math.round(y)} رفت`,
  "edge.a11yDescription.default": "اتصال؛ برای حذف Delete را بزنید.",
  "controls.ariaLabel": "ابزار نمایش",
  "controls.zoomIn.ariaLabel": "بزرگ‌نمایی",
  "controls.zoomOut.ariaLabel": "کوچک‌نمایی",
  "controls.fitView.ariaLabel": "نمایش همه",
  "controls.interactive.ariaLabel": "قفل",
  "minimap.ariaLabel": "نقشه کوچک",
  "handle.ariaLabel": "نقطه اتصال",
};

// -- builder -------------------------------------------------------------------------

/** The visual builder (spec 4.6): blocks are dragged from the palette or added with
 * buttons, connected by their handles or from the settings panel, and execution order
 * always comes from the connections. */
export function Builder({
  initial,
  problems,
  onChange,
  ruleSettings,
}: {
  initial: Graph;
  problems: Problem[];
  onChange: (graph: Graph) => void;
  ruleSettings: ReactNode;
}) {
  const colorMode = useResolvedTheme();
  const flow = useReactFlow();
  const [{ nodes, edges }, setFlow] = useState(() => toFlow(initial));
  const [revision, setRevision] = useState(0);
  const latest = useRef({ nodes, edges });
  useLayoutEffect(() => {
    latest.current = { nodes, edges };
  }, [nodes, edges]);

  const bump = () => setRevision((r) => r + 1);
  useEffect(() => {
    if (revision > 0) onChange(toGraph(latest.current.nodes, latest.current.edges));
  }, [revision, onChange]);

  const graph = useMemo(() => toGraph(nodes, edges), [nodes, edges]);
  const order = useMemo(() => pathOrder(graph), [graph]);
  const problemsByNode = useMemo(() => {
    const map = new Map<string, string[]>();
    for (const p of problems) if (p.node_id) map.set(p.node_id, [...(map.get(p.node_id) ?? []), p.message]);
    return map;
  }, [problems]);
  const display = useMemo(
    () =>
      nodes.map((n) => ({
        ...n,
        data: { ...n.data, step: order.indexOf(n.id), problems: problemsByNode.get(n.id) ?? [] },
      })),
    [nodes, order, problemsByNode],
  );
  const selected = nodes.find((n) => n.selected) ?? null;
  const trigger = nodes.find((n) => n.data.kind === "trigger");
  const subject = subjectOf(trigger?.data.config);
  const general = problems.filter((p) => !p.node_id);

  const onNodesChange = useCallback((changes: NodeChange<BlockNode>[]) => {
    setFlow((f) => ({ ...f, nodes: applyNodeChanges(changes, f.nodes) }));
    if (changes.some((c) => c.type === "position" || c.type === "remove" || c.type === "add")) bump();
  }, []);

  const onEdgesChange = useCallback((changes: EdgeChange<FlowEdge>[]) => {
    setFlow((f) => ({ ...f, edges: applyEdgeChanges(changes, f.edges) }));
    if (changes.some((c) => c.type === "remove" || c.type === "add")) bump();
  }, []);

  /** Removing a block in the middle keeps the path joined: its neighbours are connected. */
  const onNodesDelete = useCallback((deleted: BlockNode[]) => {
    const gone = new Set(deleted.map((n) => n.id));
    // React Flow removes the connected edges before calling this, so read the edges as
    // they were when the deletion started (the state has not re-rendered yet).
    const before = latest.current.edges;
    const bridges: FlowEdge[] = [];
    for (const node of deleted) {
      const from = before.find((e) => e.target === node.id && !gone.has(e.source))?.source;
      let to = before.find((e) => e.source === node.id)?.target;
      while (to && gone.has(to)) to = before.find((e) => e.source === to)?.target;
      if (from && to) bridges.push({ id: `e-${from}-${to}`, source: from, target: to, type: "removable" });
    }
    setFlow((f) => ({
      ...f,
      edges: [...f.edges.filter((e) => !gone.has(e.source) && !gone.has(e.target)), ...bridges],
    }));
    bump();
  }, []);

  const isValidConnection = useCallback(
    (c: Connection | Edge) => connectionProblem(toGraph(latest.current.nodes, latest.current.edges), c.source, c.target) === null,
    [],
  );

  const onConnect = useCallback((c: Connection) => {
    const current = toGraph(latest.current.nodes, latest.current.edges);
    const problem = connectionProblem(current, c.source, c.target);
    if (problem) {
      toast.error(problem);
      return;
    }
    setFlow((f) => ({
      ...f,
      edges: [...f.edges, { id: `e-${c.source}-${c.target}`, source: c.source, target: c.target, type: "removable" }],
    }));
    bump();
  }, []);

  function select(id: string) {
    setFlow((f) => ({ ...f, nodes: f.nodes.map((n) => ({ ...n, selected: n.id === id })) }));
  }

  function create(kind: BlockKind, position?: { x: number; y: number }) {
    if (kind === "trigger" && trigger) {
      toast.error("هر اتوماسیون فقط یک رویداد شروع دارد.");
      return;
    }
    const { nodes: ns, edges: es } = latest.current;
    const id = newNodeId(toGraph(ns, es).nodes);
    const node: BlockNode = {
      id,
      type: "block",
      position: position ?? { x: 0, y: 0 },
      data: { kind, config: BLOCK_BY_KIND[kind].defaults(), step: -1, problems: [] },
      selected: true,
    };
    let nextNodes: BlockNode[] = ns.map((n) => ({ ...n, selected: false }));
    let nextEdges = es;

    if (!position) {
      // Button or keyboard: insert after the selected block, or at the end of the path.
      const path = pathOrder(toGraph(ns, es));
      const anchor = ns.find((n) => n.selected) ?? ns.find((n) => n.id === path[path.length - 1]);
      if (kind === "trigger" || !anchor) {
        const top = ns.length ? Math.min(...ns.map((n) => n.position.y)) - ROW : 0;
        node.position = { x: ns[0]?.position.x ?? 0, y: kind === "trigger" ? top : Math.max(0, ...ns.map((n) => n.position.y + ROW)) };
        if (kind === "trigger" && ns.length) {
          // Connect the new start event to the first block that has no input.
          const first = ns.find((n) => !es.some((e) => e.target === n.id));
          if (first) nextEdges = [...es, { id: `e-${id}-${first.id}`, source: id, target: first.id, type: "removable" }];
        }
      } else {
        node.position = { x: anchor.position.x, y: anchor.position.y + ROW };
        const out = es.find((e) => e.source === anchor.id);
        nextEdges = es.filter((e) => e !== out);
        nextEdges.push({ id: `e-${anchor.id}-${id}`, source: anchor.id, target: id, type: "removable" });
        if (out) {
          nextEdges.push({ id: `e-${id}-${out.target}`, source: id, target: out.target, type: "removable" });
          // Make room: everything after the anchor on the path moves down one row.
          const after = new Set(path.slice(path.indexOf(anchor.id) + 1));
          nextNodes = nextNodes.map((n) => (after.has(n.id) ? { ...n, position: { ...n.position, y: n.position.y + ROW } } : n));
        }
      }
    }
    nextNodes = [...nextNodes, node];
    setFlow({ nodes: nextNodes, edges: nextEdges });
    bump();
    if (!position) window.requestAnimationFrame(() => void flow.fitView({ nodes: [{ id }], duration: 200, maxZoom: 1 }));
  }

  function onDrop(event: DragEvent) {
    event.preventDefault();
    const kind = event.dataTransfer.getData(DRAG_TYPE) as BlockKind;
    if (!kind || !BLOCK_BY_KIND[kind]) return;
    const point = flow.screenToFlowPosition({ x: event.clientX, y: event.clientY });
    create(kind, { x: point.x - 120, y: point.y - 30 });
  }

  function updateConfig(id: string, config: BlockConfig) {
    setFlow((f) => ({ ...f, nodes: f.nodes.map((n) => (n.id === id ? { ...n, data: { ...n.data, config } } : n)) }));
    bump();
  }

  function setNext(id: string, target: string) {
    setFlow((f) => {
      const edges = f.edges.filter((e) => e.source !== id);
      if (target) edges.push({ id: `e-${id}-${target}`, source: id, target, type: "removable" });
      return { ...f, edges };
    });
    bump();
  }

  const nextOptions = selected
    ? nodes.filter((n) => {
        if (n.id === selected.id) return false;
        const withoutOwn = toGraph(nodes, edges.filter((e) => e.source !== selected.id));
        return connectionProblem(withoutOwn, selected.id, n.id) === null;
      })
    : [];
  const currentNext = selected ? edges.find((e) => e.source === selected.id)?.target ?? "" : "";

  return (
    <div className="grid gap-4 lg:h-[calc(100svh-15rem)] lg:min-h-[34rem] lg:grid-cols-[13rem_minmax(0,1fr)_20rem]">
      {/* palette */}
      <section aria-label="بلوک‌ها" className="space-y-2 rounded-xl border bg-card p-3 lg:overflow-y-auto">
        <h2 className="text-sm font-semibold">بلوک‌ها</h2>
        <p className="text-xs leading-5 text-muted-foreground">
          بلوک را به فضای طراحی بکشید، یا روی آن بزنید تا بعد از بلوک انتخاب‌شده اضافه و وصل شود.
        </p>
        <ul className="grid grid-cols-2 gap-2 lg:grid-cols-1">
          {BLOCKS.map((block) => {
            const disabled = block.kind === "trigger" && Boolean(trigger);
            return (
              <li key={block.kind}>
                <button
                  type="button"
                  draggable={!disabled}
                  disabled={disabled}
                  onDragStart={(e) => {
                    e.dataTransfer.setData(DRAG_TYPE, block.kind);
                    e.dataTransfer.effectAllowed = "move";
                  }}
                  onClick={() => create(block.kind)}
                  title={disabled ? "رویداد شروع قبلاً اضافه شده است." : block.hint}
                  className="flex w-full cursor-grab items-center gap-2 rounded-lg border bg-background p-2 text-start text-sm hover:bg-muted/60 focus-visible:outline-2 focus-visible:outline-ring active:cursor-grabbing disabled:cursor-not-allowed disabled:opacity-50"
                >
                  <span className={cn("grid size-7 shrink-0 place-items-center rounded-md", block.tone)}>
                    <block.icon className="size-4" aria-hidden />
                  </span>
                  <span className="min-w-0">
                    <span className="block font-medium">{block.label}</span>
                    <span className="block truncate text-[11px] text-muted-foreground">{block.hint}</span>
                  </span>
                </button>
              </li>
            );
          })}
        </ul>
      </section>

      {/* canvas */}
      <section aria-label="فضای طراحی" className="relative h-[60svh] overflow-hidden rounded-xl border bg-muted/30 lg:h-auto">
        {general.length ? (
          <div role="alert" className="absolute inset-x-3 top-3 z-10 rounded-lg border border-destructive/40 bg-card px-3 py-2 text-sm text-destructive shadow-sm" dir="rtl">
            {general.map((p) => (
              <p key={p.message}>{p.message}</p>
            ))}
          </div>
        ) : null}
        <div dir="ltr" className="size-full" onDragOver={(e) => { e.preventDefault(); e.dataTransfer.dropEffect = "move"; }} onDrop={onDrop}>
          <svg className="absolute size-0" aria-hidden>
            <defs>
              <marker id="crm-arrow" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
                <path d="M0 0 10 5 0 10z" fill="var(--muted-foreground)" />
              </marker>
            </defs>
          </svg>
          <ReactFlow<BlockNode, FlowEdge>
            nodes={display}
            edges={edges}
            nodeTypes={nodeTypes}
            edgeTypes={edgeTypes}
            onNodesChange={onNodesChange}
            onEdgesChange={onEdgesChange}
            onNodesDelete={onNodesDelete}
            onConnect={onConnect}
            isValidConnection={isValidConnection}
            deleteKeyCode={["Delete", "Backspace"]}
            fitView
            fitViewOptions={{ padding: 0.2, maxZoom: 1 }}
            minZoom={0.3}
            maxZoom={1.5}
            proOptions={{ hideAttribution: true }}
            ariaLabelConfig={ARIA_LABELS}
            colorMode={colorMode}
          >
            <Background gap={20} size={1} />
            <ZoomControls />
          </ReactFlow>
        </div>
        {nodes.length === 0 ? (
          <div className="pointer-events-none absolute inset-0 grid place-items-center p-6 text-center text-sm text-muted-foreground" dir="rtl">
            با افزودن یک بلوک «رویداد» شروع کنید.
          </div>
        ) : null}
      </section>

      {/* settings */}
      <section aria-label="تنظیمات" className="space-y-4 rounded-xl border bg-card p-4 lg:overflow-y-auto">
        {selected ? (
          <>
            <div className="flex items-center gap-2">
              {(() => {
                const def = BLOCK_BY_KIND[selected.data.kind];
                return (
                  <>
                    <span className={cn("grid size-8 place-items-center rounded-md", def.tone)}>
                      <def.icon className="size-4" aria-hidden />
                    </span>
                    <h2 className="font-semibold">{def.label}</h2>
                  </>
                );
              })()}
              <Button variant="ghost" size="icon-sm" className="ms-auto" aria-label="بستن تنظیمات بلوک" onClick={() => select("")}>
                <X />
              </Button>
            </div>
            {problemsByNode.get(selected.id)?.length ? (
              <ul role="alert" className="space-y-1 rounded-md bg-destructive/10 px-3 py-2 text-xs leading-5 text-destructive">
                {problemsByNode.get(selected.id)!.map((p) => (
                  <li key={p}>{p}</li>
                ))}
              </ul>
            ) : null}
            <BlockSettings
              key={selected.id}
              nodeId={selected.id}
              kind={selected.data.kind}
              config={selected.data.config}
              subject={subject}
              onChange={(config) => updateConfig(selected.id, config)}
            />
            <Field label="بلوک بعدی" htmlFor="next-block" hint="ترتیب اجرا فقط از اتصال‌ها تعیین می‌شود.">
              <NativeSelect id="next-block" className="w-full" value={currentNext} onChange={(e) => setNext(selected.id, e.target.value)}>
                <NativeSelectOption value="">بدون اتصال (پایان مسیر)</NativeSelectOption>
                {nextOptions.map((n) => (
                  <NativeSelectOption key={n.id} value={n.id}>
                    {BLOCK_BY_KIND[n.data.kind].label} ({n.id})
                  </NativeSelectOption>
                ))}
              </NativeSelect>
            </Field>
            <Button
              variant="outline"
              className="w-full text-destructive"
              onClick={() => void flow.deleteElements({ nodes: [{ id: selected.id }] })}
            >
              <Trash2 aria-hidden />
              حذف بلوک
            </Button>
          </>
        ) : (
          ruleSettings
        )}
      </section>
    </div>
  );
}
