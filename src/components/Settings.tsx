import Constants from 'expo-constants';
import React, { useMemo } from 'react';
import { ActivityIndicator, StyleSheet, Text, View } from 'react-native';
import { useData } from '../../App';
import appConfig from '../../app.json';
import { feedState, realtimeState, type FeedState, type RealtimeStatus } from '../lib/feedStatus';
import { GlassPressable, GlassSurface } from '../ui/Glass';
import { useTheme, type ThemeColors } from '../ui/Theme';
import { ThemePicker } from './ThemePicker';

const feedLabels: Record<FeedState, string> = { available: 'Disponibile', unavailable: 'Non disponibile', stale: 'Dati non aggiornati', unknown: 'Da verificare' };
const statusLabels = { available: 'Operativo', partial: 'Parzialmente disponibile', unavailable: 'Non disponibile', unknown: 'Stato non verificabile' };
const timestampLabel = (timestamp: number | null | undefined) => typeof timestamp === 'number' && Number.isFinite(timestamp) && timestamp > 0
  ? new Date(timestamp * 1000).toLocaleString('it-IT', { timeZone: 'Europe/Rome', day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit', second: '2-digit' })
  : 'Non disponibile';

export function Settings() {
  const { colors } = useTheme();
  const s = useMemo(() => createStyles(colors), [colors]);
  const state = useData<RealtimeStatus>('status', 0, true);
  const currentTime = state.receivedAt;
  const status = realtimeState(state.data, currentTime, Boolean(state.error));
  const checking = !state.data && !state.error;
  const version = Constants.expoConfig?.version || appConfig.expo.version;
  const copyright = Constants.expoConfig?.extra?.copyright || appConfig.expo.extra.copyright;
  return <View style={s.page}>
    <Text accessibilityRole="header" style={s.title}>Impostazioni</Text>

    <GlassSurface style={s.section}>
      <Text accessibilityRole="header" style={s.heading}>Aspetto</Text>
      <ThemePicker />
    </GlassSurface>

    <GlassSurface style={s.section}>
      <Text accessibilityRole="header" style={s.heading}>Informazioni sull’app</Text>
      <Text style={s.brand}>ROMABUS</Text>
      <View style={s.infoRow}><Text style={s.body}>Versione</Text><Text selectable style={s.value}>{version}</Text></View>
      <Text selectable style={s.muted}>{copyright}</Text>
      <Text style={s.small}>Dati di Roma Servizi per la Mobilità.</Text>
    </GlassSurface>

    <GlassSurface style={s.section}>
      <Text accessibilityRole="header" style={s.heading}>Stato dati realtime</Text>
      <Text selectable style={s.body}>romamobilita.it</Text>
      <View style={s.statusRow}>
        <View style={[s.dot, { backgroundColor: checking ? colors.muted : status === 'available' ? colors.live : status === 'unknown' ? colors.muted : colors.accent }]} />
        <Text style={[s.status, { color: checking ? colors.muted : status === 'available' ? colors.live : status === 'unknown' ? colors.muted : colors.accent }]}>{checking ? 'Verifica in corso…' : statusLabels[status]}</Text>
      </View>
      {state.error ? <Text accessibilityRole="alert" style={s.muted}>Impossibile verificare la fonte dati. Controlla la connessione e riprova.</Text> : <Text style={s.small}>Stato dei feed all’ultima verifica. Usa Verifica ora per aggiornarlo.</Text>}
      {(['vehicles', 'updates'] as const).map(kind => {
        const feed = state.data?.[kind];
        const value = state.error ? 'unknown' : feedState(feed, currentTime);
        const url = state.data?.[kind === 'vehicles' ? 'vehiclesUrl' : 'updatesUrl'];
        return <View key={kind} style={s.feed}>
          <Text style={s.feedTitle}>{kind === 'vehicles' ? 'Posizioni autobus' : 'Previsioni di arrivo'}</Text>
          <Text style={[s.feedStatus, { color: value === 'available' ? colors.live : value === 'unknown' ? colors.muted : colors.accent }]}>{feedLabels[value]}</Text>
          <Text style={s.small}>Orario del feed: {timestampLabel(feed?.timestamp)}</Text>
          {!!url && <Text selectable style={s.endpoint}>{url}</Text>}
        </View>;
      })}
      <Text style={s.small}>Ultima verifica riuscita: {timestampLabel(state.receivedAt)}</Text>
      <GlassPressable accessibilityRole="button" accessibilityLabel="Verifica ora lo stato dei dati realtime" aria-busy={state.loading} disabled={state.loading} onPress={() => { void state.retry(); }} style={s.checkButton}>
        {state.loading && <ActivityIndicator color={colors.onAccent} />}
        <Text style={s.checkButtonText}>{state.loading ? 'Verifica in corso…' : 'Verifica ora'}</Text>
      </GlassPressable>
      <Text style={s.small}>Se i dati realtime non sono disponibili, l’app usa gli orari programmati dove presenti.</Text>
    </GlassSurface>
  </View>;
}

const createStyles = (colors: ThemeColors) => StyleSheet.create({
  page: { gap: 18 }, title: { color: colors.text, fontSize: 26, fontWeight: '800' }, section: { padding: 18, gap: 12, borderRadius: 22 },
  heading: { color: colors.text, fontSize: 18, fontWeight: '700' }, brand: { color: colors.accent, fontSize: 22, fontWeight: '800', letterSpacing: 2 },
  body: { color: colors.text, fontSize: 14 }, value: { color: colors.text, fontSize: 14, fontWeight: '700' }, infoRow: { flexDirection: 'row', justifyContent: 'space-between', gap: 12 },
  muted: { color: colors.muted, fontSize: 14, lineHeight: 21 }, small: { color: colors.muted, fontSize: 12, lineHeight: 18 },
  statusRow: { flexDirection: 'row', alignItems: 'center', gap: 8 }, dot: { width: 8, height: 8, borderRadius: 4 }, status: { flex: 1, fontSize: 16, fontWeight: '700' },
  feed: { gap: 6, borderTopWidth: 1, borderColor: colors.border, paddingTop: 12 }, feedTitle: { color: colors.text, fontSize: 14, fontWeight: '700' }, feedStatus: { fontSize: 13, fontWeight: '600' }, endpoint: { color: colors.muted, fontSize: 11, lineHeight: 16 },
  checkButton: { minHeight: 48, flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 8, padding: 12, borderRadius: 16, backgroundColor: colors.accentFill, borderColor: colors.accentFill }, checkButtonText: { color: colors.onAccent, fontWeight: '700', fontSize: 14 },
});
