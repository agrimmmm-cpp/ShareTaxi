import { Ionicons } from '@expo/vector-icons';
import { ReactNode } from 'react';
import {
  ActivityIndicator, Pressable, ScrollView, StyleProp, StyleSheet, Text as RNText, TextInput, TextInputProps, TextStyle, View, ViewStyle,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { colors, radius, shadow, space } from '@/theme';

type Icon = keyof typeof Ionicons.glyphMap;

// ------------------------------------------------------------------ Text
const textStyles = {
  display: { fontSize: 32, fontWeight: '800', letterSpacing: -0.8, lineHeight: 38 },
  title: { fontSize: 24, fontWeight: '800', letterSpacing: -0.4, lineHeight: 30 },
  h2: { fontSize: 18, fontWeight: '700', letterSpacing: -0.2 },
  body: { fontSize: 15, fontWeight: '400', lineHeight: 21 },
  bodyBold: { fontSize: 15, fontWeight: '600', lineHeight: 21 },
  caption: { fontSize: 13, fontWeight: '400', lineHeight: 18 },
  label: { fontSize: 12, fontWeight: '700', letterSpacing: 0.6, textTransform: 'uppercase' },
  money: { fontSize: 28, fontWeight: '800', letterSpacing: -0.5 },
} as const;

export function Text({ variant = 'body', color = colors.ink, style, children, ...rest }: {
  variant?: keyof typeof textStyles; color?: string; style?: StyleProp<TextStyle>; children?: ReactNode; numberOfLines?: number; onPress?: () => void;
}) {
  return <RNText {...rest} style={[textStyles[variant], { color }, style]}>{children}</RNText>;
}

// ------------------------------------------------------------------ Button
type BtnVariant = 'primary' | 'secondary' | 'ghost' | 'danger' | 'driver' | 'soft';
const btn: Record<BtnVariant, { bg: string; fg: string; border?: string }> = {
  primary: { bg: colors.brand, fg: colors.white },
  driver: { bg: colors.driver, fg: colors.white },
  secondary: { bg: colors.card, fg: colors.ink, border: colors.line },
  soft: { bg: colors.brandSoft, fg: colors.brandDark },
  ghost: { bg: 'transparent', fg: colors.brand },
  danger: { bg: colors.dangerSoft, fg: colors.danger },
};

export function Button({ title, onPress, variant = 'primary', icon, loading, disabled, style, small }: {
  title: string; onPress?: () => void; variant?: BtnVariant; icon?: Icon; loading?: boolean; disabled?: boolean; style?: StyleProp<ViewStyle>; small?: boolean;
}) {
  const c = btn[variant];
  const off = disabled || loading;
  return (
    <Pressable
      accessibilityRole="button" accessibilityState={{ disabled: !!off }} onPress={off ? undefined : onPress}
      style={({ pressed }) => [s.btn, small && s.btnSmall, { backgroundColor: c.bg, borderColor: c.border ?? 'transparent', opacity: off ? 0.5 : pressed ? 0.85 : 1 }, style]}
    >
      {loading ? <ActivityIndicator color={c.fg} /> : (
        <>
          {icon && <Ionicons name={icon} size={small ? 16 : 18} color={c.fg} style={{ marginRight: 8 }} />}
          <RNText style={{ color: c.fg, fontWeight: '700', fontSize: small ? 14 : 16 }}>{title}</RNText>
        </>
      )}
    </Pressable>
  );
}

// ------------------------------------------------------------------ layout
export function Screen({ children, scroll = true, padded = true, footer, bg = colors.bg }: {
  children: ReactNode; scroll?: boolean; padded?: boolean; footer?: ReactNode; bg?: string;
}) {
  const body = scroll ? (
    <ScrollView contentContainerStyle={[padded && s.pad, { paddingBottom: space.xxl * 2 }]} keyboardShouldPersistTaps="handled" showsVerticalScrollIndicator={false}>
      {children}
    </ScrollView>
  ) : <View style={[{ flex: 1 }, padded && s.pad]}>{children}</View>;
  return (
    <SafeAreaView style={{ flex: 1, backgroundColor: bg }} edges={['top', 'left', 'right']}>
      {body}
      {footer && <View style={s.footer}>{footer}</View>}
    </SafeAreaView>
  );
}

export function Card({ children, style, onPress, tone }: { children: ReactNode; style?: StyleProp<ViewStyle>; onPress?: () => void; tone?: 'brand' | 'warn' | 'savings' | 'driver' }) {
  const bg = tone === 'brand' ? colors.brandSoft : tone === 'warn' ? colors.warnSoft : tone === 'savings' ? colors.savingsSoft : tone === 'driver' ? colors.driverSoft : colors.card;
  const inner = <View style={[s.card, tone ? { backgroundColor: bg, shadowOpacity: 0 } : null, style]}>{children}</View>;
  return onPress ? <Pressable onPress={onPress} style={({ pressed }) => ({ opacity: pressed ? 0.9 : 1 })}>{inner}</Pressable> : inner;
}

export const Row = ({ children, style, gap = space.md, align = 'center' }: { children: ReactNode; style?: StyleProp<ViewStyle>; gap?: number; align?: 'center' | 'flex-start' | 'flex-end' }) => (
  <View style={[{ flexDirection: 'row', alignItems: align, gap }, style]}>{children}</View>
);
export const Spacer = ({ h = space.lg }: { h?: number }) => <View style={{ height: h }} />;
export const Divider = () => <View style={{ height: StyleSheet.hairlineWidth, backgroundColor: colors.line, marginVertical: space.md }} />;

export function Section({ title, action, children }: { title: string; action?: { label: string; onPress: () => void }; children: ReactNode }) {
  return (
    <View style={{ marginTop: space.xl }}>
      <Row style={{ justifyContent: 'space-between', marginBottom: space.md }}>
        <Text variant="h2">{title}</Text>
        {action && <Text variant="bodyBold" color={colors.brand} onPress={action.onPress}>{action.label}</Text>}
      </Row>
      {children}
    </View>
  );
}

// ------------------------------------------------------------------ small pieces
export function Badge({ label, tone = 'neutral', icon }: { label: string; tone?: 'neutral' | 'brand' | 'savings' | 'warn' | 'danger' | 'info' | 'driver'; icon?: Icon }) {
  const t = {
    neutral: [colors.line, colors.inkSoft], brand: [colors.brandSoft, colors.brandDark], savings: [colors.savingsSoft, colors.savings],
    warn: [colors.warnSoft, colors.warn], danger: [colors.dangerSoft, colors.danger], info: [colors.infoSoft, colors.info], driver: [colors.driverSoft, colors.driver],
  }[tone];
  return (
    <View style={[s.badge, { backgroundColor: t[0] }]}>
      {icon && <Ionicons name={icon} size={12} color={t[1]} style={{ marginRight: 4 }} />}
      <RNText style={{ color: t[1], fontSize: 12, fontWeight: '700' }}>{label}</RNText>
    </View>
  );
}

export function Chip({ label, selected, onPress, icon }: { label: string; selected?: boolean; onPress?: () => void; icon?: Icon }) {
  return (
    <Pressable onPress={onPress} accessibilityState={{ selected: !!selected }} style={[s.chip, selected && { backgroundColor: colors.ink, borderColor: colors.ink }]}>
      {icon && <Ionicons name={icon} size={14} color={selected ? colors.white : colors.inkSoft} style={{ marginRight: 6 }} />}
      <RNText style={{ color: selected ? colors.white : colors.inkSoft, fontWeight: '600', fontSize: 14 }}>{label}</RNText>
    </Pressable>
  );
}

export function Field({ label, error, ...input }: TextInputProps & { label?: string; error?: string | null }) {
  return (
    <View style={{ marginBottom: space.md }}>
      {label && <Text variant="label" color={colors.mute} style={{ marginBottom: 6 }}>{label}</Text>}
      <TextInput placeholderTextColor={colors.mute} {...input} style={[s.input, error ? { borderColor: colors.danger } : null, input.style]} />
      {error ? <Text variant="caption" color={colors.danger} style={{ marginTop: 4 }}>{error}</Text> : null}
    </View>
  );
}

export function Stepper({ value, onChange, min = 0, max = 99, step = 1, format }: {
  value: number; onChange: (v: number) => void; min?: number; max?: number; step?: number; format?: (v: number) => string;
}) {
  const btnStyle = (disabled: boolean): ViewStyle => ({ ...s.stepBtn, opacity: disabled ? 0.35 : 1 });
  return (
    <Row gap={space.md}>
      <Pressable accessibilityLabel="Decrease" disabled={value <= min} onPress={() => onChange(Math.max(min, value - step))} style={btnStyle(value <= min)}>
        <Ionicons name="remove" size={20} color={colors.ink} />
      </Pressable>
      <Text variant="h2" style={{ minWidth: 64, textAlign: 'center' }}>{format ? format(value) : value}</Text>
      <Pressable accessibilityLabel="Increase" disabled={value >= max} onPress={() => onChange(Math.min(max, value + step))} style={btnStyle(value >= max)}>
        <Ionicons name="add" size={20} color={colors.ink} />
      </Pressable>
    </Row>
  );
}

export function Toggle({ value, onChange, left, right }: { value: string; onChange: (v: string) => void; left: { key: string; label: string; icon: Icon }; right: { key: string; label: string; icon: Icon } }) {
  return (
    <View style={s.toggle}>
      {[left, right].map((o) => (
        <Pressable key={o.key} onPress={() => onChange(o.key)} style={[s.toggleItem, value === o.key && { backgroundColor: colors.white, ...shadow.card }]}>
          <Ionicons name={o.icon} size={16} color={value === o.key ? colors.ink : colors.mute} />
          <RNText style={{ marginLeft: 6, fontWeight: '700', color: value === o.key ? colors.ink : colors.mute }}>{o.label}</RNText>
        </Pressable>
      ))}
    </View>
  );
}

export function ErrorBanner({ error }: { error: unknown }) {
  if (!error) return null;
  return (
    <View style={[s.card, { backgroundColor: colors.dangerSoft, shadowOpacity: 0, marginBottom: space.md }]}>
      <Text color={colors.danger} variant="bodyBold">{error instanceof Error ? error.message : 'Something went wrong'}</Text>
    </View>
  );
}

export function Loading() {
  return <View style={{ padding: space.xxl, alignItems: 'center' }}><ActivityIndicator color={colors.brand} /></View>;
}

export function Empty({ icon, title, body, action }: { icon: Icon; title: string; body?: string; action?: ReactNode }) {
  return (
    <View style={{ alignItems: 'center', padding: space.xxl, gap: space.sm }}>
      <View style={s.emptyIcon}><Ionicons name={icon} size={28} color={colors.brand} /></View>
      <Text variant="h2" style={{ textAlign: 'center' }}>{title}</Text>
      {body && <Text color={colors.mute} style={{ textAlign: 'center' }}>{body}</Text>}
      {action}
    </View>
  );
}

export function IconButton({ icon, onPress, label, tone = 'default' }: { icon: Icon; onPress: () => void; label: string; tone?: 'default' | 'danger' }) {
  return (
    <Pressable accessibilityLabel={label} onPress={onPress} style={[s.iconBtn, tone === 'danger' && { backgroundColor: colors.dangerSoft }]}>
      <Ionicons name={icon} size={20} color={tone === 'danger' ? colors.danger : colors.ink} />
    </Pressable>
  );
}

const s = StyleSheet.create({
  pad: { padding: space.lg },
  footer: { padding: space.lg, backgroundColor: colors.card, borderTopWidth: StyleSheet.hairlineWidth, borderTopColor: colors.line },
  btn: { minHeight: 52, borderRadius: radius.md, paddingHorizontal: space.xl, alignItems: 'center', justifyContent: 'center', flexDirection: 'row', borderWidth: 1 },
  btnSmall: { minHeight: 40, paddingHorizontal: space.lg, borderRadius: radius.sm },
  card: { backgroundColor: colors.card, borderRadius: radius.lg, padding: space.lg, ...shadow.card },
  badge: { flexDirection: 'row', alignItems: 'center', paddingHorizontal: 10, paddingVertical: 4, borderRadius: radius.pill, alignSelf: 'flex-start' },
  chip: { flexDirection: 'row', alignItems: 'center', paddingHorizontal: 14, paddingVertical: 9, borderRadius: radius.pill, borderWidth: 1, borderColor: colors.line, backgroundColor: colors.card },
  input: { minHeight: 52, borderRadius: radius.md, borderWidth: 1, borderColor: colors.line, backgroundColor: colors.card, paddingHorizontal: space.lg, fontSize: 16, color: colors.ink },
  stepBtn: { width: 40, height: 40, borderRadius: 20, backgroundColor: colors.card, borderWidth: 1, borderColor: colors.line, alignItems: 'center', justifyContent: 'center' },
  toggle: { flexDirection: 'row', backgroundColor: colors.line, borderRadius: radius.pill, padding: 3 },
  toggleItem: { flex: 1, flexDirection: 'row', alignItems: 'center', justifyContent: 'center', paddingVertical: 9, borderRadius: radius.pill },
  emptyIcon: { width: 64, height: 64, borderRadius: 32, backgroundColor: colors.brandSoft, alignItems: 'center', justifyContent: 'center', marginBottom: space.sm },
  iconBtn: { width: 42, height: 42, borderRadius: 21, backgroundColor: colors.card, alignItems: 'center', justifyContent: 'center', ...shadow.card },
});
