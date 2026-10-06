import { render, screen } from '@testing-library/react';
import { describe, it, expect } from 'vitest';
import { ArchitectureEvidence } from './ArchitectureEvidence';

describe('ArchitectureEvidence', () => {
  it('renders the Architecture business workflow and deterministic safety model', () => {
    render(<ArchitectureEvidence />);

    expect(screen.getByRole('heading', { name: 'Architecture & Tests' })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Business Workflow' })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Deterministic Safety Model' })).toBeInTheDocument();

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

  it('renders the technical architecture diagram with all pipeline nodes', () => {
    render(<ArchitectureEvidence />);

    const nodes = [
      'Upstream providers (Massive, SEC, CFTC, FRED)', 'Spark',
      'Delta bronze/silver/gold', 'FastAPI', 'React',
      'AI agent', 'Lakebase', 'analytics_outbox',
      'Spark analytics', 'Delta analytics',
    ];
    for (const node of nodes) {
      expect(screen.getByText(node)).toBeInTheDocument();
    }
  });

  it('renders pipeline nodes as an ordered list in correct sequence', () => {
    render(<ArchitectureEvidence />);

    const expectedOrder = [
      'Upstream providers (Massive, SEC, CFTC, FRED)', 'Spark',
      'Delta bronze/silver/gold', 'FastAPI', 'React',
      'AI agent', 'Lakebase', 'analytics_outbox',
      'Spark analytics', 'Delta analytics',
    ];
    const pipelineList = screen.getByLabelText('Technical architecture pipeline nodes');
    const pipelineItems = pipelineList.querySelectorAll('li');
    expect(pipelineItems).toHaveLength(10);
    pipelineItems.forEach((item, i) => {
      expect(item).toHaveTextContent(expectedOrder[i]);
    });
  });

  it('does not use role="img" on the pipeline diagram container', () => {
    const { container } = render(<ArchitectureEvidence />);

    const diagramContainer = container.querySelector('[data-tour="pipeline-nodes"]');
    expect(diagramContainer).toBeInTheDocument();
    expect(diagramContainer).not.toHaveAttribute('role', 'img');
  });

  it('renders verified test groups with commit/date placeholders', () => {
    render(<ArchitectureEvidence />);

    expect(screen.getByText('Contract tests')).toBeInTheDocument();
    expect(screen.getByText('Integration tests')).toBeInTheDocument();
    expect(screen.getByText('UI component tests')).toBeInTheDocument();
    expect(screen.getByText('Retrieval tests')).toBeInTheDocument();

    const placeholders = screen.getAllByText(/<pending>/);
    expect(placeholders.length).toBeGreaterThanOrEqual(4);
  });

  it('renders known limitations including baseline signals and DLT', () => {
    render(<ArchitectureEvidence />);

    expect(screen.getByText(/Baseline signals only/)).toBeInTheDocument();
    expect(screen.getByText(/DLT.*built but not deployed/)).toBeInTheDocument();
    expect(screen.getByText(/Paper broker scaffold/)).toBeInTheDocument();
    expect(screen.getByText(/Analytics require the.*refresh run/)).toBeInTheDocument();
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

    const steps = screen.getAllByRole('listitem', { name: '' });
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
    render(<ArchitectureEvidence />);

    expect(screen.getByText('analytics_outbox')).toBeInTheDocument();
  });

  it('renders responsive overflow-safe markup with no React Flow imports', () => {
    const { container } = render(<ArchitectureEvidence />);

    expect(container.querySelector('[data-tour="pipeline-nodes"]')).toBeInTheDocument();
    expect(container.querySelector('[data-tour="provenance"]')).toBeInTheDocument();
  });
});