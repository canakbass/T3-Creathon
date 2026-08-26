import pytest

from tests.conftest import kullanici_ac


def test_register_user(client, db_session):
    """Kayit HESAP ACIYOR ama HICBIR ROL VERMIYOR.

    Govdedeki `role`/`roles` alanlari TAMAMEN yok sayiliyor. Kara liste
    (AYRICALIKLI_ROLLER) yetmezdi: `REFEREE` o listede degil ve kendine
    hakem rolu veren biri /reports/lookup ile kurumun butun basvuru
    kunyelerini okuyabilirdi.
    """
    from app import models

    response = client.post(
        "/api/auth/register",
        json={"email": "new_user@teknofest.org", "password": "securepwd123", "role": "REFEREE"}
    )
    assert response.status_code == 202, response.text[:200]
    assert "dogrulama" in response.json()["message"].lower()

    kullanici = (
        db_session.query(models.User)
        .filter(models.User.email == "new_user@teknofest.org")
        .first()
    )
    assert kullanici is not None
    assert kullanici.role_list == [], "kayit rol verdi"
    assert kullanici.email_verified is False, "kayit hesabi dogrulanmis saydi"


def test_register_duplicate_email_VARLIK_KAHINI_DEGIL(client):
    """Ikinci kayit denemesi ILK deneme ile AYNI cevabi vermeli.

    "Bu e-posta zaten kayitli" demek, herhangi birinin adres deneyerek
    sistemde kimin hesabi oldugunu ogrenmesi demekti. Fark yalnizca posta
    kutusunun sahibine gonderilen mektupta gorunuyor.
    """
    ilk = client.post(
        "/api/auth/register",
        json={"email": "dup@teknofest.org", "password": "parola1234"}
    )
    ikinci = client.post(
        "/api/auth/register",
        json={"email": "dup@teknofest.org", "password": "baskaparola"}
    )
    assert ilk.status_code == ikinci.status_code == 202
    assert ilk.json()["message"] == ikinci.json()["message"]


def test_register_kisa_sifre_reddediliyor(client):
    r = client.post(
        "/api/auth/register", json={"email": "kisa@teknofest.org", "password": "abc"}
    )
    assert r.status_code == 400
    assert "8 karakter" in r.json()["detail"]


def test_login_user(client):
    kullanici_ac("login@teknofest.org", ["REFEREE"], "mypassword")
    
    # Login (form-urlencoded)
    response = client.post(
        "/api/auth/login",
        data={"username": "login@teknofest.org", "password": "mypassword"}
    )
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"


def test_login_invalid_credentials(client):
    response = client.post(
        "/api/auth/login",
        data={"username": "nonexistent@teknofest.org", "password": "wrongpassword"}
    )
    assert response.status_code == 401
    assert "hatali" in response.json()["detail"].lower()


def test_get_me(client):
    email = "me@teknofest.org"
    pwd = "password1"
    kullanici_ac(email, ["REFEREE"], pwd)
    login_res = client.post(
        "/api/auth/login",
        data={"username": email, "password": pwd}
    )
    token = login_res.json()["access_token"]
    
    # Access /me
    response = client.get(
        "/api/auth/me",
        headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 200
    assert response.json()["email"] == email
    assert response.json()["role"] == "REFEREE"


def test_get_me_unauthorized(client):
    response = client.get("/api/auth/me")
    assert response.status_code == 401
