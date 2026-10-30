import React, { createContext, useContext, useEffect, useState } from 'react';
import { AccessibilityInfo, Platform, Pressable, StyleSheet, View, type PressableProps, type ViewProps } from 'react-native';
import { BlurView } from 'expo-blur';
import { GlassView, isGlassEffectAPIAvailable, isLiquidGlassAvailable } from 'expo-glass-effect';
import { LinearGradient } from 'expo-linear-gradient';

const ReduceTransparency = createContext(false);
const nativeGlass = Platform.OS === 'ios' && isGlassEffectAPIAvailable() && isLiquidGlassAvailable();
export const glassStyle = {
  backgroundColor: 'rgba(255,255,255,0.58)',
  borderWidth: 1,
  borderColor: 'rgba(255,255,255,0.95)',
  borderRadius: 22,
  boxShadow: '0 6px 24px rgba(66,45,59,0.06), inset 0 1px 0 rgba(255,255,255,0.9)',
} as const;

export function GlassProvider({ children }: React.PropsWithChildren) {
  const [reduced, setReduced] = useState(false);
  useEffect(() => {
    if (Platform.OS !== 'ios') return;
    let active = true;
    void AccessibilityInfo.isReduceTransparencyEnabled().then(value => { if (active) setReduced(value); }).catch(() => {});
    const subscription = AccessibilityInfo.addEventListener('reduceTransparencyChanged', setReduced);
    return () => { active = false; subscription.remove(); };
  }, []);
  return <ReduceTransparency.Provider value={reduced}>{children}</ReduceTransparency.Provider>;
}

/** Native glass for floating controls; quieter frosted material for reading surfaces. */
export function GlassSurface({ children, style, floating = false, ...props }: ViewProps & { floating?: boolean }) {
  const reduced = useContext(ReduceTransparency);
  return <View {...props} style={[glassStyle, style, reduced && styles.opaque]}>
    {!reduced && <View pointerEvents="none" accessible={false} style={[styles.material, { borderRadius: StyleSheet.flatten(style)?.borderRadius ?? 22 }]}>
      {floating && nativeGlass
        ? <GlassView glassEffectStyle="regular" colorScheme="light" style={styles.fill} />
        : <BlurView tint="light" intensity={floating ? 65 : 24} style={styles.fill} />}
      <LinearGradient colors={['rgba(255,255,255,0.48)', 'rgba(255,255,255,0.03)', 'rgba(255,255,255,0.18)']} style={styles.fill} />
    </View>}
    {children}
  </View>;
}

export function GlassPressable({ children, style, floating = false, ...props }: Omit<PressableProps, 'style' | 'children'> & { children: React.ReactNode; style?: ViewProps['style']; floating?: boolean }) {
  return <Pressable {...props} style={({ pressed }) => [pressed && styles.pressed]}>
    <GlassSurface floating={floating} style={style}>{children}</GlassSurface>
  </Pressable>;
}

export function GlassBackground() {
  return <View pointerEvents="none" accessible={false} style={[styles.fill, styles.backdrop]}>
    <LinearGradient colors={['#f8e9ed', '#f5f4f8', '#e4eff1']} start={{ x: 0, y: 0 }} end={{ x: 1, y: 1 }} style={styles.fill} />
    <LinearGradient colors={['rgba(196,58,96,0.14)', 'rgba(239,187,199,0.02)']} style={styles.rose} />
    <LinearGradient colors={['rgba(164,204,217,0.22)', 'rgba(222,242,244,0.02)']} style={styles.blue} />
  </View>;
}
const styles = StyleSheet.create({
  fill: { position: 'absolute', top: 0, right: 0, bottom: 0, left: 0 },
  material: { position: 'absolute', top: 0, right: 0, bottom: 0, left: 0, overflow: 'hidden' },
  backdrop: { overflow: 'hidden' },
  pressed: { transform: [{ scale: 0.985 }] },
  opaque: { backgroundColor: '#ffffff' },
  rose: { position: 'absolute', width: 420, height: 420, borderRadius: 210, top: 120, right: -260, transform: [{ rotate: '-25deg' }] },
  blue: { position: 'absolute', width: 460, height: 460, borderRadius: 230, bottom: -160, left: -250, transform: [{ rotate: '35deg' }] },
});
