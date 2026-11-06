export type FeedStatus = { available: boolean; timestamp: number | null; error?: string; retained?: boolean };
export type RealtimeStatus = {
  provider?: string;
  vehiclesUrl?: string;
  updatesUrl?: string;
  vehicles?: FeedStatus;
  updates?: FeedStatus;
};
export type FeedState = 'available' | 'unavailable' | 'stale' | 'unknown';

export function feedState(feed: FeedStatus | undefined, now: number): FeedState {
  if (!feed || typeof feed.available !== 'boolean') return 'unknown';
  if (!feed.available || feed.error) return 'unavailable';
  if (typeof feed.timestamp !== 'number' || !Number.isFinite(feed.timestamp) || feed.timestamp <= 0) return 'unknown';
  // Match the source adapter's tolerance; a cached screen must also expire.
  const age = now - feed.timestamp;
  return age < -60 || age > 180 ? 'stale' : 'available';
}

export function realtimeState(status: RealtimeStatus | null, now: number, verificationFailed = false) {
  if (!status || verificationFailed) return 'unknown';
  const states = [feedState(status.vehicles, now), feedState(status.updates, now)];
  if (states.every(state => state === 'available')) return 'available';
  if (states.some(state => state === 'available')) return 'partial';
  return states.includes('unknown') ? 'unknown' : 'unavailable';
}
