import AsyncStorage from '@react-native-async-storage/async-storage';
import { resolveArrivalDestination } from './src/lib/resolveArrival';
import React, { useEffect, useRef, useState } from 'react';
import { ActivityIndicator, AppState, Image, Pressable, ScrollView, StyleSheet, Text, TextInput, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { StatusBar } from 'expo-status-bar';
import { Slot, router, usePathname, useLocalSearchParams, useGlobalSearchParams } from 'expo-router';

const ATAC_LOGO = require('./assets/atac-logo.png');
const API = process.env.EXPO_PUBLIC_API_URL?.replace(/\/$/, '') || '';
export type Stop = { stop_id: string; name: string };
export type Route = { route_id: string; name: string; description: string };
type Health = { vehicles: { available: boolean }; updates: { available: boolean } };
type Arrivals = { apiVersion?: number; arrivals: { tripId: string; routeId?: string; variantId?: string; vehicleId?: string | null; line: string; headsign: string; time: number; scheduledTime?: number; kind: string }[]; liveAvailable: boolean; timestamp: number | null };
type Journey = { message: string; legs: { line: string; fromName: string; toName: string; departure: number; arrival: number; stops: number }[] };
async function api<T>(path: string, signal?: AbortSignal): Promise<T> {
  if (!API) throw new Error('Configura EXPO_PUBLIC_API_URL con l’indirizzo del servizio dati raggiungibile dall’iPhone.');
  const response = await fetch(`${API}/api/${path}`, { signal });
  const body = await response.json();
  if (!response.ok) throw new Error(body.error || 'Servizio non disponibile');
  return body;
}
export const clock = (t: number) => new Date(t * 1000).toLocaleTimeString('it-IT', { timeZone: 'Europe/Rome', hour: '2-digit', minute: '2-digit' });
export const stamp = (t: number | null) => t ? `Aggiornato alle ${clock(t)}` : 'Nessun aggiornamento disponibile';
export function Button({ text, onPress, disabled = false }: { text: string; onPress: () => void; disabled?: boolean }) {
  return <Pressable accessibilityRole="button" disabled={disabled} onPress={onPress} style={[s.button, disabled && { opacity: 0.4 }]}><Text style={s.buttonText}>{text}</Text></Pressable>;
}
export function Notice({ text }: { text: string }) { return <View accessibilityRole="alert" style={s.notice}><Text style={s.muted}>{text}</Text></View>; }
export function Badge({ name }: { name: string }) { return <View style={s.badge}><Text style={s.badgeText}>{name}</Text></View>; }

// Abort obsolete requests. Retained line boards check vehicle freshness separately.
export function useData<T>(path: string | null, interval = 0, retainWhileLoading = false) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const [revision, setRevision] = useState(0);
  useEffect(() => {
    setData(null); setError(''); setLoading(false);
    if (!path) return;
    let controller: AbortController | undefined;
    let inFlight = false;
    const load = () => {
      // A slow feed must finish instead of being aborted at every polling tick.
      if (inFlight) return;
      inFlight = true;
      controller?.abort(); controller = new AbortController(); const signal = controller.signal;
      if (!retainWhileLoading) setData(null);
      setError(''); setLoading(true);
      api<T>(path, signal).then(value => { if (!signal.aborted) setData(value); }).catch(e => { if (!signal.aborted) { if (!retainWhileLoading) setData(null); setError(e.message); } })
        .finally(() => { inFlight = false; if (!signal.aborted) setLoading(false); });
    };
    const delay = setTimeout(load, 250);
    const timer = interval ? setInterval(load, interval) : undefined;
    const listener = AppState.addEventListener('change', state => { if (state === 'active') load(); });
    return () => { controller?.abort(); clearTimeout(delay); if (timer) clearInterval(timer); listener.remove(); };
  }, [path, interval, revision, retainWhileLoading]);
  return { data, error, loading, retry: () => setRevision(n => n + 1) };
}
export function RequestState({ state }: { state: { loading: boolean; error: string; retry: () => void } }) {
  return <>{state.loading && <ActivityIndicator color="#a01d35" />}{!!state.error && <><Notice text={state.error} /><Button text="Riprova" onPress={state.retry} /></>}</>;
}
function StopSearch({ label, selected, onSelect }: { label: string; selected: Stop | null; onSelect: (stop: Stop | null) => void }) {
  const [query, setQuery] = useState('');
  const state = useData<Stop[]>(!selected && query.trim().length >= 2 ? `stops?q=${encodeURIComponent(query.trim())}` : null);
  return <View><Text style={s.label}>{label}</Text>
    <TextInput accessibilityLabel={label} placeholder="Nome o codice fermata" placeholderTextColor="#738197" value={selected?.name || query} onChangeText={text => { onSelect(null); setQuery(text); }} style={s.input} autoCorrect={false} />
    <RequestState state={state} />
    {state.data?.length === 0 && <Text style={s.muted}>Nessuna fermata trovata.</Text>}
    {!selected && state.data?.map(stop => <Pressable accessibilityRole="button" key={stop.stop_id} style={s.stop} onPress={() => onSelect(stop)}><Text style={s.body}>{stop.name}</Text><Text style={s.small}>Fermata {stop.stop_id}</Text></Pressable>)}
  </View>;
}
export default function App() {
  const [logoReady, setLogoReady] = useState(false);
  const pathname = usePathname();
  const params = useGlobalSearchParams<{ id?: string; variant?: string; stopId?: string; fromRouteId?: string; fromVariant?: string; fromLine?: string }>();
  const scroll = useRef<React.ComponentRef<typeof ScrollView>>(null);
  const home = pathname === '/';
  const lineDetail = pathname.startsWith('/line/');
  const stopDetail = pathname.startsWith('/stop/') || (pathname === '/stops' && Boolean(params.stopId));
  const tab = pathname === '/stops' ? 'stops' : pathname === '/plan' ? 'plan' : 'lines';
  useEffect(() => { scroll.current?.scrollTo({ y: 0, animated: false }); }, [pathname, params.stopId]);
  const returnToSearch = () => router.replace({ pathname: '/lines', params: { focus: '1' } });
  const returnFromStop = () => {
    if (params.fromRouteId && params.fromVariant) router.replace({ pathname: '/line/[id]/[variant]', params: { id: params.fromRouteId, variant: params.fromVariant } });
    else router.replace('/stops');
  };
  return <SafeAreaView style={s.safe}><StatusBar style="dark" />
    {!home && !lineDetail && !stopDetail && <View style={s.fixedHeader}><Pressable accessibilityRole="button" accessibilityLabel="Torna alla home" style={s.headerAction} onPress={() => router.replace('/')}><Text style={s.headerActionText}>← Home</Text></Pressable></View>}
    {!home && !lineDetail && !stopDetail && <View style={s.tabs}>{([['lines', 'Linee'], ['stops', 'Fermate'], ['plan', 'Percorso']] as const).map(([key, label]) => <Pressable accessibilityRole="tab" accessibilityState={{ selected: key === tab }} key={key} onPress={() => router.replace(key === 'lines' ? '/lines' : key === 'stops' ? '/stops' : '/plan')} style={[s.tab, key === tab && s.active]}><Text style={[s.tabText, key === tab && { color: '#a01d35' }]}>{label}</Text></Pressable>)}</View>}
    {(lineDetail || stopDetail) && <View style={s.fixedHeader}>
      <Pressable accessibilityRole="button" accessibilityLabel={lineDetail ? 'Torna a cerca linea' : params.fromRouteId && params.fromVariant ? 'Torna alla linea' : 'Torna a cerca fermata'} style={[s.headerAction, s.headerReturn]} onPress={lineDetail ? returnToSearch : returnFromStop}>
        <Text numberOfLines={1} style={s.headerActionText}>{lineDetail ? '← Cerca linea' : params.fromRouteId && params.fromVariant ? `← Torna alla linea ${params.fromLine || ''}` : '← Cerca fermata'}</Text>
      </Pressable>
      {lineDetail && params.id && params.variant && <Pressable accessibilityRole="button" accessibilityLabel="Cambia direzione" style={s.headerAction} onPress={() => router.replace({ pathname: '/line/[id]', params: { id: params.id! } })}><Text style={s.headerActionText}>Direzione</Text></Pressable>}
    </View>}
    <View style={[s.content, home && s.homeContent]}><ScrollView ref={scroll} keyboardShouldPersistTaps="handled" contentContainerStyle={home ? s.homeScroll : s.scroll}>
      <Slot />
    </ScrollView></View>
    {!logoReady && <View accessibilityLabel="Avvio app" style={s.launchScreen}>
      <Image source={ATAC_LOGO} resizeMode="contain" accessibilityLabel="Logo ATAC" style={s.launchLogo} onLoadEnd={() => requestAnimationFrame(() => requestAnimationFrame(() => setLogoReady(true)))} />
      <ActivityIndicator color="#a01d35" accessibilityLabel="Caricamento" />
    </View>}
  </SafeAreaView>;
}
export function Home() {
  const state = useData<Health>('status', 30000);
  const live = state.data?.vehicles.available && state.data?.updates.available;
  return <View style={s.home}>
    <View style={s.homeHeader}>
      <View style={s.row}><Text style={s.eyebrow}>ROMA · AUTOBUS</Text><Text style={[s.small, { color: live ? '#167450' : '#9b6a20' }]}>{live ? '● Feed live' : state.loading ? 'Verifica live…' : '● Live non disponibile'}</Text></View>
      <Image source={ATAC_LOGO} resizeMode="contain" accessibilityLabel="Logo ATAC" style={s.homeLogo} />
      <Text style={s.homeTitle}>La città, in movimento.</Text>
      <Text style={s.homeSubtitle}>Linee, fermate e percorsi a Roma</Text>
    </View>
    <View style={s.homeActions}>
      <Button text="Cerca linea" onPress={() => router.push('/lines')} />
      <Button text="Cerca fermata" onPress={() => router.push('/stops')} />
      <Button text="Calcola percorso" onPress={() => router.push('/plan')} />
    </View>
  </View>;
}
export function Lines() {
  const { focus, query: initialQuery } = useLocalSearchParams<{ focus?: string; query?: string }>();
  const [query, setQuery] = useState(initialQuery || '');
  const state = useData<Route[]>(`routes?q=${encodeURIComponent(query)}`);
  const [recent, setRecent] = useState<Route[]>([]);
  useEffect(() => { let active = true; AsyncStorage.getItem('recent-lines').then(raw => {
    const value: unknown = JSON.parse(raw || '[]');
    if (active && Array.isArray(value)) setRecent(value.filter(r => typeof r?.route_id === 'string' && typeof r?.name === 'string').slice(0, 10));
  }).catch(() => {}); return () => { active = false; }; }, []);
  const [recentError, setRecentError] = useState('');
  const [opening, setOpening] = useState(false);
  const openLine = async (candidate: Route) => {
    if (opening) return;
    setRecentError(''); setOpening(true);
    let route = candidate;
    try {
      if (!state.data?.some(r => r.route_id === candidate.route_id)) {
        const matches = await api<Route[]>(`routes?q=${encodeURIComponent(candidate.name)}`);
        const current = matches.find(r => r.name === candidate.name);
        if (!current) throw new Error('Linea non presente negli orari attuali.');
        route = current;
      }
    } catch (error) { setRecentError(error instanceof Error ? error.message : 'Impossibile aprire la linea.'); setOpening(false); return; }
    const next = [route, ...recent.filter(r => r.name !== route.name)].slice(0, 10);
    setRecent(next); void AsyncStorage.setItem('recent-lines', JSON.stringify(next)).catch(() => {});
    setOpening(false); router.push({ pathname: '/line/[id]', params: { id: route.route_id } });
  };
  const rank = new Map(recent.map((r, i) => [r.name, i]));
  const results = [...(state.data || [])];
  if (!query.trim() && state.data) for (const r of recent) if (!results.some(item => item.name === r.name)) results.push(r);
  results.sort((a, b) => (rank.get(a.name) ?? 100) - (rank.get(b.name) ?? 100));
  return <View style={s.stack}><TextInput autoFocus={focus === '1'} accessibilityLabel="Cerca linea autobus" value={query} onChangeText={setQuery} placeholder="Es. 64, 40, H…" placeholderTextColor="#738197" style={s.input} autoCorrect={false} /><RequestState state={state} />
    {state.data?.length === 0 && <Notice text="Nessuna linea trovata." />}
    {!!recentError && <Notice text={recentError} />}
    {opening && <ActivityIndicator color="#a01d35" />}
    {results.map(r => <Pressable disabled={opening} accessibilityRole="button" key={r.route_id} style={s.route} onPress={() => openLine(r)}><Badge name={r.name} /><View style={s.flex}><Text style={s.body}>{r.description || `Linea ${r.name}`}</Text><Text style={s.small}>Scegli la direzione →</Text></View><Text style={s.arrow}>›</Text></Pressable>)}
  </View>;
}
export function Stops() {
  const params = useLocalSearchParams<{ stopId?: string; stopName?: string; fromRouteId?: string; fromVariant?: string; fromLine?: string }>();
  const [stop, setStop] = useState<Stop | null>(() => params.stopId && params.stopName ? { stop_id: params.stopId, name: params.stopName } : null);
  useEffect(() => {
    if (params.stopId && params.stopName) setStop({ stop_id: params.stopId, name: params.stopName });
  }, [params.stopId, params.stopName]);
  const state = useData<Arrivals>(stop ? `stops/${encodeURIComponent(stop.stop_id)}/arrivals` : null, 30000, true);
  const [now, setNow] = useState(() => Date.now() / 1000);
  useEffect(() => {
    const timer = setInterval(() => setNow(Date.now() / 1000), 10000);
    return () => clearInterval(timer);
  }, []);
  const navigation = useRef<AbortController | null>(null);
  const [openingRoute, setOpeningRoute] = useState<string | null>(null);
  const [navigationError, setNavigationError] = useState('');
  useEffect(() => () => navigation.current?.abort(), []);
  const openArrival = async (arrival: Arrivals['arrivals'][number]) => {
    navigation.current?.abort();
    const controller = new AbortController(); navigation.current = controller;
    setOpeningRoute(arrival.tripId); setNavigationError('');
    try {
      const destination = await resolveArrivalDestination(arrival, api, controller.signal);
      if (!controller.signal.aborted) router.push(destination);
    } catch (error) {
      if (!controller.signal.aborted) setNavigationError((error as Error).message);
    } finally {
      if (!controller.signal.aborted) setOpeningRoute(null);
    }
  };
  const specificStop = Boolean(params.stopId);
  const liveFresh = Boolean(state.data?.liveAvailable && state.data.timestamp && now - state.data.timestamp <= 180);
  const arrivals = (state.data?.arrivals || []).map(a => a.kind === 'live' && !liveFresh
    ? { ...a, time: a.scheduledTime || 0, kind: 'scheduled' } : a).filter(a => a.time >= now && a.time <= now + 7200);
  return <View style={s.stack}>
    <Text style={s.heading}>{specificStop ? 'Autobus in arrivo' : 'Cerca fermata'}</Text>
    {specificStop && <Text style={s.muted}>Tutte le linee · prossime 2 ore</Text>}
    {specificStop && stop ? <View style={s.card}><Text style={s.heading}>{stop.name}</Text><Text style={s.small}>Fermata {stop.stop_id}</Text></View> : <StopSearch label="Fermata" selected={stop} onSelect={selected => { if (selected) router.push({ pathname: '/stop/[stopId]', params: { stopId: selected.stop_id, stopName: selected.name } }); else setStop(null); }} />}
    <RequestState state={state} />
    {openingRoute && <View style={s.row}><ActivityIndicator color="#a01d35" /><Text style={s.muted}>Apertura itinerario…</Text></View>}
    {!!navigationError && <Notice text={navigationError} />}
    {state.data && !state.data.apiVersion && state.data.arrivals.some(a => !a.routeId) && <Notice text="Il servizio dati va aggiornato e riavviato: alcune informazioni sulle vetture non sono disponibili." />}
    {stop && <Button text="Aggiorna arrivi" onPress={state.retry} disabled={state.loading} />}
    {state.data && <>
      <Text style={s.muted}>{liveFresh ? stamp(state.data.timestamp) : 'Previsioni live non disponibili · solo orari programmati'}</Text>
      <Text style={s.label}>{arrivals.length} {arrivals.length === 1 ? 'arrivo disponibile' : 'arrivi disponibili'} per questa fermata</Text>
      {!arrivals.length && <Notice text="Nessun arrivo disponibile nelle prossime 2 ore. Riprova o aggiorna gli orari." />}
      {arrivals.map((a,i) => <Pressable key={`${a.tripId}-${i}`} accessibilityRole="button" accessibilityLabel={`Linea ${a.line}, direzione ${a.headsign}${a.vehicleId ? `, vettura ${a.vehicleId}` : ''}, mostra itinerario e autobus`} disabled={openingRoute === a.tripId} style={s.route} onPress={() => { void openArrival(a); }}>
        <Badge name={a.line} /><View style={s.flex}><Text style={s.body}>{a.headsign || 'Autobus'}</Text><Text style={[s.small, a.kind === 'live' && { color: '#167450' }]}>{a.kind === 'live' ? `● Previsione live · vettura ${a.vehicleId || 'non disponibile'}` : 'Orario programmato'}</Text></View>
        <View style={s.arrivalTime}><Text style={s.time}>{Math.ceil((a.time - now) / 60) <= 1 ? '≤1 min' : `${Math.ceil((a.time - now) / 60)} min`}</Text><Text style={s.small}>{clock(a.time)} ›</Text></View>
      </Pressable>)}
    </>}
  </View>;
}

export function Planner() {
  const [origin, setOrigin] = useState<Stop | null>(null);
  const [destination, setDestination] = useState<Stop | null>(null);
  const [journey, setJourney] = useState<Journey | null>(null);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const request = useRef<AbortController | null>(null);
  useEffect(() => () => request.current?.abort(), []);
  const reset = () => { request.current?.abort(); setJourney(null); setError(''); setLoading(false); };
  const calculate = async () => {
    if (!origin || !destination) return;
    request.current?.abort(); const controller = new AbortController(); request.current = controller;
    setLoading(true); setJourney(null); setError('');
    try { setJourney(await api<Journey>(`plan?from=${encodeURIComponent(origin.stop_id)}&to=${encodeURIComponent(destination.stop_id)}`, controller.signal)); }
    catch (e) { if (!controller.signal.aborted) setError((e as Error).message); }
    finally { if (!controller.signal.aborted) setLoading(false); }
  };
  return <View style={s.stack}><Text style={s.heading}>Dove vuoi andare?</Text><Text style={s.muted}>Percorsi fra fermate, con partenza adesso</Text>
    <StopSearch label="Da" selected={origin} onSelect={v => { reset(); setOrigin(v); }} /><StopSearch label="A" selected={destination} onSelect={v => { reset(); setDestination(v); }} />
    <Button text={loading ? 'Calcolo in corso…' : 'Trova percorso →'} disabled={!origin || !destination || loading} onPress={() => { void calculate(); }} />
    <Notice text="Orari programmati: solo autobus, cambi alla stessa fermata e margine di 2 minuti. Nessun tratto a piedi; traffico e previsioni live non modificano l’itinerario." />
    {!!error && <Notice text={error} />}
    {journey && <><Text style={s.muted}>{journey.message}</Text>{journey.legs.map((leg,i) => <View key={i} style={s.card}><View style={s.row}><Badge name={leg.line} /><Text style={s.heading}>{clock(leg.departure)} → {clock(leg.arrival)}</Text></View><Text style={s.body}>{leg.fromName}</Text><Text style={s.muted}>↓ {leg.stops} {leg.stops === 1 ? 'fermata' : 'fermate'}</Text><Text style={s.body}>{leg.toName}</Text>{i < journey.legs.length-1 && <Text style={s.link}>Cambia autobus qui</Text>}</View>)}</>}
  </View>;
}
const s = StyleSheet.create({
  safe: { flex: 1, backgroundColor: '#f8f6f2' },
  homeLogo: { width: 100, height: 50, alignSelf: 'flex-start' }, launchScreen: { position: 'absolute', top: 0, right: 0, bottom: 0, left: 0, zIndex: 10, backgroundColor: '#ffffff', justifyContent: 'center', alignItems: 'center', gap: 24 }, launchLogo: { width: 200, height: 100 },
  fixedHeader: { minHeight: 56, paddingHorizontal: 16, paddingVertical: 6, flexDirection: 'row', justifyContent: 'flex-start', alignItems: 'center', gap: 8, borderBottomWidth: 1, borderBottomColor: '#e3dfd8', marginBottom: 12 },
  headerAction: { minHeight: 44, justifyContent: 'center', paddingHorizontal: 12, borderRadius: 10 }, headerReturn: { backgroundColor: '#ebe8e3', maxWidth: '80%' }, headerActionText: { color: '#a01d35', fontWeight: '700', fontSize: 13 },
  homeContent: { paddingHorizontal: 24 }, homeScroll: { flexGrow: 1 }, home: { flex: 1, gap: 32, width: '100%', maxWidth: 420, alignSelf: 'center', paddingVertical: 20 }, homeHeader: { gap: 8 }, homeActions: { gap: 20 }, eyebrow: { fontSize: 11, fontWeight: '800', color: '#a01d35', letterSpacing: 1.4, flex: 1 }, homeTitle: { fontSize: 34, fontWeight: '800', color: '#202d3a', marginTop: 14, letterSpacing: -1.3 }, homeSubtitle: { color: '#596878', fontSize: 16 }, flex: { flex: 1 }, stack: { gap: 14 },
  row: { flexDirection: 'row', alignItems: 'center', gap: 12 },
  tabs: { flexDirection: 'row', marginHorizontal: 20, padding: 5, backgroundColor: '#ebe8e3', borderRadius: 16, marginBottom: 12, marginTop: 8 },
  tab: { flex: 1, paddingVertical: 12, alignItems: 'center', borderRadius: 12 }, active: { backgroundColor: '#fff' }, tabText: { fontWeight: '600', color: '#596878', fontSize: 15 },
  content: { flex: 1, paddingHorizontal: 20 }, scroll: { paddingBottom: 30, gap: 14 }, heading: { color: '#202d3a', fontSize: 20, fontWeight: '700', flexShrink: 1 },
  muted: { color: '#596878', fontSize: 14, lineHeight: 21 }, small: { color: '#596878', fontSize: 11, lineHeight: 16 }, body: { color: '#202d3a', fontSize: 16, fontWeight: '600' },
  input: { backgroundColor: '#fff', borderWidth: 1, borderColor: '#dedbd5', borderRadius: 14, paddingHorizontal: 16, paddingVertical: 16, color: '#202d3a', fontSize: 16, marginVertical: 12 },
  route: { paddingVertical: 18, borderBottomWidth: 1, borderBottomColor: '#e3dfd8', flexDirection: 'row', gap: 14, alignItems: 'center' },
  badge: { minWidth: 52, borderRadius: 12, padding: 12, backgroundColor: '#a01d35', alignItems: 'center' }, badgeText: { color: '#fff', fontSize: 18, fontWeight: '800' },
  arrow: { fontSize: 28, color: '#a01d35' }, time: { fontSize: 20, fontWeight: '700', color: '#202d3a' },
  arrivalTime: { alignItems: 'flex-end', gap: 4 },
  button: { backgroundColor: '#a01d35', padding: 16, borderRadius: 14, alignItems: 'center' }, buttonText: { color: '#fff', fontWeight: '700', fontSize: 15 },
  notice: { backgroundColor: '#eee9df', padding: 14, borderRadius: 12, marginVertical: 8 }, card: { backgroundColor: '#fff', borderRadius: 18, padding: 18, gap: 12, borderColor: '#e4dfd8', borderWidth: 1 },
  link: { color: '#a01d35', fontWeight: '600', fontSize: 14 },
  label: { color: '#202d3a', fontSize: 13, fontWeight: '700' }, stop: { padding: 14, backgroundColor: '#fff', borderBottomWidth: 1, borderBottomColor: '#eee9df' },
});
