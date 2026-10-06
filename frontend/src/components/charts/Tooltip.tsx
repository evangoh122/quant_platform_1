import { useState, useRef, useCallback } from 'react';
import type { ReactNode } from 'react';

interface TooltipProps {
  content: ReactNode;
  children: ReactNode;
  x: number;
  y: number;
  chartWidth: number;
  chartHeight: number;
}

export function Tooltip({ content, children, x, y, chartWidth, chartHeight }: TooltipProps) {
  const [visible, setVisible] = useState(false);
  const timeoutRef = useRef<ReturnType<typeof setTimeout>>();

  const show = useCallback(() => {
    clearTimeout(timeoutRef.current);
    setVisible(true);
  }, []);

  const hide = useCallback(() => {
    timeoutRef.current = setTimeout(() => setVisible(false), 100);
  }, []);

  const tooltipW = 140;
  const tooltipH = 32;
  const tx = x + tooltipW > chartWidth ? x - tooltipW - 8 : x + 8;
  const ty = y - tooltipH - 4 < 0 ? y + 16 : y - tooltipH - 4;

  return (
    <g onMouseEnter={show} onMouseLeave={hide} onFocus={show} onBlur={hide} tabIndex={0}>
      {children}
      {visible && (
        <g pointerEvents="none">
          <rect
            x={tx}
            y={ty}
            width={tooltipW}
            height={tooltipH}
            rx={4}
            className="fill-slate-800 dark:fill-slate-200"
            opacity={0.92}
          />
          <text
            x={tx + 8}
            y={ty + 20}
            className="fill-white dark:fill-slate-900"
            style={{ fontSize: 11 }}
          >
            {content}
          </text>
        </g>
      )}
    </g>
  );
}