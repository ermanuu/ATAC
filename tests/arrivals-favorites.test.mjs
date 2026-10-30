import test from 'node:test';
import assert from 'node:assert/strict';
import { prioritizeArrivals, visibleArrivals } from '../src/lib/arrivals.ts';
import { parseFavoriteStops, toggleFavoriteStop } from '../src/lib/favoriteStops.ts';
const a=(tripId,time,kind='scheduled',extra={})=>({tripId,routeId:'706',line:'706',headsign:'ROTELLINI',serviceDate:'20261030',stopSequence:10,time,scheduledTime:time,kind,...extra});
test('live first; schedules are fallback per direction, not extra copies of a live direction',()=>{
 const result=prioritizeArrivals([a('scheduled706',10),a('other',20,'scheduled',{routeId:'700',line:'700'}),a('live706',30,'live')]);
 assert.deepEqual(result.map(x=>x.tripId),['live706','other']);
});
test('public line and direction share live fallback even when GTFS route IDs differ',()=>{
 const result=prioritizeArrivals([a('scheduled',10,'scheduled',{routeId:'static706'}),a('live',20,'live',{routeId:'live706',headsign:' rotellini '})]);
 assert.deepEqual(result.map(x=>x.tripId),['live']);
});
test('all real live buses remain; times are ordered inside each group',()=>{
 const result=prioritizeArrivals([a('l2',50,'live'),a('s2',30,'scheduled',{routeId:'700',line:'700'}),a('l1',40,'live'),a('s1',20,'scheduled',{routeId:'724',line:'724'})]);
 assert.deepEqual(result.map(x=>x.tripId),['l1','l2','s1','s2']);
});
test('opposite direction and next service day retain their schedules',()=>{
 const result=prioritizeArrivals([a('live',20,'live'),a('opposite',10,'scheduled',{headsign:'EUR FERMI (MB)'}),a('tomorrow',30,'scheduled',{serviceDate:'20261031'})]);
 assert.equal(result.length,3);
});
test('same trip instance uses its latest live record while loop occurrences remain distinct',()=>{
 const result=prioritizeArrivals([a('t',10),a('t',15,'live',{predictionTimestamp:100}),a('t',20,'live',{predictionTimestamp:110}),a('t',30,'live',{stopSequence:20})]);
 assert.deepEqual(result.map(x=>x.time),[20,30]);
});
test('expired forecasts fall back to schedules and no longer hide untracked trips',()=>{
 const result=visibleArrivals([a('live',1200,'live',{scheduledTime:1180,predictionTimestamp:800}),a('scheduled',1300)],1000,true);
 assert.deepEqual(result.map(x=>[x.tripId,x.kind,x.time]),[['live','scheduled',1180],['scheduled','scheduled',1300]]);
});
test('favorites survive serialization, are unique by exact stop ID and can be removed',()=>{
 const one={stop_id:'74373',name:'OCEANO ATLANTICO/PAVESE'};const two={stop_id:'74374',name:'OCEANO ATLANTICO/COLOMBO'};
 let list=toggleFavoriteStop([],one);list=toggleFavoriteStop(list,two);
 assert.deepEqual(parseFavoriteStops(JSON.stringify(list)),[two,one]);
 assert.deepEqual(toggleFavoriteStop(list,one),[two]);
 assert.equal(parseFavoriteStops(JSON.stringify([one,one,two])).length,2);
});
test('damaged or unrelated saved values cannot create broken favorite rows',()=>{
 assert.deepEqual(parseFavoriteStops('{bad'),[]);
 assert.deepEqual(parseFavoriteStops(JSON.stringify([null,{}, {stop_id:4,name:'Bad'}])),[]);
});
