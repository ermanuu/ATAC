import test from 'node:test';
import assert from 'node:assert/strict';
import { departureLabel, departureState, groupDeparturesByHour, visibleDepartures } from '../src/lib/departures.ts';

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
