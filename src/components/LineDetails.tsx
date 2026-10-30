import { GlassPressable, GlassSurface } from '../ui/Glass';
import React, { useEffect, useState } from 'react';
import { Linking, Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';
import { router, useLocalSearchParams } from 'expo-router';
import { Badge, Notice, RequestState, clock, useData, type Route } from '../../App';

type Variant = { id: string; headsign: string; direction: string; fromName: string; toName: string; stopCount: number };
type Vehicle = { id: string; timestamp: number; status: string; estimated: boolean; retained?: boolean; timestampSource?: string; lat: number | null; lon: number | null };
type Stop = { stop_id: string; name: string; sequence: number; vehiclesAt: Vehicle[]; vehiclesBefore: Vehicle[] };
type Directions = { route: Route; variants: Variant[] };
type Board = Directions & { selectedVariant: Variant; stops: Stop[]; departures: { tripId: string; serviceDate: string; time: number; scheduledTime: number; kind: string }[]; window: { from: number; to: number }; liveAvailable: boolean; timestamp: number | null; departureLiveAvailable: boolean; departureTimestamp: number | null; unplacedVehicleCount: number };

export function RouteDirections() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const state = useData<Directions>(id ? `routes/${encodeURIComponent(id)}` : null, 60000, true);
  return <View style={s.stack}>
    <RequestState state={state} />
    {state.data && <>
      <View style={s.row}><Badge name={state.data.route.name} /><Text style={s.heading}>Scegli la direzione</Text></View>
      <Text style={s.muted}>Verso quale capolinea vuoi andare?</Text>
      {!state.data.variants.length && <Notice text="Nessuna direzione in servizio ora o in partenza nella prossima ora." />}
      {state.data.variants.map(variant => <GlassPressable accessibilityRole="button" accessibilityLabel={`Direzione ${variant.headsign}, da ${variant.fromName}`} key={variant.id}
        style={s.direction} onPress={() => router.push({ pathname: '/line/[id]/[variant]', params: { id, variant: variant.id } })}>
        <View style={s.flex}><Text style={s.kicker}>DIREZIONE</Text><Text style={s.directionName}>{variant.headsign}</Text><Text style={s.muted}>Da {variant.fromName}</Text><Text style={s.small}>{variant.stopCount} fermate</Text></View><Text style={s.chevron}>›</Text>
      </GlassPressable>)}
    </>}
  </View>;
}

function BusThumbnail({ vehicle, caption, onPress }: { vehicle: Vehicle; caption: string; onPress: () => void }) {
  return <Pressable accessibilityRole="button" accessibilityLabel={`Autobus ${vehicle.id}, ${caption}${vehicle.retained ? ', ultima posizione nota' : vehicle.estimated ? ', posizione approssimata' : ''}`} onPress={onPress} hitSlop={8} style={s.busButton}>
    <View style={[s.busBody, vehicle.estimated && s.estimatedBus, vehicle.retained && s.retainedBus]}><View style={s.destinationPanel} /><View style={s.windshield} /><View style={s.lights}><View style={s.light} /><View style={s.light} /></View><View style={s.wheels}><View style={s.wheel} /><View style={s.wheel} /></View></View>
    <Text numberOfLines={1} style={s.busId}>{vehicle.estimated ? '≈ ' : ''}{vehicle.id}</Text>
  </Pressable>;
}

const positionStamp = (timestamp: number | null) => timestamp ? `Posizioni alle ${new Date(timestamp * 1000).toLocaleTimeString('it-IT', { timeZone: 'Europe/Rome', hour: '2-digit', minute: '2-digit', second: '2-digit' })}` : 'Nessun aggiornamento';
const fresh = (vehicle: Vehicle, now: number) => now >= vehicle.timestamp && now - vehicle.timestamp <= 180;
export function RouteTimeline() {
  const { id, variant } = useLocalSearchParams<{ id: string; variant: string }>();
  const state = useData<Board>(id && variant ? `routes/${encodeURIComponent(id)}?variant=${encodeURIComponent(variant)}` : null, 15000, true);
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
    <RequestState state={state} />
    {data && <>
      <Text style={s.heading}>{data.route.name}-{data.selectedVariant.headsign.toLocaleUpperCase('it-IT')}</Text>
      <GlassSurface style={s.departureStrip}>
        <Text numberOfLines={1} style={s.departureLabel} accessibilityLabel="Partenze dal capolinea, da dieci minuti fa a un’ora avanti">Partenze da {data.selectedVariant.fromName.toLocaleUpperCase('it-IT')}:</Text>
        <ScrollView horizontal showsHorizontalScrollIndicator={false} style={s.departureScroller} contentContainerStyle={s.departureTrack}>
          {departures.map((departure, i) => <Text key={`${departure.tripId}-${departure.serviceDate}-${i}`} numberOfLines={1} accessibilityLabel={`Partenza ${clock(departure.time)}, ${departure.kind === 'live' ? 'previsione live' : 'orario programmato'}`} style={[s.departureTime, departure.kind === 'live' && s.liveTime, departure.time < now && s.pastTime]}>{clock(departure.time)} <Text style={s.departureKind}>{departure.kind === 'live' ? 'live' : 'prog.'}</Text></Text>)}
          {!departures.length && <Text style={s.small}>Nessuna nella fascia −10/+60 min</Text>}
        </ScrollView>
      </GlassSurface>
      <Text style={s.heading}>Fermate</Text>
      <GlassSurface style={s.timeline}>
        {data.stops.map((stop, i) => {
          const before = stop.vehiclesBefore.filter(v => fresh(v, now)), at = stop.vehiclesAt.filter(v => fresh(v, now));
          return <View key={`${stop.stop_id}-${stop.sequence}`}>
            {!!before.length && <View style={s.incomingRow}>
              <View style={s.vehicleLane}>{before.map((v, j) => <BusThumbnail key={`${v.id}-${j}`} vehicle={{ ...v, retained: v.retained || Boolean(state.error) || now - v.timestamp > 90 }} caption={`in arrivo a ${stop.name}`} onPress={() => setVehicleInfo({ id: v.id, stopName: stop.name })} />)}</View>
              <View style={s.rail}><View style={s.line} /></View><View style={s.flex} />
            </View>}
            <View style={s.timelineRow}>
              <View style={s.vehicleLane}>{at.map((v,j) => <BusThumbnail key={`${v.id}-${j}`} vehicle={{ ...v, retained: v.retained || Boolean(state.error) || now - v.timestamp > 90 }} caption={`alla fermata ${stop.name}`} onPress={() => setVehicleInfo({ id: v.id, stopName: stop.name })} />)}</View>
              <View style={s.rail}><View style={[s.line, i === 0 && !before.length && s.invisible]} /><View style={[s.stopDot, i === data.stops.length - 1 && s.lastStop]} /><View style={[s.line, i === data.stops.length - 1 && s.invisible]} /></View>
              <Pressable accessibilityRole="button" accessibilityLabel={`Fermata ${stop.name}, codice ${stop.stop_id}, mostra arrivi`} style={s.stopName} onPress={() => router.push({ pathname: '/stop/[stopId]', params: { stopId: stop.stop_id, stopName: stop.name, fromRouteId: id, fromVariant: variant, fromLine: data.route.name } })}>
                <View style={s.stopTitle}><Text style={[s.stopText, s.flex]}>{stop.name}</Text><Text style={s.stopArrow}>›</Text></View><Text style={s.small}>{i === 0 ? 'Capolinea di partenza · ' : i === data.stops.length - 1 ? 'Capolinea di arrivo · ' : ''}{stop.stop_id}</Text>
              </Pressable>
            </View>

      {selected && vehicleInfo && [...stop.vehiclesAt, ...stop.vehiclesBefore].some(v => v.id === selected.id) && <GlassSurface accessibilityRole="alert" style={s.vehicleInfo}>
        <View style={s.row}><Text style={[s.heading, s.flex]}>Bus {selected.id}</Text><Pressable accessibilityRole="button" accessibilityLabel="Chiudi dettagli autobus" onPress={() => setVehicleInfo(null)}><Text style={s.close}>×</Text></Pressable></View>
        <Text style={s.muted}>{selected.retained || Boolean(state.error) || now - selected.timestamp > 90 ? 'Ultima posizione nota vicino a' : selected.estimated ? 'Posizione approssimata vicino a' : selected.status === 'STOPPED_AT' ? 'Alla fermata' : 'In arrivo a'} {vehicleInfo.stopName}</Text><Text style={s.small}>{selected.timestampSource === 'feed' ? 'Timestamp del feed · ' : 'Rilevazione veicolo · '}{positionStamp(selected.timestamp).replace('Posizioni alle ', '')}</Text>
        {selected.lat !== null && selected.lon !== null && <Pressable accessibilityRole="link" onPress={() => { void Linking.openURL(`https://maps.apple.com/?ll=${selected.lat},${selected.lon}&q=Bus%20${encodeURIComponent(data.route.name)}`); }}><Text style={s.link}>Apri posizione in Mappe ↗</Text></Pressable>}
      </GlassSurface>}
          </View>;
        })}
      </GlassSurface>
      <Text style={s.small}>{data.liveAvailable ? `${positionStamp(data.timestamp)} · ogni 15 s` : 'Posizioni live non disponibili'}</Text>
      {data.liveAvailable && !vehicleCount && <Notice text="Nessun bus localizzabile su questa direzione dal feed attuale. Non indica necessariamente assenza di servizio." />}
      {!!data.unplacedVehicleCount && <Notice text={`${data.unplacedVehicleCount} posizioni non associabili alle fermate: non vengono collocate sul percorso.`} />}
      <Text style={s.legend}>Bus tra due fermate: in arrivo alla successiva. ≈ indica una posizione GPS approssimata.</Text>

    </>}
  </View>;
}

const s = StyleSheet.create({
  flex: { flex: 1 }, stack: { gap: 14 }, row: { flexDirection: 'row', alignItems: 'center', gap: 12 },
  heading: { color: '#202d3a', fontSize: 20, fontWeight: '700', flexShrink: 1 }, muted: { color: '#596878', fontSize: 14, lineHeight: 21 }, small: { color: '#596878', fontSize: 11, lineHeight: 16 },
  kicker: { color: '#a01d35', fontSize: 10, fontWeight: '800', letterSpacing: 1.2, marginBottom: 4 },
  direction: { flexDirection: 'row', alignItems: 'center', padding: 20, borderRadius: 26, gap: 12 }, directionName: { color: '#202d3a', fontSize: 22, fontWeight: '700', marginBottom: 8 }, chevron: { color: '#a01d35', fontSize: 30 },
  departureStrip: { gap: 3, borderRadius: 20, paddingHorizontal: 10, paddingVertical: 7 },
  departureLabel: { flexShrink: 0, fontSize: 11, color: '#596878', fontWeight: '600' }, departureScroller: { height: 26 }, departureTrack: { minHeight: 26, alignItems: 'center', gap: 14, paddingRight: 6 }, departureTime: { fontSize: 14, color: '#202d3a', fontWeight: '700' }, departureKind: { fontSize: 10, fontWeight: '400' }, liveTime: { color: '#167450' }, pastTime: { color: '#8b9298' },
  legend: { fontSize: 11, lineHeight: 17, color: '#596878' },
  timeline: { borderRadius: 26, paddingVertical: 14, paddingRight: 14, overflow: 'hidden' }, incomingRow: { flexDirection: 'row', alignItems: 'stretch', minHeight: 24 }, timelineRow: { flexDirection: 'row', alignItems: 'stretch', minHeight: 48 },
  vehicleLane: { width: 48, justifyContent: 'center', alignItems: 'center', paddingVertical: 1, gap: 2 }, rail: { width: 18, alignItems: 'center' }, line: { flex: 1, width: 3, backgroundColor: '#16845e', minHeight: 12 }, invisible: { backgroundColor: 'transparent' }, stopDot: { width: 10, height: 10, borderRadius: 5, backgroundColor: '#fff', borderWidth: 2, borderColor: '#16845e' }, lastStop: { backgroundColor: '#a01d35', borderColor: '#a01d35', borderRadius: 2 },
  stopName: { flex: 1, justifyContent: 'center', paddingLeft: 12, paddingVertical: 10, minHeight: 48 }, stopText: { color: '#a01d35', fontWeight: '700', fontSize: 15, lineHeight: 21 },
  stopTitle: { flexDirection: 'row', alignItems: 'center', gap: 10 }, stopArrow: { color: '#a01d35', fontSize: 22 },
  busButton: { width: 36, minHeight: 24, alignItems: 'center', justifyContent: 'center', paddingVertical: 1 }, busBody: { width: 12, height: 15, backgroundColor: '#a01d35', borderRadius: 4, padding: 2, justifyContent: 'space-between' }, retainedBus: { backgroundColor: '#92989d' }, estimatedBus: { backgroundColor: '#8c6a2e' }, destinationPanel: { height: 2, backgroundColor: '#f4d991', borderRadius: 1 }, windshield: { height: 5, backgroundColor: '#f8f6f2', borderRadius: 2 }, lights: { flexDirection: 'row', justifyContent: 'space-between' }, light: { width: 3, height: 2, borderRadius: 1, backgroundColor: '#fff1a8' }, wheels: { position: 'absolute', bottom: -2, left: 2, right: 2, flexDirection: 'row', justifyContent: 'space-between' }, wheel: { width: 3, height: 4, backgroundColor: '#202d3a', borderRadius: 1 }, busId: { fontSize: 8, color: '#a01d35', marginTop: 1, maxWidth: 36 },
  vehicleInfo: { borderRadius: 20, margin: 10, padding: 16, gap: 8 }, link: { color: '#a01d35', fontSize: 14, fontWeight: '600' }, close: { fontSize: 28, color: '#a01d35', paddingHorizontal: 10 },
});
