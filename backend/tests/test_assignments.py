"""Rapor dagitimi (atama) testleri.

Odak nokta CIKAR CATISMASI: bu sistemde bir hesap birden fazla role sahip
olabiliyor (kullanicinin istedigi deneme hesabinda dort rolun hepsi var).
Dolayisiyla "yarismaci" ve "hakem" ayri insanlar olmayabilir ve dagitim
kodunun bunu varsaymamasi gerekiyor.

Canli sunucuda olculen acik: ayni hesap kendi raporunu yukluyor,
auto-assign onu kendisine atiyor, sonra kendi raporuna 100/100 verip
onayliyordu. Uc adimin ucu de HTTP 200 donuyordu.
"""

import io
import uuid

import pytest


def _kaydol_ve_giris(client, email, roller, sifre="password"):
    r = client.post(
        "/api/auth/register",
        json={"email": email, "password": sifre, "roles": roller},
    )
    assert r.status_code == 201, r.text[:200]
    giris = client.post(
        "/api/auth/login", data={"username": email, "password": sifre}
    ).json()
    return giris


def _rolle(giris, client, rol):
    tok = {"Authorization": f"Bearer {giris['access_token']}"}
    if giris.get("active_role") == rol:
        return tok
    r = client.post("/api/auth/select-role", json={"role": rol}, headers=tok)
    assert r.status_code == 200, r.text[:200]
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


@pytest.fixture
def yarisma(client, db_session):
    """Yonetici + bir yarisma + cift rollu (yarismaci VE hakem) bir hesap."""
    yon_giris = _kaydol_ve_giris(client, "yon@test.org", ["COMPETITION_MANAGER"])
    yonetici = _rolle(yon_giris, client, "COMPETITION_MANAGER")

    kat = client.post(
        "/api/categories",
        json={"name": "AI & Machine Learning", "description": "Neural networks."},
        headers=yonetici,
    )
    assert kat.status_code == 201
    kat_id = kat.json()["id"]

    yar = client.post(
        "/api/competitions",
        json={"name": "Cikar Catismasi Testi", "category_id": kat_id},
        headers=yonetici,
    )
    assert yar.status_code in (200, 201), yar.text[:200]
    yar_id = yar.json()["id"]
    client.put(
        f"/api/competitions/{yar_id}/template",
        json={"required_headings": ["Özgünlük"], "min_pages": 1, "max_pages": 80},
        headers=yonetici,
    )
    client.put(
        f"/api/competitions/{yar_id}/criteria",
        json={"criteria": [{"title": "Özgünlük", "weight": 100}]},
        headers=yonetici,
    )
    client.put(
        f"/api/competitions/{yar_id}/status", json={"status": "open"}, headers=yonetici
    )

    cift_giris = _kaydol_ve_giris(client, "cift@test.org", ["COMPETITOR", "REFEREE"])
    cift_yarismaci = _rolle(cift_giris, client, "COMPETITOR")

    # Rapor YONETICI tarafindan, CIFT ROLLU hesabin takimi adina aktariliyor.
    # Cikar catismasi senaryosu icin kritik: raporu yukleyen yonetici, ama
    # sahibi o hesabin takimi - yani `submitted_by_id` kontrolu bosa duser ve
    # yalnizca TAKIM kontrolu koruyabilir.
    from app import models

    cift_kullanici_id = (
        db_session.query(models.User)
        .filter(models.User.email == "cift@test.org")
        .first()
        .id
    )
    db_session.add(models.Team(id="cift-takim", name="Çift Rollü Takım"))
    db_session.flush()
    db_session.add(
        models.TeamMember(
            id=str(uuid.uuid4()),
            team_id="cift-takim",
            user_id=cift_kullanici_id,
            role="kaptan",
        )
    )
    db_session.commit()

    yukleme = client.post(
        "/api/reports/upload",
        data={
            "project_name": "Kendi Raporum",
            "competition_id": yar_id,
            "team_id": "cift-takim",
        },
        files={"file": ("r.pdf", io.BytesIO(b"%PDF-1.4 Mock"), "application/pdf")},
        headers=yonetici,
    )
    assert yukleme.status_code == 201, yukleme.text[:200]

    hakemler = client.get("/api/assignments/referees", headers=yonetici).json()
    cift_id = next(h["id"] for h in hakemler if h["email"] == "cift@test.org")
    client.post(
        f"/api/assignments/competitions/{yar_id}/referees",
        json={"referee_id": cift_id},
        headers=yonetici,
    )

    return {
        "yonetici": yonetici,
        "yarisma_id": yar_id,
        "rapor_id": yukleme.json()["id"],
        "cift_id": cift_id,
        "cift_giris": cift_giris,
    }


def test_auto_assign_kendi_raporunu_vermez(yarisma, client):
    sonuc = client.post(
        f"/api/assignments/competitions/{yarisma['yarisma_id']}/auto-assign",
        headers=yarisma["yonetici"],
    )
    assert sonuc.status_code == 200, sonuc.text[:200]
    veri = sonuc.json()
    assert veri["assigned"] == 0, (
        f"raporun sahibi kendisine atandi: {veri['assignments']}"
    )
    # SESSIZ ATLAMA YOK: yonetici "dagitim tamam" sanip hic degerlendirilmeyen
    # bir rapor birakmamali.
    assert len(veri["skipped"]) == 1, veri
    assert "çıkar" in veri["skipped"][0]["reason"].lower() or "cikar" in veri[
        "skipped"
    ][0]["reason"].lower()


def test_elle_atama_kendi_raporunu_reddeder(yarisma, client):
    r = client.put(
        f"/api/assignments/{yarisma['rapor_id']}",
        json={"referee_id": yarisma["cift_id"]},
        headers=yarisma["yonetici"],
    )
    # Otomatik dagitimda engelleyip elle atamada birakmak, kurali tek bir
    # tiklamayla asilabilir hale getirirdi.
    assert r.status_code == 400, f"kendi raporuna elle atandi (HTTP {r.status_code})"
    assert "kendi" in r.json()["detail"].lower()


def test_baska_hakem_varsa_dogru_kisiye_gidiyor(yarisma, client):
    """Kilit fazla siki olmamali: uygun bir hakem varsa dagitim calismali."""
    baska = _kaydol_ve_giris(client, "baska_hakem@test.org", ["REFEREE"])
    hakemler = client.get(
        "/api/assignments/referees", headers=yarisma["yonetici"]
    ).json()
    baska_id = next(h["id"] for h in hakemler if h["email"] == "baska_hakem@test.org")
    client.post(
        f"/api/assignments/competitions/{yarisma['yarisma_id']}/referees",
        json={"referee_id": baska_id},
        headers=yarisma["yonetici"],
    )

    veri = client.post(
        f"/api/assignments/competitions/{yarisma['yarisma_id']}/auto-assign",
        headers=yarisma["yonetici"],
    ).json()
    assert veri["assigned"] == 1, veri
    assert veri["assignments"][0]["referee_email"] == "baska_hakem@test.org"
    assert veri["skipped"] == []
    assert baska is not None


def test_kendi_raporuna_karar_veremiyor(yarisma, client):
    """Uc adimli zincirin sonu: atama engellendigine gore karar da engelli."""
    cift_hakem = _rolle(yarisma["cift_giris"], client, "REFEREE")
    r = client.post(
        f"/api/reports/{yarisma['rapor_id']}/decision",
        json={
            "outcome": "approve",
            "final_score": 100,
            "rationale": "Kendi raporuma kendim 100 veriyorum, gerekce yeterince uzun.",
        },
        headers=cift_hakem,
    )
    assert r.status_code == 403, f"kendi raporuna karar verdi (HTTP {r.status_code})"
