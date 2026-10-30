import { useLineHeader } from '../lib/LineHeader';
import { GlassPressable, GlassSurface } from '../ui/Glass';
import React, { useEffect, useState } from 'react';
import { Image, Linking, Pressable, ScrollView, Share, StyleSheet, Text, View } from 'react-native';
import { router, useLocalSearchParams } from 'expo-router';
import { Badge, Notice, RequestState, api, clock, useData, type Route } from '../../App';

type Variant = { id: string; headsign: string; direction: string; fromName: string; toName: string; stopCount: number };
type Vehicle = { id: string; vehicleId?: string | null; timestamp: number; status: string; estimated: boolean; retained?: boolean; timestampSource?: string; positionSource?: string; predictionTimestamp?: number | null; lat: number | null; lon: number | null };
type Stop = { stop_id: string; name: string; sequence: number; vehiclesAt: Vehicle[]; vehiclesBefore: Vehicle[] };
type Directions = { route: Route; variants: Variant[] };
type Board = Directions & { selectedVariant: Variant; stops: Stop[]; departures: { tripId: string; serviceDate: string; time: number; scheduledTime: number; kind: string }[]; window: { from: number; to: number }; liveAvailable: boolean; timestamp: number | null; departureLiveAvailable: boolean; departureTimestamp: number | null; unplacedVehicleCount: number };

export function RouteDirections() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const state = useData<Directions>(id ? `routes/${encodeURIComponent(id)}` : null, 30000, true);
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
  return <Pressable accessibilityRole="button" accessibilityLabel={`Autobus ${vehicle.vehicleId || 'numero vettura non disponibile'}, ${caption}${vehicle.positionSource === 'predictions' ? ', prossima fermata da previsioni live' : vehicle.retained ? ', ultima posizione nota' : vehicle.estimated ? ', posizione approssimata' : ''}`} onPress={onPress} hitSlop={8} style={s.busButton}>
    <Image source={require('../../assets/bus-front.png')} accessibilityIgnoresInvertColors resizeMode="contain" style={s.busImage} />
    <Text numberOfLines={1} style={s.busId}>{vehicle.vehicleId || '—'}</Text>
  </Pressable>;
}

const positionStamp = (timestamp: number | null) => timestamp ? `Posizioni alle ${new Date(timestamp * 1000).toLocaleTimeString('it-IT', { timeZone: 'Europe/Rome', hour: '2-digit', minute: '2-digit', second: '2-digit' })}` : 'Nessun aggiornamento';
const fresh = (vehicle: Vehicle, now: number) => now >= vehicle.timestamp && now - vehicle.timestamp <= 90 && !vehicle.retained && (vehicle.positionSource !== 'predictions' || Boolean(vehicle.predictionTimestamp && now - vehicle.predictionTimestamp <= 180));
export function RouteTimeline() {
  const { publish } = useLineHeader();
  const { id, variant } = useLocalSearchParams<{ id: string; variant: string }>();
  const state = useData<Board>(id && variant ? `routes/${encodeURIComponent(id)}?variant=${encodeURIComponent(variant)}` : null, 30000, true);
  const [sharing, setSharing] = useState(false);
  const [shareError, setShareError] = useState('');
  const [vehicleInfo, setVehicleInfo] = useState<{ id: string; stopName: string } | null>(null);
  const [tick, setNow] = useState(() => Date.now() / 1000);
  useEffect(() => {
    const timer = setInterval(() => setNow(Date.now() / 1000), 10000);
    return () => clearInterval(timer);
  }, []);
  const now = Math.max(tick, state.receivedAt);
  const data = state.data;
  useEffect(() => { if (data) publish({ routeId: id, variant, line: data.route.name, direction: data.selectedVariant.headsign }); }, [data, id, variant, publish]);
  const departures = data?.departures.filter(d => now - 600 <= d.time && d.time <= now + 3600) || [];
  const selected = data?.stops.flatMap(stop => [...stop.vehiclesAt, ...stop.vehiclesBefore]).find(v => v.id === vehicleInfo?.id && fresh(v, now) && !state.error);
  const vehicleCount = data?.stops.reduce((total, stop) => total + [...stop.vehiclesAt, ...stop.vehiclesBefore].filter(v => fresh(v, now) && !state.error).length, 0) || 0;
  return <View style={s.stack}>
    <RequestState state={state} />
    {data && <>
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
          const before = stop.vehiclesBefore.filter(v => fresh(v, now) && !state.error), at = stop.vehiclesAt.filter(v => fresh(v, now) && !state.error);
          return <View key={`${stop.stop_id}-${stop.sequence}`}>
            <View style={s.timelineRow}>
              <View style={s.vehicleLane}>
                {!!before.length && <ScrollView horizontal showsHorizontalScrollIndicator={false} style={s.busBefore} contentContainerStyle={s.busTrack}>
                  {before.map(v => <BusThumbnail key={v.id} vehicle={v} caption={`in arrivo a ${stop.name}`} onPress={() => setVehicleInfo({ id: v.id, stopName: stop.name })} />)}
                </ScrollView>}
                {!!at.length && <ScrollView horizontal showsHorizontalScrollIndicator={false} style={s.busAt} contentContainerStyle={s.busTrack}>
                  {at.map(v => <BusThumbnail key={v.id} vehicle={v} caption={`alla fermata ${stop.name}`} onPress={() => setVehicleInfo({ id: v.id, stopName: stop.name })} />)}
                </ScrollView>}
              </View>
              <View style={s.rail}><View style={[s.line, i === 0 && !before.length && s.invisible]} /><View style={[s.stopDot, i === data.stops.length - 1 && s.lastStop]} /><View style={[s.line, i === data.stops.length - 1 && s.invisible]} /></View>
              <Pressable accessibilityRole="button" accessibilityLabel={`Fermata ${stop.name}, codice ${stop.stop_id}, mostra arrivi`} style={s.stopName} onPress={() => router.push({ pathname: '/stop/[stopId]', params: { stopId: stop.stop_id, stopName: stop.name, fromRouteId: id, fromVariant: variant, fromLine: data.route.name } })}>
                <View style={s.stopTitle}><Text style={[s.stopText, s.flex]}>{stop.name}</Text><Text style={s.stopArrow}>›</Text></View><Text style={s.small}>{i === 0 ? 'Capolinea di partenza · ' : i === data.stops.length - 1 ? 'Capolinea di arrivo · ' : ''}{stop.stop_id}</Text>
              </Pressable>
            </View>

      {selected && vehicleInfo && [...stop.vehiclesAt, ...stop.vehiclesBefore].some(v => v.id === selected.id) && <GlassSurface accessibilityRole="alert" style={s.vehicleInfo}>
        <View style={s.row}><Text style={[s.heading, s.flex]}>Vettura {selected.vehicleId || 'non disponibile'}</Text><Pressable accessibilityRole="button" accessibilityLabel="Chiudi dettagli autobus" onPress={() => setVehicleInfo(null)}><Text style={s.close}>×</Text></Pressable></View>
        <Text style={s.muted}>{selected.positionSource === 'predictions' ? 'Prossima fermata da previsioni live:' : selected.retained || Boolean(state.error) || now - selected.timestamp > 90 ? 'Ultima posizione nota vicino a' : selected.estimated ? 'Posizione approssimata vicino a' : selected.status === 'STOPPED_AT' ? 'Alla fermata' : 'In arrivo a'} {stop.name}</Text>
        {selected.positionSource === 'predictions' && <Text style={s.small}>Prossimo arrivo previsto, non posizione GPS. Previsione alle {positionStamp(selected.predictionTimestamp || null).replace('Posizioni alle ', '')}.</Text>}
        <Text style={s.small}>{selected.timestampSource === 'feed' ? 'Timestamp del feed · ' : 'Rilevazione veicolo · '}{positionStamp(selected.timestamp).replace('Posizioni alle ', '')}</Text>
        <Pressable accessibilityRole="button" disabled={sharing} onPress={() => {
          setSharing(true); setShareError('');
          void api<unknown>(`vehicles/${encodeURIComponent(selected.vehicleId || selected.id)}/diagnostics`).then(source => Share.share({
            title: `Dati vettura ${selected.vehicleId || ''}`,
            message: JSON.stringify({ app: 'ATAC', line: data.route.name, direction: data.selectedVariant.headsign, displayedStop: { id: stop.stop_id, name: stop.name }, displayedVehicle: selected, source }, null, 2),
          })).catch(() => setShareError('Impossibile leggere i dati della vettura. Aggiorna il backend e riprova.')).finally(() => setSharing(false));
        }}><Text style={s.link}>{sharing ? 'Preparazione dati…' : 'Condividi dati della vettura'}</Text></Pressable>
        {!!shareError && <Text accessibilityRole="alert" style={s.small}>{shareError}</Text>}
        {selected.lat !== null && selected.lon !== null && <Pressable accessibilityRole="link" onPress={() => { void Linking.openURL(`https://maps.apple.com/?ll=${selected.lat},${selected.lon}&q=Bus%20${encodeURIComponent(selected.vehicleId || data.route.name)}`); }}><Text style={s.link}>Apri rilevazione GPS in Mappe ↗</Text></Pressable>}
      </GlassSurface>}
          </View>;
        })}
      </GlassSurface>
      <Text style={s.small}>{data.liveAvailable ? `${positionStamp(data.timestamp)} · ogni 30 s` : 'Posizioni live non disponibili'}</Text>
      {data.liveAvailable && !vehicleCount && <Notice text="Nessun bus localizzabile su questa direzione dal feed attuale. Non indica necessariamente assenza di servizio." />}
      {!!data.unplacedVehicleCount && <Notice text={`${data.unplacedVehicleCount} posizioni non associabili alle fermate: non vengono collocate sul percorso.`} />}
      <Text style={s.legend}>Icone aggiornate ogni 30 s: la prossima fermata può essere ricavata dalle previsioni live della stessa vettura; il dettaglio distingue previsione e GPS. Le misure oltre 90 s e lo storico non sono mostrati.</Text>

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
  timeline: { borderRadius: 26, paddingVertical: 14, paddingRight: 14, overflow: 'hidden' }, timelineRow: { flexDirection: 'row', alignItems: 'stretch', minHeight: 48 },
  vehicleLane: { width: 64, justifyContent: 'center', alignItems: 'center' }, rail: { width: 18, alignItems: 'center' }, line: { flex: 1, width: 3, backgroundColor: '#16845e', minHeight: 12 }, invisible: { backgroundColor: 'transparent' }, stopDot: { width: 10, height: 10, borderRadius: 5, backgroundColor: '#fff', borderWidth: 2, borderColor: '#16845e' }, lastStop: { backgroundColor: '#a01d35', borderColor: '#a01d35', borderRadius: 2 },
  stopName: { flex: 1, justifyContent: 'center', paddingLeft: 12, paddingVertical: 10, minHeight: 48 }, stopText: { color: '#a01d35', fontWeight: '700', fontSize: 15, lineHeight: 21 },
  stopTitle: { flexDirection: 'row', alignItems: 'center', gap: 10 }, stopArrow: { color: '#a01d35', fontSize: 22 },
  busBefore: { position: 'absolute', top: -12, left: 0, right: 0, height: 26 }, busAt: { height: 26, flexGrow: 0, width: '100%' }, busTrack: { flexGrow: 1, alignItems: 'center', justifyContent: 'center', gap: 2 },
  busButton: { width: 30, height: 26, alignItems: 'center', justifyContent: 'center' },
  busImage: { width: 22, height: 18, tintColor: '#a01d35' }, busId: { fontSize: 7, lineHeight: 8, color: '#a01d35', maxWidth: 30 },
  vehicleInfo: { borderRadius: 20, margin: 10, padding: 16, gap: 8 }, link: { color: '#a01d35', fontSize: 14, fontWeight: '600' }, close: { fontSize: 28, color: '#a01d35', paddingHorizontal: 10 },
});
