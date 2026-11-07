import { Image, useImage, type ImageRef } from 'expo-image';
import { useLineHeader } from '../lib/LineHeader';
import { GlassPressable, GlassSurface } from '../ui/Glass';
import React, { useEffect, useMemo, useState } from 'react';
import { Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';
import { router, useLocalSearchParams } from 'expo-router';
import { Badge, Notice, RequestState, clock, useData, type Route } from '../../App';
import { visibleVehicles } from '../lib/vehicles';
import { useLiveClock } from '../lib/useLiveClock';
import { visibleDepartures, type Departure } from '../lib/departures';
import { useTheme, type ThemeColors } from '../ui/Theme';
import { layout, typography } from '../ui/design';
import { UpdateStatus } from '../ui/UpdateStatus';
import { DepartureTile } from './DepartureTile';
import { CourseSummary } from './CourseSummary';
import { LineAlerts } from './LineAlerts';

const BUS_ICON = require('../../assets/bus-front.png');

type Variant = { id: string; headsign: string; direction: string; fromName: string; toName: string; stopCount: number; category?: string };
type Vehicle = { id: string; vehicleId?: string | null; timestamp: number; status: string; tripId?: string; serviceDate?: string; departureTime?: number; estimated: boolean; retained?: boolean; timestampSource?: string; positionSource?: string; predictionTimestamp?: number | null; lat: number | null; lon: number | null };
type Stop = { stop_id: string; name: string; sequence: number; vehiclesAt: Vehicle[]; vehiclesBefore: Vehicle[] };
type Directions = { route: Route; variants: Variant[]; timetableVariants?: Variant[]; inactiveVariants?: Variant[] };
type Board = Directions & { selectedVariant: Variant; stops: Stop[]; departures: Departure[]; window: { from: number; to: number }; liveAvailable: boolean; timestamp: number | null; departureLiveAvailable: boolean; departureTimestamp: number | null; unplacedVehicleCount: number };

export function RouteDirections() {
  const { s } = useStyles();
  const { id } = useLocalSearchParams<{ id: string }>();
  const state = useData<Directions>(id ? `routes/${encodeURIComponent(id)}` : null, 10000, true);
  const inactiveVariants = state.data?.inactiveVariants ?? state.data?.timetableVariants?.filter(v => !state.data?.variants.some(active => active.id === v.id)) ?? [];
  return <View style={[s.stack, s.directionPage]}>
    <RequestState state={state} />
    {state.data && <>
      <View style={s.row}><Badge name={state.data.route.name} /><Text accessibilityRole="header" style={s.title}>Scegli la direzione</Text></View>
      <Text style={s.muted}>Verso quale capolinea vuoi andare?</Text>
      <LineAlerts key={id} routeId={id} />
      {!state.data.variants.length && <Notice text="Nessuna direzione in servizio ora o in partenza nei prossimi 90 minuti." />}
      {state.data.variants.map(variant => <GlassPressable accessibilityRole="button" accessibilityLabel={`Direzione ${variant.headsign}, da ${variant.fromName}`} key={variant.id}
        style={s.direction} onPress={() => router.push({ pathname: '/line/[id]/[variant]', params: { id, variant: variant.id } })}>
        <CourseSummary course={variant} /><Text style={s.chevron}>›</Text>
      </GlassPressable>)}
      {inactiveVariants.length > 0 && <InactiveDirections key={id} routeId={id} variants={inactiveVariants} />}
    </>}
  </View>;
}

function InactiveDirections({ routeId, variants }: { routeId: string; variants: Variant[] }) {
  const { s } = useStyles();
  const [inactiveOpen, setInactiveOpen] = useState(false);
  const groups = new Map<string, Variant[]>();
  const ordinary = (variant: Variant) => variant.category?.trim().toLocaleLowerCase('it-IT') === 'ordinaria';
  for (const variant of [...variants].sort((a, b) => Number(ordinary(b)) - Number(ordinary(a)))) {
    const category = variant.category || 'Altre varianti';
    groups.set(category, [...(groups.get(category) || []), variant]);
  }
  return <View style={s.inactiveSection}>
        <Pressable accessibilityRole="button" accessibilityLabel="Non attive" accessibilityHint={inactiveOpen ? 'Nasconde le direzioni non attive' : 'Mostra le direzioni non attive e i loro orari'} accessibilityState={{ expanded: inactiveOpen }} aria-expanded={inactiveOpen}
          onPress={() => setInactiveOpen(open => !open)} style={({ pressed }) => [s.inactiveToggle, pressed && s.inactiveTogglePressed]}>
          <Text style={s.inactiveHeading}>Non attive</Text><Text accessible={false} style={s.inactiveCaret}>{inactiveOpen ? '⌄' : '⌃'}</Text>
        </Pressable>
        {inactiveOpen && <View style={s.inactiveList}>{[...groups].flatMap(([category, variants]) => variants.map(variant => <GlassPressable key={variant.id} accessibilityRole="button" accessibilityLabel={`Consulta orari verso ${variant.headsign}, da ${variant.fromName}, ${category}`} style={s.inactiveDirection}
            onPress={() => router.push({ pathname: '/line/[id]/departures', params: { id: routeId, variant: variant.id, fromDirections: '1' } })}>
            <CourseSummary course={variant} compact /><Text style={s.inactiveArrow}>›</Text>
          </GlassPressable>))}</View>}
      </View>;
}

function BusThumbnail({ vehicle, caption, onPress, image }: { vehicle: Vehicle; caption: string; onPress: () => void; image: ImageRef | null }) {
  const { s, colors } = useStyles();
  return <Pressable accessibilityRole="button" accessibilityLabel={`Autobus ${vehicle.vehicleId || 'numero vettura non disponibile'}, ${caption}${vehicle.retained ? ', ultima posizione nota' : vehicle.positionSource === 'predictions' ? ', prossima fermata da previsioni live' : vehicle.estimated ? ', posizione approssimata' : ''}`} onPress={onPress} hitSlop={8} style={s.busButton}>
    <Image source={image || BUS_ICON} tintColor={colors.accent} placeholder={image || BUS_ICON} contentFit="contain" placeholderContentFit="contain" cachePolicy="memory-disk" transition={0} style={s.busImage} />
    <Text numberOfLines={1} style={s.busId}>{vehicle.vehicleId || '—'}</Text>
  </Pressable>;
}

const positionStamp = (timestamp: number | null) => timestamp ? `Posizioni alle ${new Date(timestamp * 1000).toLocaleTimeString('it-IT', { timeZone: 'Europe/Rome', hour: '2-digit', minute: '2-digit', second: '2-digit' })}` : 'Nessun aggiornamento';
export function RouteTimeline() {
  const { s, colors } = useStyles();
  // Share one decoded bitmap across rows: changing stop must not reload the icon.
  const busImage = useImage(BUS_ICON, { maxWidth: 96, maxHeight: 96, tintColor: colors.accent }, [colors.accent]);
  const { publish } = useLineHeader();
  const { id, variant } = useLocalSearchParams<{ id: string; variant: string }>();
  const state = useData<Board>(id && variant ? `routes/${encodeURIComponent(id)}?variant=${encodeURIComponent(variant)}` : null, 10000, true);
  const [vehicleInfo, setVehicleInfo] = useState<{ id: string; stopName: string } | null>(null);
  const tick = useLiveClock();
  const now = Math.max(tick, state.receivedAt);
  const data = state.data;
  useEffect(() => { if (data) publish({ routeId: id, variant, line: data.route.name, direction: data.selectedVariant.headsign, updating: state.loading }); }, [data, id, variant, publish, state.loading]);
  const departures = visibleDepartures(data?.departures || [], now);
  const visibleStops = data?.stops.map(stop => ({ ...stop,
    vehiclesAt: visibleVehicles(stop.vehiclesAt, now, Boolean(state.error)),
    vehiclesBefore: visibleVehicles(stop.vehiclesBefore, now, Boolean(state.error)),
  })) || [];
  const vehicles = visibleStops.flatMap(stop => [...stop.vehiclesAt, ...stop.vehiclesBefore]);
  const selected = vehicles.find(v => v.id === vehicleInfo?.id);
  const matchingDepartures = selected ? departures.filter(d => d.tripId === selected.tripId && (!selected.serviceDate || d.serviceDate === selected.serviceDate)) : [];
  const selectedDeparture = selected?.departureTime ?? (matchingDepartures.length === 1 ? matchingDepartures[0].time : null);
  const vehicleCount = vehicles.length;
  return <View style={s.stack}>
    <RequestState state={state} showLoading={!data} />
    {data && <>
      <LineAlerts key={id} routeId={id} />
      <GlassPressable accessibilityRole="button" accessibilityLabel={`Partenze da ${data.selectedVariant.fromName}, apri tutte le partenze della giornata`} style={s.departureStrip}
        onPress={() => router.push({ pathname: '/line/[id]/departures', params: { id, variant } })}>
        <View style={s.departureHeader}><Text numberOfLines={1} style={s.departureLabel}>Partenze da {data.selectedVariant.fromName}</Text><Text style={s.departureLink}>Tutte ›</Text></View>
        <ScrollView horizontal showsHorizontalScrollIndicator={false} style={s.departureScroller} contentContainerStyle={s.departureTrack}>
          {departures.map(departure => <DepartureTile key={`${departure.tripId}-${departure.serviceDate}`} departure={departure} now={now} />)}
          {!departures.length && <Text style={s.small}>Nessuna partenza tra −5 e +90 minuti</Text>}
        </ScrollView>
      </GlassPressable>
      <UpdateStatus timestamp={data.timestamp} message={!data.liveAvailable || state.error ? 'Posizioni live non disponibili' : undefined} />
      <Text style={s.heading}>Fermate</Text>
      <GlassSurface style={s.timeline}>
        {visibleStops.map((stop, i) => {
          const before = stop.vehiclesBefore, at = stop.vehiclesAt;
          return <View key={`${stop.stop_id}-${stop.sequence}`}>
            <View style={s.timelineRow}>
              <View style={s.vehicleLane}>
                {!!before.length && <ScrollView horizontal showsHorizontalScrollIndicator={false} style={s.busBefore} contentContainerStyle={s.busTrack}>
                  {before.map(v => <BusThumbnail key={v.id} vehicle={v} image={busImage} caption={`in arrivo a ${stop.name}`} onPress={() => setVehicleInfo({ id: v.id, stopName: stop.name })} />)}
                </ScrollView>}
                {!!at.length && <ScrollView horizontal showsHorizontalScrollIndicator={false} style={s.busAt} contentContainerStyle={s.busTrack}>
                  {at.map(v => <BusThumbnail key={v.id} vehicle={v} image={busImage} caption={i === 0 || i === data.stops.length - 1 ? `al capolinea ${stop.name}` : `alla fermata ${stop.name}`} onPress={() => setVehicleInfo({ id: v.id, stopName: stop.name })} />)}
                </ScrollView>}
              </View>
              <View style={s.rail}><View style={[s.line, i === 0 && !before.length && s.invisible]} /><View style={[s.stopDot, i === data.stops.length - 1 && s.lastStop]} /><View style={[s.line, i === data.stops.length - 1 && s.invisible]} /></View>
              <Pressable accessibilityRole="button" accessibilityLabel={`Fermata ${stop.name}, codice ${stop.stop_id}, mostra arrivi`} style={s.stopName} onPress={() => router.push({ pathname: '/stop/[stopId]', params: { stopId: stop.stop_id, stopName: stop.name, fromRouteId: id, fromVariant: variant, fromLine: data.route.name } })}>
                <View style={s.stopTitle}><Text style={[s.stopText, s.flex]}>{stop.name}</Text><Text style={s.stopArrow}>›</Text></View><Text style={s.small}>{i === 0 ? 'Capolinea di partenza · ' : i === data.stops.length - 1 ? 'Capolinea di arrivo · ' : ''}{stop.stop_id}</Text>
              </Pressable>
            </View>

      {selected && vehicleInfo && [...stop.vehiclesAt, ...stop.vehiclesBefore].some(v => v.id === selected.id) && <GlassSurface accessibilityRole="alert" style={s.vehicleInfo}>
        <View style={s.row}><Text style={[s.heading, s.flex]}>Vettura {selected.vehicleId || 'non disponibile'}</Text><Pressable accessibilityRole="button" accessibilityLabel="Chiudi dettagli autobus" onPress={() => setVehicleInfo(null)}><Text style={s.close}>×</Text></Pressable></View>
        <Text style={s.muted}>{selected.retained ? 'Ultima posizione nota vicino a' : selected.status === 'STOPPED_AT' && (i === 0 || i === data.stops.length - 1) && stop.vehiclesAt.some(v => v.id === selected.id) ? 'Al capolinea' : selected.positionSource === 'predictions' ? 'Prossima fermata da previsioni live:' : selected.estimated ? 'Posizione approssimata vicino a' : selected.status === 'STOPPED_AT' ? 'Alla fermata' : 'In arrivo a'} {stop.name}</Text>
        <Text style={s.small}>{selected.timestampSource === 'feed' ? 'Timestamp del feed · ' : 'Rilevazione veicolo · '}{positionStamp(selected.timestamp).replace('Posizioni alle ', '')}</Text>
        {i === 0 && selected.status === 'STOPPED_AT' && selectedDeparture != null && <Text style={s.expectedTime}>Partenza prevista: {clock(selectedDeparture)}</Text>}
      </GlassSurface>}
          </View>;
        })}
      </GlassSurface>
      {data.liveAvailable && !vehicleCount && <Notice text="Nessun bus localizzabile su questa direzione dal feed attuale. Non indica necessariamente assenza di servizio." />}
      {!!data.unplacedVehicleCount && <Notice text={`${data.unplacedVehicleCount} posizioni non associabili alle fermate: non vengono collocate sul percorso.`} />}

    </>}
  </View>;
}

const createStyles = (colors: ThemeColors) => StyleSheet.create({
  flex: { flex: 1 }, stack: { gap: layout.gap }, row: { flexDirection: 'row', alignItems: 'center', gap: 12 },
  directionPage: { flexGrow: 1 },
  inactiveSection: { marginTop: 'auto', paddingTop: 28, gap: 12 }, inactiveHeading: { ...typography.body, color: colors.muted, fontWeight: '700' },
  inactiveToggle: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', minHeight: 48, gap: 12 }, inactiveTogglePressed: { opacity: 0.7 }, inactiveCaret: { color: colors.muted, fontSize: 24, lineHeight: 28 }, inactiveList: { gap: 12 },
  inactiveDirection: { flexDirection: 'row', alignItems: 'center', gap: 10, padding: 12, borderRadius: 16, backgroundColor: colors.surfaceAlt, minHeight: 64 },
  inactiveArrow: { fontSize: 22, color: colors.muted },
  title: { ...typography.title, color: colors.text, flexShrink: 1 },
  heading: { ...typography.heading, color: colors.text, flexShrink: 1 }, muted: { ...typography.body, color: colors.muted }, small: { ...typography.caption, color: colors.muted },
  direction: { flexDirection: 'row', alignItems: 'center', padding: layout.cardPadding, borderRadius: layout.radius, gap: 12 }, chevron: { color: colors.accent, fontSize: 28 },
  departureStrip: { gap: 8, borderRadius: layout.radius, padding: 12 },
  departureHeader: { flexDirection: 'row', alignItems: 'center', gap: 12 },
  departureLabel: { ...typography.caption, flex: 1, color: colors.muted, fontWeight: '600' }, departureLink: { ...typography.caption, color: colors.accent, fontWeight: '700' },
  departureScroller: { minHeight: 52, flexGrow: 0 }, departureTrack: { alignItems: 'center', gap: 20 },
  expectedTime: { color: colors.live, backgroundColor: colors.liveSoft, padding: 8, borderRadius: 8, fontSize: 15, fontWeight: '700' },
  timeline: { borderRadius: layout.radius, paddingVertical: layout.cardPadding, paddingRight: layout.cardPadding, overflow: 'hidden' }, timelineRow: { flexDirection: 'row', alignItems: 'stretch', minHeight: 48 },
  vehicleLane: { width: 64, justifyContent: 'center', alignItems: 'center' }, rail: { width: 18, alignItems: 'center' }, line: { flex: 1, width: 3, backgroundColor: colors.rail, minHeight: 12 }, invisible: { backgroundColor: 'transparent' }, stopDot: { width: 10, height: 10, borderRadius: 5, backgroundColor: colors.surface, borderWidth: 2, borderColor: colors.rail }, lastStop: { backgroundColor: colors.accent, borderColor: colors.accent, borderRadius: 2 },
  stopName: { flex: 1, justifyContent: 'center', paddingLeft: 12, paddingVertical: 10, minHeight: 48 }, stopText: { ...typography.body, color: colors.accent, fontWeight: '700' },
  stopTitle: { flexDirection: 'row', alignItems: 'center', gap: 10 }, stopArrow: { color: colors.accent, fontSize: 22 },
  busBefore: { position: 'absolute', top: -12, left: 0, right: 0, height: 26 }, busAt: { height: 26, flexGrow: 0, width: '100%' }, busTrack: { flexGrow: 1, alignItems: 'center', justifyContent: 'center', gap: 2 },
  busButton: { width: 30, height: 26, alignItems: 'center', justifyContent: 'center' },
  busImage: { width: 22, height: 18 }, busId: { fontSize: 7, lineHeight: 8, color: colors.accent, maxWidth: 30 },
  vehicleInfo: { borderRadius: 20, margin: 10, padding: 16, gap: 8 }, link: { color: colors.accent, fontSize: 14, fontWeight: '600' }, close: { fontSize: 28, color: colors.accent, paddingHorizontal: 10 },
});

function useStyles() {
  const theme = useTheme();
  const s = useMemo(() => createStyles(theme.colors), [theme.colors]);
  return { ...theme, s };
}
