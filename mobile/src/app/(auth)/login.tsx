import { Link } from 'expo-router';
import { useState } from 'react';
import { KeyboardAvoidingView, Platform, View } from 'react-native';

import { useLogin } from '@/api/hooks';
import { Button, ErrorBanner, Field, Screen, Spacer, Text } from '@/components/ui';
import { useAuth } from '@/store/auth';
import { colors, space } from '@/theme';

export default function Login() {
  const [email, setEmail] = useState('alice@sharetaxi.dev');
  const [password, setPassword] = useState('password123');
  const login = useLogin();
  const signIn = useAuth((s) => s.signIn);
  const submit = () => login.mutate({ email: email.trim(), password }, { onSuccess: (t) => void signIn(t) });
  return (
    <Screen>
      <KeyboardAvoidingView behavior={Platform.OS === 'ios' ? 'padding' : undefined}>
        <Spacer h={space.xxl} />
        <Text variant="display" color={colors.brand}>ShareTaxi</Text>
        <Text color={colors.inkSoft} style={{ marginTop: 6, marginBottom: space.xl }}>Post where you're going. We find people going your way.</Text>
        <ErrorBanner error={login.error} />
        <Field label="Email" value={email} onChangeText={setEmail} autoCapitalize="none" keyboardType="email-address" autoComplete="email" />
        <Field label="Password" value={password} onChangeText={setPassword} secureTextEntry autoComplete="password" onSubmitEditing={submit} />
        <Button title="Sign in" onPress={submit} loading={login.isPending} />
        <View style={{ marginTop: space.lg, alignItems: 'center' }}>
          <Link href="/(auth)/register"><Text variant="bodyBold" color={colors.brand}>New here? Create an account</Text></Link>
        </View>
        <Text variant="caption" color={colors.mute} style={{ textAlign: 'center', marginTop: space.xl }}>Demo accounts (after seeding): alice / bob / carol / dave (driver) @sharetaxi.dev · password123</Text>
      </KeyboardAvoidingView>
    </Screen>
  );
}
