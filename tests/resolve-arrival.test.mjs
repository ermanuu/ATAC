import test from 'node:test';
import assert from 'node:assert/strict';
import { resolveArrivalDestination } from '../src/lib/resolveArrival.ts';

test('new arrivals open the exact route and variant without another request', async () => {
  const destination = await resolveArrivalDestination({ routeId:'r1',variantId:'v1',line:'64',headsign:'Termini' },()=>{ throw new Error('unexpected fetch'); });
  assert.deepEqual(destination,{pathname:'/line/[id]/[variant]',params:{id:'r1',variant:'v1'}});
});
test('legacy arrivals without route metadata resolve the line and matching direction', async () => {
  const requests=[];
  const request=async path=>{ requests.push(path); return path.startsWith('routes?q=') ? [{route_id:'r1',name:'64'}] : {variants:[{id:'outbound',headsign:'Termini'},{id:'inbound',headsign:'S. Pietro'}]}; };
  const destination=await resolveArrivalDestination({line:'64',headsign:'Termini'},request);
  assert.deepEqual(destination,{pathname:'/line/[id]/[variant]',params:{id:'r1',variant:'outbound'}});
  assert.equal(requests.length,2);
});
test('ambiguous direction opens the direction chooser instead of guessing', async () => {
  const destination=await resolveArrivalDestination({routeId:'r1',line:'64',headsign:'Termini'},async()=>({variants:[{id:'a',headsign:'Termini'},{id:'b',headsign:'Termini'}]}));
  assert.deepEqual(destination,{pathname:'/line/[id]',params:{id:'r1'}});
});
test('duplicate line numbers open a populated line search', async () => {
  const destination=await resolveArrivalDestination({line:'64',headsign:'Termini'},async()=>[{route_id:'a',name:'64'},{route_id:'b',name:'64'}]);
  assert.deepEqual(destination,{pathname:'/lines',params:{query:'64'}});
});
test('missing route exposes an actionable error instead of doing nothing', async () => {
  await assert.rejects(resolveArrivalDestination({line:'64',headsign:'Termini'},async()=>[]),/non trovato/);
});
test('network errors propagate to the visible navigation error', async () => {
  await assert.rejects(resolveArrivalDestination({line:'64',headsign:'Termini'},async()=>{throw new Error('Servizio non disponibile');}),/Servizio non disponibile/);
});
