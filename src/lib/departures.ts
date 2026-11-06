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
  if (positioned && departure.departed) return 'departed';
  if (positioned && departure.atTerminus) return 'terminal';
  if (departure.time < now) return 'departed';
  return departure.kind === 'live' ? 'live' : 'scheduled';
}

export function groupScheduledDeparturesByDay(departures: Departure[]) {
  const days = new Map<string, Departure[]>();
  const minutes = new Set<number>();
  const formatter = new Intl.DateTimeFormat('en-GB', { timeZone: 'Europe/Rome', year: 'numeric', month: '2-digit', day: '2-digit' });
  const scheduled = departures.filter(d => Number.isFinite(d.scheduledTime))
    .map(d => ({ ...d, time: d.scheduledTime, kind: 'scheduled' })).sort((a, b) => a.time-b.time);
  for (const departure of scheduled) {
    const minute = Math.floor(departure.scheduledTime/60);
    if (minutes.has(minute)) continue;
    minutes.add(minute);
    const parts = formatter.formatToParts(new Date(departure.time*1000));
    const date = ['year', 'month', 'day'].map(type => parts.find(part => part.type === type)!.value).join('-');
    const group = days.get(date) || [];
    group.push(departure);
    days.set(date, group);
  }
  return [...days].map(([date, values]) => ({ date, hours: groupDeparturesByHour(values) }));
}

export function departureLabel(departure: Departure, now: number) {
  if (departureState(departure, now) === 'departed') return 'Partito';
  if (departure.kind === 'live') return 'LIVE';
  return 'Program.';
}

export function calendarDateOffset(date: string, offset: number) {
  const day = new Date(`${date}T12:00:00Z`);
  day.setUTCDate(day.getUTCDate()+offset);
  return day.toISOString().slice(0, 10);
}

export function nightDescription(date: string) {
  const weekday = (value: string) => new Date(`${value}T12:00:00Z`).toLocaleDateString('it-IT', { timeZone: 'Europe/Rome', weekday: 'long' });
  return `Notte tra ${weekday(date)} e ${weekday(calendarDateOffset(date, 1))}`;
}

export function scheduledTimetableSections(departures: Departure[], night = false, date?: string) {
  const days = groupScheduledDeparturesByDay(departures);
  const sections: (typeof days[number] & { nightDate?: string })[] = [];
  for (const candidate of days) {
    if (date && candidate.date !== date && candidate.date !== calendarDateOffset(date, 1)) continue;
    const day = date && candidate.date !== date ? { ...candidate, hours: candidate.hours.filter(group => Number(group.hour) < 3) } : candidate;
    if (!day.hours.length) continue;
    if (!night) { sections.push(day); continue; }
    const morning = day.hours.filter(group => Number(group.hour) < 12);
    const evening = day.hours.filter(group => Number(group.hour) >= 12);
    if (morning.length) sections.push({ date: day.date, hours: morning, nightDate: calendarDateOffset(day.date, -1) });
    if (evening.length) sections.push({ date: day.date, hours: evening, nightDate: day.date });
  }
  return sections;
}
