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
  return departures.filter(d => now - 300 <= d.time && d.time <= now + 5400);
}

export function groupDeparturesByHour(departures: Departure[]) {
  const hours = new Map<string, Departure[]>();
  const formatter = new Intl.DateTimeFormat('it-IT', { timeZone: 'Europe/Rome', hour: '2-digit', hourCycle: 'h23' });
  for (const departure of [...departures].sort((a, b) => a.time-b.time)) {
    const hour = formatter.format(new Date(departure.time * 1000));
    const group = hours.get(hour) || [];
    group.push(departure);
    hours.set(hour, group);
  }
  return [...hours].map(([hour, departures]) => ({ hour, departures }));
}

export function departureState(departure: Departure, now: number) {
  const age = now - (departure.positionTimestamp || 0);
  const positioned = age >= 0 && age <= 90;
  if (positioned && departure.atTerminus) return 'terminal';
  if ((positioned && departure.departed) || departure.time < now) return 'departed';
  return departure.kind === 'live' ? 'live' : 'scheduled';
}

export function departureLabel(departure: Departure, now: number) {
  if (departure.kind === 'live') return 'LIVE';
  return departureState(departure, now) === 'departed' ? 'Partito' : 'Program.';
}
