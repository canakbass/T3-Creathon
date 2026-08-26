import pytest

def test_register_user(client):
    response = client.post(
        "/api/auth/register",
        json={"email": "new_user@teknofest.org", "password": "securepwd123", "role": "REFEREE"}
    )
    assert response.status_code == 201
    data = response.json()
    assert data["email"] == "new_user@teknofest.org"
    assert data["role"] == "REFEREE"
    assert "id" in data
    assert "password_hash" not in data


def test_register_duplicate_email(client):
    # Register once
    response = client.post(
        "/api/auth/register",
        json={"email": "dup@teknofest.org", "password": "pwd1", "role": "COMPETITOR"}
    )
    assert response.status_code == 201
    
    # Register again with same email
    response = client.post(
        "/api/auth/register",
        json={"email": "dup@teknofest.org", "password": "pwd2", "role": "COMPETITOR"}
    )
    assert response.status_code == 400
    # Mesaj Turkce'ye cevrildi; testin amaci mesajin birebir metni degil,
    # ayni e-postayla ikinci kaydin REDDEDILMESI.
    assert "kayitli" in response.json()["detail"].lower()


def test_login_user(client):
    # Register user first
    client.post(
        "/api/auth/register",
        json={"email": "login@teknofest.org", "password": "mypassword", "role": "REFEREE"}
    )
    
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
    # Register and login
    email = "me@teknofest.org"
    pwd = "password1"
    client.post(
        "/api/auth/register",
        json={"email": email, "password": pwd, "role": "REFEREE"}
    )
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
