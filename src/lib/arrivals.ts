export type Arrival = { tripId: string; routeId?: string; variantId?: string; vehicleId?: string | null; atTerminus?: boolean; atTerminusTimestamp?: number; line: string; headsign: string; time: number | null; scheduledTime?: number; departureTime?: number; scheduledDepartureTime?: number; departureKind?: 'live' | 'scheduled'; kind: string; serviceDate?: string; stopSequence?: number; predictionTimestamp?: number; predictionSource?: string };
export const ARRIVAL_WINDOW_SECONDS = 3600;
const direction = (a: Arrival) => JSON.stringify([a.line.trim().toLocaleUpperCase('it-IT'), a.headsign.trim().replace(/\s+/g, ' ').toLocaleUpperCase('it-IT'), a.serviceDate || '']);
type TimedArrival = Arrival & { time: number };
const priority = (a: Arrival) => a.kind === 'live' ? 0 : 1;
const displayPriority = (a: Arrival) => a.kind === 'live' ? a.atTerminus ? 1 : 0 : 2;
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
    .sort((a, b) => displayPriority(a) - displayPriority(b) || a.time - b.time);
}
export function visibleArrivals(arrivals: Arrival[], now: number, liveFresh: boolean) {
  const current = arrivals.map(a => {
    const item = a.kind === 'live' && (!liveFresh || (a.predictionTimestamp !== undefined && now - a.predictionTimestamp > 180))
      ? { ...a, time: a.scheduledTime || 0, kind: 'scheduled' } : a;
    const terminalFresh = item.atTerminusTimestamp !== undefined
      ? now >= item.atTerminusTimestamp && now - item.atTerminusTimestamp <= 180
      : liveFresh && item.kind === 'live';
    if (item.atTerminus && !terminalFresh) {
      return { ...item, atTerminus: false, vehicleId: item.kind === 'live' ? item.vehicleId : null };
    }
    return item;
  });
  // Out-of-window live rows must not hide timetable arrivals inside this hour.
  return prioritizeArrivals(current.filter(a => a.time !== null && a.time >= now && a.time <= now + ARRIVAL_WINDOW_SECONDS));
}

/** Never relabel a downstream arrival forecast as an origin departure. */
export function nextDeparture(arrival: Arrival, now: number): { time: number; kind: 'live' | 'scheduled' } | null {
  if (!arrival.atTerminus) return null;
  const upcoming = (value: number | undefined): value is number => typeof value === 'number' && Number.isFinite(value) && now <= value && value <= now + ARRIVAL_WINDOW_SECONDS;
  const predictionFresh = arrival.predictionTimestamp !== undefined && 0 <= now - arrival.predictionTimestamp && now - arrival.predictionTimestamp <= 180;
  if (upcoming(arrival.departureTime) && arrival.departureKind === 'live' && arrival.kind === 'live' && predictionFresh) {
    return { time: arrival.departureTime, kind: 'live' };
  }
  // A late bus can still be parked after its published departure time.
  // Keep that timetable time explicitly labelled, rather than inventing a new one.
  const scheduled = [arrival.scheduledDepartureTime, arrival.departureKind === 'scheduled' ? arrival.departureTime : undefined]
    .find((value): value is number => typeof value === 'number' && Number.isFinite(value) && value > 0);
  return scheduled !== undefined ? { time: scheduled, kind: 'scheduled' } : null;
}
