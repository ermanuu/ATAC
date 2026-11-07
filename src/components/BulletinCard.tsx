import { Link } from 'expo-router';
import React, { useMemo, useState } from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';
import type { Bulletin } from '../lib/infomobility';
import { publicationDate } from '../lib/infomobility';
import { GlassSurface } from '../ui/Glass';
import { useTheme, type ThemeColors } from '../ui/Theme';
import { layout, typography } from '../ui/design';

export function OfficialLink({ url, label }: { url: string; label: string }) {
  const { colors } = useTheme();
  return <Link href={url} target="_blank" rel="noopener noreferrer" accessibilityLabel={label} style={[typography.caption, { color: colors.accent, fontWeight: '700', minHeight: 44, paddingVertical: 13, alignSelf: 'flex-start' }]}>{label} →</Link>;
}

export function BulletinCard({ item, compact = false }: { item: Bulletin; compact?: boolean }) {
  const { colors } = useTheme();
  const s = useMemo(() => createStyles(colors), [colors]);
  const [expanded, setExpanded] = useState(false);
  const date = publicationDate(item.updatedAt || item.publishedAt);
  const content = <>
    <View style={s.meta}><Text style={s.category}>{item.category.toLocaleUpperCase('it-IT')}</Text><Text style={s.source}>{item.source}{item.live ? ' · Stato del servizio' : ''}</Text></View>
    <Text style={s.title}>{item.title}</Text>
    {!!date && <Text style={s.date}>{item.updatedAt && item.publishedAt && item.updatedAt > item.publishedAt ? 'Aggiornato' : 'Pubblicato'} il {date}</Text>}
    {!!(item.text || item.summary) && <Text numberOfLines={expanded ? undefined : compact ? 2 : 3} style={s.description}>{expanded ? item.text || item.summary : item.summary || item.text}</Text>}
    {item.text.length > 200 && <Pressable accessibilityRole="button" accessibilityLabel={`${expanded ? 'Nascondi' : 'Mostra'} dettaglio: ${item.title}`} accessibilityState={{ expanded }} aria-expanded={expanded} onPress={() => setExpanded(value => !value)} style={s.detailButton}><Text style={s.detailText}>{expanded ? 'Mostra meno' : 'Leggi il dettaglio'}</Text></Pressable>}
    <OfficialLink url={item.url} label={`Apri su ${item.source}`} />
  </>;
  return compact ? <View style={s.compact}>{content}</View> : <GlassSurface style={s.card}>{content}</GlassSurface>;
}

const createStyles = (colors: ThemeColors) => StyleSheet.create({
  card: { padding: layout.cardPadding, gap: 8, borderRadius: layout.radius }, compact: { gap: 6, borderTopWidth: 1, borderColor: colors.border, paddingTop: 12 },
  meta: { flexDirection: 'row', flexWrap: 'wrap', alignItems: 'center', gap: 8 }, category: { ...typography.micro, fontWeight: '700', letterSpacing: 0.6, color: colors.accent }, source: { ...typography.micro, color: colors.muted },
  title: { ...typography.body, color: colors.text, fontWeight: '700' }, date: { ...typography.micro, color: colors.muted }, description: { ...typography.caption, color: colors.muted },
  detailButton: { minHeight: 44, alignSelf: 'flex-start', justifyContent: 'center' }, detailText: { ...typography.caption, fontWeight: '600', color: colors.text },
});
