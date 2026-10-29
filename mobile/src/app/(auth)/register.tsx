import { Link } from 'expo-router';
import { useState } from 'react';

import { useRegister } from '@/api/hooks';
import { Button, ErrorBanner, Field, Screen, Spacer, Text } from '@/components/ui';
import { useAuth } from '@/store/auth';
import { colors, space } from '@/theme';

export default function Register() {
  const [f, setF] = useState({ full_name: '', email: '', phone: '', password: '' });
  const reg = useRegister();
  const signIn = useAuth((s) => s.signIn);
  const valid = f.full_name.trim() && /\S+@\S+\.\S+/.test(f.email) && f.password.length >= 8;
  const set = (k: keyof typeof f) => (v: string) => setF((p) => ({ ...p, [k]: v }));
  return (
    <Screen>
      <Spacer h={space.xl} />
      <Text variant="title">Create your account</Text>
      <Text color={colors.inkSoft} style={{ marginBottom: space.xl, marginTop: 6 }}>One account for riding and, once verified, driving.</Text>
      <ErrorBanner error={reg.error} />
      <Field label="Full name" value={f.full_name} onChangeText={set('full_name')} autoComplete="name" />
      <Field label="Email" value={f.email} onChangeText={set('email')} autoCapitalize="none" keyboardType="email-address" autoComplete="email" />
      <Field label="Phone (optional)" value={f.phone} onChangeText={set('phone')} keyboardType="phone-pad" autoComplete="tel" />
      <Field label="Password" value={f.password} onChangeText={set('password')} secureTextEntry autoComplete="new-password" error={f.password && f.password.length < 8 ? 'At least 8 characters' : null} />
      <Button title="Create account" disabled={!valid} loading={reg.isPending}
        onPress={() => reg.mutate({ ...f, email: f.email.trim(), phone: f.phone || undefined }, { onSuccess: (t) => void signIn(t) })} />
      <Spacer />
      <Link href="/(auth)/login"><Text variant="bodyBold" color={colors.brand} style={{ textAlign: 'center' }}>I already have an account</Text></Link>
    </Screen>
  );
}
