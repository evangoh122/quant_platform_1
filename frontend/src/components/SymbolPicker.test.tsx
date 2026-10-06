import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { SymbolPicker } from './SymbolPicker';
import * as symbolStorage from '../utils/symbolStorage';

describe('SymbolPicker', () => {
  let urlSpy: ReturnType<typeof vi.spyOn>;
  let setUrlSpy: ReturnType<typeof vi.spyOn>;

  beforeEach(() => {
    localStorage.clear();
    urlSpy = vi.spyOn(symbolStorage, 'getUrlSymbol').mockReturnValue(null);
    setUrlSpy = vi.spyOn(symbolStorage, 'setUrlSymbol').mockImplementation(() => {});
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('offers quick choices and the existing data-backed universe without duplication', () => {
    const onChange = vi.fn();
    render(<SymbolPicker value="" onChange={onChange} list="market" />);

    // Quick choices are visible as buttons
    for (const sym of ['NVDA', 'AAPL', 'MSFT', 'AMD', 'SPY']) {
      expect(screen.getByText(sym, { selector: 'button' })).toBeInTheDocument();
    }

    // Open dropdown and check data-backed list
    const input = screen.getByRole('combobox');
    fireEvent.focus(input);

    const options = screen.getAllByRole('option');
    expect(options.length).toBeGreaterThan(5); // market list has many more

    // Each quick choice appears once in the dropdown
    const optionTexts = options.map((o) => o.textContent);
    for (const sym of ['NVDA', 'AAPL', 'MSFT', 'AMD', 'SPY']) {
      const count = optionTexts.filter((t) => t === sym).length;
      expect(count).toBe(1);
    }
  });

  it('reads ?symbol= URL parameter on mount', async () => {
    urlSpy.mockReturnValue('MSFT');
    const onChange = vi.fn();
    render(<SymbolPicker value="NVDA" onChange={onChange} list="market" />);

    // The SymbolPicker reads the URL on mount
    await waitFor(() => {
      expect(urlSpy).toHaveBeenCalled();
    });

    // URL param should be lifted to the parent via onChange
    expect(onChange).toHaveBeenCalledWith('MSFT');
  });

  it('initializes from ?symbol=AMD and drives the parent', async () => {
    urlSpy.mockReturnValue('AMD');
    const onChange = vi.fn();
    render(<SymbolPicker value="NVDA" onChange={onChange} list="market" />);

    await waitFor(() => {
      expect(onChange).toHaveBeenCalledWith('AMD');
    });
  });

  it('shows no coverage for a valid-looking symbol outside the selected dataset', () => {
    const onChange = vi.fn();
    render(<SymbolPicker value="XYZ" onChange={onChange} list="market" hasCoverage={false} />);

    expect(screen.getByText(/No coverage/)).toBeInTheDocument();
    expect(screen.getByText(/XYZ is not in the market dataset/)).toBeInTheDocument();
  });

  it('shows coverage indicator when hasCoverage is true', () => {
    const onChange = vi.fn();
    render(<SymbolPicker value="NVDA" onChange={onChange} list="market" hasCoverage={true} />);

    expect(screen.getByText('Has data')).toBeInTheDocument();
  });

  it('persists a valid recent symbol on selection', () => {
    const onChange = vi.fn();
    render(<SymbolPicker value="NVDA" onChange={onChange} list="market" />);

    // Click AAPL quick choice
    fireEvent.click(screen.getByText('AAPL', { selector: 'button' }));

    expect(onChange).toHaveBeenCalledWith('AAPL');
    const recent = JSON.parse(localStorage.getItem('qp_recent_symbols') || '[]');
    expect(recent).toContain('AAPL');
  });

  it('accepts typed input and normalizes to uppercase', () => {
    const onChange = vi.fn();
    render(<SymbolPicker value="" onChange={onChange} list="market" />);

    const input = screen.getByRole('combobox');
    fireEvent.change(input, { target: { value: 'goog' } });

    expect(input).toHaveValue('GOOG');
  });

  it('does not accept an invalid symbol via typing without selection', () => {
    const onChange = vi.fn();
    render(<SymbolPicker value="" onChange={onChange} list="market" />);

    const input = screen.getByRole('combobox');
    fireEvent.change(input, { target: { value: 'FAKE123' } });

    // onChange should NOT have been called with an invalid symbol
    expect(onChange).not.toHaveBeenCalled();
  });

  it('allows submitting a typed ticker that passes format check', async () => {
    const onChange = vi.fn();
    render(<SymbolPicker value="" onChange={onChange} list="market" />);

    const input = screen.getByRole('combobox');
    fireEvent.focus(input);
    fireEvent.change(input, { target: { value: 'ZZZZ' } });

    // ZZZZ is not in market list, but passes ticker format — should show submit option
    await waitFor(() => {
      expect(screen.getByText(/Submit ZZZZ/)).toBeInTheDocument();
    });

    // Click submit
    fireEvent.mouseDown(screen.getByText(/Submit ZZZZ/));

    expect(onChange).toHaveBeenCalledWith('ZZZZ');
  });

  it('updates URL on selection', () => {
    const onChange = vi.fn();
    render(<SymbolPicker value="NVDA" onChange={onChange} list="market" />);

    fireEvent.click(screen.getByText('AAPL', { selector: 'button' }));

    expect(onChange).toHaveBeenCalledWith('AAPL');
    expect(setUrlSpy).toHaveBeenCalledWith('AAPL');
  });

  it('filters dropdown on typing', () => {
    const onChange = vi.fn();
    render(<SymbolPicker value="" onChange={onChange} list="market" />);

    const input = screen.getByRole('combobox');
    fireEvent.focus(input);
    fireEvent.change(input, { target: { value: 'NV' } });

    const options = screen.getAllByRole('option');
    const texts = options.map((o) => o.textContent);
    expect(texts).toContain('NVDA');
    expect(texts).not.toContain('AAPL');
  });

  it('shows recent symbols in quick choices', () => {
    // Pre-populate localStorage
    localStorage.setItem('qp_recent_symbols', JSON.stringify(['TSLA', 'GOOG']));
    const onChange = vi.fn();
    render(<SymbolPicker value="NVDA" onChange={onChange} list="market" />);

    expect(screen.getByText('TSLA', { selector: 'button' })).toBeInTheDocument();
    expect(screen.getByText('GOOG', { selector: 'button' })).toBeInTheDocument();
  });

  it('updates recent list after selection without remount', () => {
    const onChange = vi.fn();
    render(<SymbolPicker value="NVDA" onChange={onChange} list="market" />);

    // No TSLA recent button initially
    expect(screen.queryByText('TSLA', { selector: 'button' })).not.toBeInTheDocument();

    // Select TSLA from dropdown
    const input = screen.getByRole('combobox');
    fireEvent.focus(input);
    fireEvent.change(input, { target: { value: 'TSLA' } });

    // Find and click TSLA in the dropdown
    const options = screen.getAllByRole('option');
    const tslaOption = options.find((o) => o.textContent === 'TSLA');
    expect(tslaOption).toBeTruthy();
    fireEvent.mouseDown(tslaOption!);

    // TSLA should now appear as a recent button in the same render tree
    expect(screen.getByText('TSLA', { selector: 'button' })).toBeInTheDocument();
  });

  it('secMode uses coverage items as options', () => {
    const onChange = vi.fn();
    const coverage = [
      { ticker: 'NVDA', n_filings: 20, last_filed: '2025-09-30' },
      { ticker: 'AMD', n_filings: 15, last_filed: '2025-08-15' },
    ];
    render(
      <SymbolPicker
        value=""
        onChange={onChange}
        secMode
        secCoverage={coverage}
      />,
    );

    const input = screen.getByRole('combobox');
    fireEvent.focus(input);

    const options = screen.getAllByRole('option');
    expect(options).toHaveLength(2);
    expect(options[0]).toHaveTextContent('NVDA');
    expect(options[1]).toHaveTextContent('AMD');
  });

  it('accepts a share-class ticker such as BRK.B from ?symbol=', async () => {
    urlSpy.mockReturnValue('brk.b');
    const onChange = vi.fn();
    render(<SymbolPicker value="" onChange={onChange} list="market" />);
    await waitFor(() => {
      expect(onChange).toHaveBeenCalledWith('BRK.B');
    });
  });

  it('still rejects a malformed ?symbol= value', async () => {
    urlSpy.mockReturnValue('NVDA;DROP');
    const onChange = vi.fn();
    render(<SymbolPicker value="" onChange={onChange} list="market" />);
    await new Promise((r) => setTimeout(r, 20));
    expect(onChange).not.toHaveBeenCalled();
  });

  it('preserves a valid-format ticker from ?symbol= not in options and shows no-coverage', async () => {
    urlSpy.mockReturnValue('ZZZZ');
    const onChange = vi.fn();
    render(<SymbolPicker value="" onChange={onChange} list="market" />);

    // ZZZZ should be accepted (valid format) even though not in any list
    await waitFor(() => {
      expect(onChange).toHaveBeenCalledWith('ZZZZ');
    });

    // Should show no-coverage message since ZZZZ is not in the market list
    render(<SymbolPicker value="ZZZZ" onChange={onChange} list="market" hasCoverage={false} />);
    expect(screen.getByText(/ZZZZ is not in the market dataset/)).toBeInTheDocument();
    expect(screen.getByText(/No coverage/)).toBeInTheDocument();
  });

  it('submits a valid custom ticker with Enter when dropdown is closed', () => {
    const onChange = vi.fn();
    render(<SymbolPicker value="" onChange={onChange} list="market" />);

    const input = screen.getByRole('combobox');
    fireEvent.change(input, { target: { value: 'ZZZZ' } });
    // Close the dropdown first
    fireEvent.keyDown(input, { key: 'Escape' });
    // Now press Enter with dropdown closed
    fireEvent.keyDown(input, { key: 'Enter' });

    expect(onChange).toHaveBeenCalledWith('ZZZZ');
  });

  it('does not submit an invalid ticker with Enter when dropdown is closed', () => {
    const onChange = vi.fn();
    render(<SymbolPicker value="" onChange={onChange} list="market" />);

    const input = screen.getByRole('combobox');
    fireEvent.change(input, { target: { value: 'INVALID123' } });
    fireEvent.keyDown(input, { key: 'Escape' });
    fireEvent.keyDown(input, { key: 'Enter' });

    // Should NOT submit, should reopen dropdown
    expect(onChange).not.toHaveBeenCalled();
  });

  it('blur timeout restores the synchronized ref value, not a stale prop', async () => {
    vi.useFakeTimers();
    const onChange = vi.fn();
    const { rerender } = render(<SymbolPicker value="NVDA" onChange={onChange} list="market" />);

    const input = screen.getByRole('combobox');

    // Simulate selecting AMD (updates value prop via parent)
    fireEvent.click(screen.getByText('AMD', { selector: 'button' }));
    expect(onChange).toHaveBeenCalledWith('AMD');

    // Rerender with new value (simulating parent updating)
    rerender(<SymbolPicker value="AMD" onChange={onChange} list="market" />);

    // Blur the input
    fireEvent.blur(input);
    vi.advanceTimersByTime(200);

    // After blur, the input should show AMD (the ref-synced value), not NVDA (stale)
    expect(input).toHaveValue('AMD');

    vi.useRealTimers();
  });
});