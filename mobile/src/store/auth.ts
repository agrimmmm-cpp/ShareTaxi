import { create } from 'zustand';

import { api, loadTokens, setSignedOutHandler, setTokens } from '@/api/client';
import { storage } from '@/api/storage';
import type { Me, TokenPair } from '@/api/types';

export type Mode = 'passenger' | 'driver';

interface AuthState {
  ready: boolean;
  me: Me | null;
  mode: Mode;
  onboarded: boolean;
  bootstrap: () => Promise<void>;
  signIn: (tokens: TokenPair) => Promise<void>;
  signOut: () => Promise<void>;
  refreshMe: () => Promise<void>;
  setMode: (m: Mode) => void;
  finishOnboarding: () => Promise<void>;
}

export const useAuth = create<AuthState>((set, get) => ({
  ready: false,
  me: null,
  mode: 'passenger',
  onboarded: false,
  async bootstrap() {
    setSignedOutHandler(() => set({ me: null, mode: 'passenger' }));
    const [onboarded, mode] = await Promise.all([storage.get('onboarded'), storage.get('mode')]);
    set({ onboarded: onboarded === '1', mode: mode === 'driver' ? 'driver' : 'passenger' });
    if (await loadTokens()) {
      try {
        set({ me: await api<Me>('/auth/me') });
      } catch { /* signed out by the client on 401; offline keeps tokens */ }
    }
    set({ ready: true });
  },
  async signIn(tokens) {
    await setTokens(tokens);
    set({ me: await api<Me>('/auth/me') });
  },
  async signOut() {
    await setTokens(null);
    set({ me: null, mode: 'passenger' });
  },
  async refreshMe() {
    set({ me: await api<Me>('/auth/me') });
  },
  setMode(mode) {
    if (mode === 'driver' && !get().me?.roles.includes('driver')) return;
    void storage.set('mode', mode);
    set({ mode });
  },
  async finishOnboarding() {
    await storage.set('onboarded', '1');
    set({ onboarded: true });
  },
}));
