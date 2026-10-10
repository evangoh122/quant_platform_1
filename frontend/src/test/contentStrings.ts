import { expect } from 'vitest';

export interface StringLeaf {
  path: string;
  value: string;
}

export function collectStringLeaves(node: unknown, path = '$', out: StringLeaf[] = []): StringLeaf[] {
  if (typeof node === 'string') {
    out.push({ path, value: node });
  } else if (Array.isArray(node)) {
    node.forEach((item, index) => collectStringLeaves(item, `${path}[${index}]`, out));
  } else if (node !== null && typeof node === 'object') {
    for (const [key, value] of Object.entries(node as Record<string, unknown>)) {
      collectStringLeaves(value, `${path}.${key}`, out);
    }
  }
  return out;
}

export function domHaystack(container: HTMLElement): string {
  const parts: string[] = [container.textContent ?? ''];
  for (const el of Array.from(container.querySelectorAll('*'))) {
    for (const attr of Array.from(el.attributes)) {
      parts.push(attr.value);
    }
  }
  return parts.join('\n');
}

export function expectStringsInDom(container: HTMLElement, node: unknown, label: string): void {
  const haystack = domHaystack(container);
  const missing = collectStringLeaves(node)
    .filter((leaf) => leaf.value.length > 0 && !haystack.includes(leaf.value))
    .map((leaf) => `${label} ${leaf.path}: ${JSON.stringify(leaf.value)}`);
  expect(missing).toEqual([]);
}

export function headingLevels(container: HTMLElement): number[] {
  return Array.from(container.querySelectorAll('h1,h2,h3,h4,h5,h6')).map((el) =>
    Number(el.tagName.substring(1)),
  );
}

export function expectHeadingOrder(container: HTMLElement): void {
  const levels = headingLevels(container);
  expect(levels.length).toBeGreaterThan(0);
  expect(levels[0]).toBe(1);
  for (let i = 1; i < levels.length; i += 1) {
    expect(levels[i] - levels[i - 1]).toBeLessThanOrEqual(1);
  }
}
