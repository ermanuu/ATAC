export type Arrival = { tripId: string; routeId?: string; variantId?: string; vehicleId?: string | null; atTerminus?: boolean; atTerminusTimestamp?: number; line: string; headsign: string; time: number | null; scheduledTime?: number; kind: string; serviceDate?: string; stopSequence?: number; predictionTimestamp?: number; predictionSource?: string };
const direction = (a: Arrival) => JSON.stringify([a.line.trim().toLocaleUpperCase('it-IT'), a.headsign.trim().replace(/\s+/g, ' ').toLocaleUpperCase('it-IT'), a.serviceDate || '']);
const priority = (a: Arrival) => a.kind === 'live' ? 0 : a.kind === 'observed' ? 1 : 2;
/** Live is authoritative for a direction; schedules are its fallback. */
export function prioritizeArrivals(arrivals: Arrival[]) {
  const unique = new Map<string, Arrival>();
  for (const item of arrivals) {
    const key = JSON.stringify([item.routeId || item.line, item.tripId, item.serviceDate || '', item.stopSequence ?? null]);
    const previous = unique.get(key);
    if (!previous || priority(item) < priority(previous) ||
      (item.kind === previous.kind && (item.predictionTimestamp || 0) > (previous.predictionTimestamp || 0))) unique.set(key, item);
  }
  const liveDirections = new Set([...unique.values()].filter(a => a.kind === 'live' || a.kind === 'observed').map(direction));
  return [...unique.values()].filter(a => a.kind === 'live' || a.kind === 'observed' || a.atTerminus || !liveDirections.has(direction(a)))
    .sort((a, b) => priority(a) - priority(b) || (a.time ?? 0) - (b.time ?? 0));
}
export function visibleArrivals(arrivals: Arrival[], now: number, liveFresh: boolean) {
  return prioritizeArrivals(arrivals.map(a => {
    let item = a.kind === 'live' && (!liveFresh || (a.predictionTimestamp !== undefined && now - a.predictionTimestamp > 180))
      ? { ...a, time: a.scheduledTime || 0, kind: 'scheduled' } : a;
    const terminalFresh = item.atTerminusTimestamp !== undefined
      ? now >= item.atTerminusTimestamp && now - item.atTerminusTimestamp <= 180
      : liveFresh && item.kind === 'live';
    if (item.atTerminus && !terminalFresh) {
      item = { ...item, atTerminus: false, vehicleId: item.kind === 'live' ? item.vehicleId : null };
      if (item.kind === 'observed') item = { ...item, kind: 'scheduled', time: item.scheduledTime || 0 };
    }
    if (item.atTerminus && (item.kind === 'scheduled' || item.time === null || item.time < now)) {
      item = { ...item, kind: 'observed', time: null };
    }
    return item;
  }).filter(a => a.kind === 'observed' ? a.atTerminus : a.time !== null && (a.time >= now || a.atTerminus) && a.time <= now + 7200));
}
