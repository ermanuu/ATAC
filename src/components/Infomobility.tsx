import { router } from 'expo-router';
import React, { useMemo, useState } from 'react';
import { ActivityIndicator, Pressable, StyleSheet, Text, View } from 'react-native';
import { Button, RequestState, useData } from '../../App';
import { sourceMessage, type MetroData, type MetroLine, type NewsData } from '../lib/infomobility';
import { GlassSurface } from '../ui/Glass';
import { LiveIndicator } from '../ui/LiveIndicator';
import { useTheme, type ThemeColors } from '../ui/Theme';
import { UpdateStatus } from '../ui/UpdateStatus';
import { layout, typography } from '../ui/design';
import { BulletinCard, OfficialLink } from './BulletinCard';

export function Metro() {
  const { colors } = useTheme();
  const s = useMemo(() => createStyles(colors), [colors]);
  const state = useData<MetroData>('metro', 30000, true);
  const data = state.data;
  const live = Boolean(data?.available && !state.error && data.lines.some(line => line.status !== 'unknown'));
  const message = sourceMessage(data, Boolean(state.error));
  return <View style={s.page}>
    <View style={s.header}><Text accessibilityRole="header" style={s.title}>Metro</Text><Pressable accessibilityRole="button" accessibilityLabel="Apri News" onPress={() => router.replace('/news')} style={s.switch}><Text style={s.link}>News ›</Text></Pressable></View>
    <Text style={s.subtitle}>Lo stato delle metropolitane di Roma.</Text>
    <LiveIndicator label={live ? 'Stato live' : 'Stato da verificare'} active={live} />
    <RequestState state={state} showLoading={!data} />
    {data && <>
      <UpdateStatus timestamp={data.timestamp} message={message || undefined} />
      {data.lines.map(line => <MetroCard key={line.code} line={line} verified={Boolean(data.available && !state.error)} />)}
      <Text style={s.caption}>Stato del servizio pubblicato da ATAC. Gli avvisi possono riguardare anche singole tratte o stazioni.</Text>
      <OfficialLink url={data.sourceUrl} label="Consulta lo stato ufficiale ATAC" />
    </>}
  </View>;
}

function MetroCard({ line, verified }: { line: MetroLine; verified: boolean }) {
  const { colors } = useTheme();
  const s = useMemo(() => createStyles(colors), [colors]);
  const [expanded, setExpanded] = useState(false);
  const status = verified ? line.status : 'unknown';
  const color = status === 'regular' ? colors.live : status === 'unknown' ? colors.muted : colors.accent;
  const badgeColor = line.code === 'A' ? '#e98300' : line.code === 'C' ? '#008349' : '#006cb5';
  return <GlassSurface style={s.metroCard}>
    <View style={s.metroHeader}>
      <View style={[s.metroBadge, { backgroundColor: badgeColor }]}><Text accessible={false} style={[s.metroCode, { color: line.code === 'A' ? '#211609' : '#ffffff' }]}>{line.code}</Text></View>
      <View style={s.flex}><Text accessibilityRole="header" style={s.metroName}>{line.name}</Text><View style={s.statusRow}><View accessible={false} style={[s.dot, { backgroundColor: color }]} /><Text style={[s.status, { color }]}>{verified ? line.label : 'Stato non verificabile'}</Text></View></View>
    </View>
    {verified && !!line.detail && <>
      <Text numberOfLines={expanded ? undefined : 3} style={s.description}>{line.detail}</Text>
      {line.detail.length > 180 && <Pressable accessibilityRole="button" accessibilityLabel={`${expanded ? 'Nascondi' : 'Mostra'} dettaglio ${line.name}`} accessibilityState={{ expanded }} aria-expanded={expanded} onPress={() => setExpanded(value => !value)} style={s.switch}><Text style={s.link}>{expanded ? 'Mostra meno' : 'Mostra dettaglio'}</Text></Pressable>}
      <OfficialLink url={line.url} label={`Fonte ${line.name}`} />
    </>}
  </GlassSurface>;
}

export function News() {
  const { colors } = useTheme();
  const s = useMemo(() => createStyles(colors), [colors]);
  const state = useData<NewsData>('news', 60000, true);
  const [section, setSection] = useState('Tutte');
  const [limit, setLimit] = useState(20);
  const articles = state.data?.articles.filter(article => section === 'Tutte' || article.section === section) || [];
  const message = sourceMessage(state.data, Boolean(state.error));
  return <View style={s.page}>
    <View style={s.header}><Text accessibilityRole="header" style={s.title}>News</Text><Pressable accessibilityRole="button" accessibilityLabel="Apri Metro" onPress={() => router.replace('/metro')} style={s.switch}><Text style={s.link}>Metro ›</Text></Pressable></View>
    <Text style={s.subtitle}>Notizie e aggiornamenti da Roma Mobilità.</Text>
    <View accessibilityRole="tablist" accessibilityLabel="Categorie delle notizie" style={s.filters}>
      {['Tutte', 'Infomobilità', 'News'].map(value => <Pressable key={value} accessibilityRole="tab" accessibilityLabel={value} accessibilityState={{ selected: section === value }} aria-selected={section === value} onPress={() => { setSection(value); setLimit(20); }} style={({ pressed }) => [s.filter, section === value && s.selectedFilter, pressed && s.pressed]}><Text style={[s.filterText, section === value && s.selectedFilterText]}>{value}</Text></Pressable>)}
    </View>
    <RequestState state={state} showLoading={!state.data} />
    {state.data && <>
      <UpdateStatus timestamp={state.data.timestamp} message={message || undefined} />
      {articles.slice(0, limit).map(article => <BulletinCard key={article.id} item={article} />)}
      {!articles.length && !state.data.refreshing && <GlassSurface style={s.metroCard}><Text style={s.description}>{state.data.available ? 'Nessuna notizia disponibile in questa categoria.' : 'Le notizie non sono al momento disponibili.'}</Text></GlassSurface>}
      {state.data.refreshing && !articles.length && <ActivityIndicator accessibilityLabel="Aggiornamento notizie" color={colors.accent} />}
      {articles.length > limit && <Button text="Mostra altre notizie" onPress={() => setLimit(value => value + 20)} />}
      <OfficialLink url="https://romamobilita.it/news-eventi/" label="Tutte le notizie su Roma Mobilità" />
    </>}
  </View>;
}

const createStyles = (colors: ThemeColors) => StyleSheet.create({
  page: { gap: layout.gap }, header: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', gap: 12 }, title: { ...typography.title, color: colors.text },
  subtitle: { ...typography.body, color: colors.muted }, caption: { ...typography.caption, color: colors.muted }, description: { ...typography.body, color: colors.muted }, link: { ...typography.label, color: colors.accent, fontWeight: '700' }, switch: { minHeight: 44, justifyContent: 'center', alignSelf: 'flex-start' },
  metroCard: { padding: layout.cardPadding, borderRadius: layout.radius, gap: 12 }, metroHeader: { flexDirection: 'row', alignItems: 'center', gap: 14 }, metroBadge: { width: 52, minHeight: 52, borderRadius: 12, justifyContent: 'center', alignItems: 'center', padding: 8 }, metroCode: { fontSize: 22, lineHeight: 28, fontWeight: '800' }, metroName: { ...typography.heading, color: colors.text }, flex: { flex: 1, minWidth: 0, gap: 5 }, statusRow: { flexDirection: 'row', alignItems: 'center', gap: 6 }, status: { ...typography.label, flexShrink: 1 }, dot: { width: 6, height: 6, borderRadius: 3 },
  filters: { flexDirection: 'row', gap: 4, borderRadius: 16, padding: 4, backgroundColor: colors.surfaceAlt, borderColor: colors.border, borderWidth: 1 }, filter: { flex: 1, minHeight: 44, justifyContent: 'center', alignItems: 'center', borderRadius: 12, paddingHorizontal: 4, paddingVertical: 8 }, filterText: { ...typography.caption, color: colors.muted, fontWeight: '600', textAlign: 'center' }, selectedFilter: { backgroundColor: colors.accentFill }, selectedFilterText: { color: colors.onAccent, fontWeight: '700' }, pressed: { opacity: 0.7 },
});
