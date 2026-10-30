import React, { useEffect, useState } from 'react';
import { Linking, Pressable, StyleSheet, Text, View } from 'react-native';
import { router, useLocalSearchParams } from 'expo-router';
import { Badge, Button, Notice, RequestState, clock, stamp, useData, type Route } from '../../App';

type Variant = { id: string; headsign: string; direction: string; fromName: string; toName: string; stopCount: number };
type Vehicle = { id: string; timestamp: number; status: string; estimated: boolean; lat: number | null; lon: number | null };
type Stop = { stop_id: string; name: string; sequence: number; vehiclesAt: Vehicle[]; vehiclesBefore: Vehicle[] };
type Directions = { route: Route; variants: Variant[] };
type Board = Directions & { selectedVariant: Variant; stops: Stop[]; departures: { tripId: string; serviceDate: string; time: number; scheduledTime: number; kind: string }[]; window: { from: number; to: number }; liveAvailable: boolean; timestamp: number | null; departureLiveAvailable: boolean; departureTimestamp: number | null; unplacedVehicleCount: number };

export function RouteDirections() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const state = useData<Directions>(id ? `routes/${encodeURIComponent(id)}` : null);
  return <View style={s.stack}>
    <Button text="‹ Tutte le linee" onPress={() => router.replace('/')} />
    <RequestState state={state} />
    {state.data && <>
      <View style={s.row}><Badge name={state.data.route.name} /><Text style={s.heading}>Scegli la direzione</Text></View>
      <Text style={s.muted}>Verso quale capolinea vuoi andare?</Text>
      {!state.data.variants.length && <Notice text="Nessuna direzione disponibile nel calendario importato. Aggiorna gli orari." />}
      {state.data.variants.map(variant => <Pressable accessibilityRole="button" accessibilityLabel={`Direzione ${variant.headsign}, da ${variant.fromName}`} key={variant.id}
        style={s.direction} onPress={() => router.push({ pathname: '/line/[id]/[variant]', params: { id, variant: variant.id } })}>
        <View style={s.flex}><Text style={s.kicker}>DIREZIONE</Text><Text style={s.directionName}>{variant.headsign}</Text><Text style={s.muted}>Da {variant.fromName}</Text><Text style={s.small}>{variant.stopCount} fermate · arrivo a {variant.toName}</Text></View><Text style={s.chevron}>›</Text>
      </Pressable>)}
    </>}
  </View>;
}

function BusThumbnail({ vehicle, caption, onPress }: { vehicle: Vehicle; caption: string; onPress: () => void }) {
  return <Pressable accessibilityRole="button" accessibilityLabel={`Autobus ${vehicle.id}, ${caption}${vehicle.estimated ? ', posizione approssimata' : ''}`} onPress={onPress} style={s.busButton}>
    <View style={[s.busBody, vehicle.estimated && s.estimatedBus]}><View style={s.destinationPanel} /><View style={s.windshield} /><View style={s.lights}><View style={s.light} /><View style={s.light} /></View><View style={s.wheels}><View style={s.wheel} /><View style={s.wheel} /></View></View>
    <Text numberOfLines={1} style={s.busId}>{vehicle.estimated ? '≈ ' : ''}{vehicle.id}</Text>
  </Pressable>;
}

const fresh = (vehicle: Vehicle, now: number) => now >= vehicle.timestamp && now - vehicle.timestamp <= 180;
export function RouteTimeline() {
  const { id, variant } = useLocalSearchParams<{ id: string; variant: string }>();
  const state = useData<Board>(id && variant ? `routes/${encodeURIComponent(id)}?variant=${encodeURIComponent(variant)}` : null, 30000, true);
  const [vehicleInfo, setVehicleInfo] = useState<{ id: string; stopName: string } | null>(null);
  const [now, setNow] = useState(() => Date.now() / 1000);
  useEffect(() => {
    const timer = setInterval(() => setNow(Date.now() / 1000), 10000);
    return () => clearInterval(timer);
  }, []);
  const data = state.data;
  const departures = data?.departures.filter(d => now - 600 <= d.time && d.time <= now + 3600) || [];
  const selected = data?.stops.flatMap(stop => [...stop.vehiclesAt, ...stop.vehiclesBefore]).find(v => v.id === vehicleInfo?.id && fresh(v, now));
  const vehicleCount = data?.stops.reduce((total, stop) => total + [...stop.vehiclesAt, ...stop.vehiclesBefore].filter(v => fresh(v, now)).length, 0) || 0;
  return <View style={s.stack}>
    <Button text="‹ Cambia direzione" onPress={() => router.replace({ pathname: '/line/[id]', params: { id } })} />
    <RequestState state={state} />
    {data && <>
      <View style={s.row}><Badge name={data.route.name} /><View style={s.flex}><Text style={s.kicker}>DIREZIONE</Text><Text style={s.heading}>{data.selectedVariant.headsign}</Text><Text style={s.small}>Da {data.selectedVariant.fromName}</Text></View></View>
      <View style={s.card}>
        <Text style={s.heading}>Partenze dal capolinea</Text>
        <Text style={s.muted}>{data.selectedVariant.fromName}</Text>
        <Text style={s.small}>Da 10 minuti fa a un’ora avanti · {clock(data.window.from)}–{clock(data.window.to)}</Text>
        <View style={s.departures}>
          {departures.map((departure, i) => <View key={`${departure.tripId}-${departure.serviceDate}-${i}`} style={[s.departure, departure.kind === 'live' && s.liveDeparture, departure.time < now && s.pastDeparture]}>
            <Text style={s.departureTime}>{clock(departure.time)}</Text><Text style={s.small}>{departure.kind === 'live' ? '● Live' : 'Programmato'}</Text>
            {departure.time < now && <Text style={s.small}>{Math.ceil((now - departure.time) / 60)} min fa</Text>}
          </View>)}
        </View>
        {!departures.length && <Text style={s.muted}>Nessuna partenza disponibile in questa fascia oraria.</Text>}
        <Text style={s.small}>{data.departureLiveAvailable ? stamp(data.departureTimestamp) : 'Previsioni non disponibili · orari programmati'}</Text>
      </View>
      <Text style={s.heading}>Fermate</Text>
      <Text style={s.muted}>Tocca una fermata per gli arrivi o un autobus per i dettagli.</Text>
      <Text style={s.small}>{data.liveAvailable ? `${stamp(data.timestamp)} · aggiornamento ogni 30 s` : 'Posizioni live non disponibili'}</Text>
      {data.liveAvailable && !vehicleCount && <Notice text="Nessun bus localizzabile su questa direzione dal feed attuale. Non indica necessariamente assenza di servizio." />}
      {!!data.unplacedVehicleCount && <Notice text={`${data.unplacedVehicleCount} posizioni non associabili alle fermate: non vengono collocate sul percorso.`} />}
      <Text style={s.legend}>Bus tra due fermate: in arrivo alla successiva. ≈ indica una posizione GPS approssimata.</Text>
      {selected && vehicleInfo && <View accessibilityRole="alert" style={s.vehicleInfo}>
        <View style={s.row}><Text style={[s.heading, s.flex]}>Bus {selected.id}</Text><Pressable accessibilityRole="button" accessibilityLabel="Chiudi dettagli autobus" onPress={() => setVehicleInfo(null)}><Text style={s.close}>×</Text></Pressable></View>
        <Text style={s.muted}>{selected.estimated ? 'Posizione approssimata vicino a' : selected.status === 'STOPPED_AT' ? 'Alla fermata' : 'In arrivo a'} {vehicleInfo.stopName}</Text><Text style={s.small}>{stamp(selected.timestamp)}</Text>
        {selected.lat !== null && selected.lon !== null && <Pressable accessibilityRole="link" onPress={() => { void Linking.openURL(`https://maps.apple.com/?ll=${selected.lat},${selected.lon}&q=Bus%20${encodeURIComponent(data.route.name)}`); }}><Text style={s.link}>Apri posizione in Mappe ↗</Text></Pressable>}
      </View>}
      <View style={s.timeline}>
        {data.stops.map((stop, i) => {
          const before = stop.vehiclesBefore.filter(v => fresh(v, now)), at = stop.vehiclesAt.filter(v => fresh(v, now));
          return <View key={`${stop.stop_id}-${stop.sequence}`}>
            {!!before.length && <View style={s.timelineRow}>
              <View style={s.vehicleLane}>{before.map((v, j) => <BusThumbnail key={`${v.id}-${j}`} vehicle={v} caption={`in arrivo a ${stop.name}`} onPress={() => setVehicleInfo({ id: v.id, stopName: stop.name })} />)}</View>
              <View style={s.rail}><View style={s.line} /></View><Text style={[s.small, s.flex]}>In arrivo ↓</Text>
            </View>}
            <View style={s.timelineRow}>
              <View style={s.vehicleLane}>{at.map((v,j) => <BusThumbnail key={`${v.id}-${j}`} vehicle={v} caption={`alla fermata ${stop.name}`} onPress={() => setVehicleInfo({ id: v.id, stopName: stop.name })} />)}</View>
              <View style={s.rail}><View style={[s.line, i === 0 && !before.length && s.invisible]} /><View style={[s.stopDot, i === data.stops.length - 1 && s.lastStop]} /><View style={[s.line, i === data.stops.length - 1 && s.invisible]} /></View>
              <Pressable accessibilityRole="button" accessibilityLabel={`Fermata ${stop.name}, codice ${stop.stop_id}, mostra arrivi`} style={s.stopName} onPress={() => router.push({ pathname: '/stops', params: { stopId: stop.stop_id, stopName: stop.name } })}>
                <Text style={s.stopText}>{stop.name}</Text><Text style={s.small}>{i === 0 ? 'Capolinea di partenza · ' : i === data.stops.length - 1 ? 'Capolinea di arrivo · ' : ''}{stop.stop_id}</Text>
              </Pressable>
            </View>
          </View>;
        })}
      </View>
    </>}
  </View>;
}

const s = StyleSheet.create({
  flex: { flex: 1 }, stack: { gap: 14 }, row: { flexDirection: 'row', alignItems: 'center', gap: 12 },
  heading: { color: '#202d3a', fontSize: 20, fontWeight: '700', flexShrink: 1 }, muted: { color: '#596878', fontSize: 14, lineHeight: 21 }, small: { color: '#596878', fontSize: 11, lineHeight: 16 },
  kicker: { color: '#a01d35', fontSize: 10, fontWeight: '800', letterSpacing: 1.2, marginBottom: 4 },
  direction: { flexDirection: 'row', alignItems: 'center', padding: 20, backgroundColor: '#fff', borderWidth: 1, borderColor: '#dedbd5', borderRadius: 18, gap: 12 }, directionName: { color: '#202d3a', fontSize: 22, fontWeight: '700', marginBottom: 8 }, chevron: { color: '#a01d35', fontSize: 30 },
  card: { backgroundColor: '#fff', borderRadius: 18, borderWidth: 1, borderColor: '#e4dfd8', padding: 18, gap: 8 },
  departures: { flexDirection: 'row', flexWrap: 'wrap', gap: 10, marginVertical: 8 }, departure: { borderRadius: 12, padding: 10, backgroundColor: '#f1eee8', minWidth: 74 }, liveDeparture: { backgroundColor: '#e4f2e9' }, pastDeparture: { opacity: 0.6 }, departureTime: { fontSize: 21, color: '#202d3a', fontWeight: '700' },
  legend: { fontSize: 11, lineHeight: 17, color: '#596878' },
  timeline: { backgroundColor: '#fff', borderRadius: 18, paddingVertical: 14, paddingRight: 14, overflow: 'hidden' }, timelineRow: { flexDirection: 'row', alignItems: 'stretch', minHeight: 58 },
  vehicleLane: { width: 64, justifyContent: 'center', alignItems: 'center', paddingVertical: 5, gap: 8 }, rail: { width: 22, alignItems: 'center' }, line: { flex: 1, width: 3, backgroundColor: '#16845e', minHeight: 12 }, invisible: { backgroundColor: 'transparent' }, stopDot: { width: 10, height: 10, borderRadius: 5, backgroundColor: '#fff', borderWidth: 2, borderColor: '#16845e' }, lastStop: { backgroundColor: '#a01d35', borderColor: '#a01d35', borderRadius: 2 },
  stopName: { flex: 1, justifyContent: 'center', paddingLeft: 12, paddingVertical: 14, minHeight: 58 }, stopText: { color: '#a01d35', fontWeight: '700', fontSize: 15, lineHeight: 21 },
  busButton: { minWidth: 48, minHeight: 48, alignItems: 'center', justifyContent: 'center', paddingVertical: 3 }, busBody: { width: 24, height: 29, backgroundColor: '#a01d35', borderRadius: 5, padding: 3, justifyContent: 'space-between' }, estimatedBus: { backgroundColor: '#8c6a2e' }, destinationPanel: { height: 3, backgroundColor: '#f4d991', borderRadius: 1 }, windshield: { height: 11, backgroundColor: '#f8f6f2', borderRadius: 2 }, lights: { flexDirection: 'row', justifyContent: 'space-between' }, light: { width: 4, height: 3, borderRadius: 1, backgroundColor: '#fff1a8' }, wheels: { position: 'absolute', bottom: -3, left: 3, right: 3, flexDirection: 'row', justifyContent: 'space-between' }, wheel: { width: 4, height: 5, backgroundColor: '#202d3a', borderRadius: 1 }, busId: { fontSize: 9, color: '#a01d35', marginTop: 6, maxWidth: 58 },
  vehicleInfo: { borderRadius: 14, borderWidth: 1, borderColor: '#a01d35', backgroundColor: '#fff', padding: 16, gap: 8 }, link: { color: '#a01d35', fontSize: 14, fontWeight: '600' }, close: { fontSize: 28, color: '#a01d35', paddingHorizontal: 10 },
});
