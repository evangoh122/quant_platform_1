import { render, screen } from '@testing-library/react';
import { describe, it, expect } from 'vitest';
import { ExecutionTrace } from './ExecutionTrace';
import type { ToolCall } from '../api/types';

describe('ExecutionTrace', () => {
  it('shows Retrieval = Complete and Write = Failed when search succeeds but save fails', () => {
    const toolCalls: ToolCall[] = [
      {
        name: 'search_sec_filings',
        arguments: { ticker: 'NVDA' },
        result: { rows: [{ chunk_id: 'c1' }] },
        ok: true,
      },
      {
        name: 'save_research_note',
        arguments: { symbol: 'NVDA', content: 'test' },
        result: { error: 'db_unavailable' },
        ok: false,
      },
    ];

    render(<ExecutionTrace toolCalls={toolCalls} available={true} sending={false} reply="Search results found." />);

    expect(screen.getByTestId('trace-retrieval')).toHaveTextContent('Complete');
    expect(screen.getByTestId('trace-tool_execution')).toHaveTextContent('Failed');
    expect(screen.getByTestId('trace-response')).toHaveTextContent('Complete');
  });

  it('shows Response = Failed when the agent is unavailable', () => {
    const toolCalls: ToolCall[] = [
      { name: 'search_sec_filings', arguments: { ticker: 'NVDA' }, result: { rows: [{ chunk_id: 'c1' }] }, ok: true },
    ];
    render(<ExecutionTrace toolCalls={toolCalls} available={false} sending={false} reply="" />);
    expect(screen.getByTestId('trace-response')).toHaveTextContent('Failed');
  });

  it('shows Retrieval = Failed when search fails and write succeeds', () => {
    const toolCalls: ToolCall[] = [
      {
        name: 'search_sec_filings',
        arguments: { ticker: 'NVDA' },
        result: { error: 'retrieval_unavailable' },
        ok: false,
      },
      {
        name: 'save_research_note',
        arguments: { symbol: 'NVDA', content: 'test' },
        result: { note_id: 'n1', symbol: 'NVDA', status: 'saved' },
        ok: true,
      },
    ];

    render(<ExecutionTrace toolCalls={toolCalls} available={true} sending={false} reply="" />);

    expect(screen.getByTestId('trace-retrieval')).toHaveTextContent('Failed');
    expect(screen.getByTestId('trace-tool_execution')).toHaveTextContent('Complete');
  });

  it('shows both stages complete when all tools succeed', () => {
    const toolCalls: ToolCall[] = [
      {
        name: 'search_sec_filings',
        arguments: { ticker: 'NVDA' },
        result: { rows: [{ chunk_id: 'c1' }] },
        ok: true,
      },
      {
        name: 'save_research_note',
        arguments: { symbol: 'NVDA', content: 'test' },
        result: { note_id: 'n1', symbol: 'NVDA', status: 'saved' },
        ok: true,
      },
    ];

    render(<ExecutionTrace toolCalls={toolCalls} available={true} sending={false} reply="Both succeeded." />);

    expect(screen.getByTestId('trace-retrieval')).toHaveTextContent('Complete');
    expect(screen.getByTestId('trace-tool_execution')).toHaveTextContent('Complete');
    expect(screen.getByTestId('trace-response')).toHaveTextContent('Complete');
  });

  it('shows Retrieval = Skipped when no retrieval tools are called', () => {
    const toolCalls: ToolCall[] = [
      {
        name: 'save_research_note',
        arguments: { symbol: 'NVDA', content: 'test' },
        result: { note_id: 'n1', symbol: 'NVDA', status: 'saved' },
        ok: true,
      },
    ];

    render(<ExecutionTrace toolCalls={toolCalls} available={true} sending={false} reply="Note saved." />);

    expect(screen.getByTestId('trace-retrieval')).toHaveTextContent('Skipped');
    expect(screen.getByTestId('trace-tool_execution')).toHaveTextContent('Complete');
  });

  it('shows pending when still sending with no reply', () => {
    render(<ExecutionTrace toolCalls={[]} available={true} sending={true} reply="" />);

    expect(screen.getByTestId('trace-response')).toHaveTextContent('Running');
    expect(screen.getByTestId('trace-tool_execution')).toHaveTextContent('Running');
  });

  it('shows complete trace when reply delivered with zero tools', () => {
    render(<ExecutionTrace toolCalls={[]} available={true} sending={false} reply="Hello, how can I help?" />);

    expect(screen.getByTestId('execution-trace')).toBeInTheDocument();
    expect(screen.getByTestId('trace-response')).toHaveTextContent('Complete');
    expect(screen.getByTestId('trace-tool_execution')).toHaveTextContent('Skipped');
  });

  it('shows failed when finished without a delivered reply', () => {
    const toolCalls: ToolCall[] = [
      {
        name: 'search_sec_filings',
        arguments: { ticker: 'NVDA' },
        result: { rows: [{ chunk_id: 'c1' }] },
        ok: true,
      },
    ];

    render(<ExecutionTrace toolCalls={toolCalls} available={false} sending={false} reply="" />);

    expect(screen.getByTestId('trace-response')).toHaveTextContent('Failed');
  });
});