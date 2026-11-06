import test from 'node:test';
import assert from 'node:assert/strict';
import { feedState, realtimeState } from '../src/lib/feedStatus.ts';

const now = 1000;
const fresh = { available: true, timestamp: now };

test('both source feeds must have valid recent data for an operational status', () => {
  assert.equal(realtimeState({ vehicles: fresh, updates: fresh }, now), 'available');
  assert.equal(realtimeState({ vehicles: fresh, updates: { available: false, timestamp: null } }, now), 'partial');
  assert.equal(realtimeState({ vehicles: { available: false, timestamp: null }, updates: fresh }, now), 'partial');
});

test('a cached success expires without needing a new API response', () => {
  assert.equal(feedState({ ...fresh, timestamp: now - 180 }, now), 'available');
  assert.equal(feedState({ ...fresh, timestamp: now - 181 }, now), 'stale');
  assert.equal(realtimeState({ vehicles: fresh, updates: fresh }, now + 181), 'unavailable');
});

test('future feed timestamps follow the same tolerance as the backend', () => {
  assert.equal(feedState({ ...fresh, timestamp: now + 60 }, now), 'available');
  assert.equal(feedState({ ...fresh, timestamp: now + 61 }, now), 'stale');
});

test('retained bus positions and source errors never imply source availability', () => {
  assert.equal(feedState({ available: false, timestamp: null, retained: true }, now), 'unavailable');
  assert.equal(feedState({ ...fresh, error: 'Source unavailable' }, now), 'unavailable');
});

test('failed verification hides an older healthy result without blaming the source', () => {
  assert.equal(realtimeState({ vehicles: fresh, updates: fresh }, now, true), 'unknown');
  assert.equal(realtimeState(null, now), 'unknown');
});

test('incomplete responses cannot produce a healthy status', () => {
  for (const timestamp of [null, 0, NaN, Infinity]) assert.equal(feedState({ available: true, timestamp }, now), 'unknown');
  assert.equal(feedState(undefined, now), 'unknown');
  assert.equal(realtimeState({}, now), 'unknown');
});
