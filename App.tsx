import React, { useEffect, useRef, useState } from 'react';
import { ActivityIndicator, AppState, Pressable, ScrollView, StyleSheet, Text, TextInput, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { StatusBar } from 'expo-status-bar';
import { Slot, router, usePathname, useLocalSearchParams } from 'expo-router';

const API = process.env.EXPO_PUBLIC_API_URL?.replace(/\/$/, '') || '';
export type Stop = { stop_id: string; name: string };
export type Route = { route_id: string; name: string; description: string };
type Live = { available: boolean; timestamp: number | null };
type Health = { staticAvailable: boolean; serviceToday?: boolean; vehicles: Live; updates: Live };
type Arrivals = { arrivals: { tripId: string; line: string; headsign: string; time: number; scheduledTime?: number; kind: string }[]; liveAvailable: boolean; timestamp: number | null };
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
    const load = () => {
      controller?.abort(); controller = new AbortController(); const signal = controller.signal;
      if (!retainWhileLoading) setData(null);
      setError(''); setLoading(true);
      api<T>(path, signal).then(value => { if (!signal.aborted) setData(value); }).catch(e => { if (!signal.aborted) { setData(null); setError(e.message); } })
        .finally(() => { if (!signal.aborted) setLoading(false); });
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
  const pathname = usePathname();
  const tab = pathname === '/stops' ? 'stops' : pathname === '/plan' ? 'plan' : 'lines';
  const state = useData<Health>('status', 30000);
  const live = state.data?.vehicles.available && state.data?.updates.available;
  return <SafeAreaView style={s.safe}><StatusBar style="dark" />
    <View style={s.header}><View style={s.row}><Text style={s.eyebrow}>ROMA · AUTOBUS</Text><Text style={[s.small, { color: live ? '#167450' : '#9b6a20' }]}>{live ? '● Feed live' : '● Live non disponibile'}</Text></View><Text style={s.title}>La città, in movimento.</Text><Text style={s.subtitle}>Linee, fermate e percorsi a Roma</Text></View>
    <View style={s.tabs}>{([['lines', 'Linee'], ['stops', 'Fermate'], ['plan', 'Percorso']] as const).map(([key, label]) => <Pressable accessibilityRole="tab" accessibilityState={{ selected: key === tab }} key={key} onPress={() => router.replace(key === 'lines' ? '/' : key === 'stops' ? '/stops' : '/plan')} style={[s.tab, key === tab && s.active]}><Text style={[s.tabText, key === tab && { color: '#a01d35' }]}>{label}</Text></Pressable>)}</View>
    <View style={s.content}><ScrollView keyboardShouldPersistTaps="handled" contentContainerStyle={s.scroll}>
      <RequestState state={state} />
      {state.data && !state.data.staticAvailable && <Notice text="Orari non ancora caricati. Il servizio deve importare il GTFS ufficiale Roma Mobilità." />}
      {state.data?.staticAvailable && !state.data.serviceToday && <Notice text="Il calendario importato non contiene servizio per oggi. Aggiornare il GTFS." />}
      <Slot />
    </ScrollView></View>
    <View style={s.footer}><Text style={s.small}>Dati: Roma Servizi per la Mobilità · App indipendente</Text><Text style={s.small}>{state.data?.updates.available ? stamp(state.data.updates.timestamp) : 'Le previsioni live possono essere indisponibili'}</Text></View>
  </SafeAreaView>;
}
export function Lines() {
  const [query, setQuery] = useState('');
  const state = useData<Route[]>(`routes?q=${encodeURIComponent(query)}`);
  return <View style={s.stack}><Text style={s.heading}>Trova il tuo autobus</Text><Text style={s.muted}>Cerca la linea, poi scegli la direzione</Text><TextInput accessibilityLabel="Cerca linea autobus" value={query} onChangeText={setQuery} placeholder="Es. 64, 40, H…" placeholderTextColor="#738197" style={s.input} autoCorrect={false} /><RequestState state={state} />
    {state.data?.length === 0 && <Notice text="Nessuna linea trovata." />}
    {state.data?.map(r => <Pressable accessibilityRole="button" key={r.route_id} style={s.route} onPress={() => router.push({ pathname: '/line/[id]', params: { id: r.route_id } })}><Badge name={r.name} /><View style={s.flex}><Text style={s.body}>{r.description || `Linea ${r.name}`}</Text><Text style={s.small}>Scegli la direzione →</Text></View><Text style={s.arrow}>›</Text></Pressable>)}
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
  const fromLine = Boolean(params.fromRouteId && params.fromVariant);
  const liveFresh = Boolean(state.data?.liveAvailable && state.data.timestamp && now - state.data.timestamp <= 180);
  const arrivals = (state.data?.arrivals || []).map(a => a.kind === 'live' && !liveFresh
    ? { ...a, time: a.scheduledTime || 0, kind: 'scheduled' } : a).filter(a => a.time >= now && a.time <= now + 7200);
  return <View style={s.stack}>
    {fromLine && <Button text={`‹ Torna alla linea ${params.fromLine || ''}`} onPress={() => router.replace({ pathname: '/line/[id]/[variant]', params: { id: params.fromRouteId!, variant: params.fromVariant! } })} />}
    <Text style={s.heading}>Autobus in arrivo</Text>
    <Text style={s.muted}>Tutte le linee · prossime 2 ore · aggiornamento ogni 30 s</Text>
    {fromLine && stop ? <View style={s.card}><Text style={s.heading}>{stop.name}</Text><Text style={s.small}>Fermata {stop.stop_id}</Text></View> : <StopSearch label="Fermata" selected={stop} onSelect={setStop} />}
    <RequestState state={state} />
    {stop && <Button text="Aggiorna arrivi" onPress={state.retry} disabled={state.loading} />}
    {state.data && <>
      <Text style={s.muted}>{liveFresh ? stamp(state.data.timestamp) : 'Previsioni live non disponibili · solo orari programmati'}</Text>
      <Text style={s.label}>{arrivals.length} {arrivals.length === 1 ? 'arrivo disponibile' : 'arrivi disponibili'} per questa fermata</Text>
      {!arrivals.length && <Notice text="Nessun arrivo disponibile nelle prossime 2 ore. Riprova o aggiorna gli orari." />}
      {arrivals.map((a,i) => <View key={`${a.tripId}-${i}`} style={s.route}>
        <Badge name={a.line} /><View style={s.flex}><Text style={s.body}>{a.headsign || 'Autobus'}</Text><Text style={[s.small, a.kind === 'live' && { color: '#167450' }]}>{a.kind === 'live' ? '● Previsione live' : 'Orario programmato'}</Text></View>
        <View style={s.arrivalTime}><Text style={s.time}>{Math.ceil((a.time - now) / 60) <= 1 ? '≤1 min' : `${Math.ceil((a.time - now) / 60)} min`}</Text><Text style={s.small}>{clock(a.time)}</Text></View>
      </View>)}
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
  safe: { flex: 1, backgroundColor: '#f8f6f2' }, flex: { flex: 1 }, stack: { gap: 14 },
  header: { paddingHorizontal: 24, paddingTop: 20, paddingBottom: 24 }, row: { flexDirection: 'row', alignItems: 'center', gap: 12 },
  eyebrow: { fontSize: 11, fontWeight: '800', color: '#a01d35', letterSpacing: 1.4, flex: 1 },
  title: { fontSize: 34, fontWeight: '800', color: '#202d3a', marginTop: 22, letterSpacing: -1.3 }, subtitle: { color: '#596878', fontSize: 16, marginTop: 8 },
  tabs: { flexDirection: 'row', marginHorizontal: 20, padding: 5, backgroundColor: '#ebe8e3', borderRadius: 16, marginBottom: 20 },
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
  label: { color: '#202d3a', fontSize: 13, fontWeight: '700' }, stop: { padding: 14, backgroundColor: '#fff', borderBottomWidth: 1, borderBottomColor: '#eee9df' },
  link: { color: '#a01d35', fontWeight: '600', fontSize: 14 }, footer: { padding: 12, alignItems: 'center', borderTopWidth: 1, borderColor: '#e3dfd8' },
});
