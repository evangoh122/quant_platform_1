export interface ScaleDomain {
  min: number;
  max: number;
}

export interface ScaleRange {
  start: number;
  end: number;
}

export function linearScale(domain: ScaleDomain, range: ScaleRange): (v: number) => number {
  const d = domain.max - domain.min || 1;
  const r = range.end - range.start;
  return (v: number) => range.start + ((v - domain.min) / d) * r;
}

export function bandScale(
  domain: string[],
  range: ScaleRange,
): { (v: string): number; bandwidth: number; step: number } {
  const n = domain.length || 1;
  const r = range.end - range.start;
  const step = r / n;
  const bandwidth = step * 0.8;
  const fn = (v: string): number => {
    const idx = domain.indexOf(v);
    return range.start + (idx >= 0 ? idx : 0) * step + (step - bandwidth) / 2;
  };
  fn.bandwidth = bandwidth;
  fn.step = step;
  return fn;
}

export function niceExtent(min: number, max: number, tickCount = 5): [number, number] {
  if (min === max) return [min - 1, max + 1];
  const range = max - min;
  const roughStep = range / (tickCount - 1);
  const mag = Math.pow(10, Math.floor(Math.log10(roughStep)));
  const residual = roughStep / mag;
  let niceStep: number;
  if (residual <= 1.5) niceStep = 1 * mag;
  else if (residual <= 3) niceStep = 2 * mag;
  else if (residual <= 7) niceStep = 5 * mag;
  else niceStep = 10 * mag;
  const niceMin = Math.floor(min / niceStep) * niceStep;
  const niceMax = Math.ceil(max / niceStep) * niceStep;
  return [niceMin, niceMax];
}

export function tickValues(min: number, max: number, count = 5): number[] {
  const [nMin, nMax] = niceExtent(min, max, count);
  const step = (nMax - nMin) / (count - 1);
  return Array.from({ length: count }, (_, i) => nMin + i * step);
}