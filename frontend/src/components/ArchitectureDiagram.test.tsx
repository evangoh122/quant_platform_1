import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import ArchitectureDiagram, {
  BOUNDARIES,
  DIAGRAM_HEIGHT,
  DIAGRAM_WIDTH,
  EDGES,
  KIND_STYLES,
  LEGEND_Y,
  NODES,
  SUBLABEL_FONT_SIZE,
  nodeLabelFontSize,
  nodeTextBaselines,
  type DiagramNode,
} from './ArchitectureDiagram';

const BUILT_NODE_IDS = [
  'upstream',
  'spark',
  'delta',
  'react',
  'fastapi',
  'agent',
  'lakebase',
  'outbox',
  'spark_analytics',
  'delta_analytics',
  'mlflow',
];

const PLANNED_NODE_IDS = [
  'hyperliquid',
  'binance',
  'bronze_perps',
  'silver_perp',
  'gold_weekend',
];

const BUILT_NODE_LABELS = [
  'Upstream providers',
  'Spark',
  'Delta Lake',
  'React',
  'FastAPI',
  'AI agent',
  'Lakebase',
  'analytics_outbox',
  'Spark analytics',
  'Delta analytics',
  'MLflow',
];

function node(id: string): DiagramNode {
  const match = NODES.find((candidate) => candidate.id === id);
  if (!match) throw new Error(`Missing node ${id}`);
  return match;
}

function xOverlap(a: DiagramNode, b: DiagramNode): boolean {
  return a.x < b.x + b.width && b.x < a.x + a.width;
}

function yOverlap(a: DiagramNode, b: DiagramNode): boolean {
  return a.y < b.y + b.height && b.y < a.y + a.height;
}

function boxesOverlap(a: DiagramNode, b: DiagramNode): boolean {
  return xOverlap(a, b) && yOverlap(a, b);
}

function verticalGap(a: DiagramNode, b: DiagramNode): number {
  return a.y < b.y ? b.y - (a.y + a.height) : a.y - (b.y + b.height);
}

function horizontalGap(a: DiagramNode, b: DiagramNode): number {
  return a.x < b.x ? b.x - (a.x + a.width) : a.x - (b.x + b.width);
}

function nodeShape(container: HTMLElement, id: string): Element {
  const shape = container.querySelector(`[data-node-id="${id}"] rect[data-node-shape="true"]`);
  if (!shape) throw new Error(`Missing rendered node outline for ${id}`);
  return shape;
}

describe('ArchitectureDiagram', () => {
  it('exposes one labelled image with a title and a description', () => {
    render(<ArchitectureDiagram />);

    const svg = screen.getByRole('img', { name: /architecture diagram/i });
    expect(svg.tagName.toLowerCase()).toBe('svg');
    expect(svg).toHaveAttribute('aria-labelledby');

    const title = svg.querySelector('title');
    const desc = svg.querySelector('desc');
    expect(title?.textContent).toMatch(/architecture diagram/i);
    expect(desc?.textContent).toMatch(/planned/i);
    expect(desc?.textContent).toMatch(/not deployed to production/i);
  });

  it('renders every built component in the diagram with no planned styling', () => {
    const { container } = render(<ArchitectureDiagram />);

    for (const id of BUILT_NODE_IDS) {
      const group = container.querySelector(`[data-node-id="${id}"]`);
      expect(group).not.toBeNull();
      expect(group).toHaveAttribute('data-planned', 'false');
      expect(nodeShape(container, id)).not.toHaveAttribute('stroke-dasharray');
    }

    for (const label of BUILT_NODE_LABELS) {
      expect(screen.getByText(label)).toBeInTheDocument();
    }
  });

  it('renders the planned perps pipeline as present AND explicitly planned', () => {
    const { container } = render(<ArchitectureDiagram />);

    for (const id of PLANNED_NODE_IDS) {
      const group = container.querySelector(`[data-node-id="${id}"]`);
      expect(group).not.toBeNull();
      expect(group).toHaveAttribute('data-kind', 'planned');
      expect(group).toHaveAttribute('data-planned', 'true');
      expect(nodeShape(container, id)).toHaveAttribute('stroke-dasharray');
      expect(group?.textContent).toMatch(/planned/i);
    }

    expect(screen.getByText('Hyperliquid HIP-3 API')).toBeInTheDocument();
    expect(screen.getByText('Binance futures archives')).toBeInTheDocument();
    expect(screen.getByText('bronze_perps_*')).toBeInTheDocument();
    expect(screen.getByText('silver_perp_*')).toBeInTheDocument();
    expect(screen.getByText('gold_weekend_perp_features')).toBeInTheDocument();

    const plannedBoundary = container.querySelector(
      '[data-boundary-id="perps"][data-boundary-part="fill"]',
    );
    expect(plannedBoundary).toHaveAttribute('data-planned', 'true');
    expect(
      container.querySelector('[data-boundary-id="perps"][data-boundary-part="label"]'),
    ).toHaveTextContent(/not in production/i);
  });

  it('draws arrows after the region fills and before the node boxes', () => {
    const { container } = render(<ArchitectureDiagram />);
    const svg = container.querySelector('svg');
    const layers = Array.from(svg?.querySelectorAll('[data-layer]') ?? []).map((el) =>
      el.getAttribute('data-layer'),
    );

    expect(layers).toEqual(['background', 'regions', 'edges', 'region-labels', 'nodes', 'legend']);

    const edgePaths = svg?.querySelectorAll('[data-edge]') ?? [];
    expect(edgePaths).toHaveLength(EDGES.length);
    for (const path of Array.from(edgePaths)) {
      expect(path.getAttribute('d')).toMatch(/^M /);
      expect(path.getAttribute('marker-end')).toBe('url(#architecture-diagram-arrow)');
    }
  });

  it('keeps every translucent region fill behind the connectors', () => {
    // Regression: `regions` used to be painted after `edges`, so the boundary
    // fills (alpha 0.45-0.6) composited over 54% of the connector length and
    // dropped arrow contrast to ~1.8:1 — below the WCAG 3:1 non-text floor.
    // A fill may only be translucent while it sits underneath the arrows.
    const { container } = render(<ArchitectureDiagram />);
    const svg = container.querySelector('svg');
    const layers = Array.from(svg?.querySelectorAll('[data-layer]') ?? []).map((el) =>
      el.getAttribute('data-layer'),
    );
    const regionsIndex = layers.indexOf('regions');
    const edgesIndex = layers.indexOf('edges');

    expect(regionsIndex).toBeGreaterThan(-1);
    expect(edgesIndex).toBeGreaterThan(-1);
    expect(regionsIndex).toBeLessThan(edgesIndex);

    const fillRects = Array.from(
      container.querySelectorAll('[data-layer="regions"] rect[data-boundary-id]'),
    );
    expect(fillRects).toHaveLength(BOUNDARIES.length);

    for (const rect of fillRects) {
      const fill = rect.getAttribute('fill') ?? '';
      const alpha = fill.startsWith('rgba') ? Number(fill.split(',').pop()?.replace(')', '')) : 1;
      expect(Number.isFinite(alpha)).toBe(true);
      const mutesConnectors = regionsIndex > edgesIndex && alpha > 0.3;
      expect(mutesConnectors).toBe(false);
    }
  });

  it('labels MLflow as the offline ML lane and not a deployed component', () => {
    const { container } = render(<ArchitectureDiagram />);

    const mlflow = container.querySelector('[data-node-id="mlflow"]');
    expect(mlflow).not.toBeNull();
    // The node stays solid: mlflow is real, tested code (ml/registry.py).
    expect(mlflow).toHaveAttribute('data-planned', 'false');
    expect(mlflow?.querySelector('text')).toHaveTextContent('MLflow');
    expect(mlflow?.textContent).toMatch(/offline ML lane/i);
    expect(mlflow?.textContent).toMatch(/not deployed/i);

    const desc = container.querySelector('svg desc')?.textContent ?? '';
    expect(desc).toMatch(/offline ML ablation lane/i);
    expect(desc).toMatch(/not part of the deployed stack/i);
    expect(desc).toMatch(/not deployed to production/i);
  });

  it('dashes planned edges and keeps every edge endpoint on a real node', () => {
    const { container } = render(<ArchitectureDiagram />);
    const ids = new Set(NODES.map((candidate) => candidate.id));

    for (const edge of EDGES) {
      expect(ids.has(edge.from)).toBe(true);
      expect(ids.has(edge.to)).toBe(true);

      const path = container.querySelector(`[data-edge="${edge.from}->${edge.to}"]`);
      expect(path).not.toBeNull();
      if (edge.planned) {
        expect(path).toHaveAttribute('stroke-dasharray');
        expect(path).toHaveAttribute('data-planned', 'true');
      } else {
        expect(path).not.toHaveAttribute('stroke-dasharray');
      }
    }
  });

  it('renders a legend outside every boundary, below the lowest one', () => {
    const { container } = render(<ArchitectureDiagram />);

    const legend = container.querySelector('[data-layer="legend"]');
    expect(legend).not.toBeNull();
    expect(legend?.querySelectorAll('[data-legend-kind]')).toHaveLength(7);
    expect(screen.getByText('Planned (not built)')).toBeInTheDocument();

    const lowestBoundary = Math.max(...BOUNDARIES.map((boundary) => boundary.y + boundary.height));
    expect(LEGEND_Y).toBeGreaterThanOrEqual(lowestBoundary + 20);
    expect(LEGEND_Y).toBeLessThan(DIAGRAM_HEIGHT);

    for (const boundary of BOUNDARIES) {
      expect(LEGEND_Y).toBeGreaterThan(boundary.y + boundary.height);
    }
  });

  it('keeps every node inside the viewBox and free of overlaps', () => {
    for (const a of NODES) {
      expect(a.x).toBeGreaterThanOrEqual(0);
      expect(a.y).toBeGreaterThanOrEqual(0);
      expect(a.x + a.width).toBeLessThanOrEqual(DIAGRAM_WIDTH);
      expect(a.y + a.height).toBeLessThanOrEqual(DIAGRAM_HEIGHT);
    }

    for (const boundary of BOUNDARIES) {
      expect(boundary.x + boundary.width).toBeLessThanOrEqual(DIAGRAM_WIDTH);
      expect(boundary.y + boundary.height).toBeLessThan(DIAGRAM_HEIGHT);
    }

    for (let i = 0; i < NODES.length; i += 1) {
      for (let j = i + 1; j < NODES.length; j += 1) {
        expect(boxesOverlap(NODES[i], NODES[j])).toBe(false);
      }
    }
  });

  it('keeps at least 40 px between stacked or adjacent node boxes', () => {
    for (let i = 0; i < NODES.length; i += 1) {
      for (let j = i + 1; j < NODES.length; j += 1) {
        const a = NODES[i];
        const b = NODES[j];
        if (xOverlap(a, b)) {
          expect(verticalGap(a, b)).toBeGreaterThanOrEqual(40);
        }
        if (yOverlap(a, b)) {
          expect(horizontalGap(a, b)).toBeGreaterThanOrEqual(40);
        }
      }
    }
  });

  it('fits every node label and sublabel inside its box without text collisions', () => {
    // Monospace advance width is ~0.6 em; check the longest possible line.
    for (const candidate of NODES) {
      const labelWidth = candidate.label.length * nodeLabelFontSize(candidate) * 0.6;
      const sublabelWidth = (candidate.sublabel?.length ?? 0) * SUBLABEL_FONT_SIZE * 0.6;
      expect(labelWidth).toBeLessThan(candidate.width - 16);
      expect(sublabelWidth).toBeLessThan(candidate.width - 16);

      const baselines = nodeTextBaselines(candidate);
      expect(baselines.label).toBeGreaterThan(candidate.y);
      expect(baselines.sublabel - baselines.label).toBeGreaterThanOrEqual(14);
      expect(baselines.sublabel).toBeLessThan(candidate.y + candidate.height);
      if (baselines.tag !== undefined) {
        expect(baselines.tag).toBeLessThan(candidate.y + candidate.height);
      }
    }
  });

  it('uses only the semantic palette from the diagram skill and no raster image', () => {
    const { container } = render(<ArchitectureDiagram />);

    for (const candidate of NODES) {
      const shape = nodeShape(container, candidate.id);
      expect(shape.getAttribute('fill')).toBe(KIND_STYLES[candidate.kind].fill);
      expect(shape.getAttribute('stroke')).toBe(KIND_STYLES[candidate.kind].stroke);
    }

    expect(container.querySelector('img')).toBeNull();
    expect(container.querySelector('image')).toBeNull();
    // Guard the node ids used above against silent renames.
    expect(node('gold_weekend').kind).toBe('planned');
  });

  it('keeps every in-SVG label at or above the 10 px legibility floor', () => {
    const { container } = render(<ArchitectureDiagram />);

    const texts = Array.from(container.querySelectorAll('svg text'));
    expect(texts.length).toBeGreaterThan(0);
    for (const text of texts) {
      const size = Number(text.getAttribute('font-size'));
      expect(Number.isFinite(size)).toBe(true);
      expect(size).toBeGreaterThanOrEqual(10);
    }
  });
});
