export type Arrival = { tripId: string; routeId?: string; variantId?: string; vehicleId?: string | null; line: string; headsign: string; time: number; scheduledTime?: number; kind: string; serviceDate?: string; stopSequence?: number; predictionTimestamp?: number };
const direction = (a: Arrival) => JSON.stringify([a.line.trim().toLocaleUpperCase('it-IT'), a.headsign.trim().replace(/\s+/g, ' ').toLocaleUpperCase('it-IT'), a.serviceDate || '']);
/** Live is authoritative for a direction; schedules are its fallback. */
export function prioritizeArrivals(arrivals: Arrival[]) {
  const unique = new Map<string, Arrival>();
  for (const item of arrivals) {
    const key = JSON.stringify([item.routeId || item.line, item.tripId, item.serviceDate || '', item.stopSequence ?? null]);
    const previous = unique.get(key);
    if (!previous || (item.kind === 'live' && previous.kind !== 'live') ||
      (item.kind === previous.kind && (item.predictionTimestamp || 0) > (previous.predictionTimestamp || 0))) unique.set(key, item);
  }
  const liveDirections = new Set([...unique.values()].filter(a => a.kind === 'live').map(direction));
  return [...unique.values()].filter(a => a.kind === 'live' || !liveDirections.has(direction(a)))
    .sort((a, b) => Number(b.kind === 'live') - Number(a.kind === 'live') || a.time - b.time);
}
export function visibleArrivals(arrivals: Arrival[], now: number, liveFresh: boolean) {
  return prioritizeArrivals(arrivals.map(a => a.kind === 'live' && (!liveFresh || (a.predictionTimestamp !== undefined && now - a.predictionTimestamp > 180))
    ? { ...a, time: a.scheduledTime || 0, kind: 'scheduled' } : a).filter(a => a.time >= now && a.time <= now + 7200));
}
