import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { Stack, useRouter, useSegments } from 'expo-router';
import { StatusBar } from 'expo-status-bar';
import { useEffect, useState } from 'react';
import { View } from 'react-native';
import { SafeAreaProvider } from 'react-native-safe-area-context';

import { useUserSocket } from '@/api/hooks';
import { Loading } from '@/components/ui';
import { useAuth } from '@/store/auth';
import { colors } from '@/theme';

function LiveUpdates() {
  useUserSocket(); // real-time notifications + state changes over WebSocket
  return null;
}

/** Sends people to the right place: onboarding -> sign in -> the passenger or driver tabs. */
function Gate() {
  const { ready, me, onboarded, mode } = useAuth();
  const segments = useSegments();
  const router = useRouter();
  useEffect(() => {
    if (!ready) return;
    const top = segments[0] as string | undefined;
    if (!onboarded && top !== 'onboarding') router.replace('/onboarding');
    else if (onboarded && !me && top !== '(auth)') router.replace('/(auth)/login');
    else if (me && (top === '(auth)' || top === 'onboarding' || top === undefined)) router.replace(mode === 'driver' ? '/(driver)/dashboard' : '/(passenger)');
  }, [ready, me, onboarded, mode, segments, router]);
  return null;
}

export default function RootLayout() {
  const [client] = useState(() => new QueryClient({ defaultOptions: { queries: { retry: 1, staleTime: 5_000 } } }));
  const { ready, me, bootstrap } = useAuth();
  useEffect(() => { void bootstrap(); }, [bootstrap]);

  return (
    <QueryClientProvider client={client}>
      <SafeAreaProvider>
        <StatusBar style="dark" />
        {!ready ? <View style={{ flex: 1, backgroundColor: colors.bg, justifyContent: 'center' }}><Loading /></View> : (
          <>
            <Gate />
            {me && <LiveUpdates />}
            <Stack screenOptions={{ headerShown: false, contentStyle: { backgroundColor: colors.bg } }}>
              <Stack.Screen name="request/new" options={{ presentation: 'modal' }} />
              <Stack.Screen name="driver/new-trip" options={{ presentation: 'modal' }} />
              <Stack.Screen name="pay/[id]" options={{ presentation: 'modal' }} />
              <Stack.Screen name="rate/[id]" options={{ presentation: 'modal' }} />
              <Stack.Screen name="safety/[id]" options={{ presentation: 'modal' }} />
            </Stack>
          </>
        )}
      </SafeAreaProvider>
    </QueryClientProvider>
  );
}
