import React, { useEffect, useState } from 'react';
import { AccessibilityInfo, Animated, Easing, Platform, StyleSheet, Text, View } from 'react-native';
import { useTheme } from './Theme';
import { typography } from './design';

export function LiveIndicator() {
  const { colors } = useTheme();
  const [opacity] = useState(() => new Animated.Value(1));
  const [reduceMotion, setReduceMotion] = useState(true);
  useEffect(() => {
    let active = true;
    void AccessibilityInfo.isReduceMotionEnabled().then(value => { if (active) setReduceMotion(value); }).catch(() => {});
    const listener = AccessibilityInfo.addEventListener('reduceMotionChanged', setReduceMotion);
    return () => { active = false; listener?.remove(); };
  }, []);
  useEffect(() => {
    opacity.setValue(1);
    if (reduceMotion) return;
    const config = { duration: 1300, easing: Easing.inOut(Easing.ease), useNativeDriver: Platform.OS !== 'web', isInteraction: false };
    const pulse = Animated.loop(Animated.sequence([
      Animated.timing(opacity, { ...config, toValue: 0.45 }),
      Animated.timing(opacity, { ...config, toValue: 1 }),
    ]));
    pulse.start();
    return () => pulse.stop();
  }, [opacity, reduceMotion]);
  return <View style={styles.row}>
    <Animated.View accessible={false} style={[styles.dot, { backgroundColor: colors.live, opacity }]} />
    <Text style={[styles.label, { color: colors.live }]}>Live</Text>
  </View>;
}

const styles = StyleSheet.create({
  row: { flexDirection: 'row', alignItems: 'center', gap: 4 },
  dot: { width: 6, height: 6, borderRadius: 3 }, label: typography.caption,
});
