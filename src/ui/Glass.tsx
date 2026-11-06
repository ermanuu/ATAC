import React from 'react';
import { Pressable, StyleSheet, View, type PressableProps, type ViewProps } from 'react-native';
import { LinearGradient } from 'expo-linear-gradient';
import { useTheme, type ThemeColors } from './Theme';
import { layout } from './design';

export const getSurfaceStyle = (colors: ThemeColors) => ({
  backgroundColor: colors.surface,
  borderWidth: 1,
  borderColor: colors.border,
  borderRadius: layout.radius,
  boxShadow: colors.shadow,
});

/** Opaque reading surfaces shared by the light and dark themes. */
export function GlassSurface({ children, style, floating = false, ...props }: ViewProps & { floating?: boolean }) {
  const { colors } = useTheme();
  return <View {...props} style={[getSurfaceStyle(colors), floating && { boxShadow: colors.floatingShadow }, style]}>{children}</View>;
}

export function GlassPressable({ children, style, floating = false, ...props }: Omit<PressableProps, 'style' | 'children'> & { children: React.ReactNode; style?: ViewProps['style']; floating?: boolean }) {
  return <Pressable {...props} style={({ pressed }) => [pressed && styles.pressed, props.disabled && styles.disabled]}>
    <GlassSurface floating={floating} style={style}>{children}</GlassSurface>
  </Pressable>;
}

export function GlassBackground() {
  const { colors } = useTheme();
  return <View pointerEvents="none" accessible={false} style={[StyleSheet.absoluteFill, styles.backdrop, { backgroundColor: colors.background }]}>
    <LinearGradient colors={colors.backgroundGradient} start={{ x: 0, y: 0 }} end={{ x: 1, y: 1 }} style={StyleSheet.absoluteFill} />
    <LinearGradient colors={colors.sphereRed} style={styles.sphereRed} />
    <LinearGradient colors={colors.sphereBlue} style={styles.sphereBlue} />
  </View>;
}
const styles = StyleSheet.create({
  backdrop: { overflow: 'hidden' },
  sphereRed: { position: 'absolute', width: 420, height: 420, borderRadius: 210, top: 120, right: -260, transform: [{ rotate: '-25deg' }] },
  sphereBlue: { position: 'absolute', width: 460, height: 460, borderRadius: 230, bottom: -160, left: -250, transform: [{ rotate: '35deg' }] },
  pressed: { opacity: 0.8, transform: [{ scale: 0.985 }] },
  disabled: { opacity: 0.55 },
});
