import React, { useMemo, useState } from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';
import { useData } from '../../App';
import { publicationDate, sourceMessage, type LineAlertsData } from '../lib/infomobility';
import { GlassSurface } from '../ui/Glass';
import { useTheme, type ThemeColors } from '../ui/Theme';
import { layout, typography } from '../ui/design';
import { BulletinCard } from './BulletinCard';

export function LineAlerts({ routeId }: { routeId: string }) {
  const { colors } = useTheme();
  const s = useMemo(() => createStyles(colors), [colors]);
  const state = useData<LineAlertsData>(`routes/${encodeURIComponent(routeId)}/alerts`, 60000, true);
  const [expanded, setExpanded] = useState(false);
  const data = state.data;
  const message = sourceMessage(data, Boolean(state.error));
  if (!data?.items.length) return null;
  const first = data.items[0];
  const date = publicationDate(first.updatedAt || first.publishedAt);
  return <GlassSurface style={s.card}>
    <Pressable accessibilityRole="button" accessibilityLabel={`${expanded ? 'Nascondi' : 'Mostra'} segnalazioni linea ${data.line}`} accessibilityState={{ expanded }} aria-expanded={expanded} onPress={() => setExpanded(value => !value)} style={s.toggle}>
      <Text accessibilityRole="header" style={s.heading}>Segnalazioni e novità · {data.line}</Text><Text accessible={false} style={s.caret}>{expanded ? '⌃' : '⌄'}</Text>
    </Pressable>
    {!!message && <Text style={s.note}>{message}</Text>}
    {expanded ? <>
      <Text style={s.note}>Avvisi del gestore e notizie pubblicate da Roma Mobilità. Consulta le date per i dettagli.</Text>
      <View style={s.items}>{data.items.map(item => <BulletinCard key={item.id} item={item} compact />)}</View>
    </> : <View style={s.preview}>
      <Text numberOfLines={2} style={s.previewTitle}>{first.title}</Text>
      <Text style={s.note}>{first.source}{date ? ` · ${date}` : ''}{data.items.length > 1 ? ` · +${data.items.length - 1}` : ''}</Text>
    </View>}
  </GlassSurface>;
}

const createStyles = (colors: ThemeColors) => StyleSheet.create({
  card: { borderRadius: layout.radius, paddingHorizontal: layout.cardPadding, paddingTop: 6, paddingBottom: 14, gap: 8 }, heading: { ...typography.label, color: colors.text, fontWeight: '700', flex: 1 }, note: { ...typography.caption, color: colors.muted },
  items: { gap: 12 }, toggle: { minHeight: 44, flexDirection: 'row', alignItems: 'center', gap: 12 }, caret: { fontSize: 22, color: colors.accent }, preview: { gap: 6 }, previewTitle: { ...typography.label, color: colors.text },
});
