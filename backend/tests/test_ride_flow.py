"""End-to-end: post -> group -> driver match -> accept -> pay -> ride -> complete -> rate."""
from app.models import DriverPayout, Payment, PaymentStatus, Notification, Profile, User
from tests.conftest import auth_headers
from tests.helpers import make_driver, post_trio, ride_payload, trip_payload


def test_posting_validates_input(client):
    h = auth_headers(client, "a@t.dev")
    assert client.post("/ride-requests", json=ride_payload("Burnaby", "Abbotsford", 10, 0, passenger_count=9), headers=h).status_code == 422
    assert client.post("/ride-requests", json=ride_payload("Nowhereville", "Abbotsford", 10, 0), headers=h).status_code == 422
    assert client.post("/ride-requests", json=ride_payload("Burnaby", "Burnaby", 10, 0), headers=h).status_code == 422
    assert client.post("/ride-requests", json={**ride_payload("Burnaby", "Abbotsford", 10, 0), "origin_lat": 49.2}, headers=h).status_code == 422


def test_first_request_immediately_shows_search_summary(client):
    h = auth_headers(client, "a@t.dev")
    r = client.post("/ride-requests", json=ride_payload("SFU Burnaby", "Abbotsford", 10, 0), headers=h).json()
    s = r["search"]
    assert r["status"] == "searching" and s["potential_matches"] == 0 and s["stage"] == "Searching for riders"
    assert s["solo_benchmark"] > 50 and s["estimated_duration_min"] > 30


def test_group_forms_as_riders_join_and_driver_is_searched(client):
    ha = auth_headers(client, "a@t.dev")
    a = client.post("/ride-requests", json=ride_payload("Burnaby", "Abbotsford", 10, 0), headers=ha).json()
    hb = auth_headers(client, "b@t.dev")
    b = client.post("/ride-requests", json=ride_payload("Coquitlam", "Abbotsford", 9, 50), headers=hb).json()
    assert b["status"] == "group_found" and b["search"]["potential_matches"] == 1 and b["search"]["likely_passengers"] == 2
    assert b["search"]["estimated_fare"] and b["search"]["estimated_savings"] > 0
    hc = auth_headers(client, "c@t.dev")
    c = client.post("/ride-requests", json=ride_payload("Burnaby", "Langley", 10, 10), headers=hc).json()
    assert c["status"] == "driver_search" and c["search"]["likely_passengers"] == 3
    assert client.get(f"/ride-requests/{a['id']}", headers=ha).json()["status"] == "driver_search"
    # everyone was told, once
    types = [n["type"] for n in client.get("/notifications", headers=ha).json()]
    assert "potential_riders_found" in types and "third_passenger_joined" in types


def test_group_view_hides_other_passengers_exact_locations(client):
    ha, _, _ = post_trio(client)
    gid = client.get("/ride-requests", headers=ha).json()[0]["ride_group_id"]
    g = client.get(f"/ride-groups/{gid}", headers=ha).json()
    assert [m["label"] for m in g["members"]].count("You") == 1 and len(g["members"]) == 3
    assert all("lat" not in m and "address" not in m for m in g["members"])
    assert g["your_fare"] and g["solo_benchmark"] > g["your_fare"] and g["fare_low"] < g["fare_high"]


def test_driver_post_finds_existing_group_and_accepts(client, db_session):
    post_trio(client)
    dh, driver, vehicle = make_driver(client, db_session)
    trip = client.post("/driver/trips", json=trip_payload(vehicle.id), headers=dh)
    assert trip.status_code == 201 and trip.json()["recommendations"] >= 1
    matches = client.get(f"/matches/driver-trip/{trip.json()['id']}", headers=dh).json()
    best = matches[0]
    assert best["passengers"] == 3 and best["driver_net_earnings"] >= 55 and best["overall_score"] > 70
    assert best["added_min"] <= 30 and len(best["stops"]) == 6
    # privacy for the driver before accepting: neighbourhood-level coordinates only
    assert all(s["address"] is None and round(s["lat"], 2) == s["lat"] for s in best["stops"])
    ride = client.post(f"/matches/{best['id']}/accept", headers=dh)
    assert ride.status_code == 200, ride.text
    r = ride.json()
    assert r["status"] == "confirmed" and r["passenger_count"] == 3 and r["is_driver"] and r["driver_payout"] > 0
    assert all(s["address"] for s in r["stops"])  # driver gets exact stops once confirmed
    assert client.post(f"/matches/{best['id']}/accept", headers=dh).status_code == 409  # not twice


def test_passenger_sees_ride_with_privacy_and_fare_breakdown(client, db_session):
    ha, hb, hc = post_trio(client)
    dh, _, vehicle = make_driver(client, db_session)
    tid = client.post("/driver/trips", json=trip_payload(vehicle.id), headers=dh).json()["id"]
    m = client.get(f"/matches/driver-trip/{tid}", headers=dh).json()[0]
    # passengers can see the proposal with their own price before the driver accepts
    mine = client.get(f"/matches/ride-request/{client.get('/ride-requests', headers=ha).json()[0]['id']}", headers=ha).json()
    assert mine and mine[0]["your_fare"] and mine[0]["your_savings_percent"] > 30
    client.post(f"/matches/{m['id']}/accept", headers=dh)
    ride = client.get("/rides", headers=ha).json()[0]
    assert ride["status"] == "confirmed" and ride["driver"]["vehicle"]["license_plate"] == "ABC 123"
    assert ride["your_fare"]["fare"] < ride["your_fare"]["solo_benchmark"]
    fb = ride["your_fare"]
    assert abs(fb["distance_part"] + fb["time_part"] + fb["detour_part"] - fb["fare"]) < 0.05
    others = [s for s in ride["stops"] if s["label"] != "You"]
    assert others and all(s["address"] is None for s in others)  # no one else's home address
    assert all(s["address"] for s in ride["stops"] if s["label"] == "You")
    assert ride["total_fare"] is None and ride["driver_payout"] is None  # money details are driver-only
    # a stranger can't see the ride at all
    assert client.get(f"/rides/{ride['id']}", headers=auth_headers(client, "stranger@t.dev")).status_code == 404


def _confirmed_ride(client, db_session):
    hs = post_trio(client)
    dh, driver, vehicle = make_driver(client, db_session)
    tid = client.post("/driver/trips", json=trip_payload(vehicle.id), headers=dh).json()["id"]
    m = client.get(f"/matches/driver-trip/{tid}", headers=dh).json()[0]
    ride = client.post(f"/matches/{m['id']}/accept", headers=dh).json()
    return hs, dh, driver, ride


def test_full_lifecycle_with_payments_and_payout(client, db_session):
    (ha, hb, hc), dh, driver, ride = _confirmed_ride(client, db_session)
    for h in (ha, hb, hc):
        p = client.post("/payments/create", json={"ride_id": ride["id"]}, headers=h).json()
        assert p["client_secret"] and p["status"] == "requires_confirmation"
        assert client.post("/payments/confirm", json={"payment_id": p["id"]}, headers=h).json()["status"] == "authorized"
    assert client.post(f"/rides/{ride['id']}/complete", headers=dh).status_code == 409  # can't skip start
    assert client.post(f"/rides/{ride['id']}/arriving", headers=dh).json()["status"] == "driver_arriving"
    assert client.post(f"/rides/{ride['id']}/start", headers=ha).status_code == 403  # passengers can't drive
    assert client.post(f"/rides/{ride['id']}/start", headers=dh).json()["status"] == "active"
    done = client.post(f"/rides/{ride['id']}/complete", headers=dh).json()
    assert done["status"] == "completed"

    pays = db_session.query(Payment).all()
    assert len(pays) == 3 and all(p.status == PaymentStatus.CAPTURED for p in pays)
    gross = sum(p.amount_cents for p in pays)
    payout = db_session.query(DriverPayout).one()
    fee = sum(p.platform_fee_cents for p in pays)
    assert payout.amount_cents == gross - fee and payout.status == "paid"
    assert abs(gross / 100 - done["total_fare"]) < 0.05
    assert client.get("/payments/history", headers=ha).json()[0]["status"] == "captured"
    assert client.get("/driver/earnings", headers=dh).json()["total"] == payout.amount_cents / 100
    assert client.get("/driver/dashboard", headers=dh).json()["earnings_today"] >= 0
    types = {n["type"] for n in client.get("/notifications", headers=ha).json()}
    assert {"ride_confirmed", "ride_started", "ride_completed", "payment_receipt", "rating_reminder"} <= types

    # ratings: passengers rate the driver, the driver rates passengers, nobody rates twice
    driver_uid = driver.user_id
    r = client.post("/ratings", headers=ha, json={"ride_id": ride["id"], "ratee_id": driver_uid, "overall": 5, "punctuality": 4, "safety": 5, "comment": "Smooth"})
    assert r.status_code == 201
    assert client.post("/ratings", headers=ha, json={"ride_id": ride["id"], "ratee_id": driver_uid, "overall": 1}).status_code == 409
    client.post("/ratings", headers=hb, json={"ride_id": ride["id"], "ratee_id": driver_uid, "overall": 4})
    a_uid = db_session.query(User).filter(User.email == "a@t.dev").one().id
    assert client.post("/ratings", headers=ha, json={"ride_id": ride["id"], "ratee_id": a_uid, "overall": 5}).status_code == 403
    assert client.post("/ratings", headers=dh, json={"ride_id": ride["id"], "ratee_id": a_uid, "overall": 5, "communication": 5}).status_code == 201
    summary = client.get(f"/users/{driver_uid}/ratings", headers=ha).json()
    assert summary["count"] == 2 and summary["average"] == 4.5
    assert db_session.query(Profile).filter(Profile.user_id == driver_uid).one().rating_avg == 4.5


def test_cannot_rate_before_completion(client, db_session):
    (ha, _, _), dh, driver, ride = _confirmed_ride(client, db_session)
    assert client.post("/ratings", headers=ha, json={"ride_id": ride["id"], "ratee_id": driver.user_id, "overall": 5}).status_code == 409


def test_driver_cancel_releases_payments_and_finds_new_driver(client, db_session):
    (ha, hb, hc), dh, driver, ride = _confirmed_ride(client, db_session)
    p = client.post("/payments/create", json={"ride_id": ride["id"]}, headers=ha).json()
    client.post("/payments/confirm", json={"payment_id": p["id"]}, headers=ha)
    # a second driver is already on the route
    d2h, _, v2 = make_driver(client, db_session, "driver2@t.dev")
    client.post("/driver/trips", json=trip_payload(v2.id, 9, 35), headers=d2h)
    res = client.post(f"/rides/{ride['id']}/cancel", json={"reason": "car trouble"}, headers=dh)
    assert res.status_code == 200 and res.json()["status"] == "cancelled"
    assert db_session.query(Payment).filter(Payment.status == PaymentStatus.AUTHORIZED).count() == 0
    reqs = client.get("/ride-requests", headers=ha).json()
    assert reqs[0]["status"] == "driver_found"  # automatically re-matched with the other driver
    assert driver.cancellation_rate == 1.0
    msgs = [n["title"] for n in client.get("/notifications", headers=ha).json()]
    assert "Your driver cancelled" in msgs


def test_passenger_cancel_fee_depends_on_time_to_departure(client, db_session):
    (ha, hb, hc), dh, driver, ride = _confirmed_ride(client, db_session)
    p = client.post("/payments/create", json={"ride_id": ride["id"]}, headers=ha).json()
    client.post("/payments/confirm", json={"payment_id": p["id"]}, headers=ha)
    # departure is ~tomorrow 09:30 UTC; depending on the clock this lands in a fee tier, so assert consistency
    res = client.post(f"/rides/{ride['id']}/cancel", json={}, headers=ha)
    assert res.status_code == 200
    pay = db_session.query(Payment).filter(Payment.id == p["id"]).one()
    assert pay.status in (PaymentStatus.CAPTURED, PaymentStatus.CANCELLED)
    if pay.status == PaymentStatus.CAPTURED:
        assert pay.cancellation_fee_cents == pay.amount_cents > 0
    assert client.get(f"/rides/{ride['id']}", headers=ha).json()["status"] == "confirmed"  # others still ride
    assert client.post(f"/rides/{ride['id']}/cancel", json={}, headers=ha).status_code == 403  # already out
    assert client.get("/ride-requests", headers=ha).json()[0]["status"] == "cancelled"


def test_chat_is_private_masks_phone_numbers_and_has_quick_replies(client, db_session):
    (ha, hb, hc), dh, driver, ride = _confirmed_ride(client, db_session)
    url = f"/rides/{ride['id']}/messages"
    r = client.post(url, json={"body": "Call me on 604-555-1234 please"}, headers=ha)
    assert r.status_code == 201 and "604" not in r.json()["body"] and "[number hidden]" in r.json()["body"]
    client.post(url, json={"body": "I'm at the pickup point.", "kind": "quick"}, headers=dh)
    seen = client.get(url, headers=hb).json()
    assert [m["kind"] for m in seen][-2:] == ["text", "quick"] and seen[0]["kind"] == "system"
    assert client.get(url, headers=auth_headers(client, "stranger@t.dev")).status_code == 404
    assert client.post(url, json={"body": "hi"}, headers=auth_headers(client, "stranger@t.dev")).status_code == 404
    assert "Running 5 minutes late." in client.get("/messages/quick", headers=ha).json()


def test_driver_can_reject_match_and_it_stays_rejected(client, db_session):
    post_trio(client)
    dh, _, vehicle = make_driver(client, db_session)
    tid = client.post("/driver/trips", json=trip_payload(vehicle.id), headers=dh).json()["id"]
    m = client.get(f"/matches/driver-trip/{tid}?refresh=false", headers=dh).json()[0]
    assert client.post(f"/matches/{m['id']}/reject", headers=dh).status_code == 204
    assert client.post(f"/matches/{m['id']}/accept", headers=dh).status_code == 409
    client.post("/admin/rematch", headers=auth_headers(client, "x@t.dev"))  # forbidden, but harmless
    left = client.get(f"/matches/driver-trip/{tid}?refresh=false", headers=dh).json()
    assert all(x["id"] != m["id"] for x in left if x["source"] == "group")


def test_other_driver_cannot_accept_my_match(client, db_session):
    post_trio(client)
    dh, _, vehicle = make_driver(client, db_session)
    tid = client.post("/driver/trips", json=trip_payload(vehicle.id), headers=dh).json()["id"]
    mid = client.get(f"/matches/driver-trip/{tid}", headers=dh).json()[0]["id"]
    d2h, _, _ = make_driver(client, db_session, "other@t.dev")
    assert client.post(f"/matches/{mid}/accept", headers=d2h).status_code == 404


def test_driver_economics_respected_unreasonable_minimum_gets_no_match(client, db_session):
    post_trio(client)
    dh, _, vehicle = make_driver(client, db_session)
    t = client.post("/driver/trips", json=trip_payload(vehicle.id, minimum_earnings=900), headers=dh).json()
    assert t["recommendations"] == 0


def test_driver_edits_trip_flexibility_and_cancels(client, db_session):
    post_trio(client)
    dh, _, vehicle = make_driver(client, db_session)
    t = client.post("/driver/trips", json=trip_payload(vehicle.id), headers=dh).json()
    assert t["recommendations"] >= 1
    tight = client.patch(f"/driver/trips/{t['id']}", json={"maximum_detour_minutes": 2}, headers=dh).json()
    assert tight["recommendations"] == 0 and tight["maximum_detour_minutes"] == 2
    assert client.patch(f"/driver/trips/{t['id']}", json={"available_seats": 9}, headers=dh).status_code == 422
    assert client.patch(f"/driver/trips/{t['id']}", json={"status": "cancelled"}, headers=dh).json()["status"] == "cancelled"


def test_cancel_request_before_driver_is_free_and_regroups(client):
    ha, hb, hc = post_trio(client)
    rid = client.get("/ride-requests", headers=hc).json()[0]["id"]
    d = client.delete(f"/ride-requests/{rid}", headers=hc)
    assert d.status_code == 204, d.text
    a = client.get("/ride-requests", headers=ha).json()[0]
    assert a["status"] == "group_found" and a["search"] is None
    assert client.get(f"/ride-requests/{a['id']}", headers=ha).json()["search"]["likely_passengers"] == 2


def test_explore_shows_joinable_ride_with_personal_price_and_join_works(client):
    ha = auth_headers(client, "a@t.dev")
    client.post("/ride-requests", json=ride_payload("Burnaby", "Abbotsford", 10, 0), headers=ha)
    hb = auth_headers(client, "b@t.dev")
    params = {"origin_address": "Coquitlam", "destination_address": "Abbotsford", "departure": ride_payload("x", "y", 9, 50)["preferred_departure"]}
    cards = client.get("/explore/rides", params=params, headers=hb).json()
    assert len(cards) == 1 and cards[0]["your_fare"] < cards[0]["solo_benchmark"] and cards[0]["seats_left"] >= 1
    req = client.post("/ride-requests", json=ride_payload("Coquitlam", "Abbotsford", 9, 50), headers=hb).json()
    joined = client.post(f"/ride-groups/{cards[0]['id']}/join", json={"request_id": req["id"]}, headers=hb)
    assert joined.status_code == 200 and len(joined.json()["members"]) == 2
    # leaving withdraws the request
    assert client.post(f"/ride-groups/{cards[0]['id']}/leave", headers=hb).status_code == 204


def test_join_rejects_incompatible_request(client):
    ha = auth_headers(client, "a@t.dev")
    gid = client.post("/ride-requests", json=ride_payload("Burnaby", "Abbotsford", 10, 0), headers=ha).json()["search"]["group_id"]
    hb = auth_headers(client, "b@t.dev")
    rid = client.post("/ride-requests", json=ride_payload("UBC", "YVR Airport", 10, 0), headers=hb).json()["id"]
    assert client.post(f"/ride-groups/{gid}/join", json={"request_id": rid}, headers=hb).status_code == 409


def test_demand_marketplace_and_popular_routes_and_quote(client):
    for i in range(3):
        client.post("/ride-requests", json=ride_payload("Richmond", "Downtown Vancouver", 8, 10 * i), headers=auth_headers(client, f"r{i}@t.dev"))
    h = auth_headers(client, "viewer@t.dev")
    clusters = client.get("/demand", headers=h).json()
    assert clusters[0]["origin_area"] == "Richmond" and clusters[0]["passengers"] == 3 and clusters[0]["level"] == "medium"
    assert client.get("/popular-routes", headers=h).json()[0]["origin"] == "Richmond"
    q = client.post("/quote", json={"origin_address": "Vancouver", "destination_address": "Abbotsford"}, headers=h).json()
    assert q["typical_shared_fare"] < q["solo_benchmark"] and q["savings_percent"] > 40


def test_recurring_commute_generates_requests_that_group(client):
    h = auth_headers(client, "rc@t.dev")
    tpl = {"origin_address": "SFU Burnaby", "destination_address": "Downtown Vancouver", "maximum_detour_minutes": 25}
    r = client.post("/recurring", json={"days_of_week": [0, 1, 2, 3, 4, 5, 6], "time_of_day": "08:00", "template": tpl}, headers=h)
    assert r.status_code == 201
    reqs = client.get("/ride-requests", headers=h).json()
    assert len(reqs) >= 6 and all(x["preferred_departure"].endswith(("08:00:00", "08:00:00Z")) or "T08:00" in x["preferred_departure"] for x in reqs)
    assert client.post("/recurring", json={"days_of_week": [1], "time_of_day": "8am", "template": tpl}, headers=h).status_code == 422
    assert client.post("/recurring", json={"days_of_week": [1], "time_of_day": "08:00", "template": {"origin_address": "x"}}, headers=h).status_code == 422


def test_safety_features(client, db_session):
    (ha, hb, hc), dh, driver, ride = _confirmed_ride(client, db_session)
    assert client.post("/safety/contacts", json={"name": "Mum", "phone": "+16045550000"}, headers=ha).status_code == 201
    sos = client.post("/safety/sos", json={"ride_id": ride["id"], "lat": 49.1, "lng": -122.5}, headers=ha).json()
    assert sos["notified_contacts"] == ["Mum"] and sos["share_token"]
    live = client.get(f"/share/{sos['share_token']}").json()   # public, minimal
    assert live["driver"]["plate"] == "ABC 123" and "email" not in str(live) and "phone" not in str(live)
    assert client.get("/share/not-a-token").status_code == 404
    assert client.post("/safety/report", json={"category": "conduct", "details": "rude", "ride_id": ride["id"]}, headers=hb).status_code == 201
    other = db_session.query(User).filter(User.email == "c@t.dev").one().id
    assert client.post(f"/safety/block/{other}", headers=hb).status_code == 204


def test_admin_dashboard_endpoints_and_fee_control(client, db_session):
    (ha, hb, hc), dh, driver, ride = _confirmed_ride(client, db_session)
    admin = auth_headers(client, "admin@t.dev")
    db_session.query(User).filter(User.email == "admin@t.dev").one().is_admin = True
    db_session.commit()
    for h in (ha, hb, hc):
        p = client.post("/payments/create", json={"ride_id": ride["id"]}, headers=h).json()
        client.post("/payments/confirm", json={"payment_id": p["id"]}, headers=h)
    client.post(f"/rides/{ride['id']}/start", headers=dh)
    client.post(f"/rides/{ride['id']}/complete", headers=dh)
    a = client.get("/admin/analytics", headers=admin).json()
    assert a["total_bookings"] == 1 and a["average_occupancy"] == 3.0 and a["average_savings_percent"] > 30
    assert a["platform_revenue"] > 0 and a["passenger_match_rate"] == 1.0 and a["popular_routes"]
    pay = client.get("/admin/payments", headers=admin).json()[0]
    assert client.post(f"/admin/payments/{pay['id']}/refund", json={"amount_cents": 500}, headers=admin).json()["refunded"] == 5.0
    assert client.post(f"/admin/payments/{pay['id']}/refund", json={"amount_cents": 99999999}, headers=admin).json()["status"] == "refunded"
    for path in ("users", "drivers", "rides", "trips", "requests", "matches", "reports", "ratings"):
        assert client.get(f"/admin/{path}", headers=admin).status_code == 200, path
    # platform fee is admin-configurable and applies to new matches
    assert client.put("/admin/settings/fees", json={"platform_commission_rate": 0.2}, headers=admin).status_code == 200
    assert client.put("/admin/settings/fees", json={"platform_commission_rate": 0.9}, headers=admin).status_code == 422
    assert client.get("/admin/settings", headers=admin).json()["platform_commission_rate"] == 0.2
    uid = db_session.query(User).filter(User.email == "c@t.dev").one().id
    assert client.post(f"/admin/users/{uid}/suspend", headers=admin).json()["suspended"] is True
    assert client.get("/auth/me", headers=hc).status_code == 403
