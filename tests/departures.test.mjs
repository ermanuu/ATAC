import test from 'node:test';
import assert from 'node:assert/strict';
import { calendarDateOffset, departureLabel, departureState, groupDeparturesByHour, groupScheduledDeparturesByDay, nightDescription, scheduledTimetableSections, visibleDepartures } from '../src/lib/departures.ts';

const now = 10000;
const departure = { tripId: 'trip', serviceDate: '20261106', time: now, scheduledTime: now, kind: 'scheduled' };

test('the strip includes exactly minus five minutes to plus ninety minutes', () => {
  const times = [now-301, now-300, now-1, now, now+3600, now+3601, now+5400, now+5401];
  assert.deepEqual(visibleDepartures(times.map(time => ({ ...departure, time })), now).map(d => d.time), times.slice(1, 7));
});

test('live stays visible for parked buses but confirmed departures take priority', () => {
  assert.equal(departureLabel({ ...departure, kind: 'live', atTerminus: true, positionTimestamp: now }, now), 'LIVE');
  assert.equal(departureLabel({ ...departure, kind: 'live', time: now-60, departed: true, positionTimestamp: now }, now), 'Partito');
  assert.equal(departureLabel({ ...departure, kind: 'live', time: now+60, departed: true, positionTimestamp: now }, now), 'Partito');
  assert.equal(departureLabel({ ...departure, kind: 'live', time: now-60, atTerminus: true, positionTimestamp: now }, now), 'LIVE');
  assert.equal(departureLabel({ ...departure, time: now-60 }, now), 'Partito');
  assert.equal(departureLabel({ ...departure, atTerminus: true, positionTimestamp: now }, now), 'Program.');
});

test('daily departures share one chronological row per Rome hour without mutating input', () => {
  const at = iso => ({ ...departure, time: Date.parse(iso)/1000 });
  const input = [at('2026-11-06T19:00:00Z'), at('2026-11-06T18:40:00Z'), at('2026-11-06T18:05:00Z')];
  const original = [...input];
  const groups = groupDeparturesByHour(input);
  assert.deepEqual(groups.map(g => g.hour), ['19', '20']);
  assert.deepEqual(groups[0].departures, [input[2], input[1]]);
  assert.deepEqual(input, original);
});

test('Rome hours use daylight saving and preserve midnight as 00', () => {
  const at = iso => ({ ...departure, time: Date.parse(iso)/1000 });
  assert.deepEqual(groupDeparturesByHour([at('2026-07-01T17:10:00Z')]).map(g => g.hour), ['19']);
  assert.deepEqual(groupDeparturesByHour([at('2026-11-05T23:10:00Z')]).map(g => g.hour), ['00']);
  assert.deepEqual(groupDeparturesByHour([]), []);
});

test('the timetable uses only scheduled times and separates dates after midnight', () => {
  const before = Date.parse('2026-11-06T23:50:00+01:00')/1000;
  const after = Date.parse('2026-11-07T00:30:00+01:00')/1000;
  const rows = [
    { ...departure, kind: 'live', scheduledTime: after, time: after+4500 },
    { ...departure, kind: 'live', scheduledTime: before, time: before+1200 },
  ];
  const groups = groupScheduledDeparturesByDay(rows);
  assert.deepEqual(groups.map(g => g.date), ['2026-11-06', '2026-11-07']);
  assert.deepEqual(groups.map(g => g.hours[0].hour), ['23', '00']);
  assert.equal(groups[0].hours[0].departures[0].time, before);
  assert.equal(rows[1].time, before+1200);
  assert.equal(rows[1].kind, 'live');
});

test('live-only rows without a timetable time cannot become scheduled departures', () => {
  assert.deepEqual(groupScheduledDeparturesByDay([{...departure, scheduledTime: undefined}]), []);
});

test('overlapping GTFS service dates do not repeat the same scheduled minute', () => {
  const time = Date.parse('2026-11-07T01:35:00+01:00')/1000;
  const groups = groupScheduledDeparturesByDay([
    {...departure, tripId:'night-from-friday', serviceDate:'20261106', scheduledTime:time},
    {...departure, tripId:'early-saturday', serviceDate:'20261107', scheduledTime:time},
  ]);
  assert.equal(groups[0].hours[0].departures.length, 1);
});

test('night captions use the two correct weekdays, including accented names', () => {
  assert.equal(nightDescription('2026-11-07'), 'Notte tra sabato e domenica');
  assert.equal(nightDescription('2026-11-04'), 'Notte tra mercoledì e giovedì');
  assert.equal(calendarDateOffset('2026-12-31', 1), '2027-01-01');
});

test('a calendar-day night timetable distinguishes the previous and following nights', () => {
  const at = value => ({...departure, scheduledTime:Date.parse(value)/1000});
  const sections = scheduledTimetableSections([
    at('2026-11-07T01:00:00+01:00'),
    at('2026-11-07T23:30:00+01:00'),
    at('2026-11-08T02:15:00+01:00'),
  ], true);
  assert.deepEqual(sections.map(s=>s.nightDate), ['2026-11-06','2026-11-07','2026-11-07']);
  assert.deepEqual(sections.map(s=>s.hours[0].hour), ['01','23','02']);
});

test('the visible timetable keeps the calendar day and only 00–02 of the following day', () => {
  const at = value => ({...departure, scheduledTime:Date.parse(value)/1000});
  const sections = scheduledTimetableSections([
    at('2026-11-05T23:59:00+01:00'), at('2026-11-06T00:00:00+01:00'),
    at('2026-11-06T23:59:00+01:00'), at('2026-11-07T00:00:00+01:00'),
    at('2026-11-07T02:59:00+01:00'), at('2026-11-07T03:00:00+01:00'),
  ], false, '2026-11-06');
  assert.deepEqual(sections.map(s=>s.hours.map(h=>h.hour)), [['00','23'],['00','02']]);
});

test('past times and buses already beyond the origin are marked departed', () => {
  assert.equal(departureState({ ...departure, time: now-1 }, now), 'departed');
  assert.equal(departureState({ ...departure, time: now+120, departed: true, positionTimestamp: now }, now), 'departed');
});

test('a recent parked bus is not shown as departed just because its time has passed', () => {
  const parked = { ...departure, time: now-60, atTerminus: true, positionTimestamp: now };
  assert.equal(departureState(parked, now), 'terminal');
  assert.equal(departureState(parked, now+91), 'departed');
});

test('future departures show live or programmed without trusting stale or future positions', () => {
  assert.equal(departureState(departure, now), 'scheduled');
  assert.equal(departureState({ ...departure, kind: 'live' }, now), 'live');
  assert.equal(departureState({ ...departure, departed: true, positionTimestamp: now-91 }, now), 'scheduled');
  assert.equal(departureState({ ...departure, departed: true, positionTimestamp: now+1 }, now), 'scheduled');
});
