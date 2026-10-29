"""Create passenger requests and driver trips (geocode -> route -> persist)."""
from __future__ import annotations

from datetime import timedelta

from sqlalchemy.orm import Session

from app.models import Driver, DriverTripPost, PassengerRequest, Vehicle
from app.schemas.rides import DriverTripIn, RideRequestIn
from app.services import route_service as rs
from app.utils.geo import Point
from app.utils.time import to_naive_utc


class PostingError(ValueError):
    pass


def resolve_point(address: str, lat: float | None, lng: float | None) -> tuple[Point, str]:
    """Coordinates win when given (map pin / GPS); otherwise geocode the text."""
    if lat is not None and lng is not None:
        return Point(lat, lng), address
    try:
        place = rs.geocode_address(address)
    except rs.GeocodeError as exc:
        raise PostingError(str(exc))
    return place.point, address


def create_ride_request(db: Session, user_id: int, data: RideRequestIn, *, recurring_id: int | None = None) -> PassengerRequest:
    origin, o_addr = resolve_point(data.origin_address, data.origin_lat, data.origin_lng)
    dest, d_addr = resolve_point(data.destination_address, data.destination_lat, data.destination_lng)
    if rs.haversine_km(origin, dest) < 1.0:
        raise PostingError("Pickup and destination are too close for a shared ride")
    route = rs.calculate_route(origin, dest)
    preferred = to_naive_utc(data.preferred_departure)
    flex = timedelta(minutes=data.flexible_minutes)
    req = PassengerRequest(
        user_id=user_id, origin_lat=origin.lat, origin_lng=origin.lng, origin_address=o_addr,
        destination_lat=dest.lat, destination_lng=dest.lng, destination_address=d_addr,
        origin_area=rs.approximate_area(origin), destination_area=rs.approximate_area(dest),
        preferred_departure=preferred, earliest_departure=preferred - flex, latest_departure=preferred + flex,
        passenger_count=data.passenger_count, luggage_count=data.luggage_count, accessibility_needs=data.accessibility_needs,
        max_pickup_deviation_min=data.max_pickup_deviation_min, maximum_detour_minutes=data.maximum_detour_minutes,
        ride_type=data.ride_type, notes=data.notes, estimated_direct_distance=round(route.distance_km, 2),
        estimated_direct_duration=round(route.duration_min, 1), route_polyline=route.polyline, recurring_request_id=recurring_id,
    )
    db.add(req)
    db.flush()
    return req


def create_driver_trip(db: Session, driver: Driver, data: DriverTripIn, *, recurring_id: int | None = None) -> DriverTripPost:
    vehicle = db.get(Vehicle, data.vehicle_id)
    if vehicle is None or vehicle.driver_id != driver.id:
        raise PostingError("Unknown vehicle")
    if data.available_seats > vehicle.seats:
        raise PostingError(f"This vehicle has only {vehicle.seats} passenger seats")
    origin, o_addr = resolve_point(data.origin_address, data.origin_lat, data.origin_lng)
    dest, d_addr = resolve_point(data.destination_address, data.destination_lat, data.destination_lng)
    route = rs.calculate_route(origin, dest)
    trip = DriverTripPost(
        driver_id=driver.id, vehicle_id=vehicle.id, origin_lat=origin.lat, origin_lng=origin.lng, origin_address=o_addr,
        destination_lat=dest.lat, destination_lng=dest.lng, destination_address=d_addr,
        departure_time=to_naive_utc(data.departure_time), available_seats=data.available_seats,
        maximum_detour_minutes=data.maximum_detour_minutes, minimum_earnings=data.minimum_earnings,
        auto_match=data.auto_match, preferred_route_note=data.preferred_route_note,
        route_polyline=route.polyline, estimated_distance=round(route.distance_km, 2),
        estimated_duration=round(route.duration_min, 1), recurring_request_id=recurring_id,
    )
    db.add(trip)
    db.flush()
    return trip
