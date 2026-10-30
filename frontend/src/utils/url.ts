export function safeHttpUrl(url: string | null | undefined): string | undefined {
  if (!url || typeof url !== 'string') return undefined;
  try {
    const parsed = new URL(url);
    if (parsed.protocol === 'http:' || parsed.protocol === 'https:') {
      return url;
    }
    return undefined;
  } catch {
    return undefined;
  }
}
