export type Arrival = { tripId: string; routeId?: string; variantId?: string; vehicleId?: string | null; atTerminus?: boolean; atTerminusTimestamp?: number; line: string; headsign: string; time: number | null; scheduledTime?: number; kind: string; serviceDate?: string; stopSequence?: number; predictionTimestamp?: number; predictionSource?: string };
const direction = (a: Arrival) => JSON.stringify([a.line.trim().toLocaleUpperCase('it-IT'), a.headsign.trim().replace(/\s+/g, ' ').toLocaleUpperCase('it-IT'), a.serviceDate || '']);
type TimedArrival = Arrival & { time: number };
const priority = (a: Arrival) => a.kind === 'live' ? 0 : 1;
const directArrival = (a: Arrival): a is TimedArrival => a.time !== null &&
  (a.kind === 'live' || a.kind === 'scheduled') && a.predictionSource !== 'propagated';
/** Live is authoritative for a direction; schedules are its fallback. */
export function prioritizeArrivals(arrivals: Arrival[]) {
  const unique = new Map<string, TimedArrival>();
  for (const item of arrivals.filter(directArrival)) {
    const key = JSON.stringify([item.routeId || item.line, item.tripId, item.serviceDate || '', item.stopSequence ?? null]);
    const previous = unique.get(key);
    if (!previous || priority(item) < priority(previous) ||
      (item.kind === previous.kind && (item.predictionTimestamp || 0) > (previous.predictionTimestamp || 0))) unique.set(key, item);
  }
  const liveDirections = new Set([...unique.values()].filter(a => a.kind === 'live').map(direction));
  return [...unique.values()].filter(a => a.kind === 'live' || !liveDirections.has(direction(a)))
    .sort((a, b) => priority(a) - priority(b) || a.time - b.time);
}
export function visibleArrivals(arrivals: Arrival[], now: number, liveFresh: boolean) {
  return prioritizeArrivals(arrivals.map(a => {
    const item = a.kind === 'live' && (!liveFresh || (a.predictionTimestamp !== undefined && now - a.predictionTimestamp > 180))
      ? { ...a, time: a.scheduledTime || 0, kind: 'scheduled' } : a;
    const terminalFresh = item.atTerminusTimestamp !== undefined
      ? now >= item.atTerminusTimestamp && now - item.atTerminusTimestamp <= 180
      : liveFresh && item.kind === 'live';
    if (item.atTerminus && !terminalFresh) {
      return { ...item, atTerminus: false, vehicleId: item.kind === 'live' ? item.vehicleId : null };
    }
    return item;
  })).filter(a => a.time >= now && a.time <= now + 7200);
}
