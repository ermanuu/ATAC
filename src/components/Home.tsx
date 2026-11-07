import AsyncStorage from '@react-native-async-storage/async-storage';
import { router, useFocusEffect } from 'expo-router';
import React, { useCallback, useMemo, useState } from 'react';
import { ActivityIndicator, Image, Pressable, StyleSheet, Text, View, useWindowDimensions } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { Badge, useData, useOpenLine } from '../../App';
import { parseFavoriteStops, type FavoriteStop } from '../lib/favoriteStops';
import { realtimeState, type RealtimeStatus } from '../lib/feedStatus';
import { useHomePreferences } from '../lib/HomePreferences';
import { GlassPressable, GlassSurface } from '../ui/Glass';
import { LiveIndicator } from '../ui/LiveIndicator';
import { NavIcon } from '../ui/NavIcon';
import { useTheme, type ThemeColors } from '../ui/Theme';
import { layout, typography } from '../ui/design';

const LOGO = require('../../assets/bus-front.png');

export function Home() {
  const { colors } = useTheme();
  const s = useMemo(() => createStyles(colors), [colors]);
  const { width } = useWindowDimensions();
  const insets = useSafeAreaInsets();
  const { content, recentLines, historyError } = useHomePreferences();
  const { openLine, opening, error } = useOpenLine();
  const state = useData<RealtimeStatus>('status', 0, true);
  const status = realtimeState(state.data, state.receivedAt, Boolean(state.error));
  const checking = !state.data && !state.error;
  const feedLabel = status === 'available' ? 'Feed live' : checking ? 'Verifica feed…' : status === 'partial' ? 'Feed parziale' : status === 'unknown' ? 'Feed da verificare' : 'Feed non disponibile';
  const [favorites, setFavorites] = useState<FavoriteStop[]>([]);
  const [favoritesReady, setFavoritesReady] = useState(false);
  const [favoriteError, setFavoriteError] = useState('');
  useFocusEffect(useCallback(() => {
    if (content !== 'favorite-stops') return;
    let active = true;
    setFavoritesReady(false); setFavoriteError('');
    void AsyncStorage.getItem('favorite-stops').then(raw => { if (active) setFavorites(parseFavoriteStops(raw)); })
      .catch(() => { if (active) { setFavorites([]); setFavoriteError('Impossibile recuperare le fermate preferite.'); } })
      .finally(() => { if (active) setFavoritesReady(true); });
    return () => { active = false; };
  }, [content]));
  const recentMode = content === 'recent-lines';
  return <View style={[s.page, { paddingBottom: Math.max(insets.bottom, 16) }]}>
    <View style={s.header}>
      <View style={s.brand}>
        <Image source={LOGO} resizeMode="contain" accessible={false} style={[s.logo, { tintColor: colors.accent }]} />
        <Text accessibilityLabel="ROMABUS" style={s.wordmark}>ROMABUS</Text>
      </View>
      <View style={s.feedChip}><LiveIndicator label={feedLabel} active={status === 'available'} /></View>
    </View>

    <View style={s.hero}>
      <Text accessibilityRole="header" style={[s.title, width < 360 && s.smallTitle]}>L’attesa ha{'\n'}<Text style={s.titleAccent}>i minuti contati.</Text></Text>
      <Text style={s.subtitle}>I bus di Roma, in tempo reale.</Text>
    </View>

    <GlassSurface style={s.feature}>
      <Text accessibilityRole="header" style={s.featureTitle}>{recentMode ? 'Ultime linee cercate' : 'Le tue fermate preferite'}</Text>
      {recentMode ? <>
        <Text style={s.caption}>{recentLines.length ? 'Riprendi una linea' : 'Le linee che cerchi compariranno qui.'}</Text>
        {recentLines.length > 0 && <View style={s.recentLines}>
          {recentLines.slice(0, 3).map(line => <Pressable key={line.name} disabled={opening} accessibilityRole="button" accessibilityLabel={`Apri linea recente ${line.name}`} accessibilityState={{ disabled: opening }} onPress={() => { void openLine(line); }} style={({ pressed }) => [s.recentLine, pressed && s.pressed, opening && s.disabled]}>
            <Badge name={line.name} />
          </Pressable>)}
          {opening && <ActivityIndicator accessibilityLabel="Apertura linea" color={colors.accent} />}
        </View>}
        {!!(error || historyError) && <Text accessibilityRole="alert" style={s.caption}>{error || historyError}</Text>}
      </> : <>
        {!favoritesReady ? <ActivityIndicator accessibilityLabel="Caricamento fermate preferite" color={colors.accent} /> : favorites.length > 0 ? <View>
          {favorites.slice(0, 3).map(stop => <Pressable key={stop.stop_id} accessibilityRole="button" accessibilityLabel={`Apri fermata preferita ${stop.name}`} onPress={() => router.push({ pathname: '/stop/[stopId]', params: { stopId: stop.stop_id, stopName: stop.name } })} style={({ pressed }) => [s.favorite, pressed && s.pressed]}>
            <View style={s.favoriteLabel}><Text numberOfLines={2} style={s.favoriteName}>{stop.name}</Text><Text style={s.caption}>Fermata {stop.stop_id}</Text></View>
            <Text accessible={false} style={s.arrow}>›</Text>
          </Pressable>)}
        </View> : <Text style={s.caption}>{favoriteError || 'Aggiungi una fermata ai preferiti con la stella per ritrovarla qui.'}</Text>}
      </>}
      <Pressable accessibilityRole="button" accessibilityLabel={recentMode ? 'Tutte le linee' : 'Tutte le fermate'} onPress={() => router.push(recentMode ? '/lines' : '/stops')} style={({ pressed }) => [s.featureFooter, pressed && s.pressed]}>
        <Text style={s.caption}>{recentMode ? 'Tutte le linee' : 'Tutte le fermate'}</Text><Text accessible={false} style={s.arrow}>›</Text>
      </Pressable>
    </GlassSurface>

    <View style={s.actions}>
      {([['lines', 'Cerca linea'], ['stops', 'Cerca fermata']] as const).map(([kind, label]) => <View style={s.actionSlot} key={kind}>
        <GlassPressable floating accessibilityRole="button" accessibilityLabel={label} onPress={() => router.push(kind === 'lines' ? '/lines' : '/stops')} style={s.action}>
          <NavIcon kind={kind} active /><Text style={s.actionText}>{label}</Text>
        </GlassPressable>
      </View>)}
    </View>

    <View accessible accessibilityRole="button" accessibilityLabel="Calcola percorso, funzionalità in arrivo" aria-disabled accessibilityState={{ disabled: true }} style={s.planner}>
      <NavIcon kind="plan" /><Text style={s.plannerText}>Calcola percorso</Text><Text style={s.coming}>In arrivo</Text>
    </View>

    <View style={s.footer}>
      <Text style={s.disclaimer}>ROMABUS è un progetto indipendente.{'\n'}NON è affiliato, autorizzato o connesso ad ATAC S.p.A. e/o Roma Servizi per la Mobilità.{'\n'}I dati in tempo reale sono open source e forniti ufficialmente da Roma Servizi per la Mobilità.</Text>
      <GlassPressable accessibilityRole="button" accessibilityLabel="Apri impostazioni" onPress={() => router.push('/settings')} style={s.settings}>
        <NavIcon kind="settings" active /><Text style={s.settingsText}>Impostazioni</Text><Text accessible={false} style={s.arrow}>›</Text>
      </GlassPressable>
    </View>
  </View>;
}

const createStyles = (colors: ThemeColors) => StyleSheet.create({
  page: { flex: 1, width: '100%', maxWidth: 420, alignSelf: 'center', paddingTop: 18, gap: 14 },
  header: { flexDirection: 'row', flexWrap: 'wrap', alignItems: 'center', justifyContent: 'space-between', gap: 10 },
  brand: { flexDirection: 'row', alignItems: 'center', gap: 8 }, logo: { width: 30, height: 38 }, wordmark: { fontSize: 19, fontWeight: '800', letterSpacing: 1, color: colors.accent },
  feedChip: { paddingVertical: 6, paddingHorizontal: 10, backgroundColor: colors.surface, borderRadius: 20 },
  hero: { gap: 12, marginTop: 14, marginBottom: 10 }, title: { fontSize: 36, lineHeight: 41, fontWeight: '800', letterSpacing: -1.1, color: colors.text }, smallTitle: { fontSize: 32, lineHeight: 37 }, titleAccent: { color: colors.accent }, subtitle: { ...typography.label, fontWeight: '400', color: colors.muted },
  feature: { paddingHorizontal: layout.cardPadding, paddingTop: 16, borderRadius: 21, gap: 10, minHeight: 170 }, featureTitle: { ...typography.label, fontWeight: '700', color: colors.text },
  caption: { ...typography.caption, color: colors.muted }, recentLines: { flexDirection: 'row', alignItems: 'center', gap: 12, flexWrap: 'wrap' }, recentLine: { borderRadius: 12 },
  featureFooter: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', borderTopWidth: 1, borderColor: colors.border, minHeight: 44, marginTop: 'auto', gap: 10 },
  favorite: { flexDirection: 'row', alignItems: 'center', gap: 12, minHeight: 58, paddingVertical: 8 }, favoriteLabel: { flex: 1, minWidth: 0, gap: 2 }, favoriteName: { ...typography.label, color: colors.text },
  actions: { flexDirection: 'row', gap: 12 }, actionSlot: { flex: 1, minWidth: 0 }, action: { minHeight: 94, padding: 14, gap: 12, alignItems: 'flex-start', justifyContent: 'center', borderRadius: 18 }, actionText: { ...typography.label, color: colors.text, fontWeight: '700' },
  planner: { flexDirection: 'row', alignItems: 'center', flexWrap: 'wrap', gap: 10, paddingHorizontal: 2, minHeight: 44 }, plannerText: { ...typography.caption, color: colors.muted }, coming: { ...typography.micro, color: colors.muted, marginLeft: 'auto', borderWidth: 1, borderColor: colors.border, borderRadius: 6, paddingHorizontal: 8, paddingVertical: 4 },
  footer: { marginTop: 'auto', paddingTop: 10, gap: 14 }, disclaimer: { ...typography.micro, color: colors.muted },
  settings: { flexDirection: 'row', alignItems: 'center', gap: 12, minHeight: 50, paddingHorizontal: 14, paddingVertical: 10, borderRadius: 16 }, settingsText: { ...typography.label, color: colors.text, flex: 1 }, arrow: { fontSize: 24, lineHeight: 28, color: colors.accent },
  pressed: { opacity: 0.75 }, disabled: { opacity: 0.55 },
});
