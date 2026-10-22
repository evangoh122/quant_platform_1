import type { ReactNode } from 'react';

interface EyebrowProps {
  children: ReactNode;
  /** Extra classes for spacing where the eyebrow sits in a header stack. */
  className?: string;
}

/**
 * Section eyebrow: a short gold rule followed by italic serif text in gold,
 * matching the owner's site ("product-minded AI systems", "selected work").
 * One component for every section label and page header so the pattern stays
 * identical across screens.
 */
export function Eyebrow({ children, className }: EyebrowProps) {
  return (
    <p className={className ? `eyebrow ${className}` : 'eyebrow'}>
      <span className="eyebrow-rule" aria-hidden="true" />
      <span>{children}</span>
    </p>
  );
}

export default Eyebrow;
