"""Kullanicinin KENDI kurumunu acmasi.

NEDEN BU UC VAR: kullanici kayit olup e-postasini dogruladiginda, adresiyle
yuklenmis bir rapor yoksa hicbir kuruma bagli olmuyordu ve karsisina secim
yapilacak HICBIR SEY olmayan bir "kurum/rol secin" ekrani cikiyordu - olu bir
yol. Kullanicinin bildirdigi hata buydu.

NEDEN ONCE REDDEDILMISTI: "bir uc noktadan kurum acilabilse hesabi olan
herkes kendini sorumlu yaptigi kiraci uretirdi." O gerekce ARTIK GECERLI
DEGIL - kurum yalitimi kapandi, yeni acilan kurum BOMBOS ve sahibi baska
hicbir kurumun tek kaydini goremiyor. Tehlike "kurumu olmak" degildi,
"baska kuruma ULASMAK"ti. Bu dosya o iddiayi sinar.
"""

import uuid

import pytest

from tests.conftest import kullanici_ac


def _giris(client, eposta, sifre="parola1234"):
    j = client.post(
        "/api/auth/login", data={"username": eposta, "password": sifre}
    ).json()
    return {"Authorization": f"Bearer {j['access_token']}"}, j


@pytest.fixture
def dogrulanmis(client, db_session):
    """Kayitli, e-postasi dogrulanmis ama HICBIR KURUMDA olmayan kullanici."""
    from app import models

    kimlik = kullanici_ac("yalniz@kimse.org", [], "parola1234")
    kisi = db_session.query(models.User).filter(models.User.id == kimlik).first()
    kisi.email_verified = True
    db_session.commit()
    return _giris(client, "yalniz@kimse.org")[0]


def test_kendi_kurumunu_acabiliyor(client, db_session, dogrulanmis):
    r = client.post(
        "/api/organizations", json={"name": "Ege Üniversitesi"}, headers=dogrulanmis
    )
    assert r.status_code == 201, r.text[:200]
    govde = r.json()
    assert govde["name"] == "Ege Üniversitesi"
    assert govde["my_roles"] == ["ORG_OWNER"]


def test_slug_TURKCE_katlaniyor(client, dogrulanmis):
    """Slug URL'de ve gunlukte gorunuyor; diakritik birakmak ayni kuruma iki
    farkli adresten bakilmasina yol acardi."""
    r = client.post(
        "/api/organizations", json={"name": "İSTANBUL Üniversitesi"}, headers=dogrulanmis
    )
    assert r.json()["slug"] == "istanbul-universitesi", r.json()["slug"]


def test_ayni_ADLA_ikinci_kurum_FARKLI_slug_aliyor(client, dogrulanmis):
    ilk = client.post("/api/organizations", json={"name": "Deneme"}, headers=dogrulanmis)
    ikinci = client.post("/api/organizations", json={"name": "Deneme"}, headers=dogrulanmis)
    assert ilk.json()["slug"] != ikinci.json()["slug"]
    assert ikinci.json()["slug"] == "deneme-2"


def test_acildiktan_sonra_GIRISTE_gorunuyor(client, dogrulanmis):
    """Olu ekran sorununun asil cozumu: artik secilecek bir sey var."""
    client.post("/api/organizations", json={"name": "Yeni Kurum"}, headers=dogrulanmis)
    _, giris = _giris(client, "yalniz@kimse.org")
    assert giris["active_role"] == "ORG_OWNER"
    assert len(giris["memberships"]) == 1
    assert giris["memberships"][0]["organization_name"] == "Yeni Kurum"


def test_yeni_kurum_BOMBOS(client, db_session, dogrulanmis):
    """Guvenlik iddiasinin can alici noktasi."""
    from app import models

    r = client.post("/api/organizations", json={"name": "Bos Kurum"}, headers=dogrulanmis)
    kurum_id = r.json()["id"]
    assert db_session.query(models.Competition).filter(
        models.Competition.organization_id == kurum_id
    ).count() == 0
    assert db_session.query(models.Report).filter(
        models.Report.organization_id == kurum_id
    ).count() == 0
    assert r.json()["member_count"] == 1


def test_yeni_kurum_sahibi_BASKA_kurumu_GOREMIYOR(client, db_session, dogrulanmis):
    """"Kendini sorumlu yaptigi kiraci uretmek" korkusunun cevabi.

    Kurumu olmak tehlikeli degil; BASKA kuruma ulasmak tehlikeliydi ve o
    kapi kapali.
    """
    from app import models

    # Baska bir kurumda gercek veri
    kullanici_ac("t3.yonetici@t3.org", ["COMPETITION_MANAGER"], "parola1234")
    t3 = _giris(client, "t3.yonetici@t3.org")[0]
    kat = client.post(
        "/api/categories", json={"name": "Gizli", "description": "x"}, headers=t3
    ).json()["id"]
    gizli = client.post(
        "/api/competitions",
        json={"name": "T3 GİZLİ", "category_label": "Lise", "category_id": kat},
        headers=t3,
    ).json()

    r = client.post("/api/organizations", json={"name": "Yabanci"}, headers=dogrulanmis)
    yeni_kurum = r.json()["id"]
    yeni_tok, _ = _giris(client, "yalniz@kimse.org")

    # Sorumlu olarak giris yapip bakiyor
    sec = client.post(
        "/api/auth/select-role",
        json={"role": "ORG_OWNER", "organization_id": yeni_kurum},
        headers=yeni_tok,
    )
    assert sec.status_code == 200, sec.text[:200]
    sorumlu = {"Authorization": f"Bearer {sec.json()['access_token']}"}

    assert client.get("/api/reports", headers=sorumlu).json() == []
    assert client.get("/api/competitions", headers=sorumlu).json() == []
    assert client.get(f"/api/competitions/{gizli['id']}", headers=sorumlu).status_code == 404
    uyeler = client.get("/api/organizations/me/members", headers=sorumlu).json()
    assert [u["email"] for u in uyeler["items"]] == ["yalniz@kimse.org"]
    assert client.get("/api/dashboard/stats", headers=sorumlu).json()["total_reports"] == 0


def test_DOGRULANMAMIS_hesap_kurum_ACAMIYOR(client, db_session):
    """Dogrulanmamis adresle kurum acilabilseydi sahte adreslerle sinirsiz
    kiraci uretilebilirdi. Ustelik o kurumun sorumlusu ulasilamayan bir posta
    kutusuna bagli olurdu - sifresini unuttugunda kurtarma yolu kalmazdi."""
    from app import models

    kimlik = kullanici_ac("dogrulanmamis@kimse.org", [], "parola1234")
    kisi = db_session.query(models.User).filter(models.User.id == kimlik).first()
    kisi.email_verified = False
    db_session.commit()
    tok, _ = _giris(client, "dogrulanmamis@kimse.org")

    r = client.post("/api/organizations", json={"name": "Sahte Kurum"}, headers=tok)
    assert r.status_code == 403, r.status_code
    assert "dogrula" in r.json()["detail"].lower()
    assert db_session.query(models.Organization).filter(
        models.Organization.name == "Sahte Kurum"
    ).count() == 0


def test_UST_SINIR_var(client, dogrulanmis):
    """Sinir olmadan bu uc bir kiraci fabrikasina donusurdu."""
    for i in range(3):
        r = client.post(
            "/api/organizations", json={"name": f"Kurum {i}"}, headers=dogrulanmis
        )
        assert r.status_code == 201, (i, r.text[:150])
    dorduncu = client.post(
        "/api/organizations", json={"name": "Dorduncu"}, headers=dogrulanmis
    )
    assert dorduncu.status_code == 400
    assert "en fazla" in dorduncu.json()["detail"].lower()


def test_cok_kisa_ad_reddediliyor(client, dogrulanmis):
    r = client.post("/api/organizations", json={"name": "ab"}, headers=dogrulanmis)
    assert r.status_code == 400


def test_kurum_acmak_BASKA_kurumdaki_rolu_DEGISTIRMIYOR(client, db_session, dogrulanmis):
    """Baska bir kurumda yarismaci olan biri burada kendi kurumunun sorumlusu
    olur ama ORADA yarismaci kalmaya devam eder."""
    from app import models

    kisi = (
        db_session.query(models.User)
        .filter(models.User.email == "yalniz@kimse.org")
        .first()
    )
    db_session.add(
        models.UserRole(
            id=str(uuid.uuid4()),
            user_id=kisi.id,
            organization_id="org-t3",
            role="COMPETITOR",
        )
    )
    db_session.commit()

    r = client.post("/api/organizations", json={"name": "Kendi"}, headers=dogrulanmis)
    yeni = r.json()["id"]

    db_session.expire_all()
    kisi = (
        db_session.query(models.User)
        .filter(models.User.email == "yalniz@kimse.org")
        .first()
    )
    assert kisi.roles_in("org-t3") == ["COMPETITOR"]
    assert kisi.roles_in(yeni) == ["ORG_OWNER"]
