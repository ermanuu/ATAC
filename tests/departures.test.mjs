import test from 'node:test';
import assert from 'node:assert/strict';
import { departureState, visibleDepartures } from '../src/lib/departures.ts';

const now = 10000;
const departure = { tripId: 'trip', serviceDate: '20261106', time: now, scheduledTime: now, kind: 'scheduled' };

test('the strip includes exactly minus five minutes to plus one hour', () => {
  const times = [now-301, now-300, now-1, now, now+3600, now+3601];
  assert.deepEqual(visibleDepartures(times.map(time => ({ ...departure, time })), now).map(d => d.time), times.slice(1, 5));
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
