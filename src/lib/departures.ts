export type Departure = {
  tripId: string;
  serviceDate: string;
  time: number;
  scheduledTime: number;
  kind: string;
  atTerminus?: boolean;
  departed?: boolean;
  positionTimestamp?: number;
};

export function visibleDepartures(departures: Departure[], now: number) {
  return departures.filter(d => now - 300 <= d.time && d.time <= now + 3600);
}

export function departureState(departure: Departure, now: number) {
  const age = now - (departure.positionTimestamp || 0);
  const positioned = age >= 0 && age <= 90;
  if (positioned && departure.atTerminus) return 'terminal';
  if ((positioned && departure.departed) || departure.time < now) return 'departed';
  return departure.kind === 'live' ? 'live' : 'scheduled';
}
