"""Rapor uc noktalarinin yetkilendirme regresyon testleri.

Buradaki her test, canli sunucuda GERCEKTEN calistigi dogrulanmis bir
aciga karsilik geliyor. Dordu de "rol dogru ama nesne yanlis" sinifindan:
kod "bu kullanici hakem mi?" diye soruyor, "bu rapor BU hakemin mi?" diye
sormuyordu.

Acilan kapilar (duzeltmeden onceki olculen davranis):

  1. POST /api/reports/{id}/decision  -> HTTP 200
     Sistemdeki HERHANGI bir hakem, kendisine atanmamis bir raporu
     onaylayabiliyordu. Karar geri alinamayan tek eylem oldugu icin en
     agir olani buydu.
  2. GET  /api/reports/{id}           -> HTTP 200 + tam AI analizi
     Atanmamis hakem, baska bir yarismacinin puanini, gerekcesini ve
     benzerlik sonucunu okuyabiliyordu.
  3. GET  /api/reports                -> tum raporlar
     Cok rollu bir kullanici giris yapip HENUZ ROL SECMEDEN listeyi
     cagirdiginda hicbir filtre dalina girmiyordu; filtre sessizce devre
     disi kaliyor ve tum yarismacilarin raporlari donuyordu.
  4. outcome serbest metindi ve dogrudan Report.status'a yaziliyordu:
     {"outcome": "SACMA"} raporun durumunu "SACMA" yapiyor, rapor da
     hicbir arayuz filtresine dusmedigi icin ortadan kayboluyordu.

Testlerin yalnizca ENGELLENDIGINI degil, gecerli kullanicinin HALA
calistigini da dogrulamasi onemli: fazla siki bir kilit, acik kadar
kotudur - hakem hicbir raporu goremezse sistem kullanilamaz.
"""

import io

import pytest


def _kaydol_ve_giris(client, email, rol, sifre="password"):
    client.post(
        "/api/auth/register", json={"email": email, "password": sifre, "role": rol}
    )
    r = client.post("/api/auth/login", data={"username": email, "password": sifre})
    assert r.status_code == 200, r.text[:200]
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


@pytest.fixture
def senaryo(client):
    """Bir rapor, iki hakem: biri atanmis, digeri atanmamis.

    Atanmamis hakem bu senaryonun saldirganidir; gecerli bir hesabi ve
    gecerli bir REFEREE rolu var - eksik olan tek sey ATAMA.
    """
    yonetici = _kaydol_ve_giris(client, "y@test.org", "COMPETITION_MANAGER")
    hakem_atanan = _kaydol_ve_giris(client, "atanan@test.org", "REFEREE")
    hakem_yabanci = _kaydol_ve_giris(client, "yabanci@test.org", "REFEREE")
    yarismaci = _kaydol_ve_giris(client, "yarismaci@test.org", "COMPETITOR")

    kat = client.post(
        "/api/categories",
        json={"name": "AI & Machine Learning", "description": "Neural networks."},
        headers=yonetici,
    )
    assert kat.status_code == 201
    kat_id = kat.json()["id"]

    yukleme = client.post(
        "/api/reports/upload",
        data={"project_name": "Gizli Proje", "category_id": kat_id},
        files={"file": ("r.pdf", io.BytesIO(b"%PDF-1.4 Mock"), "application/pdf")},
        headers=yarismaci,
    )
    assert yukleme.status_code == 201
    rapor_id = yukleme.json()["id"]

    hakemler = client.get("/api/assignments/referees", headers=yonetici).json()
    atanan_id = next(h["id"] for h in hakemler if h["email"] == "atanan@test.org")
    atama = client.put(
        f"/api/assignments/{rapor_id}",
        json={"referee_id": atanan_id},
        headers=yonetici,
    )
    assert atama.status_code == 200, atama.text[:200]

    return {
        "rapor_id": rapor_id,
        "yonetici": yonetici,
        "atanan": hakem_atanan,
        "yabanci": hakem_yabanci,
        "yarismaci": yarismaci,
    }


# --- Acik 1: atanmamis hakem karar veriyordu ------------------------------

def test_atanmamis_hakem_karar_veremez(senaryo, client):
    r = client.post(
        f"/api/reports/{senaryo['rapor_id']}/decision",
        json={
            "outcome": "approve",
            "final_score": 95,
            "rationale": "Bu rapor bana atanmadi ama yine de karar vermeye calisiyorum.",
        },
        headers=senaryo["yabanci"],
    )
    assert r.status_code == 403, (
        f"atanmamis hakem karar verebildi (HTTP {r.status_code})"
    )
    # Karar gercekten kaydedilmemis olmali - 403 donup yine de yazmak
    # en sinsi hata olurdu.
    detay = client.get(
        f"/api/reports/{senaryo['rapor_id']}", headers=senaryo["yonetici"]
    ).json()
    assert detay["status"] != "approved"


def test_atanan_hakem_karar_verebilir(senaryo, client):
    r = client.post(
        f"/api/reports/{senaryo['rapor_id']}/decision",
        json={
            "outcome": "revise",
            "final_score": 72,
            "rationale": "Yontem bolumu yeterli ancak bulgular kismi genisletilmeli.",
        },
        headers=senaryo["atanan"],
    )
    assert r.status_code == 200, r.text[:300]
    detay = client.get(
        f"/api/reports/{senaryo['rapor_id']}", headers=senaryo["yonetici"]
    ).json()
    # Arayuzun tanidigi degerler: frontend/src/lib/mock-reports.ts
    assert detay["status"] == "revise"


# --- Acik 2: atanmamis hakem tam analizi okuyordu -------------------------

def test_atanmamis_hakem_raporu_okuyamaz(senaryo, client):
    rid = senaryo["rapor_id"]
    assert client.get(f"/api/reports/{rid}", headers=senaryo["yabanci"]).status_code == 403
    assert client.get(f"/api/reports/{rid}/file", headers=senaryo["yabanci"]).status_code == 403
    assert client.post(
        f"/api/reports/{rid}/rationale-draft", headers=senaryo["yabanci"]
    ).status_code == 403
    # Listede de gorunmemeli: detay 403 verirken listede gorunmek,
    # proje adi + yarismaci bilgisini yine de sizdirirdi.
    liste = client.get("/api/reports", headers=senaryo["yabanci"])
    assert liste.status_code == 200
    assert [r for r in liste.json() if r["id"] == rid] == []


def test_atanan_hakem_raporu_okuyabilir(senaryo, client):
    rid = senaryo["rapor_id"]
    detay = client.get(f"/api/reports/{rid}", headers=senaryo["atanan"])
    assert detay.status_code == 200
    assert detay.json()["ai_analysis"] is not None
    assert client.get(f"/api/reports/{rid}/file", headers=senaryo["atanan"]).status_code == 200
    liste = client.get("/api/reports", headers=senaryo["atanan"])
    assert [r["id"] for r in liste.json()] == [rid]


def test_yarismaci_baskasinin_raporunu_okuyamaz(senaryo, client):
    baskasi = _kaydol_ve_giris(client, "baska_yarismaci@test.org", "COMPETITOR")
    rid = senaryo["rapor_id"]
    assert client.get(f"/api/reports/{rid}", headers=baskasi).status_code == 403
    assert client.get(f"/api/reports/{rid}/file", headers=baskasi).status_code == 403
    assert client.get("/api/reports", headers=baskasi).json() == []
    # Kendi raporunu ise gorebilmeli
    assert client.get(f"/api/reports/{rid}", headers=senaryo["yarismaci"]).status_code == 200


def test_yonetici_hepsini_gorur(senaryo, client):
    rid = senaryo["rapor_id"]
    assert client.get(f"/api/reports/{rid}", headers=senaryo["yonetici"]).status_code == 200
    assert client.get(f"/api/reports/{rid}/file", headers=senaryo["yonetici"]).status_code == 200
    assert [r["id"] for r in client.get("/api/reports", headers=senaryo["yonetici"]).json()] == [rid]


# --- Acik 3: rol secmemis cok-rollu token her seyi goruyordu --------------

def test_rol_secilmeden_rapora_erisilemez(senaryo, client):
    """Cok rollu kullanici giris yapar ama HENUZ ROL SECMEZ.

    Bu, arayuzdeki gercek bir ara durum: rol secme ekrani gosterilirken
    elde gecerli bir token var. O tokenla yapilan istekler hicbir rolun
    yetkisini kullanmamali.
    """
    email = "cok_rollu@test.org"
    kayit = client.post(
        "/api/auth/register",
        json={
            "email": email,
            "password": "password",
            "roles": ["REFEREE", "COMPETITOR", "COMPETITION_MANAGER"],
        },
    )
    assert kayit.status_code == 201, kayit.text[:200]
    giris = client.post(
        "/api/auth/login", data={"username": email, "password": "password"}
    ).json()
    assert giris["active_role"] is None, (
        "birden fazla rolu olan kullaniciya otomatik rol atanmamali"
    )
    rolsuz = {"Authorization": f"Bearer {giris['access_token']}"}

    rid = senaryo["rapor_id"]
    liste = client.get("/api/reports", headers=rolsuz)
    assert liste.status_code == 403, (
        f"rol secilmeden liste donduruldu (HTTP {liste.status_code}, "
        f"{len(liste.json()) if liste.status_code == 200 else 0} rapor)"
    )
    assert client.get(f"/api/reports/{rid}", headers=rolsuz).status_code == 403
    assert client.get(f"/api/reports/{rid}/file", headers=rolsuz).status_code == 403

    # Rol secilince calismali - kilit fazla siki olmamali.
    secim = client.post(
        "/api/auth/select-role", json={"role": "COMPETITION_MANAGER"}, headers=rolsuz
    )
    assert secim.status_code == 200, secim.text[:200]
    secili = {"Authorization": f"Bearer {secim.json()['access_token']}"}
    assert client.get("/api/reports", headers=secili).status_code == 200


# --- Acik 4: outcome dogrulanmadan Report.status'a yaziliyordu ------------

@pytest.mark.parametrize(
    "govde, aciklama",
    [
        ({"outcome": "SACMA", "final_score": 50, "rationale": "x" * 40},
         "taninmayan outcome"),
        ({"outcome": "approve", "final_score": 500, "rationale": "x" * 40},
         "100 uzeri puan"),
        ({"outcome": "approve", "final_score": -5, "rationale": "x" * 40},
         "negatif puan"),
        ({"outcome": "approve", "final_score": 80, "rationale": ""},
         "bos gerekce"),
        ({"outcome": "approve", "final_score": 80, "rationale": "kisa"},
         "cok kisa gerekce"),
    ],
)
def test_gecersiz_karar_govdesi_reddedilir(senaryo, client, govde, aciklama):
    r = client.post(
        f"/api/reports/{senaryo['rapor_id']}/decision",
        json=govde,
        headers=senaryo["atanan"],
    )
    assert r.status_code == 422, f"{aciklama} kabul edildi (HTTP {r.status_code})"
    # Rapor durumu bozulmamis olmali
    detay = client.get(
        f"/api/reports/{senaryo['rapor_id']}", headers=senaryo["yonetici"]
    ).json()
    assert detay["status"] in ("pending", "analyzed", "error"), detay["status"]
