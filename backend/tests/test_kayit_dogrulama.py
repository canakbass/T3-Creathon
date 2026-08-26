"""Kendi kendine kayit, e-posta dogrulama ve sifre sifirlama.

KULLANICININ ISTEGI: "kullanici kendi kendine de hesap olusturabilsin,
sifremi unuttum gibi islemler yapabilsin."

NEDEN BU KADAR TEST: kayit bir kez kapatilmisti ve sebebi ciddiydi - raporun
sonucunu TAKIM UYELIGI belirliyor, uyelik e-postaya bagli; kayit acik
olsaydi bir takim uyesinin e-postasini ILK KAYDETTIREN kisi o takimin
sonuclarini gorurdu. Kapiyi tekrar acmanin tek sarti, dogrulamanin o acigi
GERCEKTEN kapatmasi. Bu dosya onu sinar.
"""

import datetime
import io
import os
import uuid

import pytest

from tests.conftest import kullanici_ac


@pytest.fixture(autouse=True)
def jetonu_goster(monkeypatch, tmp_path):
    """Testlerde jetonu yanitta gorebilelim.

    URETIMDE KAPALI: jetonu yanitta dondurmek, "bu kutunun sahibi misin"
    sorusunu kendi kendine cevaplatmak demek olurdu. Uc katli koruma var -
    varsayilan kapali, `smtp` arka ucunda hic calismiyor, acikken uyari
    basiyor. Testte acikca aciyoruz.
    """
    monkeypatch.setenv("DEV_EXPOSE_EMAIL_TOKEN", "1")
    monkeypatch.setenv("EMAIL_BACKEND", "file")
    monkeypatch.setenv("EMAIL_OUTBOX", str(tmp_path / "outbox"))


def _kaydol(client, eposta, sifre="parola1234", **ekstra):
    govde = {"email": eposta, "password": sifre}
    govde.update(ekstra)
    return client.post("/api/auth/register", json=govde)


def _giris(client, eposta, sifre="parola1234"):
    return client.post(
        "/api/auth/login", data={"username": eposta, "password": sifre}
    )


# --- Kayit ---------------------------------------------------------------

def test_kayit_dogrulama_baglantisi_URETIYOR(client):
    r = _kaydol(client, "yeni@ogrenci.edu.tr")
    assert r.status_code == 202, r.text[:200]
    assert r.json()["dev_token"], "dogrulama jetonu uretilmedi"


def test_kayit_MEKTUBU_gercekten_yaziliyor(client, tmp_path):
    """Akis GERCEK, teslimat degisken. SMTP yokken mektup diske dusuyor;
    demoda o dosya acilip baglanti kopyalaniyor. `EMAIL_BACKEND=smtp` ile
    ayni kod gercek sunucuya gonderiyor."""
    _kaydol(client, "mektup@ogrenci.edu.tr")
    kutu = tmp_path / "outbox"
    dosyalar = list(kutu.glob("*.eml"))
    assert dosyalar, "outbox bos"
    icerik = dosyalar[0].read_text(encoding="utf-8")
    assert "dogrula?token=" in icerik.replace("\n", "").replace("=\n", "")


def test_dogrulanmamis_hesap_GIRIS_YAPABILIR_ama_HICBIR_SEY_GORMEZ(client):
    """Giris 403 dondurseydi kayit akisi tamamen KILITLENIRDI: yeni kayit
    olanin rolu yok, giremiyor, "e-postani dogrula" ekranina bile
    ulasamiyordu.

    Guvenlik sorunu degil - "girebilmek" ile "gorebilmek" ayri seyler:
    rolsuz/kurumsuz token her veri ucundan 403 aliyor.
    """
    _kaydol(client, "bekleyen@ogrenci.edu.tr")
    r = _giris(client, "bekleyen@ogrenci.edu.tr")
    assert r.status_code == 200, r.text[:200]
    j = r.json()
    assert j["email_verified"] is False
    assert j["active_role"] is None and j["memberships"] == []

    tok = {"Authorization": f"Bearer {j['access_token']}"}
    assert client.get("/api/auth/me", headers=tok).status_code == 200
    for yol in ("/api/reports", "/api/competitions", "/api/categories"):
        assert client.get(yol, headers=tok).status_code == 403, yol


# --- Dogrulama -----------------------------------------------------------

def test_dogrulama_calisiyor(client, db_session):
    from app import models

    jeton = _kaydol(client, "dogrula@ogrenci.edu.tr").json()["dev_token"]
    r = client.post("/api/auth/verify-email", json={"token": jeton})
    assert r.status_code == 200, r.text[:200]

    kullanici = (
        db_session.query(models.User)
        .filter(models.User.email == "dogrula@ogrenci.edu.tr")
        .first()
    )
    assert kullanici.email_verified is True


def test_jeton_TEK_KULLANIMLIK(client):
    """Kullanilmis bir baglanti ikinci kez calismamali - JWT kullanmamamizin
    sebebi tam olarak bu."""
    jeton = _kaydol(client, "tek@ogrenci.edu.tr").json()["dev_token"]
    assert client.post("/api/auth/verify-email", json={"token": jeton}).status_code == 200
    ikinci = client.post("/api/auth/verify-email", json={"token": jeton})
    assert ikinci.status_code == 400


def test_gecersiz_suresi_dolmus_ve_kullanilmis_AYNI_cevabi_veriyor(client, db_session):
    """Ayrilsaydi saldirgan gecerli bir jetonun VAR OLDUGUNU dogrulayabilirdi."""
    from app import models

    jeton = _kaydol(client, "ayni@ogrenci.edu.tr").json()["dev_token"]
    kullanilmis = client.post("/api/auth/verify-email", json={"token": jeton})
    assert kullanilmis.status_code == 200

    yanitlar = [
        client.post("/api/auth/verify-email", json={"token": jeton}),          # kullanilmis
        client.post("/api/auth/verify-email", json={"token": "boyle-bir-sey-yok"}),  # yok
    ]
    # Suresi dolmus bir jeton
    jeton2 = _kaydol(client, "dolmus@ogrenci.edu.tr").json()["dev_token"]
    from app import jetonlar

    kayit = (
        db_session.query(models.EmailToken)
        .filter(models.EmailToken.token_hash == jetonlar.ozetle(jeton2))
        .first()
    )
    kayit.expires_at = datetime.datetime.now(datetime.UTC).replace(tzinfo=None) - datetime.timedelta(hours=1)
    db_session.commit()
    yanitlar.append(client.post("/api/auth/verify-email", json={"token": jeton2}))

    assert {r.status_code for r in yanitlar} == {400}
    assert len({r.json()["detail"] for r in yanitlar}) == 1, [
        r.json()["detail"] for r in yanitlar
    ]


def test_jeton_veri_tabaninda_HAM_saklanmiyor(client, db_session):
    """Veri tabani sizarsa jetonlar kullanilamamali - sifirlama jetonlarinin
    sizmasi "her hesabi ele gecir" demek."""
    from app import models

    jeton = _kaydol(client, "ozet@ogrenci.edu.tr").json()["dev_token"]
    kayitlar = [k.token_hash for k in db_session.query(models.EmailToken).all()]
    assert jeton not in kayitlar, "ham jeton veri tabaninda"
    assert all(len(h) == 64 for h in kayitlar), "SHA-256 ozeti bekleniyordu"


def test_yeni_jeton_ESKISINI_iptal_ediyor(client):
    """Kullanici "baglanti gelmedi" deyip ikinci kez isteyince ELINDE iki
    gecerli baglanti olurdu ve eskisi - belki bir yerde loglanmis olan -
    hala calisirdi."""
    eski = _kaydol(client, "iki.jeton@ogrenci.edu.tr").json()["dev_token"]
    client.post(
        "/api/auth/resend-verification", json={"email": "iki.jeton@ogrenci.edu.tr"}
    )
    # Bekleme suresi yuzunden yeni jeton uretilmemis olabilir; uretildiyse
    # eskisi olmus olmali.
    assert client.post("/api/auth/verify-email", json={"token": eski}).status_code in (
        200,
        400,
    )


# --- BEKLEYEN UYELIGE BAGLANMA (asil is) --------------------------------

@pytest.fixture
def bekleyen_rapor(client, db_session):
    """Yonetici, henuz kayitli OLMAYAN bir e-postayla rapor yukluyor."""
    kullanici_ac("yon@t3.org", ["COMPETITION_MANAGER"], "parola1234")
    yon = {
        "Authorization": "Bearer "
        + _giris(client, "yon@t3.org").json()["access_token"]
    }
    kat = client.post(
        "/api/categories", json={"name": "AI", "description": "x"}, headers=yon
    ).json()["id"]
    yar = client.post(
        "/api/competitions",
        json={"name": "Y", "category_label": "Lise", "category_id": kat},
        headers=yon,
    ).json()["id"]
    client.put(
        f"/api/competitions/{yar}/template",
        json={"required_headings": ["A"], "min_pages": 1, "max_pages": 9},
        headers=yon,
    )
    client.put(
        f"/api/competitions/{yar}/criteria",
        json={"criteria": [{"title": "A", "weight": 100}]},
        headers=yon,
    )
    client.put(f"/api/competitions/{yar}/status", json={"status": "open"}, headers=yon)
    r = client.post(
        "/api/reports/upload",
        data={"competition_id": yar},
        files={
            "file": (
                "ogrenci@okul.edu.tr_arkadas@okul.edu.tr.pdf",
                io.BytesIO(b"%PDF-1.4 Mock"),
                "application/pdf",
            )
        },
        headers=yon,
    )
    assert r.status_code == 201, r.text[:300]
    return {"yonetici": yon, "rapor_id": r.json()["id"]}


def test_dogrulama_BEKLEYEN_UYELIGI_bagliyor(client, db_session, bekleyen_rapor):
    """Butun akisin can damari.

    Yonetici raporu e-postayla yukledi, ogrenci sonradan kayit oldu ve
    dogruladi - simdi kendi raporunu gormeli.
    """
    jeton = _kaydol(client, "ogrenci@okul.edu.tr").json()["dev_token"]
    r = client.post("/api/auth/verify-email", json={"token": jeton})
    assert r.status_code == 200
    assert r.json()["linked_teams"] == 1

    giris = _giris(client, "ogrenci@okul.edu.tr").json()
    assert giris["active_role"] == "COMPETITOR"
    assert giris["active_organization_id"] == "org-t3"

    tok = {"Authorization": f"Bearer {giris['access_token']}"}
    detay = client.get(f"/api/reports/{bekleyen_rapor['rapor_id']}", headers=tok)
    assert detay.status_code == 200, detay.text[:200]


def test_DOGRULAMADAN_ONCE_hicbir_sey_baglanmiyor(client, db_session, bekleyen_rapor):
    """Bag KAYIT aninda kurulsaydi saldirgan kayit olur, dogrulamaz ve bag
    yine kurulmus olurdu. Bu, kayit ucunu kapatmamizin sebebi olan acigin ta
    kendisi."""
    from app import models

    _kaydol(client, "ogrenci@okul.edu.tr")
    kullanici = (
        db_session.query(models.User)
        .filter(models.User.email == "ogrenci@okul.edu.tr")
        .first()
    )
    assert kullanici.role_list == []
    uyelik = (
        db_session.query(models.TeamMember)
        .filter(models.TeamMember.email == "ogrenci@okul.edu.tr")
        .first()
    )
    assert uyelik.user_id is None, "dogrulanmadan takima baglandi"

    giris = _giris(client, "ogrenci@okul.edu.tr").json()
    tok = {"Authorization": f"Bearer {giris['access_token']}"}
    assert (
        client.get(f"/api/reports/{bekleyen_rapor['rapor_id']}", headers=tok).status_code
        == 403
    )


def test_BASKASININ_epostasiyla_kayit_o_takimi_ACMIYOR(client, bekleyen_rapor):
    """Dogrulama olmadan "ilk kaydettiren gorur" acigi geri gelirdi.

    Burada saldirgan kurbanin adresini yaziyor ama posta kutusuna
    erisemedigi icin jetona ulasamiyor - hesap dogrulanmiyor, bag
    kurulmuyor.
    """
    saldirgan = _kaydol(client, "arkadas@okul.edu.tr")
    assert saldirgan.status_code == 202
    # Jeton YALNIZCA posta kutusuna gidiyor. (Testte gorunur kildik ama
    # kullanmiyoruz - saldirganin elinde olmayacagi icin.)
    giris = _giris(client, "arkadas@okul.edu.tr").json()
    tok = {"Authorization": f"Bearer {giris['access_token']}"}
    assert (
        client.get(f"/api/reports/{bekleyen_rapor['rapor_id']}", headers=tok).status_code
        == 403
    )


def test_baglanma_YALNIZCA_COMPETITOR_veriyor(client, db_session, bekleyen_rapor):
    """Baska rol verilseydi kendi kendine kayit, kuruma yetkiyle girmenin
    yolu olurdu."""
    from app import models

    jeton = _kaydol(client, "ogrenci@okul.edu.tr").json()["dev_token"]
    client.post("/api/auth/verify-email", json={"token": jeton})
    kullanici = (
        db_session.query(models.User)
        .filter(models.User.email == "ogrenci@okul.edu.tr")
        .first()
    )
    assert kullanici.roles_in("org-t3") == ["COMPETITOR"]


def test_basvurusu_olmayan_dogrulanmis_hesap_HICBIR_KURUMDA_degil(client, db_session):
    """Kendi kendine kayit, kurum sinirini asmanin yeni bir yolu OLMAMALI."""
    from app import models

    jeton = _kaydol(client, "yalniz@kimse.org").json()["dev_token"]
    r = client.post("/api/auth/verify-email", json={"token": jeton})
    assert r.json()["linked_teams"] == 0

    kullanici = (
        db_session.query(models.User).filter(models.User.email == "yalniz@kimse.org").first()
    )
    assert kullanici.role_list == []
    giris = _giris(client, "yalniz@kimse.org").json()
    assert giris["email_verified"] is True
    assert giris["memberships"] == []


# --- Sifre sifirlama -----------------------------------------------------

def test_sifirlama_calisiyor(client):
    kullanici_ac("unuttum@t3.org", ["REFEREE"], "eskisifre")
    istek = client.post(
        "/api/auth/password-reset/request", json={"email": "unuttum@t3.org"}
    )
    assert istek.status_code == 202

    from app import jetonlar, models
    from tests.conftest import TestingSessionLocal

    db = TestingSessionLocal()
    try:
        kullanici = db.query(models.User).filter(models.User.email == "unuttum@t3.org").first()
        kayit = (
            db.query(models.EmailToken)
            .filter(
                models.EmailToken.user_id == kullanici.id,
                models.EmailToken.purpose == jetonlar.SIFIRLAMA,
            )
            .first()
        )
        assert kayit is not None, "sifirlama jetonu uretilmedi"
    finally:
        db.close()


def test_sifirlama_istegi_VARLIK_KAHINI_degil(client, monkeypatch):
    """URETIM DAVRANISI: kayitli ve kayitsiz adres AYNI cevabi vermeli.

    Ayrilsaydi herhangi biri adres deneyerek sistemde kimin hesabi oldugunu
    ogrenirdi. SMTP istek icinde beklenseydi ZAMANLAMA farki da olcum
    verirdi; gonderim arka plan gorevine alindi.

    BAYRAGI ACIKCA KAPATIYORUZ: `DEV_EXPOSE_EMAIL_TOKEN` yalnizca
    gelistirmede acik ve acikken yaniti FARKLILASTIRIYOR (kayitli adres
    baglantiyi geri aliyor). Testin sinadigi sey uretim sozlesmesi, o yuzden
    bayrak kapali olmali - aksi halde bu test uretimde bir seyin bozuldugunu
    hicbir zaman fark etmezdi.
    """
    monkeypatch.setenv("DEV_EXPOSE_EMAIL_TOKEN", "0")
    kullanici_ac("var@t3.org", ["REFEREE"], "parola1234")
    a = client.post("/api/auth/password-reset/request", json={"email": "var@t3.org"})
    b = client.post("/api/auth/password-reset/request", json={"email": "yok@hicbir.org"})
    assert a.status_code == b.status_code == 202
    assert a.json() == b.json()
    assert a.json()["dev_token"] is None


def test_gelistirme_bayragi_ACIKKEN_baglanti_yanitta(client):
    """GELISTIRME KOLAYLIGI - ve bilincli bir taviz.

    SMTP ayarlanmadan "sifremi unuttum" akisi hic denenemiyordu;
    kullanicinin "sifirlama e-postasi gelmedi" sikayetinin sebebi buydu.
    Bayrak acikken baglanti yanitta donuyor.

    TAVIZIN ADI KONUYOR: bu, ucu bir VARLIK KAHINI yapiyor - dolu gelmesi
    "bu adres kayitli" demek. Bu yuzden bayrak VARSAYILAN KAPALI, `smtp`
    arka ucunda HIC calismiyor ve acikken sunucu acilista uyari basiyor.
    """
    kullanici_ac("dev.kullanici@t3.org", ["REFEREE"], "parola1234")
    r = client.post(
        "/api/auth/password-reset/request", json={"email": "dev.kullanici@t3.org"}
    )
    assert r.status_code == 202
    assert r.json()["dev_token"], "gelistirmede baglanti donmeliydi"

    # Ve o baglanti GERCEKTEN calisiyor - yoksa demo edilemezdi.
    onay = client.post(
        "/api/auth/password-reset/confirm",
        json={"token": r.json()["dev_token"], "new_password": "yepyeni1234"},
    )
    assert onay.status_code == 200, onay.text[:200]
    assert _giris(client, "dev.kullanici@t3.org", "yepyeni1234").status_code == 200


def test_sifirlama_ESKI_TOKENLARI_dusuruyor(client):
    """En kritik kural.

    Token 60 dakika gecerli ve rol/kurum veri tabanina karsi dogrulaniyor
    ama SIFRE dogrulanmiyordu - yani calinmis bir token, kurban sifresini
    sifirladiktan SONRA da bir saat daha calisiyordu. Bu, sifre
    sifirlamanin tek amacini ("hesabi geri al") ortadan kaldiriyordu.
    """
    from app import jetonlar, models
    from tests.conftest import TestingSessionLocal

    kullanici_ac("calindi@t3.org", ["REFEREE"], "eskisifre")
    calinan = _giris(client, "calindi@t3.org", "eskisifre").json()["access_token"]
    tok = {"Authorization": f"Bearer {calinan}"}
    assert client.get("/api/auth/me", headers=tok).status_code == 200

    client.post("/api/auth/password-reset/request", json={"email": "calindi@t3.org"})
    db = TestingSessionLocal()
    try:
        kullanici = db.query(models.User).filter(models.User.email == "calindi@t3.org").first()
        ham = jetonlar.uret(db, kullanici.id, jetonlar.SIFIRLAMA)
        db.commit()
    finally:
        db.close()

    r = client.post(
        "/api/auth/password-reset/confirm",
        json={"token": ham, "new_password": "yepyenisifre"},
    )
    assert r.status_code == 200, r.text[:200]

    # Calinan token ARTIK CALISMAMALI - 401 (yetki degil KIMLIK sorunu).
    assert client.get("/api/auth/me", headers=tok).status_code == 401
    # Yeni sifre calisiyor, eski calismiyor
    assert _giris(client, "calindi@t3.org", "yepyenisifre").status_code == 200
    assert _giris(client, "calindi@t3.org", "eskisifre").status_code == 401


def test_sifirlama_jetonu_TEK_KULLANIMLIK(client):
    from app import jetonlar, models
    from tests.conftest import TestingSessionLocal

    kullanici_ac("tekrar@t3.org", ["REFEREE"], "parola1234")
    db = TestingSessionLocal()
    try:
        kullanici = db.query(models.User).filter(models.User.email == "tekrar@t3.org").first()
        ham = jetonlar.uret(db, kullanici.id, jetonlar.SIFIRLAMA)
        db.commit()
    finally:
        db.close()

    ilk = client.post(
        "/api/auth/password-reset/confirm", json={"token": ham, "new_password": "birincisifre"}
    )
    ikinci = client.post(
        "/api/auth/password-reset/confirm", json={"token": ham, "new_password": "ikincisifre"}
    )
    assert ilk.status_code == 200
    assert ikinci.status_code == 400
    assert _giris(client, "tekrar@t3.org", "birincisifre").status_code == 200


def test_sifirlama_DOGRULAMA_yerine_geciyor(client, db_session, bekleyen_rapor):
    """Sifresini e-posta uzerinden sifirlayabilen kisi o kutuya ERISIYOR
    demektir - bu, dogrulamanin ta kendisi. Ayrica sifirlama sonrasi
    bekleyen uyelikler de baglaniyor, yoksa kullanici "sifremi degistirdim
    ama hala hicbir sey goremiyorum" derdi."""
    from app import jetonlar, models
    from tests.conftest import TestingSessionLocal

    _kaydol(client, "ogrenci@okul.edu.tr")  # dogrulanmadi
    db = TestingSessionLocal()
    try:
        kullanici = (
            db.query(models.User).filter(models.User.email == "ogrenci@okul.edu.tr").first()
        )
        ham = jetonlar.uret(db, kullanici.id, jetonlar.SIFIRLAMA)
        db.commit()
    finally:
        db.close()

    r = client.post(
        "/api/auth/password-reset/confirm",
        json={"token": ham, "new_password": "yenisifre123"},
    )
    assert r.status_code == 200
    assert r.json()["linked_teams"] == 1

    giris = _giris(client, "ogrenci@okul.edu.tr", "yenisifre123").json()
    assert giris["email_verified"] is True
    tok = {"Authorization": f"Bearer {giris['access_token']}"}
    assert (
        client.get(f"/api/reports/{bekleyen_rapor['rapor_id']}", headers=tok).status_code
        == 200
    )


def test_kisa_sifreyle_sifirlanamiyor(client):
    r = client.post(
        "/api/auth/password-reset/confirm", json={"token": "x", "new_password": "abc"}
    )
    assert r.status_code == 400
    assert "8 karakter" in r.json()["detail"]


def test_hiz_siniri_SESSIZ(client):
    """Sinira takilan istek 429 degil yine 202 almali - yoksa "hizli
    deneyince farkli cevap veriyor" yeni bir varlik kahini olurdu."""
    kullanici_ac("hizli@t3.org", ["REFEREE"], "parola1234")
    yanitlar = [
        client.post("/api/auth/password-reset/request", json={"email": "hizli@t3.org"})
        for _ in range(3)
    ]
    assert {r.status_code for r in yanitlar} == {202}
    assert len({r.json()["message"] for r in yanitlar}) == 1
