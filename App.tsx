import { nextDeparture, visibleArrivals, type Arrival } from './src/lib/arrivals';
import { parseFavoriteStops, toggleFavoriteStop } from './src/lib/favoriteStops';
import { LineHeaderProvider, useLineHeader } from './src/lib/LineHeader';
import { RefreshProvider, useRefresh } from './src/lib/Refresh';
import { GlassBackground, GlassPressable, GlassSurface, getSurfaceStyle } from './src/ui/Glass';
import { NavIcon } from './src/ui/NavIcon';
import { layout, typography } from './src/ui/design';
import { UpdateStatus } from './src/ui/UpdateStatus';
import { ThemeProvider, useTheme, type ThemeColors } from './src/ui/Theme';
import AsyncStorage from '@react-native-async-storage/async-storage';
import { resolveArrivalDestination } from './src/lib/resolveArrival';
import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { ActivityIndicator, AppState, Image, Platform, Pressable, RefreshControl, ScrollView, StyleSheet, Text, TextInput, View, useWindowDimensions } from 'react-native';
import { SafeAreaView, useSafeAreaInsets } from 'react-native-safe-area-context';
import { StatusBar } from 'expo-status-bar';
import { Slot, router, usePathname, useLocalSearchParams, useGlobalSearchParams } from 'expo-router';

const ROMABUS_LOGO = require('./assets/bus-front.png');
const API = process.env.EXPO_PUBLIC_API_URL?.replace(/\/$/, '') || '';
export type Stop = { stop_id: string; name: string };
export type Route = { route_id: string; name: string; description: string };
type Health = { vehicles: { available: boolean }; updates: { available: boolean } };
type Arrivals = { apiVersion?: number; arrivals: Arrival[]; liveAvailable: boolean; timestamp: number | null };
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
  const { s } = useStyles();
  return <GlassPressable accessibilityRole="button" floating disabled={disabled} onPress={onPress} style={[s.button, disabled && s.buttonDisabled]}><Text style={[s.buttonText, disabled && s.buttonDisabledText]}>{text}</Text></GlassPressable>;
}
export function Notice({ text }: { text: string }) {
  const { s } = useStyles();
  return <GlassSurface accessibilityRole="alert" style={s.notice}><Text style={s.muted}>{text}</Text></GlassSurface>;
}
export function Badge({ name }: { name: string }) {
  const { s } = useStyles();
  // Web text does not implement adjustsFontSizeToFit: reserve room for night-line prefixes too.
  const fontSize = Math.min(18, Math.floor(62 / Math.max(1, Array.from(name).length)));
  return <View style={s.badge}><Text numberOfLines={1} adjustsFontSizeToFit minimumFontScale={0.5} style={[s.badgeText, { fontSize }]}>{name}</Text></View>;
}

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

export function RequestState({ state, showLoading = true }: { state: { loading: boolean; error: string; retry: () => void }; showLoading?: boolean }) {
  const { colors } = useTheme();
  return <>{showLoading && state.loading && <ActivityIndicator color={colors.accent} />}{!!state.error && <><Notice text={state.error} /><Button text="Riprova" onPress={state.retry} disabled={state.loading} /></>}</>;
}
function StopSearch({ label, selected, onSelect }: { label: string; selected: Stop | null; onSelect: (stop: Stop | null) => void }) {
  const { s, colors, scheme } = useStyles();
  const [query, setQuery] = useState('');
  const state = useData<Stop[]>(!selected && query.trim().length >= 2 ? `stops?q=${encodeURIComponent(query.trim())}` : null);
  return <View><Text style={s.label}>{label}</Text>
    <TextInput accessibilityLabel={label} placeholder="Nome o codice fermata" placeholderTextColor={colors.placeholder} keyboardAppearance={scheme} selectionColor={colors.accent} value={selected?.name || query} onChangeText={text => { onSelect(null); setQuery(text); }} style={s.input} autoCorrect={false} />
    <RequestState state={state} />
    {state.data?.length === 0 && <Text style={s.muted}>Nessuna fermata trovata.</Text>}
    {!selected && state.data?.map(stop => <GlassPressable accessibilityRole="button" key={stop.stop_id} style={s.stop} onPress={() => onSelect(stop)}><Text style={s.body}>{stop.name}</Text><Text style={s.small}>Fermata {stop.stop_id}</Text></GlassPressable>)}
  </View>;
}
export default function App() { return <ThemeProvider><RefreshProvider><LineHeaderProvider><AppShell /></LineHeaderProvider></RefreshProvider></ThemeProvider>; }
function AppShell() {
  const { s, colors, scheme } = useStyles();
  const { title } = useLineHeader();
  const { refresh, refreshing } = useRefresh();
  const insets = useSafeAreaInsets();
  const { width } = useWindowDimensions();
  const [logoReady, setLogoReady] = useState(false);
  const pathname = usePathname();
  const params = useGlobalSearchParams<{ id?: string; variant?: string; stopId?: string; fromRouteId?: string; fromVariant?: string; fromLine?: string; fromDirections?: string }>();
  const scroll = useRef<React.ComponentRef<typeof ScrollView>>(null);
  const home = pathname === '/';
  const lineDetail = pathname.startsWith('/line/');
  const departurePage = lineDetail && pathname.endsWith('/departures');
  const stopDetail = pathname.startsWith('/stop/') || (pathname === '/stops' && Boolean(params.stopId));
  const board = lineDetail && !departurePage && Boolean(params.id && params.variant);
  const lineTitle = title && title.routeId === params.id && title.variant === params.variant ? `${title.line}-${title.direction.toLocaleUpperCase('it-IT')}` : '';
  const detailRefreshing = refreshing || Boolean(board && lineTitle && title?.updating);
  const tab = stopDetail || pathname === '/stops' ? 'stops' : pathname === '/settings' ? 'settings' : pathname === '/plan' ? 'plan' : 'lines';
  useEffect(() => { scroll.current?.scrollTo({ y: 0, animated: false }); }, [pathname, params.stopId]);
  const returnToSearch = () => router.replace({ pathname: '/lines', params: { focus: '1' } });
  const returnFromStop = () => {
    if (params.fromRouteId && params.fromVariant) router.replace({ pathname: '/line/[id]/[variant]', params: { id: params.fromRouteId, variant: params.fromVariant } });
    else router.replace('/stops');
  };
  const returnFromDepartures = () => params.variant && params.fromDirections !== '1'
    ? router.replace({ pathname: '/line/[id]/[variant]', params: { id: params.id!, variant: params.variant } })
    : router.replace({ pathname: '/line/[id]', params: { id: params.id! } });
  return <View style={s.safe}><GlassBackground /><SafeAreaView edges={['top', 'left', 'right']} style={s.safeContent}><StatusBar style={scheme === 'dark' ? 'light' : 'dark'} />
    {!home && !lineDetail && !stopDetail && <View style={s.fixedHeader}><GlassPressable floating accessibilityRole="button" accessibilityLabel="Torna alla home" style={s.headerAction} onPress={() => router.replace('/')}><Text style={s.headerActionText}>← Home</Text></GlassPressable></View>}

    {board && <View style={s.boardHeader}>
      <View style={s.headerLeft}><GlassPressable floating accessibilityRole="button" accessibilityLabel="Torna a cerca linea" style={s.boardAction} onPress={returnToSearch}><Text style={s.boardActionText}>← Linee</Text></GlassPressable></View>
      <Text accessibilityRole="header" accessibilityLabel={lineTitle || 'Caricamento linea'} numberOfLines={2} adjustsFontSizeToFit minimumFontScale={0.8} style={s.boardTitle}>{lineTitle || 'Linea…'}</Text>
      <View style={s.headerRight}><GlassPressable floating accessibilityRole="button" accessibilityLabel="Cambia Direzione" style={s.boardAction} onPress={() => router.replace({ pathname: '/line/[id]', params: { id: params.id! } })}><Text style={s.boardActionText}>Cambia Direzione</Text></GlassPressable></View>
    </View>}
    {!board && (lineDetail || stopDetail) && <View style={s.fixedHeader}>
      <GlassPressable floating accessibilityRole="button" accessibilityLabel={departurePage ? 'Torna alla linea' : lineDetail ? 'Torna a cerca linea' : params.fromRouteId && params.fromVariant ? 'Torna alla linea' : 'Torna a cerca fermata'} style={[s.headerAction, s.headerReturn]} onPress={departurePage ? returnFromDepartures : lineDetail ? returnToSearch : returnFromStop}>
        <Text numberOfLines={1} style={s.headerActionText}>{departurePage ? '← Torna alla linea' : lineDetail ? '← Cerca linea' : params.fromRouteId && params.fromVariant ? `← Torna alla linea ${params.fromLine || ''}` : '← Cerca fermata'}</Text>
      </GlassPressable>

    </View>}
    <View style={[s.content, home && s.homeContent]}><ScrollView ref={scroll} alwaysBounceVertical refreshControl={stopDetail ? undefined : <RefreshControl refreshing={refreshing} onRefresh={refresh} tintColor={colors.accent} colors={[colors.accent]} progressBackgroundColor={colors.surface} />} keyboardShouldPersistTaps="handled" contentContainerStyle={home ? s.homeScroll : [s.scroll, board && s.boardScroll]}>
      <Slot />
    </ScrollView></View>
    {(board || stopDetail || departurePage) && <View pointerEvents="box-none" style={[s.lineRefreshDock, { right: Math.max(layout.gutter, (width-layout.maxWidth)/2+layout.gutter), bottom: 96 + Math.max(insets.bottom, 12) }]}>
      <GlassPressable floating accessibilityRole="button" accessibilityLabel={departurePage ? 'Aggiorna partenze della giornata' : stopDetail ? 'Aggiorna arrivi della fermata' : 'Aggiorna fermate della linea'} aria-busy={detailRefreshing} accessibilityState={{ busy: detailRefreshing, disabled: detailRefreshing }} disabled={detailRefreshing} onPress={() => { void refresh(); }} style={s.lineRefreshButton}>
        {detailRefreshing ? <ActivityIndicator accessibilityLabel={stopDetail ? 'Aggiornamento arrivi in corso' : 'Aggiornamento fermate in corso'} color={colors.onAccent} /> : <Text style={s.lineRefreshIcon}>↻</Text>}
      </GlassPressable>
    </View>}
    {!home && <View pointerEvents="box-none" style={[s.bottomDock, { paddingBottom: Math.max(insets.bottom, 12) }]}>
      <GlassSurface floating style={s.bottomBar} accessibilityRole="tablist">
        {([['lines', 'Linee', '/lines'], ['stops', 'Fermate', '/stops'], ['plan', 'Percorso', '/plan'], ['settings', 'Impostazioni', '/settings']] as const).map(([key, label, path]) => <Pressable key={key} accessibilityRole="tab" accessibilityLabel={key === 'plan' ? 'Percorso, funzionalità in arrivo' : label} aria-selected={key === tab} aria-disabled={key === 'plan'} accessibilityState={{ selected: key === tab, disabled: key === 'plan' }} disabled={key === 'plan'} onPress={() => router.replace(path)} style={({ pressed }) => [s.bottomTab, key === tab && s.bottomTabActive, key === 'plan' && s.bottomTabUnavailable, pressed && s.bottomTabPressed]}>
          <NavIcon kind={key} active={key === tab} /><Text style={[s.bottomTabText, key === tab && s.bottomTabSelected]}>{label}</Text>
        </Pressable>)}
      </GlassSurface>
    </View>}
    {!logoReady && <View accessibilityLabel="Avvio app" style={s.launchScreen}>
      <Image source={ROMABUS_LOGO} resizeMode="contain" accessibilityLabel="Logo ROMABUS" style={[s.launchLogo, { tintColor: colors.accent }]} onLoadEnd={() => requestAnimationFrame(() => requestAnimationFrame(() => setLogoReady(true)))} />
      <Text style={s.launchName}>ROMABUS</Text>
      <ActivityIndicator color={colors.accent} accessibilityLabel="Caricamento" />
    </View>}
  </SafeAreaView></View>;
}
export function Home() {
  const { s, colors } = useStyles();
  const insets = useSafeAreaInsets();
  const state = useData<Health>('status', 10000);
  const live = state.data?.vehicles.available && state.data?.updates.available;
  return <View style={[s.home, { paddingBottom: Math.max(insets.bottom, 16) }]}>
    <View style={s.homeHeader}>
      <Image source={ROMABUS_LOGO} resizeMode="contain" accessibilityLabel="Logo ROMABUS" style={[s.homeLogo, { tintColor: colors.accent }]} />
      <Text style={s.eyebrow}>ROMABUS</Text>
      <Text style={[s.livePill, { color: live ? colors.live : colors.muted }]}>{live ? '● Feed LIVE' : state.loading ? 'Verifica live…' : '● LIVE non disponibile'}</Text>
      <Text style={s.homeTitle}>La città, in movimento.</Text>
      <Text style={s.homeSubtitle}>Linee, fermate e percorsi a Roma</Text>
    </View>
    <View style={s.homeActions}>
      {([['lines', 'Cerca linea'], ['stops', 'Cerca fermata'], ['plan', 'Calcola percorso']] as const).map(([kind, label]) => {
        const content = <>
          <View style={s.homeActionIcon}><NavIcon kind={kind} active={kind !== 'plan'} /></View>
          <View style={s.homeActionLabel}><Text style={s.homeActionText}>{label}</Text>{kind === 'plan' && <Text style={s.homeActionHint}>Funzionalità in arrivo</Text>}</View>
          {kind !== 'plan' && <Text style={s.arrow}>›</Text>}
        </>;
        return kind === 'plan'
          ? <GlassSurface key={kind} accessible accessibilityRole="button" accessibilityLabel="Calcola percorso, funzionalità in arrivo" aria-disabled accessibilityState={{ disabled: true }} style={[s.homeAction, s.homeActionUnavailable]}>{content}</GlassSurface>
          : <GlassPressable floating key={kind} accessibilityRole="button" style={s.homeAction} onPress={() => router.push(kind === 'lines' ? '/lines' : '/stops')}>{content}</GlassPressable>;
      })}
    </View>
    <View style={s.homeSettingsDock}>
      <GlassPressable accessibilityRole="button" accessibilityLabel="Apri impostazioni" onPress={() => router.push('/settings')} style={s.homeSettings}>
        <NavIcon kind="settings" active /><Text style={s.homeSettingsText}>Impostazioni</Text><Text style={s.arrow}>›</Text>
      </GlassPressable>
    </View>
  </View>;
}
export function Lines() {
  const { s, colors, scheme } = useStyles();
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
  return <View style={s.stack}><Text accessibilityRole="header" style={s.pageTitle}>Cerca linea</Text><TextInput autoFocus={focus === '1'} accessibilityLabel="Cerca linea autobus" value={query} onChangeText={setQuery} placeholder="Es. 64, 40, H…" placeholderTextColor={colors.placeholder} keyboardAppearance={scheme} selectionColor={colors.accent} style={s.input} autoCorrect={false} /><RequestState state={state} />
    {state.data?.length === 0 && <Notice text="Nessuna linea trovata." />}
    {!!recentError && <Notice text={recentError} />}
    {opening && <ActivityIndicator color={colors.accent} />}
    {results.map(r => <GlassPressable disabled={opening} accessibilityRole="button" key={r.route_id} style={s.route} onPress={() => openLine(r)}><Badge name={r.name} /><View style={s.flex}><Text style={s.body}>{r.description || `Linea ${r.name}`}</Text><Text style={s.small}>Scegli la direzione →</Text></View><Text style={s.arrow}>›</Text></GlassPressable>)}
  </View>;
}
export function Stops() {
  const { s, colors } = useStyles();
  const { fontScale } = useWindowDimensions();
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
  const state = useData<Arrivals>(stop ? `stops/${encodeURIComponent(stop.stop_id)}/arrivals` : null, 10000, true);
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
    <Text accessibilityRole="header" style={s.pageTitle}>{specificStop ? 'Autobus in arrivo' : 'Cerca fermata'}</Text>
    {!!favoriteError && <Notice text={favoriteError} />}
    {!specificStop && favorites.length > 0 && <View style={s.stack}>
      <Text style={s.heading}>Preferite</Text>
      {favorites.map(favorite => <GlassSurface key={favorite.stop_id} style={s.favoriteRow}>
        <Pressable accessibilityRole="button" accessibilityLabel={`Apri fermata preferita ${favorite.name}`} style={s.favoriteOpen} onPress={() => router.push({ pathname: '/stop/[stopId]', params: { stopId: favorite.stop_id, stopName: favorite.name } })}><Text style={s.body}>{favorite.name}</Text><Text style={s.small}>Fermata {favorite.stop_id} ›</Text></Pressable>
        <Pressable accessibilityRole="button" accessibilityLabel={`Rimuovi ${favorite.name} dalle preferite`} style={s.favoriteToggle} onPress={() => { void toggleFavorite(favorite); }}><Text style={s.favoriteStar}>★</Text></Pressable>
      </GlassSurface>)}
    </View>}
    {specificStop && stop ? <GlassSurface style={s.card}><View style={s.row}><Text numberOfLines={2} style={[s.heading, s.flex]}>{stop.name}</Text><Pressable accessibilityRole="button" accessibilityLabel={favorites.some(f => f.stop_id === stop.stop_id) ? 'Rimuovi fermata dalle preferite' : 'Aggiungi fermata alle preferite'} accessibilityState={{ selected: favorites.some(f => f.stop_id === stop.stop_id), disabled: !favoritesReady }} disabled={!favoritesReady} style={s.favoriteToggle} onPress={() => { void toggleFavorite(stop); }}><Text style={s.favoriteStar}>{favorites.some(f => f.stop_id === stop.stop_id) ? '★' : '☆'}</Text></Pressable></View><Text style={s.small}>Fermata {stop.stop_id}</Text></GlassSurface> : <StopSearch label="Fermata" selected={stop} onSelect={selected => { if (selected) router.push({ pathname: '/stop/[stopId]', params: { stopId: selected.stop_id, stopName: selected.name } }); else setStop(null); }} />}
    <RequestState state={state} showLoading={!specificStop} />
    {openingRoute && <View style={s.row}><ActivityIndicator color={colors.accent} /><Text style={s.muted}>Apertura itinerario…</Text></View>}
    {!!navigationError && <Notice text={navigationError} />}
    {state.data && !state.data.apiVersion && state.data.arrivals.some(a => !a.routeId) && <Notice text="Il servizio dati va aggiornato e riavviato: alcune informazioni sulle vetture non sono disponibili." />}
    {state.data && <>
      <UpdateStatus timestamp={state.data.timestamp} message={!liveFresh ? 'Previsioni live non disponibili · solo orari programmati' : arrivals.length > 0 && !arrivals.some(a => a.kind === 'live') ? 'Nessuna previsione live per questa fermata · orari programmati' : undefined} />
      {!arrivals.length && <Notice text="Nessun arrivo disponibile nella prossima ora. Riprova o aggiorna gli orari." />}
      {arrivals.map((a,i) => {
        const departure = nextDeparture(a, now);
        const minutes = Math.ceil((a.time - now) / 60);
        const imminent = minutes <= 1;
        const arrivalLabel = imminent ? 'In arrivo' : `${minutes} min`;
        const timing = a.atTerminus ? `Prossima partenza: ${departure ? `${clock(departure.time)}${departure.kind === 'scheduled' ? ', programmata' : ''}` : 'non disponibile'}` : imminent ? arrivalLabel : `In arrivo tra: ${arrivalLabel}`;
        return <GlassPressable key={`${a.tripId}-${i}`} accessibilityRole="button" accessibilityLabel={`Linea ${a.line}, direzione ${a.headsign}, ${timing}${a.vehicleId ? `, vettura ${a.vehicleId}` : ''}, mostra itinerario e autobus`} disabled={openingRoute === a.tripId} style={[s.arrivalCard, { minHeight: 112 * fontScale }]} onPress={() => { void openArrival(a); }}>
          <View style={s.arrivalRow}>
            <View style={s.arrivalBadge}><Badge name={a.line} /></View>
            <View style={s.arrivalDetails}>
              <Text numberOfLines={2} style={[s.body, s.arrivalDestination]}>{a.headsign || 'Autobus'}</Text>
              <Text numberOfLines={1} style={[s.small, s.arrivalStatus, a.kind === 'live' && { color: colors.live }]}>{a.kind === 'live' ? '● LIVE' : 'Orario programmato'}{a.atTerminus ? ' · al capolinea' : ''}</Text>
              <Text numberOfLines={1} style={s.vehicleNumber}>Vettura {a.vehicleId || 'non disponibile'}</Text>
            </View>
            <View style={s.arrivalTiming}>
              {a.atTerminus
                ? <><Text style={s.departureLabel}>Prossima{'\n'}partenza:</Text><Text maxFontSizeMultiplier={1.4} style={departure ? s.departureClock : s.timingNote}>{departure ? clock(departure.time) : 'Non disponibile'}</Text>{departure?.kind === 'scheduled' && <Text style={s.timingNote}>Programmata</Text>}</>
                : <>{!imminent && <Text numberOfLines={1} style={s.departureLabel}>In arrivo tra:</Text>}<Text numberOfLines={1} adjustsFontSizeToFit minimumFontScale={0.75} maxFontSizeMultiplier={1.4} style={[s.time, a.kind === 'live' && s.liveEta, imminent && s.arrivalImminent]}>{arrivalLabel}</Text></>}
            </View>
          </View>
        </GlassPressable>;
      })}
    </>}
  </View>;
}

export function Planner() {
  const { s } = useStyles();
  return <View style={s.stack}>
    <Text accessibilityRole="header" style={s.pageTitle}>Calcola percorso</Text>
    <GlassSurface style={s.comingSoon}>
      <NavIcon kind="plan" active />
      <Text style={s.comingSoonTitle}>Funzionalità in arrivo</Text>
      <Text style={s.muted}>Qui potrai trovare un percorso tra due fermate.</Text>
    </GlassSurface>
  </View>;
}

const createStyles = (colors: ThemeColors) => StyleSheet.create({
  safe: { flex: 1, backgroundColor: colors.background }, safeContent: { flex: 1 },
  homeLogo: { width: 140, height: 84, alignSelf: 'center' }, launchScreen: { position: 'absolute', top: 0, right: 0, bottom: 0, left: 0, zIndex: 10, backgroundColor: colors.background, justifyContent: 'center', alignItems: 'center', gap: 8 }, launchLogo: { width: 180, height: 180 }, launchName: { color: colors.accent, fontWeight: '800', fontSize: 22, letterSpacing: 3, marginBottom: 24 },
  boardHeader: { minHeight: 64, width: '100%', maxWidth: layout.maxWidth, alignSelf: 'center', paddingHorizontal: 12, paddingVertical: 8, flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: 8 }, headerLeft: { width: 88 }, headerRight: { width: 88 }, boardAction: { minHeight: 48, borderRadius: 20, paddingHorizontal: 8, justifyContent: 'center', alignItems: 'center' }, boardActionText: { ...typography.caption, color: colors.accent, fontWeight: '700', textAlign: 'center' }, boardTitle: { ...typography.label, flex: 1, textAlign: 'center', color: colors.text, fontWeight: '800' },
  fixedHeader: { minHeight: 64, width: '100%', maxWidth: layout.maxWidth, alignSelf: 'center', paddingHorizontal: layout.gutter, paddingVertical: 8, flexDirection: 'row', justifyContent: 'flex-start', alignItems: 'center', gap: 8, marginBottom: 8 },
  headerAction: { minHeight: 48, justifyContent: 'center', paddingHorizontal: 14, borderRadius: 20 }, headerReturn: { maxWidth: '100%' }, headerActionText: { ...typography.label, color: colors.accent, fontWeight: '700' },
  homeContent: { paddingHorizontal: layout.gutter }, homeScroll: { flexGrow: 1 }, home: { flex: 1, gap: 24, width: '100%', maxWidth: 420, alignSelf: 'center', paddingTop: 12, paddingBottom: 36 }, homeHeader: { gap: 10, alignItems: 'center' }, homeActions: { gap: 12 }, eyebrow: { fontSize: 24, fontWeight: '800', color: colors.accent, letterSpacing: 3 }, homeTitle: { fontSize: 30, lineHeight: 36, fontWeight: '800', color: colors.text, marginTop: 6, letterSpacing: -1, textAlign: 'center' }, homeSubtitle: { ...typography.body, color: colors.muted, textAlign: 'center' }, flex: { flex: 1, minWidth: 0 }, stack: { gap: layout.gap },
  row: { flexDirection: 'row', alignItems: 'center', gap: 12 },
  livePill: { fontSize: 11, fontWeight: '600', paddingHorizontal: 12, paddingVertical: 6, borderRadius: 20, backgroundColor: colors.surface, overflow: 'hidden' },
  homeAction: { flexDirection: 'row', alignItems: 'center', padding: layout.cardPadding, gap: 14, borderRadius: layout.radius, minHeight: 78 }, homeActionIcon: { width: 44, height: 44, borderRadius: 14, backgroundColor: colors.accentSoft, alignItems: 'center', justifyContent: 'center' }, homeActionText: { ...typography.body, color: colors.text, fontWeight: '700' },
  bottomDock: { position: 'absolute', bottom: 0, left: 0, right: 0, paddingHorizontal: 16, paddingTop: 12 }, bottomBar: { flexDirection: 'row', borderRadius: 32, padding: 6, maxWidth: 460, width: '100%', alignSelf: 'center' },
  bottomTab: { flex: 1, alignItems: 'center', justifyContent: 'center', gap: 4, paddingVertical: 10, borderRadius: 26, minHeight: 62 }, bottomTabActive: { backgroundColor: colors.accentSoft, boxShadow: 'none' }, bottomTabPressed: { backgroundColor: colors.pressed }, bottomTabText: { ...typography.micro, color: colors.muted, fontWeight: '600' }, bottomTabSelected: { color: colors.accent, fontWeight: '800' }, bottomTabUnavailable: { opacity: 0.5 },
  content: { flex: 1, width: '100%', maxWidth: layout.maxWidth, alignSelf: 'center', paddingHorizontal: layout.gutter }, scroll: { paddingBottom: 140, gap: layout.gap }, pageTitle: { ...typography.title, color: colors.text }, heading: { ...typography.heading, color: colors.text, flexShrink: 1 },
  boardScroll: { paddingBottom: 190 },
  lineRefreshDock: { position: 'absolute', right: 20 }, lineRefreshButton: { width: 48, height: 48, borderRadius: 24, alignItems: 'center', justifyContent: 'center', backgroundColor: colors.accentFill, borderColor: colors.accentFill }, lineRefreshIcon: { fontSize: 30, color: colors.onAccent, lineHeight: 34 },
  muted: { ...typography.body, color: colors.muted }, small: { ...typography.caption, color: colors.muted }, body: { ...typography.body, color: colors.text, fontWeight: '600' },
  input: { ...getSurfaceStyle(colors), ...typography.body, minHeight: 56, borderRadius: layout.radius, paddingHorizontal: layout.cardPadding, paddingVertical: 16, color: colors.text, marginVertical: 8 },
  route: { padding: layout.cardPadding, flexDirection: 'row', gap: 14, alignItems: 'center' },
  badge: { width: 52, minHeight: 52, borderRadius: 12, paddingHorizontal: 3, paddingVertical: 12, backgroundColor: colors.accentFill, justifyContent: 'center', alignItems: 'center', borderWidth: 1, borderColor: colors.accentFill }, badgeText: { maxWidth: '100%', textAlign: 'center', color: colors.onAccent, fontSize: 18, lineHeight: 24, fontWeight: '800' },
  arrow: { fontSize: 28, color: colors.accent }, time: { ...typography.time, color: colors.text },
  favoriteRow: { flexDirection: 'row', alignItems: 'center', paddingHorizontal: 12 }, favoriteOpen: { flex: 1, minWidth: 0, paddingVertical: 16, gap: 4 }, favoriteToggle: { flexShrink: 0, minWidth: 44, minHeight: 44, alignItems: 'center', justifyContent: 'center' }, favoriteStar: { fontSize: 27, color: colors.accent },
  liveEta: { color: colors.live },
  arrivalCard: { padding: layout.cardPadding, justifyContent: 'center' }, arrivalRow: { flexDirection: 'row', gap: 8, alignItems: 'center' }, arrivalBadge: { width: 52 }, arrivalDetails: { flex: 1, minWidth: 0, gap: 3 }, arrivalDestination: { lineHeight: 22 }, arrivalStatus: { ...typography.micro }, vehicleNumber: { ...typography.caption, color: colors.muted },
  arrivalTiming: { width: 76, alignItems: 'flex-end', justifyContent: 'center', gap: 3 }, departureLabel: { ...typography.micro, color: colors.muted, fontWeight: '600', textAlign: 'right' }, departureClock: { ...typography.time, color: colors.live }, timingNote: { ...typography.micro, color: colors.muted, textAlign: 'right' },
  arrivalImminent: { fontSize: 16, lineHeight: 24 },
  button: { minHeight: 48, padding: 14, borderRadius: 16, alignItems: 'center', backgroundColor: colors.accentFill, borderColor: colors.accentFill }, buttonText: { ...typography.label, color: colors.onAccent, fontWeight: '700' }, buttonDisabled: { backgroundColor: colors.disabled, borderColor: colors.border }, buttonDisabledText: { color: colors.muted },
  notice: { padding: layout.cardPadding, borderRadius: layout.radius, marginVertical: 8 }, card: { borderRadius: layout.radius, padding: layout.cardPadding, gap: 12 },
  link: { color: colors.accent, fontWeight: '600', fontSize: 14 },
  label: { ...typography.label, color: colors.text, fontWeight: '700' }, stop: { padding: layout.cardPadding, marginBottom: 8 },
  homeActionLabel: { flex: 1, gap: 4 }, homeActionHint: { ...typography.caption, color: colors.muted }, homeActionUnavailable: { backgroundColor: colors.surfaceAlt },
  homeSettingsDock: { marginTop: 'auto' },
  comingSoon: { padding: layout.cardPadding, gap: layout.gap, alignItems: 'flex-start' }, comingSoonTitle: { ...typography.heading, color: colors.accent },
  homeSettings: { flexDirection: 'row', alignItems: 'center', gap: 12, minHeight: 56, paddingHorizontal: layout.cardPadding, paddingVertical: 12 }, homeSettingsText: { ...typography.body, flex: 1, color: colors.text, fontWeight: '600' },
});

function useStyles() {
  const theme = useTheme();
  const s = useMemo(() => createStyles(theme.colors), [theme.colors]);
  return { ...theme, s };
}
