export type FavoriteStop = { stop_id: string; name: string };
export function parseFavoriteStops(raw: string | null): FavoriteStop[] {
  try {
    const value: unknown = JSON.parse(raw || '[]');
    if (!Array.isArray(value)) return [];
    const unique = new Map<string, FavoriteStop>();
    for (const stop of value) if (typeof stop?.stop_id === 'string' && typeof stop?.name === 'string') unique.set(stop.stop_id, { stop_id: stop.stop_id, name: stop.name });
    return [...unique.values()];
  } catch { return []; }
}
export function toggleFavoriteStop(stops: FavoriteStop[], stop: FavoriteStop) {
  return stops.some(s => s.stop_id === stop.stop_id) ? stops.filter(s => s.stop_id !== stop.stop_id) : [stop, ...stops];
}
