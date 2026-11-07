import Constants from 'expo-constants';
import React, { useMemo } from 'react';
import { ActivityIndicator, StyleSheet, Text, View } from 'react-native';
import { useData } from '../../App';
import appConfig from '../../app.json';
import { feedState, realtimeState, type FeedState, type RealtimeStatus } from '../lib/feedStatus';
import { GlassPressable, GlassSurface } from '../ui/Glass';
import { useTheme, type ThemeColors } from '../ui/Theme';
import { ThemePicker } from './ThemePicker';
import { HomeContentPicker } from './HomeContentPicker';
import { layout, typography } from '../ui/design';

const feedLabels: Record<FeedState, string> = { available: 'Disponibile', unavailable: 'Non disponibile', stale: 'Dati non aggiornati', unknown: 'Da verificare' };
const statusLabels = { available: 'Operativo', partial: 'Parzialmente disponibile', unavailable: 'Non disponibile', unknown: 'Stato non verificabile' };
const timestampLabel = (timestamp: number | null | undefined) => typeof timestamp === 'number' && Number.isFinite(timestamp) && timestamp > 0
  ? new Date(timestamp * 1000).toLocaleString('it-IT', { timeZone: 'Europe/Rome', day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit' })
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
      <Text accessibilityRole="header" style={s.heading}>Home</Text>
      <HomeContentPicker />
    </GlassSurface>

    <GlassSurface style={s.section}>
      <Text accessibilityRole="header" style={s.heading}>Stato dati realtime</Text>
      <Text selectable style={s.body}>romamobilita.it</Text>
      <View style={s.statusRow}>
        <View style={[s.dot, { backgroundColor: checking ? colors.muted : status === 'available' ? colors.live : status === 'unknown' ? colors.muted : colors.accent }]} />
        <Text style={[s.status, { color: checking ? colors.muted : status === 'available' ? colors.live : status === 'unknown' ? colors.muted : colors.accent }]}>{checking ? 'Verifica in corso…' : statusLabels[status]}</Text>
      </View>
      {!!state.error && <Text accessibilityRole="alert" style={s.muted}>Impossibile verificare la fonte dati. Controlla la connessione e riprova.</Text>}
      {(['vehicles', 'updates'] as const).map(kind => {
        const feed = state.data?.[kind];
        const value = state.error ? 'unknown' : feedState(feed, currentTime);
        return <View key={kind} style={s.feed}>
          <Text style={s.feedTitle}>{kind === 'vehicles' ? 'Posizioni autobus' : 'Previsioni di arrivo'}</Text>
          <Text style={[s.feedStatus, { color: value === 'available' ? colors.live : value === 'unknown' ? colors.muted : colors.accent }]}>{feedLabels[value]}</Text>
        </View>;
      })}
      <Text style={s.small}>Ultima verifica riuscita: {timestampLabel(state.receivedAt)}</Text>
      <GlassPressable accessibilityRole="button" accessibilityLabel="Verifica ora lo stato dei dati realtime" aria-busy={state.loading} disabled={state.loading} onPress={() => { void state.retry(); }} style={s.checkButton}>
        {state.loading && <ActivityIndicator color={colors.onAccent} />}
        <Text style={s.checkButtonText}>{state.loading ? 'Verifica in corso…' : 'Verifica ora'}</Text>
      </GlassPressable>
    </GlassSurface>

    <GlassSurface style={s.section}>
      <Text accessibilityRole="header" style={s.heading}>Informazioni sull’app</Text>
      <Text style={s.brand}>ROMABUS</Text>
      <View style={s.infoRow}><Text style={s.body}>Versione</Text><Text selectable style={s.value}>{version}</Text></View>
      <Text style={s.small}>Dati di Roma Servizi per la Mobilità.</Text>
      <View style={s.infoFooter}>
        <Text style={[s.small, s.fallback]}>Se i dati realtime non sono disponibili, l’app usa gli orari programmati dove presenti.</Text>
        <Text selectable style={s.copyright}>{copyright}</Text>
      </View>
    </GlassSurface>
  </View>;
}

const createStyles = (colors: ThemeColors) => StyleSheet.create({
  page: { gap: layout.gap }, title: { ...typography.title, color: colors.text }, section: { padding: layout.cardPadding, gap: 12, borderRadius: layout.radius },
  heading: { ...typography.heading, color: colors.text }, brand: { ...typography.heading, color: colors.accent, fontWeight: '800', letterSpacing: 2 },
  body: { ...typography.body, color: colors.text }, value: { ...typography.body, color: colors.text, fontWeight: '700' }, infoRow: { flexDirection: 'row', justifyContent: 'space-between', gap: 12 },
  infoFooter: { flexDirection: 'row', flexWrap: 'wrap', alignItems: 'flex-end', gap: 12 }, fallback: { flexBasis: 240, flexGrow: 1, flexShrink: 1, minWidth: 0 }, copyright: { ...typography.body, color: colors.muted, marginLeft: 'auto', textAlign: 'right' },
  muted: { ...typography.body, color: colors.muted }, small: { ...typography.caption, color: colors.muted },
  statusRow: { flexDirection: 'row', alignItems: 'center', gap: 8 }, dot: { width: 8, height: 8, borderRadius: 4 }, status: { ...typography.body, flex: 1, fontWeight: '700' },
  feed: { gap: 6, borderTopWidth: 1, borderColor: colors.border, paddingTop: 12 }, feedTitle: { ...typography.label, color: colors.text, fontWeight: '700' }, feedStatus: { ...typography.label },
  checkButton: { minHeight: 48, flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 8, padding: 12, borderRadius: 16, backgroundColor: colors.accentFill, borderColor: colors.accentFill }, checkButtonText: { ...typography.label, color: colors.onAccent, fontWeight: '700' },
});
