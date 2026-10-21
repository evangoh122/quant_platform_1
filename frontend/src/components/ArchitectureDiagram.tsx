/**
 * Inline, dependency-free architecture diagram for the Architecture & Tests
 * screen.
 *
 * Visual language follows the Cocoon architecture-diagram skill
 * (`.agentlogs/skills/architecture-diagram/SKILL.md`): one semantic colour per
 * component type, a 40 px minimum vertical gap between stacked components,
 * connection arrows painted before the boxes, and a legend placed below every
 * boundary. Accessibility follows the Apple HIG
 * (`.agentlogs/skills/apple-design/references/hig/accessibility.md` › Vision):
 * the SVG is a single labelled image with a title and description, and the
 * surrounding screen repeats the flow as an ordered list so no information is
 * conveyed by colour alone.
 *
 * Components are PLANNED unless a real module/table backs them: planned nodes
 * use a dashed outline and are labelled "planned" so the diagram never implies
 * a perps pipeline that is deployed.
 */

export type ComponentKind =
  | 'frontend'
  | 'backend'
  | 'database'
  | 'cloud'
  | 'security'
  | 'bus'
  | 'external'
  | 'planned';

export interface DiagramNode {
  id: string;
  label: string;
  sublabel?: string;
  kind: ComponentKind;
  x: number;
  y: number;
  width: number;
  height: number;
}

export interface DiagramEdge {
  from: string;
  to: string;
  /** Planned edges are dashed; they never claim a production path. */
  planned?: boolean;
}

export interface DiagramBoundary {
  id: string;
  label: string;
  x: number;
  y: number;
  width: number;
  height: number;
  planned?: boolean;
}

/** Semantic palette from the architecture-diagram skill (dark theme).
 *  `security` stays in the type system for dashed security groups; no node
 *  uses it today, so the legend only lists kinds that are on the canvas. */
export const KIND_STYLES: Record<ComponentKind, { fill: string; stroke: string }> = {
  frontend: { fill: 'rgba(8, 51, 68, 0.4)', stroke: '#22d3ee' },
  backend: { fill: 'rgba(6, 78, 59, 0.4)', stroke: '#34d399' },
  database: { fill: 'rgba(76, 29, 149, 0.4)', stroke: '#a78bfa' },
  cloud: { fill: 'rgba(120, 53, 15, 0.3)', stroke: '#fbbf24' },
  security: { fill: 'rgba(136, 19, 55, 0.4)', stroke: '#fb7185' },
  bus: { fill: 'rgba(251, 146, 60, 0.3)', stroke: '#fb923c' },
  external: { fill: 'rgba(30, 41, 59, 0.5)', stroke: '#94a3b8' },
  planned: { fill: 'rgba(30, 41, 59, 0.35)', stroke: '#94a3b8' },
};

export const KIND_LABELS: Record<ComponentKind, string> = {
  frontend: 'Frontend',
  backend: 'Backend',
  database: 'Database',
  cloud: 'Cloud / compute',
  security: 'Security',
  bus: 'Message bus',
  external: 'External source',
  planned: 'Planned (not built)',
};

export const DIAGRAM_WIDTH = 1160;
export const DIAGRAM_HEIGHT = 960;

const NODE_WIDTH = 220;
const NODE_HEIGHT = 64;
const COLUMN_1 = 48;
const COLUMN_2 = 328;
const COLUMN_3 = 608;
const COLUMN_4 = 888;

/**
 * Built components only. Planned perps nodes live in a separate dashed
 * boundary below and never appear in the page's PIPELINE_TECH_NODES list.
 */
export const NODES: DiagramNode[] = [
  {
    id: 'upstream',
    label: 'Upstream providers',
    sublabel: 'Massive · SEC · CFTC · FRED',
    kind: 'external',
    x: COLUMN_1,
    y: 96,
    width: NODE_WIDTH,
    height: NODE_HEIGHT,
  },
  {
    id: 'spark',
    label: 'Spark',
    sublabel: 'batch + feature jobs',
    kind: 'cloud',
    x: COLUMN_2,
    y: 96,
    width: NODE_WIDTH,
    height: NODE_HEIGHT,
  },
  {
    id: 'delta',
    label: 'Delta Lake',
    sublabel: 'bronze / silver / gold',
    kind: 'database',
    x: COLUMN_3,
    y: 96,
    width: NODE_WIDTH,
    height: NODE_HEIGHT,
  },
  {
    id: 'react',
    label: 'React',
    sublabel: 'research UI',
    kind: 'frontend',
    x: COLUMN_1,
    y: 256,
    width: NODE_WIDTH,
    height: NODE_HEIGHT,
  },
  {
    id: 'fastapi',
    label: 'FastAPI',
    sublabel: 'governed API',
    kind: 'backend',
    x: COLUMN_2,
    y: 256,
    width: NODE_WIDTH,
    height: NODE_HEIGHT,
  },
  {
    id: 'agent',
    label: 'AI agent',
    sublabel: 'typed tools · allowlist',
    kind: 'backend',
    x: COLUMN_3,
    y: 256,
    width: NODE_WIDTH,
    height: NODE_HEIGHT,
  },
  {
    id: 'lakebase',
    label: 'Lakebase',
    sublabel: 'writes + audit trail',
    kind: 'database',
    x: COLUMN_1,
    y: 412,
    width: NODE_WIDTH,
    height: NODE_HEIGHT,
  },
  {
    id: 'outbox',
    label: 'analytics_outbox',
    sublabel: 'event bus table',
    kind: 'bus',
    x: COLUMN_2,
    y: 412,
    width: NODE_WIDTH,
    height: NODE_HEIGHT,
  },
  {
    id: 'spark_analytics',
    label: 'Spark analytics',
    sublabel: 'scheduled refresh',
    kind: 'cloud',
    x: COLUMN_3,
    y: 412,
    width: NODE_WIDTH,
    height: NODE_HEIGHT,
  },
  {
    id: 'delta_analytics',
    label: 'Delta analytics',
    sublabel: 'materialised views',
    kind: 'database',
    x: COLUMN_4,
    y: 412,
    width: NODE_WIDTH,
    height: NODE_HEIGHT,
  },
  {
    id: 'mlflow',
    label: 'MLflow',
    sublabel: 'run comparison',
    kind: 'cloud',
    x: COLUMN_4,
    y: 516,
    width: NODE_WIDTH,
    height: NODE_HEIGHT,
  },
  {
    id: 'hyperliquid',
    label: 'Hyperliquid HIP-3 API',
    sublabel: 'perp funding + marks',
    kind: 'planned',
    x: COLUMN_1,
    y: 700,
    width: NODE_WIDTH,
    height: NODE_HEIGHT,
  },
  {
    id: 'bronze_perps',
    label: 'bronze_perps_*',
    sublabel: 'raw perp ingestion',
    kind: 'planned',
    x: COLUMN_2,
    y: 700,
    width: NODE_WIDTH,
    height: NODE_HEIGHT,
  },
  {
    id: 'silver_perp',
    label: 'silver_perp_*',
    sublabel: 'funding + basis features',
    kind: 'planned',
    x: COLUMN_3,
    y: 700,
    width: NODE_WIDTH,
    height: NODE_HEIGHT,
  },
  {
    id: 'gold_weekend',
    label: 'gold_weekend_perp_features',
    sublabel: 'weekend signal features',
    kind: 'planned',
    x: COLUMN_4,
    y: 700,
    width: NODE_WIDTH,
    height: NODE_HEIGHT,
  },
  {
    id: 'binance',
    label: 'Binance futures archives',
    sublabel: 'historical funding + OI',
    kind: 'planned',
    x: COLUMN_1,
    y: 804,
    width: NODE_WIDTH,
    height: NODE_HEIGHT,
  },
];

/**
 * Edges are drawn before the node boxes so arrowheads sit behind component
 * fills, as the skill requires.
 */
export const EDGES: DiagramEdge[] = [
  { from: 'upstream', to: 'spark' },
  { from: 'spark', to: 'delta' },
  { from: 'delta', to: 'fastapi' },
  { from: 'fastapi', to: 'react' },
  { from: 'fastapi', to: 'agent' },
  { from: 'agent', to: 'lakebase' },
  { from: 'lakebase', to: 'outbox' },
  { from: 'outbox', to: 'spark_analytics' },
  { from: 'spark_analytics', to: 'delta_analytics' },
  { from: 'hyperliquid', to: 'bronze_perps', planned: true },
  { from: 'binance', to: 'bronze_perps', planned: true },
  { from: 'bronze_perps', to: 'silver_perp', planned: true },
  { from: 'silver_perp', to: 'gold_weekend', planned: true },
  { from: 'gold_weekend', to: 'mlflow', planned: true },
];

export const BOUNDARIES: DiagramBoundary[] = [
  {
    id: 'sources',
    label: 'SOURCES & DELTA LAKEHOUSE',
    x: 24,
    y: 64,
    width: 1108,
    height: 120,
  },
  {
    id: 'application',
    label: 'APPLICATION & AI',
    x: 24,
    y: 224,
    width: 1108,
    height: 120,
  },
  {
    id: 'state',
    label: 'STATE, MODELS & ANALYTICS',
    x: 24,
    y: 384,
    width: 1108,
    height: 236,
  },
  {
    id: 'perps',
    label: 'PLANNED PERPS PIPELINE — NOT IN PRODUCTION',
    x: 24,
    y: 660,
    width: 1108,
    height: 244,
    planned: true,
  },
];

/** Legend sits below the lowest boundary (skill: >= 20 px clear of it). */
export const LEGEND_Y = 928;

const LEGEND_KINDS: ComponentKind[] = [
  'frontend',
  'backend',
  'database',
  'cloud',
  'bus',
  'external',
  'planned',
];

const TITLE_ID = 'architecture-diagram-title';
const DESC_ID = 'architecture-diagram-description';
const GRID_ID = 'architecture-diagram-grid';
const ARROW_ID = 'architecture-diagram-arrow';

const DIAGRAM_TITLE = 'Architecture diagram: built platform and planned perps pipeline';

const DIAGRAM_DESCRIPTION =
  'Data flows from external providers (Massive, SEC, CFTC, FRED) through Spark into Delta Lake bronze, silver and gold tables. FastAPI serves the React research UI and the AI agent, which uses typed tools. The agent writes research notes and audit records to Lakebase, which feeds analytics_outbox, Spark analytics and Delta analytics. MLflow records model runs. A separate dashed section shows the planned perps pipeline — Hyperliquid HIP-3 API and Binance futures archives into bronze_perps_*, silver_perp_* and gold_weekend_perp_features for weekend signal comparison in MLflow. Planned components are not deployed to production.';

function nodeById(id: string): DiagramNode {
  const node = NODES.find((candidate) => candidate.id === id);
  if (!node) throw new Error(`Unknown architecture node: ${id}`);
  return node;
}

/**
 * Orthogonal connector geometry: same-row neighbours connect left-to-right,
 * everything else drops through the midpoint of the vertical gap so lines
 * never cut through another box.
 */
export function edgePath(from: DiagramNode, to: DiagramNode): string {
  const sameRow = Math.abs(from.y - to.y) < 1;
  if (sameRow) {
    const startX = from.x < to.x ? from.x + from.width : from.x;
    const endX = from.x < to.x ? to.x : to.x + to.width;
    return `M ${startX} ${from.y + from.height / 2} H ${endX}`;
  }

  const fromCenterX = from.x + from.width / 2;
  const toCenterX = to.x + to.width / 2;
  const startY = from.y < to.y ? from.y + from.height : from.y;
  const endY = from.y < to.y ? to.y : to.y + to.height;

  if (Math.abs(fromCenterX - toCenterX) < 1) {
    return `M ${fromCenterX} ${startY} V ${endY}`;
  }

  const midY = startY + (endY - startY) / 2;
  return `M ${fromCenterX} ${startY} V ${midY} H ${toCenterX} V ${endY}`;
}

/** Node label baselines shared with the layout tests. */
export function nodeTextBaselines(node: DiagramNode): { label: number; sublabel: number; tag?: number } {
  if (node.kind === 'planned') {
    return { label: node.y + 24, sublabel: node.y + 40, tag: node.y + 55 };
  }
  return { label: node.y + 26, sublabel: node.y + 43 };
}

/** Long table names step down to 10.5 px so they stay inside a 220 px box. */
export function nodeLabelFontSize(node: DiagramNode): number {
  return node.label.length > 22 ? 10.5 : 12;
}

export default function ArchitectureDiagram() {
  return (
    <figure className="diagram-surface overflow-x-auto rounded-[var(--radius-md)] border border-[var(--border-subtle)] p-2">
      <svg
        role="img"
        aria-labelledby={`${TITLE_ID} ${DESC_ID}`}
        viewBox={`0 0 ${DIAGRAM_WIDTH} ${DIAGRAM_HEIGHT}`}
        className="h-auto w-full min-w-[720px]"
        xmlns="http://www.w3.org/2000/svg"
      >
        <title id={TITLE_ID}>{DIAGRAM_TITLE}</title>
        <desc id={DESC_ID}>{DIAGRAM_DESCRIPTION}</desc>

        <defs>
          <pattern id={GRID_ID} width="40" height="40" patternUnits="userSpaceOnUse">
            <path d="M 40 0 L 0 0 0 40" fill="none" stroke="#1e293b" strokeWidth="0.5" />
          </pattern>
          <marker id={ARROW_ID} markerWidth="10" markerHeight="7" refX="9" refY="3.5" orient="auto">
            <polygon points="0 0, 10 3.5, 0 7" fill="#64748b" />
          </marker>
        </defs>

        <rect data-layer="background" width={DIAGRAM_WIDTH} height={DIAGRAM_HEIGHT} fill="#020617" />
        <rect width={DIAGRAM_WIDTH} height={DIAGRAM_HEIGHT} fill={`url(#${GRID_ID})`} />

        {/* Arrows before boxes: painted behind the component fills. */}
        <g data-layer="edges" fill="none" stroke="#64748b" strokeWidth={1.4}>
          {EDGES.map((edge) => {
            const from = nodeById(edge.from);
            const to = nodeById(edge.to);
            return (
              <path
                key={`${edge.from}-${edge.to}`}
                data-edge={`${edge.from}->${edge.to}`}
                data-planned={edge.planned ? 'true' : 'false'}
                d={edgePath(from, to)}
                strokeDasharray={edge.planned ? '4 4' : undefined}
                markerEnd={`url(#${ARROW_ID})`}
              />
            );
          })}
        </g>

        <g data-layer="regions">
          {BOUNDARIES.map((boundary) => (
            <g key={boundary.id} data-boundary-id={boundary.id} data-planned={boundary.planned ? 'true' : 'false'}>
              <rect
                x={boundary.x}
                y={boundary.y}
                width={boundary.width}
                height={boundary.height}
                rx={12}
                fill={boundary.planned ? 'rgba(15, 23, 42, 0.45)' : 'rgba(15, 23, 42, 0.6)'}
                stroke={boundary.planned ? '#64748b' : '#334155'}
                strokeWidth={boundary.planned ? 1.5 : 1}
                strokeDasharray={boundary.planned ? '6 5' : '8 4'}
              />
              <text
                x={boundary.x + 16}
                y={boundary.y + 22}
                fill={boundary.planned ? '#e2e8f0' : '#94a3b8'}
                fontSize={10}
                letterSpacing="0.08em"
                fontWeight={600}
              >
                {boundary.label}
              </text>
            </g>
          ))}
        </g>

        <g data-layer="nodes">
          {NODES.map((node) => {
            const planned = node.kind === 'planned';
            const style = KIND_STYLES[node.kind];
            const baselines = nodeTextBaselines(node);
            return (
              <g
                key={node.id}
                data-node-id={node.id}
                data-kind={node.kind}
                data-planned={planned ? 'true' : 'false'}
              >
                {/* Opaque mask keeps arrows from showing through translucent fills. */}
                <rect
                  x={node.x}
                  y={node.y}
                  width={node.width}
                  height={node.height}
                  rx={6}
                  fill="#0f172a"
                />
                <rect
                  data-node-shape="true"
                  x={node.x}
                  y={node.y}
                  width={node.width}
                  height={node.height}
                  rx={6}
                  fill={style.fill}
                  stroke={style.stroke}
                  strokeWidth={1.5}
                  strokeDasharray={planned ? '6 4' : undefined}
                />
                <text
                  x={node.x + node.width / 2}
                  y={baselines.label}
                  fill="#f8fafc"
                  fontSize={nodeLabelFontSize(node)}
                  fontWeight={600}
                  textAnchor="middle"
                >
                  {node.label}
                </text>
                {node.sublabel && (
                  <text
                    x={node.x + node.width / 2}
                    y={baselines.sublabel}
                    fill="#94a3b8"
                    fontSize={9}
                    textAnchor="middle"
                  >
                    {node.sublabel}
                  </text>
                )}
                {planned && baselines.tag !== undefined && (
                  <text
                    x={node.x + node.width - 14}
                    y={baselines.tag}
                    fill="#cbd5e1"
                    fontSize={7}
                    letterSpacing="0.1em"
                    textAnchor="end"
                  >
                    PLANNED
                  </text>
                )}
              </g>
            );
          })}
        </g>

        <g data-layer="legend" aria-hidden="true">
          {LEGEND_KINDS.map((kind, index) => {
            const style = KIND_STYLES[kind];
            const x = 32 + index * 152;
            return (
              <g key={kind} data-legend-kind={kind} transform={`translate(${x} ${LEGEND_Y})`}>
                <rect
                  x={0}
                  y={-11}
                  width={14}
                  height={14}
                  rx={3}
                  fill={style.fill}
                  stroke={style.stroke}
                  strokeWidth={1.5}
                  strokeDasharray={kind === 'planned' ? '4 3' : undefined}
                />
                <text x={22} y={0} fill="#cbd5e1" fontSize={10}>
                  {KIND_LABELS[kind]}
                </text>
              </g>
            );
          })}
        </g>
      </svg>
    </figure>
  );
}
