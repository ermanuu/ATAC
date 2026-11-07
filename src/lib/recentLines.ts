export type RecentLine = { route_id: string; name: string; description: string };
export const lineKey = (name: string) => name.trim().toLocaleLowerCase('it-IT');

export function parseRecentLines(raw: string | null): RecentLine[] {
  try {
    const value: unknown = JSON.parse(raw || '[]');
    if (!Array.isArray(value)) return [];
    const seen = new Set<string>();
    const lines: RecentLine[] = [];
    for (const route of value) {
      if (typeof route?.route_id !== 'string' || !route.route_id.trim() || typeof route?.name !== 'string' || !route.name.trim()) continue;
      const name = route.name.trim();
      const key = lineKey(name);
      if (seen.has(key)) continue;
      seen.add(key);
      lines.push({ route_id: route.route_id.trim(), name, description: typeof route.description === 'string' ? route.description : '' });
      if (lines.length === 10) break;
    }
    return lines;
  } catch { return []; }
}

export function rememberRecentLine(lines: RecentLine[], route: RecentLine): RecentLine[] {
  return [{ ...route }, ...lines.filter(line => lineKey(line.name) !== lineKey(route.name))].slice(0, 10);
}
