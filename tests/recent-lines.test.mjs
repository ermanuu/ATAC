import test from 'node:test';
import assert from 'node:assert/strict';
import { parseRecentLines, rememberRecentLine } from '../src/lib/recentLines.ts';

const route = (name, route_id = name) => ({ name, route_id, description: '' });

test('missing, damaged or non-list history is an empty history', () => {
  for (const raw of [null, '', '{', 'null', '{}', '"706"']) assert.deepEqual(parseRecentLines(raw), []);
});
test('existing stored lines survive migration; incomplete entries are ignored', () => {
  const rows = [route('706', 'old-706'), null, {}, { name: '708' }, { name: '', route_id: 'bad' }, { name: '170', route_id: ' ' }, { name: ' n705 ', route_id: ' night-705 ' }];
  assert.deepEqual(parseRecentLines(JSON.stringify(rows)), [route('706', 'old-706'), route('n705', 'night-705')]);
});
test('public line names identify recents even after route IDs change or capitalization differs', () => {
  assert.deepEqual(parseRecentLines(JSON.stringify([route('n705', 'current'), route('N705', 'outdated'), route('706')])).map(r => r.route_id), ['current', '706']);
});
test('reopening a line moves it first and stores its current route ID without changing the old list', () => {
  const before = [route('170'), route('n705', 'outdated'), route('706')];
  const snapshot = structuredClone(before);
  const updated = rememberRecentLine(before, route('N705', 'current'));
  assert.deepEqual(updated, [route('N705', 'current'), route('170'), route('706')]);
  assert.deepEqual(before, snapshot);
});
test('history keeps only the ten most recent distinct public lines', () => {
  const before = Array.from({ length: 12 }, (_, i) => route(String(i)));
  assert.deepEqual(parseRecentLines(JSON.stringify(before)), before.slice(0, 10));
  assert.deepEqual(rememberRecentLine(before.slice(0, 10), route('170')).map(r => r.name), ['170', '0', '1', '2', '3', '4', '5', '6', '7', '8']);
});
