import test from 'node:test';
import assert from 'node:assert/strict';
import { visibleVehicles } from '../src/lib/vehicles.ts';

test('a temporarily omitted bus remains explicitly last-known', () => {
  const bus = { id: '2641', timestamp: 1000, retained: true };
  assert.deepEqual(visibleVehicles([bus], 1015), [bus]);
});

test('a failed poll keeps recent icons without changing their timestamps', () => {
  const bus = { id: '2641', timestamp: 1000 };
  assert.deepEqual(visibleVehicles([bus], 1015, true), [{ ...bus, retained: true }]);
  assert.equal(bus.retained, undefined);
  assert.deepEqual(visibleVehicles([bus], 1181, true), []);
});

test('positions become last-known at 90 seconds and expire at three minutes', () => {
  const bus = { id: '2641', timestamp: 1000 };
  assert.deepEqual(visibleVehicles([bus], 1090), [bus]);
  assert.deepEqual(visibleVehicles([bus], 1091), [{ ...bus, retained: true }]);
  assert.equal(visibleVehicles([bus], 1180).length, 1);
  assert.deepEqual(visibleVehicles([bus], 1181), []);
  assert.deepEqual(visibleVehicles([bus], 999), []);
});

test('a fresh GPS timestamp cannot rejuvenate an expired forecast location', () => {
  const bus = { timestamp: 1150, positionSource: 'predictions', predictionTimestamp: 1000 };
  assert.equal(visibleVehicles([bus], 1180).length, 1);
  assert.deepEqual(visibleVehicles([bus], 1181), []);
  assert.deepEqual(visibleVehicles([{ ...bus, predictionTimestamp: null }], 1180), []);
  assert.deepEqual(visibleVehicles([{ ...bus, predictionTimestamp: 1200 }], 1180), []);
});

test('an unchanged fresh snapshot keeps the icon current', () => {
  const bus = { id: '2641', timestamp: 1000, retained: false };
  assert.deepEqual(visibleVehicles([bus], 1015), [bus]);
});
