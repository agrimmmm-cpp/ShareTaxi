import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useEffect } from 'react';

import { WS_URL, api, getAccessToken } from './client';
import type {
  AppNotification, ChatMessage, DemandCluster, DriverDashboard, DriverMe, DriverTrip, DriverTripInput, Earnings,
  EmergencyContact, ExploreCard, Match, Payment, Place, PopularRoute, Quote, Ride, RideGroup, RideRequest, RideRequestInput,
  TokenPair, Vehicle,
} from './types';

const key = {
  requests: ['requests'] as const,
  request: (id: number) => ['request', id] as const,
  rides: (role: string) => ['rides', role] as const,
  ride: (id: number) => ['ride', id] as const,
};

// ------------------------------------------------------------------ auth
export const useLogin = () =>
  useMutation({ mutationFn: (b: { email: string; password: string }) => api<TokenPair>('/auth/login', { method: 'POST', body: b, auth: false }) });
export const useRegister = () =>
  useMutation({ mutationFn: (b: { email: string; password: string; full_name: string; phone?: string }) => api<TokenPair>('/auth/register', { method: 'POST', body: b, auth: false }) });

// ------------------------------------------------------------------ passenger
export const useMyRequests = () => useQuery({ queryKey: key.requests, queryFn: () => api<RideRequest[]>('/ride-requests'), refetchInterval: 15_000 });
export const useRequest = (id: number) =>
  useQuery({ queryKey: key.request(id), queryFn: () => api<RideRequest>(`/ride-requests/${id}`), refetchInterval: 6_000 });
export const useRequestMatches = (id: number, enabled = true) =>
  useQuery({ queryKey: ['request-matches', id], queryFn: () => api<Match[]>(`/matches/ride-request/${id}`), enabled, refetchInterval: 8_000 });
export const useGroup = (id: number | null | undefined) =>
  useQuery({ queryKey: ['group', id], queryFn: () => api<RideGroup>(`/ride-groups/${id}`), enabled: !!id, refetchInterval: 8_000 });

export function useCreateRequest() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (b: RideRequestInput) => api<RideRequest>('/ride-requests', { method: 'POST', body: b }),
    onSuccess: () => qc.invalidateQueries({ queryKey: key.requests }),
  });
}
export function useCancelRequest() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: number) => api<void>(`/ride-requests/${id}`, { method: 'DELETE' }),
    onSuccess: () => qc.invalidateQueries({ queryKey: key.requests }),
  });
}
export function useJoinGroup() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (v: { groupId: number; requestId: number }) => api<RideGroup>(`/ride-groups/${v.groupId}/join`, { method: 'POST', body: { request_id: v.requestId } }),
    onSuccess: () => qc.invalidateQueries({ queryKey: key.requests }),
  });
}
export const useExplore = (q: { origin: string; destination: string; departure: Date; flexible: number; passengers: number } | null) =>
  useQuery({
    queryKey: ['explore', q?.origin, q?.destination, q?.departure.toISOString(), q?.flexible, q?.passengers],
    enabled: !!q && q.origin.length > 1 && q.destination.length > 1,
    queryFn: () => api<ExploreCard[]>('/explore/rides', {
      query: { origin_address: q!.origin, destination_address: q!.destination, departure: q!.departure.toISOString(), flexible_minutes: q!.flexible, passenger_count: q!.passengers },
    }),
  });
export const useQuote = (origin: string, destination: string) =>
  useQuery({
    queryKey: ['quote', origin, destination],
    enabled: origin.length > 1 && destination.length > 1,
    retry: false,
    queryFn: () => api<Quote>('/quote', { method: 'POST', body: { origin_address: origin, destination_address: destination } }),
  });
export const usePopularRoutes = () => useQuery({ queryKey: ['popular'], queryFn: () => api<PopularRoute[]>('/popular-routes') });
export const usePlaces = () => useQuery({ queryKey: ['places'], queryFn: () => api<Place[]>('/places'), staleTime: Infinity });

// ------------------------------------------------------------------ rides
export const useRides = (role: 'passenger' | 'driver') =>
  useQuery({ queryKey: key.rides(role), queryFn: () => api<Ride[]>('/rides', { query: { role } }), refetchInterval: 15_000 });
export const useRide = (id: number) => useQuery({ queryKey: key.ride(id), queryFn: () => api<Ride>(`/rides/${id}`), refetchInterval: 6_000 });

export function useRideAction(id: number) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (a: { action: 'arriving' | 'start' | 'complete' | 'cancel'; reason?: string }) =>
      api<Ride>(`/rides/${id}/${a.action}`, { method: 'POST', body: a.action === 'cancel' ? { reason: a.reason } : undefined }),
    onSuccess: (ride) => {
      qc.setQueryData(key.ride(id), ride);
      void qc.invalidateQueries({ queryKey: ['rides'] });
      void qc.invalidateQueries({ queryKey: key.requests });
      void qc.invalidateQueries({ queryKey: ['driver'] });
    },
  });
}

export const usePayments = () => useQuery({ queryKey: ['payments'], queryFn: () => api<Payment[]>('/payments/history') });
export function usePay() {
  const qc = useQueryClient();
  return useMutation({
    // In production the Stripe SDK confirms `client_secret` between these two calls (see README → Payments).
    mutationFn: async (rideId: number) => {
      const p = await api<Payment>('/payments/create', { method: 'POST', body: { ride_id: rideId } });
      return api<Payment>('/payments/confirm', { method: 'POST', body: { payment_id: p.id } });
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ['payments'] }),
  });
}

export function useRate() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (b: { ride_id: number; ratee_id: number; overall: number; communication?: number; punctuality?: number; safety?: number; comment?: string }) =>
      api('/ratings', { method: 'POST', body: b }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['ride'] }),
  });
}

// ------------------------------------------------------------------ chat (REST + WebSocket push)
export const useMessages = (rideId: number) =>
  useQuery({ queryKey: ['messages', rideId], queryFn: () => api<ChatMessage[]>(`/rides/${rideId}/messages`), refetchInterval: 10_000 });
export const useQuickMessages = () => useQuery({ queryKey: ['quick'], queryFn: () => api<string[]>('/messages/quick'), staleTime: Infinity });
export function useSendMessage(rideId: number) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (b: { body: string; kind?: 'text' | 'quick' }) => api<ChatMessage>(`/rides/${rideId}/messages`, { method: 'POST', body: b }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['messages', rideId] }),
  });
}
/** Live updates: the server pushes new messages over a WebSocket; we just refetch. Polling is the fallback. */
export function useRideSocket(rideId: number) {
  const qc = useQueryClient();
  useEffect(() => {
    const token = getAccessToken();
    if (!token) return;
    const ws = new WebSocket(`${WS_URL}/ws/rides/${rideId}?token=${encodeURIComponent(token)}`);
    ws.onmessage = () => void qc.invalidateQueries({ queryKey: ['messages', rideId] });
    return () => ws.close();
  }, [rideId, qc]);
}
export function useUserSocket() {
  const qc = useQueryClient();
  useEffect(() => {
    const token = getAccessToken();
    if (!token) return;
    const ws = new WebSocket(`${WS_URL}/ws/me?token=${encodeURIComponent(token)}`);
    ws.onmessage = () => {
      void qc.invalidateQueries({ queryKey: ['notifications'] });
      void qc.invalidateQueries({ queryKey: key.requests });
      void qc.invalidateQueries({ queryKey: ['rides'] });
    };
    const ping = setInterval(() => ws.readyState === 1 && ws.send('ping'), 25_000);
    return () => { clearInterval(ping); ws.close(); };
  }, [qc]);
}

export const useNotifications = () => useQuery({ queryKey: ['notifications'], queryFn: () => api<AppNotification[]>('/notifications') });

// ------------------------------------------------------------------ driver
export const useDriverMe = () => useQuery({ queryKey: ['driver', 'me'], queryFn: () => api<DriverMe>('/driver/me') });
export const useDashboard = () => useQuery({ queryKey: ['driver', 'dashboard'], queryFn: () => api<DriverDashboard>('/driver/dashboard'), refetchInterval: 20_000 });
export const useDriverTrips = () => useQuery({ queryKey: ['driver', 'trips'], queryFn: () => api<DriverTrip[]>('/driver/trips'), refetchInterval: 15_000 });
export const useDriverTrip = (id: number) => useQuery({ queryKey: ['driver', 'trip', id], queryFn: () => api<DriverTrip>(`/driver/trips/${id}`) });
export const useTripMatches = (id: number) =>
  useQuery({ queryKey: ['driver', 'matches', id], queryFn: () => api<Match[]>(`/matches/driver-trip/${id}`), refetchInterval: 12_000 });
export const useEarnings = () => useQuery({ queryKey: ['driver', 'earnings'], queryFn: () => api<Earnings>('/driver/earnings') });
export const useDemand = () => useQuery({ queryKey: ['demand'], queryFn: () => api<DemandCluster[]>('/demand'), refetchInterval: 20_000 });

export function useCreateTrip() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (b: DriverTripInput) => api<DriverTrip>('/driver/trips', { method: 'POST', body: b }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['driver'] }),
  });
}
export function usePatchTrip(id: number) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (b: Partial<{ available_seats: number; maximum_detour_minutes: number; minimum_earnings: number; status: 'cancelled' }>) =>
      api<DriverTrip>(`/driver/trips/${id}`, { method: 'PATCH', body: b }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['driver'] }),
  });
}
export function useMatchAction() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (v: { id: number; action: 'accept' | 'reject' }) => api<Ride | undefined>(`/matches/${v.id}/${v.action}`, { method: 'POST' }),
    onSuccess: () => { void qc.invalidateQueries({ queryKey: ['driver'] }); void qc.invalidateQueries({ queryKey: ['rides'] }); },
  });
}
export function useDriverApply() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (v: { make: string; model: string; year: number; color: string; license_plate: string; seats: number }) =>
      api('/driver/apply', { method: 'POST', body: { vehicle: v } }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['driver'] }),
  });
}
export function useSubmitDocument() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (v: { doc_type: string; file_url: string }) => api('/driver/documents', { method: 'POST', body: v }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['driver'] }),
  });
}
export const useVehicles = () => useQuery({ queryKey: ['driver', 'vehicles'], queryFn: () => api<Vehicle[]>('/driver/vehicles') });

// ------------------------------------------------------------------ safety
export const useContacts = () => useQuery({ queryKey: ['contacts'], queryFn: () => api<EmergencyContact[]>('/safety/contacts') });
export function useAddContact() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (b: { name: string; phone: string; relationship_label?: string }) => api('/safety/contacts', { method: 'POST', body: b }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['contacts'] }),
  });
}
