import { Platform } from 'react-native';

import { storage } from './storage';
import type { TokenPair } from './types';

const fallback = Platform.OS === 'android' ? 'http://10.0.2.2:8000' : 'http://localhost:8000';
export const API_URL = (process.env.EXPO_PUBLIC_API_URL ?? fallback).replace(/\/$/, '');
export const WS_URL = API_URL.replace(/^http/, 'ws');

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

type Listener = () => void;
let tokens: TokenPair | null = null;
let onSignedOut: Listener = () => {};

export const setSignedOutHandler = (fn: Listener) => { onSignedOut = fn; };
export const getAccessToken = () => tokens?.access_token ?? null;

export async function setTokens(next: TokenPair | null): Promise<void> {
  tokens = next;
  if (next) await storage.set('tokens', JSON.stringify(next));
  else await storage.remove('tokens');
}

export async function loadTokens(): Promise<TokenPair | null> {
  const raw = await storage.get('tokens');
  tokens = raw ? (JSON.parse(raw) as TokenPair) : null;
  return tokens;
}

let refreshing: Promise<boolean> | null = null;

/** Single-flight refresh: concurrent 401s share one rotation so the refresh token isn't reused. */
async function refresh(): Promise<boolean> {
  if (!tokens) return false;
  refreshing ??= (async () => {
    try {
      const res = await fetch(`${API_URL}/auth/refresh`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ refresh_token: tokens!.refresh_token }),
      });
      if (!res.ok) return false;
      await setTokens((await res.json()) as TokenPair);
      return true;
    } catch {
      return false;
    } finally {
      setTimeout(() => { refreshing = null; }, 0);
    }
  })();
  return refreshing;
}

type Query = Record<string, string | number | boolean | undefined | null>;
interface Options { method?: 'GET' | 'POST' | 'PUT' | 'PATCH' | 'DELETE'; body?: unknown; query?: Query; auth?: boolean }

function toQuery(q?: Query): string {
  if (!q) return '';
  const parts = Object.entries(q).filter(([, v]) => v !== undefined && v !== null).map(([k, v]) => `${encodeURIComponent(k)}=${encodeURIComponent(String(v))}`);
  return parts.length ? `?${parts.join('&')}` : '';
}

export async function api<T>(path: string, opts: Options = {}, retried = false): Promise<T> {
  const { method = 'GET', body, query, auth = true } = opts;
  const headers: Record<string, string> = { 'Content-Type': 'application/json' };
  if (auth && tokens) headers.Authorization = `Bearer ${tokens.access_token}`;
  let res: Response;
  try {
    res = await fetch(`${API_URL}${path}${toQuery(query)}`, { method, headers, body: body === undefined ? undefined : JSON.stringify(body) });
  } catch {
    throw new ApiError(0, "Can't reach ShareTaxi. Check your connection.");
  }
  if (res.status === 401 && auth && !retried && (await refresh())) return api<T>(path, opts, true);
  if (res.status === 401 && auth) {
    await setTokens(null);
    onSignedOut();
  }
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const j = await res.json();
      detail = typeof j.detail === 'string' ? j.detail : Array.isArray(j.detail) ? j.detail.map((d: { msg: string }) => d.msg).join(', ') : detail;
    } catch { /* keep statusText */ }
    throw new ApiError(res.status, detail);
  }
  return (res.status === 204 ? undefined : await res.json()) as T;
}
