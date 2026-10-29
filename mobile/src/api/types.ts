/** Mirrors the FastAPI Pydantic schemas (backend/app/schemas). */
export type Role = 'passenger' | 'driver' | 'admin';

export interface TokenPair { access_token: string; refresh_token: string; token_type: string; expires_in: number }

export interface Me {
  id: number; email: string; full_name: string; phone: string | null; roles: Role[];
  email_verified: boolean; phone_verified: boolean; identity_verified: boolean;
  rating_avg: number; rating_count: number; driver_status: string | null; push_token: string | null;
}

export interface SearchSummary {
  potential_matches: number; likely_passengers: number; group_id: number | null; seats_used: number;
  estimated_fare: number | null; fare_low: number | null; fare_high: number | null; solo_benchmark: number;
  estimated_savings: number | null; savings_percent: number | null;
  departure_from: string | null; departure_to: string | null; estimated_duration_min: number; stage: string;
}

export type RequestStatus =
  | 'searching' | 'group_found' | 'driver_search' | 'driver_found' | 'confirmed'
  | 'driver_arriving' | 'active' | 'completed' | 'cancelled' | 'expired';

export interface RideRequest {
  id: number; status: RequestStatus; origin_address: string; destination_address: string;
  origin_lat: number; origin_lng: number; destination_lat: number; destination_lng: number;
  preferred_departure: string; earliest_departure: string; latest_departure: string;
  passenger_count: number; luggage_count: number; accessibility_needs: string | null;
  maximum_detour_minutes: number; max_pickup_deviation_min: number; ride_type: string; notes: string | null;
  estimated_direct_distance: number; estimated_direct_duration: number; route_polyline: string;
  ride_group_id: number | null; created_at: string; search: SearchSummary | null; ride_id: number | null;
}

export interface RideRequestInput {
  origin_address: string; destination_address: string; preferred_departure: string; flexible_minutes: number;
  passenger_count: number; luggage_count: number; accessibility_needs?: string | null;
  max_pickup_deviation_min: number; maximum_detour_minutes: number; ride_type: 'shared' | 'request'; notes?: string | null;
}

export interface GroupMember { label: string; is_you: boolean; area: string; seats: number; confirmed: boolean }
export interface RideGroup {
  id: number; status: string; headline: string; origin_area: string; destination_area: string;
  suggested_departure: string; window_start: string; window_end: string; seats_used: number; seats_total: number;
  seats_left: number; members: GroupMember[]; fare_low: number; fare_high: number;
  your_fare: number | null; solo_benchmark: number | null; your_savings: number | null; stage: string;
}
export interface ExploreCard extends RideGroup { pickup_deviation_min: number }

export interface Stop {
  order: number; kind: 'pickup' | 'dropoff'; label: string; area: string; lat: number; lng: number;
  eta: string | null; address: string | null;
}
export interface CostLine { label: string; amount: number }

export interface Match {
  id: number; status: string; source: string; trip_id: number; group_id: number | null; overall_score: number;
  scores: Record<string, number>; passengers: number; seats_used: number; seats_total: number;
  total_fare: number; platform_fee: number; driver_payout: number; driver_net_earnings: number; operating_cost: number;
  added_km: number; added_min: number; total_km: number; total_min: number; stops: Stop[];
  route_polyline: string; direct_polyline: string; cost_lines: CostLine[];
  your_fare: number | null; your_savings: number | null; your_savings_percent: number | null; solo_benchmark: number | null;
  departure: string; created_at: string;
}

export interface Vehicle { id: number; make: string; model: string; year: number; color: string; license_plate: string; seats: number }
export interface DriverTrip {
  id: number; status: string; vehicle_id: number; origin_address: string; destination_address: string;
  origin_lat: number; origin_lng: number; destination_lat: number; destination_lng: number;
  departure_time: string; available_seats: number; maximum_detour_minutes: number; minimum_earnings: number;
  auto_match: boolean; estimated_distance: number; estimated_duration: number; route_polyline: string;
  created_at: string; recommendations: number | null; ride_id: number | null;
}
export interface DriverTripInput {
  vehicle_id: number; origin_address: string; destination_address: string; departure_time: string;
  available_seats: number; maximum_detour_minutes: number; minimum_earnings: number; auto_match: boolean;
}

export type RideStatus = 'confirmed' | 'driver_arriving' | 'active' | 'completed' | 'cancelled';
export interface FareBreakdown {
  fare: number; platform_fee: number; distance_part: number; time_part: number; detour_part: number;
  solo_benchmark: number; savings: number; savings_percent: number;
}
export interface Ride {
  id: number; status: RideStatus; scheduled_departure: string; started_at: string | null; completed_at: string | null;
  headline: string;
  driver: { user_id: number; name: string; rating: number; rating_count: number; trips_completed: number; vehicle: Vehicle };
  passengers: { user_id: number; label: string; is_you: boolean; first_name: string | null; area: string; rating: number | null }[];
  passenger_count: number; stops: Stop[]; route_polyline: string; total_km: number; total_min: number;
  your_fare: FareBreakdown | null; total_fare: number | null; driver_payout: number | null;
  your_pickup_eta: string | null; your_dropoff_eta: string | null; chat_enabled: boolean;
  share_token: string | null; is_driver: boolean; can_rate: boolean;
}

export interface Payment {
  id: number; ride_id: number; amount_cents: number; platform_fee_cents: number; cancellation_fee_cents: number;
  currency: string; status: string; provider: string; client_secret: string | null; refunded_cents: number; created_at: string;
}
export interface Payout { id: number; ride_id: number; amount_cents: number; status: string; created_at: string }

export interface ChatMessage {
  id: number; ride_id: number; sender_id: number; sender_label: string; body: string; kind: 'text' | 'quick' | 'system';
  created_at: string; mine: boolean;
}
export interface AppNotification { id: number; type: string; title: string; body: string; data: Record<string, unknown> | null; read_at: string | null; created_at: string }

export interface DemandCluster {
  origin_area: string; destination_area: string; passengers: number; requests: number; window_start: string; window_end: string;
  origin_lat: number; origin_lng: number; destination_lat: number; destination_lng: number; level: 'high' | 'medium' | 'low';
}
export interface PopularRoute { origin: string; destination: string; requests: number; distance_km: number; typical_shared_fare: number; typical_solo_benchmark: number }
export interface Quote {
  distance_km: number; duration_min: number; solo_benchmark: number; typical_shared_fare: number; savings: number;
  savings_percent: number; polyline: string; origin_area: string; destination_area: string;
}
export interface Place { name: string; lat: number; lng: number }

export interface DriverMe {
  is_driver: boolean; status?: string; cancellation_rate?: number; trips_completed?: number;
  vehicles?: Vehicle[]; documents?: { id: number; doc_type: string; status: string; review_notes: string | null }[];
  required_documents?: string[];
}
export interface DriverDashboard {
  today_trips: number; earnings_today: number; earnings_week: number; available_seats: number;
  upcoming_trips: DriverTrip[]; nearby_requests: number; route_demand: DemandCluster[];
  rating: number; rating_count: number; cancellation_rate: number;
}
export interface Earnings { total: number; pending: number; payouts: Payout[] }
export interface EmergencyContact { id: number; name: string; phone: string; relationship_label: string | null }
