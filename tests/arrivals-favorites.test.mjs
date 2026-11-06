import test from 'node:test';
import assert from 'node:assert/strict';
import { nextDeparture, prioritizeArrivals, visibleArrivals } from '../src/lib/arrivals.ts';
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
test('terminal metadata does not turn a schedule into a live arrival',()=>{
 const result=visibleArrivals([a('known-terminal',1100,'scheduled',{vehicleId:'2687',atTerminus:true,atTerminusTimestamp:950}),a('other-live',1400,'live',{vehicleId:'2789',predictionTimestamp:950}),a('untracked',1300)],1000,true);
 assert.deepEqual(result.map(x=>x.tripId),['other-live']);
 assert.equal(result[0].kind,'live');
});
test('terminal status expires using its position time independently of ETA availability',()=>{
 const bus=a('terminal',1300,'live',{vehicleId:'2687',atTerminus:true,atTerminusTimestamp:900,predictionTimestamp:1000});
 assert.equal(visibleArrivals([bus],1080,true)[0].atTerminus,true);
 const expired=visibleArrivals([bus],1081,true)[0];
 assert.equal(expired.atTerminus,false);
 assert.equal(expired.vehicleId,'2687');
 assert.equal(visibleArrivals([{...bus,atTerminusTimestamp:1200}],1081,true)[0].atTerminus,false);
});
test('past timetable rows do not become waiting rows because a bus is at its origin',()=>{
 const bus=a('late-terminal',900,'scheduled',{vehicleId:'2687',atTerminus:true,atTerminusTimestamp:950});
 const result=visibleArrivals([bus,a('untracked-past',900)],1000,true);
 assert.deepEqual(result,[]);
 assert.deepEqual(visibleArrivals([bus],1131,true),[]);
});
test('legacy observed and propagated rows are excluded while direct live arrivals remain',()=>{
 const bus=a('observed',null,'observed',{scheduledTime:1300,vehicleId:'2687',atTerminus:true,atTerminusTimestamp:950});
 const propagated=a('propagated',1300,'live',{predictionSource:'propagated',predictionTimestamp:950});
 const direct=a('direct',1400,'live',{predictionSource:'direct',predictionTimestamp:950});
 assert.deepEqual(visibleArrivals([bus,propagated,direct],1000,true).map(x=>x.tripId),['direct']);
 assert.deepEqual(visibleArrivals([bus],1131,false),[]);
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

test('next departure uses the origin departure, never the stop arrival forecast',()=>{
 const bus=a('terminal',1500,'live',{atTerminus:true,departureTime:1200,departureKind:'live',predictionTimestamp:1000});
 assert.deepEqual(nextDeparture(bus,1000),{time:1200,kind:'live'});
 assert.equal(nextDeparture(a('old-api',1500,'live',{atTerminus:true}),1000),null);
 assert.equal(nextDeparture({...bus,atTerminus:false},1000),null);
});
test('expired departure forecasts use only a valid labelled timetable fallback',()=>{
 const bus=a('terminal',1500,'live',{atTerminus:true,departureTime:1200,departureKind:'live',scheduledDepartureTime:1300,predictionTimestamp:800});
 assert.deepEqual(nextDeparture(bus,1000),{time:1300,kind:'scheduled'});
 assert.equal(nextDeparture({...bus,scheduledDepartureTime:900},1000),null);
});
test('past or missing departure times are not shown as upcoming departures',()=>{
 const bus=a('terminal',1500,'live',{atTerminus:true,departureTime:900,departureKind:'live',predictionTimestamp:1000});
 assert.equal(nextDeparture(bus,1000),null);
 assert.equal(nextDeparture({...bus,departureTime:NaN},1000),null);
 assert.equal(nextDeparture({...bus,departureTime:9000},1000),null);
});
