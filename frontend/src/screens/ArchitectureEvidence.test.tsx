import { render, screen, within } from '@testing-library/react';
import { describe, it, expect } from 'vitest';
import { ArchitectureEvidence } from './ArchitectureEvidence';

const PIPELINE_NODES = [
  'Upstream providers (Massive, SEC, CFTC, FRED)', 'Spark',
  'Delta bronze/silver/gold', 'FastAPI', 'React',
  'AI agent', 'Lakebase', 'analytics_outbox',
  'Spark analytics', 'Delta analytics',
];

const PLANNED_PERPS_NODE_IDS = [
  'hyperliquid',
  'binance',
  'bronze_perps',
  'silver_perp',
  'gold_weekend',
];

describe('ArchitectureEvidence', () => {
  it('renders the Architecture business workflow and deterministic safety model', () => {
    render(<ArchitectureEvidence />);

    expect(screen.getByRole('heading', { name: 'Architecture & Tests' })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Business Workflow' })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Deterministic Safety Model' })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Expected Test Groups' })).toBeInTheDocument();

    expect(screen.getByText(/User asks a research question/)).toBeInTheDocument();
    expect(screen.getByText(/Governed retrieval/)).toBeInTheDocument();
    expect(screen.getByText(/Grounded response/)).toBeInTheDocument();
    expect(screen.getByText(/Optional: save research note to Lakebase/)).toBeInTheDocument();
    expect(screen.getByText(/when agent returns a note_id/)).toBeInTheDocument();
    expect(screen.getByText(/Lakebase audit trail/)).toBeInTheDocument();
    expect(screen.getByText(/Delta analytics materialisation/)).toBeInTheDocument();

    expect(screen.getByText('LLM proposes')).toBeInTheDocument();
    expect(screen.getByText('Typed schema validates')).toBeInTheDocument();
    expect(screen.getByText('Allowlist check')).toBeInTheDocument();
    expect(screen.getByText('Write authorisation')).toBeInTheDocument();
    expect(screen.getByText('Deterministic execution')).toBeInTheDocument();
    expect(screen.getByText('Audit record')).toBeInTheDocument();
  });

  // The diagram repeats these labels as SVG text, so the text-summary queries
  // are scoped to the ordered list instead of matching ambiguous page text.
  it('renders the technical architecture diagram with all pipeline nodes', () => {
    render(<ArchitectureEvidence />);

    const pipelineList = screen.getByLabelText('Technical architecture pipeline nodes');
    for (const node of PIPELINE_NODES) {
      expect(within(pipelineList).getByText(node)).toBeInTheDocument();
    }
  });

  it('renders pipeline nodes as an ordered list in correct sequence', () => {
    render(<ArchitectureEvidence />);

    const pipelineList = screen.getByLabelText('Technical architecture pipeline nodes');
    const pipelineItems = pipelineList.querySelectorAll('li');
    expect(pipelineItems).toHaveLength(10);
    pipelineItems.forEach((item, i) => {
      expect(item).toHaveTextContent(PIPELINE_NODES[i]);
    });
  });

  it('renders the inline SVG architecture diagram with an accessible name and no raster fallback', () => {
    const { container } = render(<ArchitectureEvidence />);

    const svg = screen.getByRole('img', { name: /architecture diagram/i });
    expect(svg.tagName.toLowerCase()).toBe('svg');
    expect(svg.querySelector('title')?.textContent).toMatch(/architecture diagram/i);
    expect(svg.querySelector('desc')?.textContent).toMatch(/planned/i);

    expect(container.querySelector('img')).toBeNull();
    expect(container.querySelector('image')).toBeNull();
    expect(container.querySelector('[src$=".gif"]')).toBeNull();
    expect(container.querySelector('[src$=".png"]')).toBeNull();
  });

  it('shows the planned perps pipeline in the diagram and labels it planned', () => {
    const { container } = render(<ArchitectureEvidence />);

    for (const id of PLANNED_PERPS_NODE_IDS) {
      const group = container.querySelector(`[data-node-id="${id}"]`);
      expect(group).not.toBeNull();
      expect(group).toHaveAttribute('data-planned', 'true');
      expect(group?.querySelector('rect[data-node-shape="true"]')).toHaveAttribute('stroke-dasharray');
      expect(group?.textContent).toMatch(/planned/i);
    }

    expect(screen.getByText('Planned (not built)')).toBeInTheDocument();
    expect(screen.getByText(/not in production/i)).toBeInTheDocument();
    expect(screen.getByText(/Dashed components are planned/)).toBeInTheDocument();
  });

  it('does not use role="img" on the pipeline diagram container', () => {
    const { container } = render(<ArchitectureEvidence />);

    const diagramContainer = container.querySelector('[data-tour="pipeline-nodes"]');
    expect(diagramContainer).toBeInTheDocument();
    expect(diagramContainer).not.toHaveAttribute('role', 'img');
  });

  it('renders expected test groups with test coverage status', () => {
    render(<ArchitectureEvidence />);

    expect(screen.getByText('Contract tests')).toBeInTheDocument();
    expect(screen.getByText('Integration tests')).toBeInTheDocument();
    expect(screen.getByText('UI component tests')).toBeInTheDocument();
    expect(screen.getByText('Retrieval tests')).toBeInTheDocument();

    const coverageLabels = screen.getAllByText(/Test coverage — pending build branch run/);
    expect(coverageLabels.length).toBeGreaterThanOrEqual(4);
  });

  it('renders known limitations including baseline signals and DLT', () => {
    render(<ArchitectureEvidence />);

    expect(screen.getByText(/Baseline signals only/)).toBeInTheDocument();
    expect(screen.getByText(/DLT.*built but not deployed/)).toBeInTheDocument();
    expect(screen.getByText(/Paper broker scaffold/)).toBeInTheDocument();
    expect(screen.getByText(/Analytics require the.*refresh run/)).toBeInTheDocument();
    expect(
      screen.getByText(
        'MLflow runs in the offline ML ablation lane only; not part of the deployed stack.',
      ),
    ).toBeInTheDocument();
  });

  it('qualifies MLflow as offline and not deployed in the diagram and its description', () => {
    const { container } = render(<ArchitectureEvidence />);

    const mlflow = container.querySelector('[data-node-id="mlflow"]');
    expect(mlflow).not.toBeNull();
    expect(mlflow?.textContent).toMatch(/offline ML lane/i);
    expect(mlflow?.textContent).toMatch(/not deployed/i);

    const desc = container.querySelector('svg desc')?.textContent ?? '';
    expect(desc).toMatch(/offline ML ablation lane/i);
    expect(desc).toMatch(/not part of the deployed stack/i);
  });

  it('labels baseline signals as a demonstration with no edge claimed', () => {
    render(<ArchitectureEvidence />);

    expect(screen.getByText(/no validated trading edge claimed/)).toBeInTheDocument();
    expect(screen.getByText(/1-trading-day logistic-regression baseline/)).toBeInTheDocument();
    expect(screen.queryByText(/AUC/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/baseline-logreg-v0/)).not.toBeInTheDocument();
  });

  it('renders safety model in correct order (LLM never executes directly)', () => {
    render(<ArchitectureEvidence />);

    const safetyList = screen.getByLabelText('Safety model steps');
    const safetyItems = safetyList.querySelectorAll('li');

    expect(safetyItems[0]).toHaveTextContent('LLM proposes');
    expect(safetyItems[1]).toHaveTextContent('Typed schema validates');
    expect(safetyItems[2]).toHaveTextContent('Allowlist check');
    expect(safetyItems[3]).toHaveTextContent('Write authorisation');
    expect(safetyItems[4]).toHaveTextContent('Deterministic execution');
    expect(safetyItems[5]).toHaveTextContent('Audit record');
  });

  it('includes analytics_outbox in the architecture diagram', () => {
    const { container } = render(<ArchitectureEvidence />);

    const pipelineList = screen.getByLabelText('Technical architecture pipeline nodes');
    expect(within(pipelineList).getByText('analytics_outbox')).toBeInTheDocument();
    expect(container.querySelector('[data-node-id="outbox"]')).not.toBeNull();
  });

  it('renders responsive overflow-safe markup with no React Flow imports', () => {
    const { container } = render(<ArchitectureEvidence />);

    expect(container.querySelector('[data-tour="pipeline-nodes"]')).toBeInTheDocument();
    expect(container.querySelector('[data-tour="provenance"]')).toBeInTheDocument();
  });
});
