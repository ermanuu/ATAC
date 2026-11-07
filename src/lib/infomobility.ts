export type SourceState = { available: boolean; partial?: boolean; stale: boolean; refreshing: boolean; timestamp: number | null; error?: string };
export type Bulletin = { id: string; title: string; text: string; summary: string; url: string; source: string; section: string; category: string; publishedAt: number | null; updatedAt: number | null; lines: string[]; live: boolean };
export type MetroLine = { code: string; name: string; status: 'regular' | 'delays' | 'modified' | 'suspended' | 'unknown'; label: string; detail: string; url: string; publishedAt: number | null };
export type MetroData = SourceState & { lines: MetroLine[]; source: string; sourceUrl: string; sourceTimestamp: number | null };
export type NewsData = SourceState & { articles: Bulletin[] };
export type LineAlertsData = SourceState & { line: string; items: Bulletin[] };

export function publicationDate(value: number | null) {
  return value ? new Date(value * 1000).toLocaleString('it-IT', { timeZone: 'Europe/Rome', day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit' }) : '';
}

export function sourceMessage(data: SourceState | null, requestFailed = false) {
  if (!data || data.stale || requestFailed) return '';
  if (data.refreshing && !data.timestamp) return 'Verifica della fonte in corso…';
  if (data.partial) return 'Alcune fonti non sono disponibili. Le informazioni potrebbero essere incomplete.';
  if (!data.available) return 'Fonte temporaneamente non disponibile. Riprova tra poco.';
  return '';
}
