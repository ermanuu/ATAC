import { visibleArrivals, type Arrival } from './src/lib/arrivals';
import { parseFavoriteStops, toggleFavoriteStop } from './src/lib/favoriteStops';
import { LineHeaderProvider, useLineHeader } from './src/lib/LineHeader';
import { RefreshProvider, useRefresh } from './src/lib/Refresh';
import { GlassBackground, GlassPressable, GlassProvider, GlassSurface, glassStyle } from './src/ui/Glass';
import { NavIcon } from './src/ui/NavIcon';
import AsyncStorage from '@react-native-async-storage/async-storage';
import { resolveArrivalDestination } from './src/lib/resolveArrival';
import React, { useCallback, useEffect, useRef, useState } from 'react';
import { ActivityIndicator, AppState, Image, Platform, Pressable, RefreshControl, ScrollView, StyleSheet, Text, TextInput, View } from 'react-native';
import { SafeAreaView, useSafeAreaInsets } from 'react-native-safe-area-context';
import { StatusBar } from 'expo-status-bar';
import { Slot, router, usePathname, useLocalSearchParams, useGlobalSearchParams } from 'expo-router';

const ATAC_LOGO = require('./assets/bus-front.png');
const API = process.env.EXPO_PUBLIC_API_URL?.replace(/\/$/, '') || '';
export type Stop = { stop_id: string; name: string };
export type Route = { route_id: string; name: string; description: string };
type Health = { vehicles: { available: boolean }; updates: { available: boolean } };
type Arrivals = { apiVersion?: number; arrivals: Arrival[]; liveAvailable: boolean; timestamp: number | null };
type Journey = { message: string; legs: { line: string; fromName: string; toName: string; departure: number; arrival: number; stops: number }[] };
export async function api<T>(path: string, signal?: AbortSignal, force = false): Promise<T> {
  if (!API && Platform.OS !== 'web') throw new Error('Configura EXPO_PUBLIC_API_URL con l’indirizzo del servizio dati raggiungibile dall’iPhone.');
  const response = await fetch(`${API}/api/${path}${force ? `${path.includes('?') ? '&' : '?'}fresh=1` : ''}`, { signal });
  const body = await response.json();
  if (!response.ok) throw new Error(body.error || 'Servizio non disponibile');
  return body;
}
export const clock = (t: number) => new Date(t * 1000).toLocaleTimeString('it-IT', { timeZone: 'Europe/Rome', hour: '2-digit', minute: '2-digit' });
export const stamp = (t: number | null) => t ? `Aggiornato alle ${clock(t)}` : 'Nessun aggiornamento disponibile';
export function Button({ text, onPress, disabled = false }: { text: string; onPress: () => void; disabled?: boolean }) {
  return <GlassPressable accessibilityRole="button" floating disabled={disabled} onPress={onPress} style={[s.button, disabled && { backgroundColor: '#e3dfe3' }]}><Text style={s.buttonText}>{text}</Text></GlassPressable>;
}
export function Notice({ text }: { text: string }) { return <GlassSurface accessibilityRole="alert" style={s.notice}><Text style={s.muted}>{text}</Text></GlassSurface>; }
export function Badge({ name }: { name: string }) { return <View style={s.badge}><Text style={s.badgeText}>{name}</Text></View>; }

// Abort obsolete requests. Retained line boards check vehicle freshness separately.
export function useData<T>(path: string | null, interval = 0, retainWhileLoading = false) {
  const [data, setData] = useState<T | null>(null);
  const [receivedAt, setReceivedAt] = useState(0);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const { register } = useRefresh();
  const loader = useRef<(force?: boolean) => Promise<void>>(async () => {});
  const retry = useCallback(() => loader.current(true), []);
  useEffect(() => {
    setData(null); setError(''); setLoading(false);
    if (!path) return;
    let controller: AbortController | undefined;
    let pending: Promise<void> | null = null;
    let disposed = false;
    const load = (force = false): Promise<void> => {
      if (disposed) return Promise.resolve();
      // Finish slow polls; an explicit refresh then fetches a new source snapshot.
      if (pending) return force ? pending.then(() => load(true)) : pending;
      controller = new AbortController(); const signal = controller.signal;
      if (!retainWhileLoading) setData(null);
      if (!retainWhileLoading) setError(''); setLoading(true);
      pending = api<T>(path, signal, force).then(value => { if (!signal.aborted) { setData(value); setError(''); setReceivedAt(Date.now() / 1000); } })
        .catch(e => { if (!signal.aborted) { if (!retainWhileLoading) setData(null); setError(e.message); } })
        .finally(() => { pending = null; if (!signal.aborted) setLoading(false); });
      return pending;
    };
    loader.current = load;
    const unregister = register(load);
    // Returning from a stop must not reuse an older line snapshot from the cache.
    const delay = setTimeout(() => { void load(Boolean(interval)); }, 250);
    const timer = interval ? setInterval(() => { void load(); }, interval) : undefined;
    const listener = AppState.addEventListener('change', state => { if (state === 'active') void load(true); });
    return () => { disposed = true; unregister(); controller?.abort(); clearTimeout(delay); if (timer) clearInterval(timer); listener.remove(); };
  }, [path, interval, retainWhileLoading, register]);
  return { data, error, loading, retry, receivedAt };
}

export function RequestState({ state }: { state: { loading: boolean; error: string; retry: () => void } }) {
  return <>{state.loading && <ActivityIndicator color="#a01d35" />}{!!state.error && <><Notice text={state.error} /><Button text="Riprova" onPress={state.retry} disabled={state.loading} /></>}</>;
}
function StopSearch({ label, selected, onSelect }: { label: string; selected: Stop | null; onSelect: (stop: Stop | null) => void }) {
  const [query, setQuery] = useState('');
  const state = useData<Stop[]>(!selected && query.trim().length >= 2 ? `stops?q=${encodeURIComponent(query.trim())}` : null);
  return <View><Text style={s.label}>{label}</Text>
    <TextInput accessibilityLabel={label} placeholder="Nome o codice fermata" placeholderTextColor="#738197" value={selected?.name || query} onChangeText={text => { onSelect(null); setQuery(text); }} style={s.input} autoCorrect={false} />
    <RequestState state={state} />
    {state.data?.length === 0 && <Text style={s.muted}>Nessuna fermata trovata.</Text>}
    {!selected && state.data?.map(stop => <GlassPressable accessibilityRole="button" key={stop.stop_id} style={s.stop} onPress={() => onSelect(stop)}><Text style={s.body}>{stop.name}</Text><Text style={s.small}>Fermata {stop.stop_id}</Text></GlassPressable>)}
  </View>;
}
export default function App() { return <RefreshProvider><LineHeaderProvider><AppShell /></LineHeaderProvider></RefreshProvider>; }
function AppShell() {
  const { title } = useLineHeader();
  const { refresh, refreshing } = useRefresh();
  const insets = useSafeAreaInsets();
  const [logoReady, setLogoReady] = useState(false);
  const pathname = usePathname();
  const params = useGlobalSearchParams<{ id?: string; variant?: string; stopId?: string; fromRouteId?: string; fromVariant?: string; fromLine?: string }>();
  const scroll = useRef<React.ComponentRef<typeof ScrollView>>(null);
  const home = pathname === '/';
  const lineDetail = pathname.startsWith('/line/');
  const stopDetail = pathname.startsWith('/stop/') || (pathname === '/stops' && Boolean(params.stopId));
  const board = lineDetail && Boolean(params.id && params.variant);
  const lineTitle = title && title.routeId === params.id && title.variant === params.variant ? `${title.line}-${title.direction.toLocaleUpperCase('it-IT')}` : '';
  const tab = stopDetail || pathname === '/stops' ? 'stops' : pathname === '/plan' ? 'plan' : 'lines';
  useEffect(() => { scroll.current?.scrollTo({ y: 0, animated: false }); }, [pathname, params.stopId]);
  const returnToSearch = () => router.replace({ pathname: '/lines', params: { focus: '1' } });
  const returnFromStop = () => {
    if (params.fromRouteId && params.fromVariant) router.replace({ pathname: '/line/[id]/[variant]', params: { id: params.fromRouteId, variant: params.fromVariant } });
    else router.replace('/stops');
  };
  return <GlassProvider><View style={s.safe}><GlassBackground /><SafeAreaView edges={['top', 'left', 'right']} style={s.safeContent}><StatusBar style="dark" />
    {!home && !lineDetail && !stopDetail && <View style={s.fixedHeader}><GlassPressable floating accessibilityRole="button" accessibilityLabel="Torna alla home" style={s.headerAction} onPress={() => router.replace('/')}><Text style={s.headerActionText}>← Home</Text></GlassPressable></View>}

    {board && <View style={s.boardHeader}>
      <View style={s.headerLeft}><GlassPressable floating accessibilityRole="button" accessibilityLabel="Torna a cerca linea" style={s.boardAction} onPress={returnToSearch}><Text numberOfLines={1} adjustsFontSizeToFit minimumFontScale={0.85} style={s.boardActionText}>← Cerca linea</Text></GlassPressable></View>
      <Text accessibilityRole="header" accessibilityLabel={lineTitle || 'Caricamento linea'} numberOfLines={2} adjustsFontSizeToFit minimumFontScale={0.8} style={s.boardTitle}>{lineTitle || 'Linea…'}</Text>
      <View style={s.headerRight}><GlassPressable floating accessibilityRole="button" accessibilityLabel="Cambia Direzione" style={s.boardAction} onPress={() => router.replace({ pathname: '/line/[id]', params: { id: params.id! } })}><Text style={s.boardActionText}>Cambia Direzione</Text></GlassPressable></View>
    </View>}
    {!board && (lineDetail || stopDetail) && <View style={s.fixedHeader}>
      <GlassPressable floating accessibilityRole="button" accessibilityLabel={lineDetail ? 'Torna a cerca linea' : params.fromRouteId && params.fromVariant ? 'Torna alla linea' : 'Torna a cerca fermata'} style={[s.headerAction, s.headerReturn]} onPress={lineDetail ? returnToSearch : returnFromStop}>
        <Text numberOfLines={1} style={s.headerActionText}>{lineDetail ? '← Cerca linea' : params.fromRouteId && params.fromVariant ? `← Torna alla linea ${params.fromLine || ''}` : '← Cerca fermata'}</Text>
      </GlassPressable>

    </View>}
    <View style={[s.content, home && s.homeContent]}><ScrollView ref={scroll} alwaysBounceVertical refreshControl={<RefreshControl refreshing={refreshing} onRefresh={refresh} tintColor="#96002d" colors={['#96002d']} />} keyboardShouldPersistTaps="handled" contentContainerStyle={home ? s.homeScroll : s.scroll}>
      <Slot />
    </ScrollView></View>
    {!home && <View pointerEvents="box-none" style={[s.bottomDock, { paddingBottom: Math.max(insets.bottom, 12) }]}>
      <GlassSurface floating style={s.bottomBar} accessibilityRole="tablist">
        {([['lines', 'Linee'], ['stops', 'Fermate'], ['plan', 'Percorso']] as const).map(([key, label]) => <Pressable key={key} accessibilityRole="tab" accessibilityLabel={label} aria-selected={key === tab} accessibilityState={{ selected: key === tab }} onPress={() => router.replace(key === 'lines' ? '/lines' : key === 'stops' ? '/stops' : '/plan')} style={({ pressed }) => [s.bottomTab, key === tab && s.bottomTabActive, pressed && s.bottomTabPressed]}>
          <NavIcon kind={key} active={key === tab} /><Text style={[s.bottomTabText, key === tab && s.bottomTabSelected]}>{label}</Text>
        </Pressable>)}
      </GlassSurface>
    </View>}
    {!logoReady && <View accessibilityLabel="Avvio app" style={s.launchScreen}>
      <Image source={ATAC_LOGO} resizeMode="contain" accessibilityLabel="Logo Roma Autobus" style={s.launchLogo} onLoadEnd={() => requestAnimationFrame(() => requestAnimationFrame(() => setLogoReady(true)))} />
      <Text style={s.launchName}>ROMA · AUTOBUS</Text>
      <ActivityIndicator color="#96002d" accessibilityLabel="Caricamento" />
    </View>}
  </SafeAreaView></View></GlassProvider>;
}
export function Home() {
  const state = useData<Health>('status', 30000);
  const live = state.data?.vehicles.available && state.data?.updates.available;
  return <View style={s.home}>
    <View style={s.homeHeader}>
      <Image source={ATAC_LOGO} resizeMode="contain" accessibilityLabel="Logo Roma Autobus" style={s.homeLogo} />
      <Text style={s.eyebrow}>ROMA · AUTOBUS</Text>
      <Text style={[s.livePill, { color: live ? '#167450' : '#815b25' }]}>{live ? '● Feed live' : state.loading ? 'Verifica live…' : '● Live non disponibile'}</Text>
      <Text style={s.homeTitle}>La città, in movimento.</Text>
      <Text style={s.homeSubtitle}>Linee, fermate e percorsi a Roma</Text>
    </View>
    <View style={s.homeActions}>
      {([['lines', 'Cerca linea'], ['stops', 'Cerca fermata'], ['plan', 'Calcola percorso']] as const).map(([kind, label]) => <GlassPressable floating key={kind} accessibilityRole="button" style={s.homeAction} onPress={() => router.push(kind === 'lines' ? '/lines' : kind === 'stops' ? '/stops' : '/plan')}>
        <View style={s.homeActionIcon}><NavIcon kind={kind} active /></View><Text style={s.homeActionText}>{label}</Text><Text style={s.arrow}>›</Text>
      </GlassPressable>)}
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
    {results.map(r => <GlassPressable disabled={opening} accessibilityRole="button" key={r.route_id} style={s.route} onPress={() => openLine(r)}><Badge name={r.name} /><View style={s.flex}><Text style={s.body}>{r.description || `Linea ${r.name}`}</Text><Text style={s.small}>Scegli la direzione →</Text></View><Text style={s.arrow}>›</Text></GlassPressable>)}
  </View>;
}
export function Stops() {
  const [favorites, setFavorites] = useState<Stop[]>([]);
  const [favoritesReady, setFavoritesReady] = useState(false);
  const [favoriteError, setFavoriteError] = useState('');
  const savingFavorite = useRef(false);
  useEffect(() => {
    let active = true;
    AsyncStorage.getItem('favorite-stops').then(raw => { if (active) { setFavorites(parseFavoriteStops(raw)); setFavoritesReady(true); } })
      .catch(() => { if (active) setFavoriteError('Impossibile leggere le fermate preferite.'); });
    return () => { active = false; };
  }, []);
  const toggleFavorite = async (selected: Stop) => {
    if (!favoritesReady || savingFavorite.current) return;
    savingFavorite.current = true; setFavoriteError('');
    const next = toggleFavoriteStop(favorites, selected);
    try { await AsyncStorage.setItem('favorite-stops', JSON.stringify(next)); setFavorites(next); }
    catch { setFavoriteError('Impossibile salvare le fermate preferite. Riprova.'); }
    finally { savingFavorite.current = false; }
  };
  const params = useLocalSearchParams<{ stopId?: string; stopName?: string; fromRouteId?: string; fromVariant?: string; fromLine?: string }>();
  const [stop, setStop] = useState<Stop | null>(() => params.stopId && params.stopName ? { stop_id: params.stopId, name: params.stopName } : null);
  useEffect(() => {
    if (params.stopId && params.stopName) setStop({ stop_id: params.stopId, name: params.stopName });
  }, [params.stopId, params.stopName]);
  const state = useData<Arrivals>(stop ? `stops/${encodeURIComponent(stop.stop_id)}/arrivals` : null, 30000, true);
  const [tick, setNow] = useState(() => Date.now() / 1000);
  useEffect(() => {
    const timer = setInterval(() => setNow(Date.now() / 1000), 10000);
    return () => clearInterval(timer);
  }, []);
  const now = Math.max(tick, state.receivedAt);
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
  const liveFresh = Boolean(!state.error && state.data?.liveAvailable && state.data.timestamp && now - state.data.timestamp <= 180);
  const arrivals = visibleArrivals(state.data?.arrivals || [], now, liveFresh);
  return <View style={s.stack}>
    <Text style={s.heading}>{specificStop ? 'Autobus in arrivo' : 'Cerca fermata'}</Text>
    {!!favoriteError && <Notice text={favoriteError} />}
    {!specificStop && favorites.length > 0 && <View style={s.stack}>
      <Text style={s.heading}>Preferite</Text>
      {favorites.map(favorite => <GlassSurface key={favorite.stop_id} style={s.favoriteRow}>
        <Pressable accessibilityRole="button" accessibilityLabel={`Apri fermata preferita ${favorite.name}`} style={s.favoriteOpen} onPress={() => router.push({ pathname: '/stop/[stopId]', params: { stopId: favorite.stop_id, stopName: favorite.name } })}><Text style={s.body}>{favorite.name}</Text><Text style={s.small}>Fermata {favorite.stop_id} ›</Text></Pressable>
        <Pressable accessibilityRole="button" accessibilityLabel={`Rimuovi ${favorite.name} dalle preferite`} style={s.favoriteToggle} onPress={() => { void toggleFavorite(favorite); }}><Text style={s.favoriteStar}>★</Text></Pressable>
      </GlassSurface>)}
    </View>}
    {specificStop && stop ? <GlassSurface style={s.card}><View style={s.row}><Text style={[s.heading, s.flex]}>{stop.name}</Text><Pressable accessibilityRole="button" accessibilityLabel={favorites.some(f => f.stop_id === stop.stop_id) ? 'Rimuovi fermata dalle preferite' : 'Aggiungi fermata alle preferite'} accessibilityState={{ selected: favorites.some(f => f.stop_id === stop.stop_id), disabled: !favoritesReady }} disabled={!favoritesReady} style={s.favoriteToggle} onPress={() => { void toggleFavorite(stop); }}><Text style={s.favoriteStar}>{favorites.some(f => f.stop_id === stop.stop_id) ? '★' : '☆'}</Text></Pressable></View><Text style={s.small}>Fermata {stop.stop_id}</Text></GlassSurface> : <StopSearch label="Fermata" selected={stop} onSelect={selected => { if (selected) router.push({ pathname: '/stop/[stopId]', params: { stopId: selected.stop_id, stopName: selected.name } }); else setStop(null); }} />}
    <RequestState state={state} />
    {openingRoute && <View style={s.row}><ActivityIndicator color="#a01d35" /><Text style={s.muted}>Apertura itinerario…</Text></View>}
    {!!navigationError && <Notice text={navigationError} />}
    {state.data && !state.data.apiVersion && state.data.arrivals.some(a => !a.routeId) && <Notice text="Il servizio dati va aggiornato e riavviato: alcune informazioni sulle vetture non sono disponibili." />}
    {state.data && <>
      <Text style={s.muted}>{liveFresh ? stamp(state.data.timestamp) : 'Previsioni live non disponibili · solo orari programmati'}</Text>
      {!arrivals.length && <Notice text="Nessun arrivo disponibile nelle prossime 2 ore. Riprova o aggiorna gli orari." />}
      {arrivals.map((a,i) => <GlassPressable key={`${a.tripId}-${i}`} accessibilityRole="button" accessibilityLabel={`Linea ${a.line}, direzione ${a.headsign}${a.vehicleId ? `, vettura ${a.vehicleId}` : ''}, mostra itinerario e autobus`} disabled={openingRoute === a.tripId} style={s.route} onPress={() => { void openArrival(a); }}>
        <Badge name={a.line} /><View style={s.flex}><Text style={s.body}>{a.headsign || 'Autobus'}</Text><Text style={[s.small, a.kind === 'live' && { color: '#167450' }]}>{a.kind === 'live' ? `● Previsione live · vettura ${a.vehicleId || 'non disponibile'}` : 'Orario programmato'}</Text></View>
        <View style={s.arrivalTime}><Text style={[s.time, a.kind === 'live' && s.liveEta]}>{Math.ceil((a.time - now) / 60) <= 1 ? '≤1 min' : `${Math.ceil((a.time - now) / 60)} min`}</Text><Text style={[s.small, a.kind === 'live' && s.liveEta]}>{clock(a.time)} ›</Text></View>
      </GlassPressable>)}
    </>}
  </View>;
}

export function Planner() {
  const { register } = useRefresh();
  const [origin, setOrigin] = useState<Stop | null>(null);
  const [destination, setDestination] = useState<Stop | null>(null);
  const [journey, setJourney] = useState<Journey | null>(null);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const request = useRef<AbortController | null>(null);
  useEffect(() => () => request.current?.abort(), []);
  const reset = () => { request.current?.abort(); setJourney(null); setError(''); setLoading(false); };
  const calculate = useCallback(async () => {
    if (!origin || !destination) return;
    request.current?.abort(); const controller = new AbortController(); request.current = controller;
    setLoading(true); setJourney(null); setError('');
    try { setJourney(await api<Journey>(`plan?from=${encodeURIComponent(origin.stop_id)}&to=${encodeURIComponent(destination.stop_id)}`, controller.signal)); }
    catch (e) { if (!controller.signal.aborted) setError((e as Error).message); }
    finally { if (!controller.signal.aborted) setLoading(false); }
  }, [origin, destination]);
  useEffect(() => { if (journey) return register(async () => { await calculate(); }); }, [register, calculate, journey]);
  return <View style={s.stack}><Text style={s.heading}>Dove vuoi andare?</Text><Text style={s.muted}>Percorsi fra fermate, con partenza adesso</Text>
    <StopSearch label="Da" selected={origin} onSelect={v => { reset(); setOrigin(v); }} /><StopSearch label="A" selected={destination} onSelect={v => { reset(); setDestination(v); }} />
    <Button text={loading ? 'Calcolo in corso…' : 'Trova percorso →'} disabled={!origin || !destination || loading} onPress={() => { void calculate(); }} />
    <Notice text="Orari programmati: solo autobus, cambi alla stessa fermata e margine di 2 minuti. Nessun tratto a piedi; traffico e previsioni live non modificano l’itinerario." />
    {!!error && <Notice text={error} />}
    {journey && <><Text style={s.muted}>{journey.message}</Text>{journey.legs.map((leg,i) => <GlassSurface key={i} style={s.card}><View style={s.row}><Badge name={leg.line} /><Text style={s.heading}>{clock(leg.departure)} → {clock(leg.arrival)}</Text></View><Text style={s.body}>{leg.fromName}</Text><Text style={s.muted}>↓ {leg.stops} {leg.stops === 1 ? 'fermata' : 'fermate'}</Text><Text style={s.body}>{leg.toName}</Text>{i < journey.legs.length-1 && <Text style={s.link}>Cambia autobus qui</Text>}</GlassSurface>)}</>}
  </View>;
}
const s = StyleSheet.create({
  safe: { flex: 1, backgroundColor: '#f4f0f3' }, safeContent: { flex: 1 },
  homeLogo: { width: 240, height: 130, alignSelf: 'center' }, launchScreen: { position: 'absolute', top: 0, right: 0, bottom: 0, left: 0, zIndex: 10, backgroundColor: '#ffffff', justifyContent: 'center', alignItems: 'center', gap: 8 }, launchLogo: { width: 240, height: 240 }, launchName: { color: '#96002d', fontWeight: '800', fontSize: 12, letterSpacing: 2, marginBottom: 24 },
  boardHeader: { minHeight: 60, paddingHorizontal: 10, paddingVertical: 6, flexDirection: 'row', alignItems: 'center', gap: 6, marginBottom: 12 }, headerLeft: { width: 82 }, headerRight: { width: 96 }, boardAction: { minHeight: 44, borderRadius: 22, paddingHorizontal: 8, justifyContent: 'center', alignItems: 'center' }, boardActionText: { color: '#a01d35', fontWeight: '700', fontSize: 10, lineHeight: 14, textAlign: 'center' }, boardTitle: { flex: 1, textAlign: 'center', color: '#202d3a', fontWeight: '800', fontSize: 12, lineHeight: 16 },
  fixedHeader: { minHeight: 56, paddingHorizontal: 16, paddingVertical: 6, flexDirection: 'row', justifyContent: 'flex-start', alignItems: 'center', gap: 8, marginBottom: 12 },
  headerAction: { minHeight: 44, justifyContent: 'center', paddingHorizontal: 12, borderRadius: 22 }, headerReturn: { maxWidth: '100%' }, headerActionText: { color: '#a01d35', fontWeight: '700', fontSize: 13 },
  homeContent: { paddingHorizontal: 24 }, homeScroll: { flexGrow: 1 }, home: { flex: 1, gap: 28, width: '100%', maxWidth: 420, alignSelf: 'center', paddingTop: 12, paddingBottom: 36 }, homeHeader: { gap: 12, alignItems: 'center' }, homeActions: { gap: 14 }, eyebrow: { fontSize: 11, fontWeight: '800', color: '#a01d35', letterSpacing: 2.2 }, homeTitle: { fontSize: 34, fontWeight: '800', color: '#202d3a', marginTop: 6, letterSpacing: -1.3, textAlign: 'center' }, homeSubtitle: { color: '#536373', fontSize: 15, textAlign: 'center' }, flex: { flex: 1 }, stack: { gap: 14 },
  row: { flexDirection: 'row', alignItems: 'center', gap: 12 },
  livePill: { fontSize: 11, fontWeight: '600', paddingHorizontal: 12, paddingVertical: 6, borderRadius: 20, backgroundColor: 'rgba(255,255,255,0.65)', overflow: 'hidden' },
  homeAction: { flexDirection: 'row', alignItems: 'center', padding: 16, gap: 14, borderRadius: 26, minHeight: 78 }, homeActionIcon: { width: 44, height: 44, borderRadius: 16, backgroundColor: 'rgba(150,0,45,0.06)', alignItems: 'center', justifyContent: 'center' }, homeActionText: { flex: 1, color: '#253240', fontSize: 17, fontWeight: '700' },
  bottomDock: { position: 'absolute', bottom: 0, left: 0, right: 0, paddingHorizontal: 16, paddingTop: 12 }, bottomBar: { flexDirection: 'row', borderRadius: 32, padding: 6, maxWidth: 460, width: '100%', alignSelf: 'center' },
  bottomTab: { flex: 1, alignItems: 'center', justifyContent: 'center', gap: 4, paddingVertical: 10, borderRadius: 26, minHeight: 62 }, bottomTabActive: { backgroundColor: 'rgba(150,0,45,0.085)', boxShadow: 'inset 0 1px 0 rgba(255,255,255,0.9)' }, bottomTabPressed: { backgroundColor: 'rgba(150,0,45,0.12)' }, bottomTabText: { color: '#536373', fontSize: 11, fontWeight: '600' }, bottomTabSelected: { color: '#96002d', fontWeight: '800' },
  content: { flex: 1, paddingHorizontal: 20 }, scroll: { paddingBottom: 140, gap: 14 }, heading: { color: '#202d3a', fontSize: 20, fontWeight: '700', flexShrink: 1 },
  muted: { color: '#596878', fontSize: 14, lineHeight: 21 }, small: { color: '#596878', fontSize: 11, lineHeight: 16 }, body: { color: '#202d3a', fontSize: 16, fontWeight: '600' },
  input: { ...glassStyle, borderRadius: 24, paddingHorizontal: 16, paddingVertical: 16, color: '#202d3a', fontSize: 16, marginVertical: 12 },
  route: { padding: 16, flexDirection: 'row', gap: 14, alignItems: 'center' },
  badge: { minWidth: 52, borderRadius: 18, padding: 12, backgroundColor: 'rgba(150,0,45,0.10)', alignItems: 'center', borderWidth: 1, borderColor: 'rgba(150,0,45,0.08)' }, badgeText: { color: '#96002d', fontSize: 18, fontWeight: '800' },
  arrow: { fontSize: 28, color: '#a01d35' }, time: { fontSize: 20, fontWeight: '700', color: '#202d3a' },
  favoriteRow: { flexDirection: 'row', alignItems: 'center', paddingHorizontal: 12 }, favoriteOpen: { flex: 1, paddingVertical: 16, gap: 4 }, favoriteToggle: { minWidth: 44, minHeight: 44, alignItems: 'center', justifyContent: 'center' }, favoriteStar: { fontSize: 27, color: '#a01d35' },
  liveEta: { color: '#167450' },
  arrivalTime: { alignItems: 'flex-end', gap: 4 },
  button: { padding: 16, borderRadius: 24, alignItems: 'center' }, buttonText: { color: '#96002d', fontWeight: '700', fontSize: 15 },
  notice: { padding: 14, borderRadius: 20, marginVertical: 8 }, card: { borderRadius: 24, padding: 18, gap: 12 },
  link: { color: '#a01d35', fontWeight: '600', fontSize: 14 },
  label: { color: '#202d3a', fontSize: 13, fontWeight: '700' }, stop: { padding: 14, marginBottom: 8 },
});
