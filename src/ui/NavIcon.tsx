import React from 'react';
import { StyleSheet, View } from 'react-native';
import { useTheme } from './Theme';
export type Category = 'lines' | 'stops' | 'plan' | 'settings';
export function NavIcon({ kind, active = false }: { kind: Category; active?: boolean }) {
  const { colors } = useTheme();
  const color = active ? colors.accent : colors.muted;
  return <View accessible={false} style={s.icon}>
    {kind === 'lines' ? <><View style={[s.bus, { borderColor: color }]}><View style={[s.window, { borderColor: color }]} /><View style={s.lights}><View style={[s.light, { backgroundColor: color }]} /><View style={[s.light, { backgroundColor: color }]} /></View></View><View style={[s.wheel, { left: 6, backgroundColor: color }]} /><View style={[s.wheel, { right: 6, backgroundColor: color }]} /></>
      : kind === 'stops' ? <><View style={[s.pin, { borderColor: color }]}><View style={[s.dot, { backgroundColor: color }]} /></View><View style={[s.stem, { backgroundColor: color }]} /></>
      : kind === 'plan' ? <><View style={[s.route, { borderColor: color }]} /><View style={[s.endpoint, { top: 2, left: 2, borderColor: color, backgroundColor: colors.surface }]} /><View style={[s.endpoint, { bottom: 2, right: 2, borderColor: color, backgroundColor: colors.surface }]} /></>
      : <>{[0, 45, 90, 135].map(angle => <View key={angle} style={[s.gearTeeth, { backgroundColor: color, transform: [{ rotate: `${angle}deg` }] }]} />)}<View style={[s.gear, { borderColor: color, backgroundColor: active ? colors.accentSoft : colors.surface }]}><View style={[s.gearCenter, { borderColor: color }]} /></View></>}
  </View>;
}
const s = StyleSheet.create({
  icon: { width: 26, height: 26, alignItems: 'center', justifyContent: 'center' },
  bus: { width: 18, height: 20, borderWidth: 1.7, borderRadius: 5, padding: 3 }, window: { height: 7, borderBottomWidth: 1.5 },
  lights: { flexDirection: 'row', justifyContent: 'space-between', marginTop: 4 }, light: { width: 3, height: 2, borderRadius: 1 }, wheel: { position: 'absolute', width: 3, height: 3, borderRadius: 1, bottom: 1 },
  pin: { width: 18, height: 18, borderWidth: 1.7, borderRadius: 9, alignItems: 'center', justifyContent: 'center', marginBottom: 6 }, dot: { width: 5, height: 5, borderRadius: 3 }, stem: { position: 'absolute', width: 1.7, height: 7, bottom: 1 },
  route: { width: 15, height: 15, borderWidth: 1.7, borderRadius: 5, transform: [{ rotate: '-20deg' }] }, endpoint: { position: 'absolute', width: 7, height: 7, borderWidth: 1.7, borderRadius: 4 },
  gearTeeth: { position: 'absolute', width: 5, height: 24, borderRadius: 1 }, gear: { width: 18, height: 18, borderRadius: 9, borderWidth: 1.7, alignItems: 'center', justifyContent: 'center' }, gearCenter: { width: 7, height: 7, borderRadius: 4, borderWidth: 1.7 },
});
