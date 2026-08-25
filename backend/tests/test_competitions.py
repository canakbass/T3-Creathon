"""Yarisma yasam dongusu ve sablon/kriter tanimi testleri.

Buradaki testler, "Kriter ve Sablon Tanimi" ekraninin GERCEKTEN bir sey
yaptigini ve yarismanin asamalarinin veriyi bozacak sekilde geri
alinamadigini dogruluyor.
"""

import io

import pytest

from app.routes.competitions import yarismanin_kurallari


def _kaydol_ve_giris(client, email, roller, sifre="password"):
    r = client.post(
        "/api/auth/register",
        json={"email": email, "password": sifre, "roles": roller},
    )
    assert r.status_code == 201, r.text[:200]
    giris = client.post(
        "/api/auth/login", data={"username": email, "password": sifre}
    ).json()
    tok = {"Authorization": f"Bearer {giris['access_token']}"}
    if giris.get("active_role") is None:
        tok = {
            "Authorization": "Bearer "
            + client.post(
                "/api/auth/select-role", json={"role": roller[0]}, headers=tok
            ).json()["access_token"]
        }
    return tok


@pytest.fixture
def kurulum(client):
    yonetici = _kaydol_ve_giris(client, "yy@test.org", ["COMPETITION_MANAGER"])
    kat_id = client.post(
        "/api/categories",
        json={"name": "AI & Machine Learning", "description": "Neural networks."},
        headers=yonetici,
    ).json()["id"]
    yar_id = client.post(
        "/api/competitions",
        json={"name": "Test Yarismasi", "category_id": kat_id},
        headers=yonetici,
    ).json()["id"]
    return {"yonetici": yonetici, "kat_id": kat_id, "yar_id": yar_id}


# --- Kriter agirliklari ---------------------------------------------------

@pytest.mark.parametrize(
    "kriterler, aciklama",
    [
        ([{"title": "A", "weight": 150}, {"title": "B", "weight": -50}],
         "toplami 100 eden negatif agirlik"),
        ([{"title": "A", "weight": 0}, {"title": "B", "weight": 100}],
         "sifir agirlik"),
        ([{"title": "", "weight": 100}], "bos baslik"),
    ],
)
def test_gecersiz_kriter_agirligi_reddedilir(kurulum, client, kriterler, aciklama):
    """REGRESYON: agirliklar yalnizca TOPLAMI uzerinden dogrulaniyordu.

    [{"A": 150}, {"B": -50}] toplami 100 ediyor ve kabul ediliyordu. Negatif
    agirlik, agirlikli ortalamada iyi puan alan bir kriterin toplami
    DUSURMESI anlamina gelir - hakemin ekranda gordugu sayiyi hicbir sekilde
    aciklayamayacagi bir sonuc.
    """
    r = client.put(
        f"/api/competitions/{kurulum['yar_id']}/criteria",
        json={"criteria": kriterler},
        headers=kurulum["yonetici"],
    )
    assert r.status_code == 422, f"{aciklama} kabul edildi (HTTP {r.status_code})"


def test_gecerli_kriterler_kabul_edilir(kurulum, client):
    r = client.put(
        f"/api/competitions/{kurulum['yar_id']}/criteria",
        json={"criteria": [
            {"title": "Özgünlük", "weight": 60},
            {"title": "Kaynakça", "weight": 40},
        ]},
        headers=kurulum["yonetici"],
    )
    assert r.status_code == 200, r.text[:200]


# --- Sablon kurallari -----------------------------------------------------

def test_baslik_bos_olsa_da_diger_kurallar_korunur():
    """REGRESYON: sadece baslik listesi bos diye TUM kurallar atiliyordu.

    Yonetici "Ingilizce de kabul, en fazla 3 sayfa" tanimlayip zorunlu
    baslik listesini bos biraktiginda, raporu hicbir uyari olmadan sabit
    TEKNOFEST varsayilanlarina (yalnizca Turkce, TEKNOFEST basliklari) gore
    degerlendiriliyordu - yazdigi kurallarin tam tersine.
    """
    class Yarisma:
        accepted_languages = '["en"]'
        required_headings = "[]"
        heading_synonyms = None
        min_pages = 1
        max_pages = 3
        min_section_chars = None

    kurallar = yarismanin_kurallari(Yarisma())
    assert kurallar is not None, "yoneticinin tanimladigi kurallar atildi"
    assert kurallar["kabul_edilen_diller"] == ["en"]
    assert kurallar["max_sayfa"] == 3
    # Baslik listesi bossa "zorunlu baslik yok" demektir - yoneticinin tanimi
    # bu; yerine TEKNOFEST basliklari konmamali.
    assert kurallar["zorunlu_basliklar"] == []


def test_hic_sablon_tanimi_yoksa_varsayilanlara_dusuluyor():
    """Kilit fazla siki olmamali: sablonu HIC doldurulmamis bir yarismada
    eski davranis (varsayilan kurallar) korunmali."""
    class Bos:
        accepted_languages = None
        required_headings = None
        heading_synonyms = None
        min_pages = None
        max_pages = None
        min_section_chars = None

    assert yarismanin_kurallari(Bos()) is None
    assert yarismanin_kurallari(None) is None


# --- Asama gecisleri ------------------------------------------------------

def _acilabilir_hale_getir(client, kurulum):
    client.put(
        f"/api/competitions/{kurulum['yar_id']}/template",
        json={"required_headings": ["Özgünlük"], "min_pages": 1, "max_pages": 80},
        headers=kurulum["yonetici"],
    )
    client.put(
        f"/api/competitions/{kurulum['yar_id']}/criteria",
        json={"criteria": [{"title": "Özgünlük", "weight": 100}]},
        headers=kurulum["yonetici"],
    )


def test_karar_yokken_asama_geri_alinabilir(kurulum, client):
    """Kilit fazla siki olmamali: yonetici yanlislikla kapattiysa geri
    acabilmeli - henuz kimse karar vermediyse zarar yok."""
    _acilabilir_hale_getir(client, kurulum)
    ynt = kurulum["yonetici"]
    yid = kurulum["yar_id"]
    assert client.put(f"/api/competitions/{yid}/status", json={"status": "open"}, headers=ynt).status_code == 200
    assert client.put(f"/api/competitions/{yid}/status", json={"status": "closed"}, headers=ynt).status_code == 200
    r = client.put(f"/api/competitions/{yid}/status", json={"status": "open"}, headers=ynt)
    assert r.status_code == 200, r.text[:200]


def test_karar_verilmisse_asama_geri_alinamaz(kurulum, client):
    """REGRESYON: 'completed' -> 'open' hicbir engel olmadan calisiyordu.

    Sonuclar aciklandiktan SONRA basvurular yeniden aciliyordu. Hakemler
    degerlendirmesini bitirmisken gelen yeni raporlar hic degerlendirilmez,
    yarismacilara duyurulan sonuclar da yarim kalirdi.
    """
    _acilabilir_hale_getir(client, kurulum)
    ynt = kurulum["yonetici"]
    yid = kurulum["yar_id"]
    client.put(f"/api/competitions/{yid}/status", json={"status": "open"}, headers=ynt)

    yarismaci = _kaydol_ve_giris(client, "y1@test.org", ["COMPETITOR"])
    hakem = _kaydol_ve_giris(client, "h1@test.org", ["REFEREE"])
    rapor_id = client.post(
        "/api/reports/upload",
        data={"project_name": "Proje", "competition_id": yid},
        files={"file": ("r.pdf", io.BytesIO(b"%PDF-1.4 Mock"), "application/pdf")},
        headers=yarismaci,
    ).json()["id"]

    hakemler = client.get("/api/assignments/referees", headers=ynt).json()
    hakem_id = next(h["id"] for h in hakemler if h["email"] == "h1@test.org")
    client.post(
        f"/api/assignments/competitions/{yid}/referees",
        json={"referee_id": hakem_id},
        headers=ynt,
    )
    assert client.put(
        f"/api/assignments/{rapor_id}", json={"referee_id": hakem_id}, headers=ynt
    ).status_code == 200

    karar = client.post(
        f"/api/reports/{rapor_id}/decision",
        json={
            "outcome": "approve",
            "final_score": 85,
            "rationale": "Rapor beklenen duzeyi karsiliyor, gerekce yeterince uzun.",
        },
        headers=hakem,
    )
    assert karar.status_code == 200, karar.text[:200]

    client.put(f"/api/competitions/{yid}/status", json={"status": "completed"}, headers=ynt)
    r = client.put(f"/api/competitions/{yid}/status", json={"status": "open"}, headers=ynt)
    assert r.status_code == 400, f"sonuclar aciklandiktan sonra basvurular yeniden acildi (HTTP {r.status_code})"
    assert "geri" in r.json()["detail"].lower()


# --- Atama butunlugu ------------------------------------------------------

def test_gorevli_olmayan_hakeme_atama_yapilamaz(kurulum, client):
    """REGRESYON: API, yarismanin hakem listesinde OLMAYAN birine atama
    yapabiliyordu. Arayuz zaten yalnizca gorevli hakemleri gosteriyor, ama
    o kisi auto-assign'in yuk hesabina hic girmedigi icin dagitim bozulurdu.
    """
    _acilabilir_hale_getir(client, kurulum)
    ynt = kurulum["yonetici"]
    yid = kurulum["yar_id"]
    client.put(f"/api/competitions/{yid}/status", json={"status": "open"}, headers=ynt)

    yarismaci = _kaydol_ve_giris(client, "y2@test.org", ["COMPETITOR"])
    _kaydol_ve_giris(client, "disarki@test.org", ["REFEREE"])
    rapor_id = client.post(
        "/api/reports/upload",
        data={"project_name": "Proje", "competition_id": yid},
        files={"file": ("r.pdf", io.BytesIO(b"%PDF-1.4 Mock"), "application/pdf")},
        headers=yarismaci,
    ).json()["id"]

    hakemler = client.get("/api/assignments/referees", headers=ynt).json()
    disarki_id = next(h["id"] for h in hakemler if h["email"] == "disarki@test.org")
    r = client.put(
        f"/api/assignments/{rapor_id}", json={"referee_id": disarki_id}, headers=ynt
    )
    assert r.status_code == 400, f"gorevli olmayan hakeme atandi (HTTP {r.status_code})"

    # Yarismaya eklendikten sonra calismali
    client.post(
        f"/api/assignments/competitions/{yid}/referees",
        json={"referee_id": disarki_id},
        headers=ynt,
    )
    assert client.put(
        f"/api/assignments/{rapor_id}", json={"referee_id": disarki_id}, headers=ynt
    ).status_code == 200


def test_karar_verilmis_raporun_atamasi_silinemez(kurulum, client):
    """REGRESYON: DELETE, PUT'un 'karar verilmis rapor devredilemez'
    kuralini atlatmanin yoluydu - once atamayi sil, sonra baskasina ata.
    """
    _acilabilir_hale_getir(client, kurulum)
    ynt = kurulum["yonetici"]
    yid = kurulum["yar_id"]
    client.put(f"/api/competitions/{yid}/status", json={"status": "open"}, headers=ynt)

    yarismaci = _kaydol_ve_giris(client, "y3@test.org", ["COMPETITOR"])
    hakem = _kaydol_ve_giris(client, "h3@test.org", ["REFEREE"])
    rapor_id = client.post(
        "/api/reports/upload",
        data={"project_name": "Proje", "competition_id": yid},
        files={"file": ("r.pdf", io.BytesIO(b"%PDF-1.4 Mock"), "application/pdf")},
        headers=yarismaci,
    ).json()["id"]
    hakemler = client.get("/api/assignments/referees", headers=ynt).json()
    hakem_id = next(h["id"] for h in hakemler if h["email"] == "h3@test.org")
    client.post(
        f"/api/assignments/competitions/{yid}/referees",
        json={"referee_id": hakem_id},
        headers=ynt,
    )
    client.put(f"/api/assignments/{rapor_id}", json={"referee_id": hakem_id}, headers=ynt)

    # Karar oncesi silinebilmeli
    assert client.delete(f"/api/assignments/{rapor_id}", headers=ynt).status_code == 204
    client.put(f"/api/assignments/{rapor_id}", json={"referee_id": hakem_id}, headers=ynt)

    client.post(
        f"/api/reports/{rapor_id}/decision",
        json={
            "outcome": "approve",
            "final_score": 85,
            "rationale": "Rapor beklenen duzeyi karsiliyor, gerekce yeterince uzun.",
        },
        headers=hakem,
    )
    r = client.delete(f"/api/assignments/{rapor_id}", headers=ynt)
    assert r.status_code == 400, f"karar verilmis raporun atamasi silindi (HTTP {r.status_code})"
