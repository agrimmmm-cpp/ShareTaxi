import { useRouter } from 'expo-router';

import { useAuth, Mode } from '@/store/auth';

import { Toggle } from './ui';

/** Passenger <-> Driver switch. Drivers see it everywhere; others get a "Drive & Earn" entry instead. */
export function ModeToggle() {
  const { mode, setMode, me } = useAuth();
  const router = useRouter();
  if (!me?.roles.includes('driver')) return null;
  return (
    <Toggle
      value={mode}
      onChange={(k) => { setMode(k as Mode); router.replace(k === 'driver' ? '/(driver)/dashboard' : '/(passenger)'); }}
      left={{ key: 'passenger', label: 'Passenger', icon: 'person' }}
      right={{ key: 'driver', label: 'Driver', icon: 'car-sport' }}
    />
  );
}
