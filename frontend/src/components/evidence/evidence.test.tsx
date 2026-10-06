import { render, screen } from '@testing-library/react';
import { describe, it, expect } from 'vitest';
import { SourceCard } from './SourceCard';
import { ToolCallCard } from './ToolCallCard';
import { ProvenanceGrid } from './ProvenanceGrid';
import type { ToolCall } from '../../api/types';

describe('SourceCard', () => {
  it('renders a link only for http: URLs', () => {
    render(<SourceCard sourceUrl="https://sec.gov/filing/1" />);
    expect(screen.getByText('View source')).toHaveAttribute('href', 'https://sec.gov/filing/1');
  });

  it('renders a link for http: URLs', () => {
    render(<SourceCard sourceUrl="http://sec.gov/filing/1" />);
    expect(screen.getByText('View source')).toHaveAttribute('href', 'http://sec.gov/filing/1');
  });

  it('rejects javascript: URLs', () => {
    render(<SourceCard sourceUrl="javascript:alert(1)" />);
    expect(screen.queryByText('View source')).not.toBeInTheDocument();
  });

  it('rejects data: URLs', () => {
    render(<SourceCard sourceUrl="data:text/html,<script>alert(1)</script>" />);
    expect(screen.queryByText('View source')).not.toBeInTheDocument();
  });

  it('rejects file: URLs', () => {
    render(<SourceCard sourceUrl="file:///etc/passwd" />);
    expect(screen.queryByText('View source')).not.toBeInTheDocument();
  });

  it('rejects malformed URLs', () => {
    render(<SourceCard sourceUrl="not-a-url" />);
    expect(screen.queryByText('View source')).not.toBeInTheDocument();
  });

  it('renders no link when sourceUrl is undefined', () => {
    render(<SourceCard />);
    expect(screen.queryByText('View source')).not.toBeInTheDocument();
  });
});

describe('ToolCallCard', () => {
  it('claims Lakebase storage only when note_id exists', () => {
    const tc: ToolCall = {
      name: 'save_research_note',
      arguments: { symbol: 'NVDA', content: 'test' },
      result: { note_id: 'n1', symbol: 'NVDA', status: 'saved' },
      ok: true,
    };
    render(<ToolCallCard toolCall={tc} index={0} />);
    expect(screen.getByText('Lakebase')).toBeInTheDocument();
  });

  it('does not claim Lakebase storage when note_id is absent', () => {
    const tc: ToolCall = {
      name: 'save_research_note',
      arguments: { symbol: 'NVDA', content: 'test' },
      result: { symbol: 'NVDA', status: 'saved' },
      ok: true,
    };
    render(<ToolCallCard toolCall={tc} index={0} />);
    expect(screen.queryByText('Lakebase')).not.toBeInTheDocument();
    expect(screen.getByText('Save not confirmed')).toBeInTheDocument();
  });

  it('does not claim Lakebase storage when call is failed', () => {
    const tc: ToolCall = {
      name: 'save_research_note',
      arguments: { symbol: 'NVDA', content: 'test' },
      result: { error: 'db_unavailable' },
      ok: false,
    };
    render(<ToolCallCard toolCall={tc} index={0} />);
    expect(screen.queryByText('Lakebase')).not.toBeInTheDocument();
  });
});

describe('ProvenanceGrid', () => {
  it('renders fallback for malformed object-valued fields', () => {
    const tc: ToolCall = {
      name: 'search_sec_filings',
      arguments: { ticker: 'NVDA' },
      result: {
        rows: [
          {
            ticker: { bad: 'object' },
            form_type: 123,
            accession_number: null,
            accepted_ts: undefined,
            source_url: { href: 'bad' },
            section: true,
            retrieval_mode: 42,
            chunk_id: [1, 2],
          },
        ],
      },
      ok: true,
    };
    render(<ProvenanceGrid toolCalls={[tc]} />);
    // Should render a source card with fallback dashes, not crash
    expect(screen.getByTestId('source-card')).toBeInTheDocument();
    expect(screen.getAllByText('—').length).toBeGreaterThanOrEqual(1);
  });

  it('renders valid string fields correctly', () => {
    const tc: ToolCall = {
      name: 'search_sec_filings',
      arguments: { ticker: 'NVDA' },
      result: {
        rows: [
          {
            ticker: 'NVDA',
            form_type: '10-K',
            accession_number: '000123',
            accepted_ts: '2024-01-01',
            source_url: 'https://sec.gov/filing/1',
            section: 'risk_factors',
            retrieval_mode: 'hybrid',
            chunk_id: 'c1',
          },
        ],
      },
      ok: true,
    };
    render(<ProvenanceGrid toolCalls={[tc]} />);
    expect(screen.getByText('NVDA')).toBeInTheDocument();
    expect(screen.getByText('10-K')).toBeInTheDocument();
    expect(screen.getByText('View source')).toBeInTheDocument();
  });
});