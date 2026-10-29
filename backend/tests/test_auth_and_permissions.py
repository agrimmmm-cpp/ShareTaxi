from app.models import RefreshToken, User
from tests.conftest import auth_headers
from tests.helpers import make_driver, ride_payload, trip_payload


def test_register_login_me(client):
    r = client.post("/auth/register", json={"email": "New@Example.com", "password": "supersecret", "full_name": "New User"})
    assert r.status_code == 201 and r.json()["token_type"] == "bearer"
    assert client.post("/auth/login", json={"email": "new@example.com", "password": "supersecret"}).status_code == 200
    me = client.get("/auth/me", headers={"Authorization": f"Bearer {r.json()['access_token']}"}).json()
    assert me["email"] == "new@example.com" and me["roles"] == ["passenger"]


def test_password_is_hashed_and_wrong_password_rejected(client, db_session):
    client.post("/auth/register", json={"email": "u@t.dev", "password": "supersecret", "full_name": "U"})
    assert db_session.query(User).one().password_hash.startswith("$2")
    assert client.post("/auth/login", json={"email": "u@t.dev", "password": "wrong-password"}).status_code == 401


def test_validation_and_duplicates(client):
    assert client.post("/auth/register", json={"email": "bad", "password": "supersecret", "full_name": "x"}).status_code == 422
    assert client.post("/auth/register", json={"email": "a@t.dev", "password": "short", "full_name": "x"}).status_code == 422
    ok = {"email": "a@t.dev", "password": "supersecret", "full_name": "x"}
    assert client.post("/auth/register", json=ok).status_code == 201
    assert client.post("/auth/register", json=ok).status_code == 409


def test_refresh_rotation_and_reuse_detection(client, db_session):
    tokens = client.post("/auth/register", json={"email": "r@t.dev", "password": "supersecret", "full_name": "R"}).json()
    new = client.post("/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
    assert new.status_code == 200 and new.json()["refresh_token"] != tokens["refresh_token"]
    # replaying the old token is theft -> everything in the family is revoked
    assert client.post("/auth/refresh", json={"refresh_token": tokens["refresh_token"]}).status_code == 401
    assert client.post("/auth/refresh", json={"refresh_token": new.json()["refresh_token"]}).status_code == 401
    assert all(t.revoked for t in db_session.query(RefreshToken).all())


def test_requires_authentication_and_rejects_garbage_token(client):
    assert client.get("/ride-requests").status_code == 401
    assert client.get("/ride-requests", headers={"Authorization": "Bearer nope"}).status_code == 401


def test_non_driver_cannot_post_trips_or_see_dashboard(client):
    h = auth_headers(client, "p@t.dev")
    assert client.post("/driver/trips", json=trip_payload(1), headers=h).status_code == 403
    assert client.get("/driver/dashboard", headers=h).status_code == 403


def test_non_admin_blocked_from_admin_api(client):
    h = auth_headers(client, "p@t.dev")
    assert client.get("/admin/users", headers=h).status_code == 403
    assert client.get("/admin/analytics").status_code == 401


def test_cannot_read_someone_elses_request(client):
    a, b = auth_headers(client, "a@t.dev"), auth_headers(client, "b@t.dev")
    rid = client.post("/ride-requests", json=ride_payload("Burnaby", "Abbotsford", 10, 0), headers=a).json()["id"]
    assert client.get(f"/ride-requests/{rid}", headers=b).status_code == 404
    assert client.delete(f"/ride-requests/{rid}", headers=b).status_code == 404
    assert client.get(f"/ride-requests/{rid}", headers=a).status_code == 200


def test_driver_cannot_use_another_drivers_vehicle(client, db_session):
    _, _, v1 = make_driver(client, db_session, "d1@t.dev")
    h2, _, _ = make_driver(client, db_session, "d2@t.dev")
    assert client.post("/driver/trips", json=trip_payload(v1.id), headers=h2).status_code == 422


def test_suspended_user_is_locked_out(client, db_session):
    h = auth_headers(client, "s@t.dev")
    db_session.query(User).one().is_suspended = True
    db_session.commit()
    assert client.get("/auth/me", headers=h).status_code == 403
    assert client.post("/auth/login", json={"email": "s@t.dev", "password": "password123"}).status_code == 403


def test_driver_onboarding_requires_all_documents_and_admin_approval(client, db_session):
    h = auth_headers(client, "newdriver@t.dev")
    admin_h = auth_headers(client, "admin@t.dev")
    db_session.query(User).filter(User.email == "admin@t.dev").one().is_admin = True
    db_session.commit()
    r = client.post("/driver/apply", headers=h, json={"vehicle": {"make": "Kia", "model": "Soul", "year": 2020, "color": "Red", "license_plate": "XYZ 9", "seats": 4}})
    assert r.status_code == 201
    assert client.get("/auth/me", headers=h).json()["roles"] == ["passenger"]
    for t in ("drivers_licence", "vehicle_registration", "insurance", "identity"):
        assert client.post("/driver/documents", headers=h, json={"doc_type": t, "file_url": f"s3://docs/{t}.pdf"}).status_code == 201
        assert client.get("/auth/me", headers=h).json()["roles"] == ["passenger"]  # still unverified
    docs = client.get("/admin/drivers", headers=admin_h).json()[0]["documents"]
    for d in docs:
        assert client.post(f"/admin/documents/{d['id']}/review?approve=true", headers=admin_h).status_code == 200
    assert client.get("/auth/me", headers=h).json()["roles"] == ["passenger", "driver"]


def test_phone_verification(client):
    h = auth_headers(client, "ph@t.dev")
    assert client.post("/auth/verify-phone/confirm", json={"code": "123456"}, headers=h).status_code == 400
    client.post("/auth/verify-phone/start", headers=h)
    assert client.post("/auth/verify-phone/confirm", json={"code": "000000"}, headers=h).status_code == 200
    assert client.get("/auth/me", headers=h).json()["phone_verified"] is True
