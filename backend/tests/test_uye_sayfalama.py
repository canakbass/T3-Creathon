"""Kurum uye listesinde sayfalama, rol filtresi ve arama.

NEDEN: kullanici "Kurum Sorumlusu Panelinde herkesi dizmeyelim, sayfalama ve
role gore filtreleme olsun" dedi. Kurum buyudukce "hepsini diz" hem yavas
hem okunamaz oluyor.

SAYFALAMA VERI TABANINDA, ARAYUZDE DEGIL: butun uyeleri gonderip tarayicida
kesmek, "sayfalama" gorunumu verirken rehberin TAMAMINI yine de tel uzerinden
gecirir - yani listenin yalnizca sorumluya acik olmasinin bir anlami kalmaz.
"""

import uuid

import pytest

from tests.conftest import kullanici_ac


def _giris(client, eposta, sifre="parola123"):
    j = client.post(
        "/api/auth/login", data={"username": eposta, "password": sifre}
    ).json()
    return {"Authorization": f"Bearer {j['access_token']}"}


@pytest.fixture
def kalabalik_kurum(client, db_session):
    """Bir sorumlu + 30 hakem + 5 yarismaci + 2 yonetici."""
    from app import models

    kullanici_ac("sorumlu@t3.org", ["ORG_OWNER"], "parola123")
    for i in range(30):
        kullanici_ac(f"hakem{i:02d}@t3.org", ["REFEREE"], "parola123")
    for i in range(5):
        kullanici_ac(f"yarismaci{i}@t3.org", ["COMPETITOR"], "parola123")
    kullanici_ac("yonetici1@t3.org", ["COMPETITION_MANAGER"], "parola123")
    # IKI ROLU olan uye: sayfalama KULLANICI basina olmali, UserRole satiri
    # basina degil - yoksa bu kisi iki kez sayilir ve sayfa kayar.
    cift = kullanici_ac("cift.rol@t3.org", ["REFEREE", "COMPETITION_MANAGER"], "parola123")
    kullanici = db_session.query(models.User).filter(models.User.id == cift).first()
    kullanici.full_name = "Çift Rollü Kişi"
    db_session.commit()
    return _giris(client, "sorumlu@t3.org")


def test_varsayilan_sayfa_HEPSINI_dondurmuyor(client, kalabalik_kurum):
    r = client.get("/api/organizations/me/members", headers=kalabalik_kurum)
    assert r.status_code == 200, r.text[:200]
    govde = r.json()
    assert len(govde["items"]) == 25, len(govde["items"])
    assert govde["total"] == 38, govde["total"]  # 1+30+5+1+1
    assert govde["limit"] == 25 and govde["offset"] == 0


def test_sayfalar_ARALARINDA_uye_kaybetmiyor_ve_TEKRARLAMIYOR(client, kalabalik_kurum):
    """En kolay yapilan sayfalama hatasi budur: siralama belirsizse ayni uye
    iki sayfada birden cikar ya da hic cikmaz. Siralama e-postaya gore
    SABIT oldugu icin bu test onu kilitliyor."""
    toplanan = []
    offset = 0
    while True:
        govde = client.get(
            "/api/organizations/me/members",
            params={"limit": 10, "offset": offset},
            headers=kalabalik_kurum,
        ).json()
        toplanan.extend(u["email"] for u in govde["items"])
        offset += 10
        if offset >= govde["total"]:
            break
    assert len(toplanan) == 38, len(toplanan)
    assert len(set(toplanan)) == 38, "bir uye birden fazla sayfada cikti"
    assert toplanan == sorted(toplanan), "siralama sayfalar arasinda tutarsiz"


def test_iki_rolu_olan_uye_TEK_KEZ_geliyor(client, kalabalik_kurum):
    """JOIN yuzunden iki rolu olan uye iki kez gelirdi; hem sayim hem sayfa
    yanlis olurdu."""
    govde = client.get(
        "/api/organizations/me/members",
        params={"limit": 100},
        headers=kalabalik_kurum,
    ).json()
    epostalar = [u["email"] for u in govde["items"]]
    assert epostalar.count("cift.rol@t3.org") == 1, epostalar


def test_rol_filtresi(client, kalabalik_kurum):
    govde = client.get(
        "/api/organizations/me/members",
        params={"role": "COMPETITOR", "limit": 100},
        headers=kalabalik_kurum,
    ).json()
    assert govde["total"] == 5, govde["total"]
    assert all("COMPETITOR" in u["roles"] for u in govde["items"])


def test_rol_filtresi_uyenin_DIGER_rollerini_gizlemiyor(client, kalabalik_kurum):
    """Roller AYRI sorgudan geliyor. JOIN'den alsaydik, rol filtresi varken
    satirda yalnizca filtrelenmis rol gorunur ve sorumlu "bu uyenin tek rolu
    var" diye YANLIS bir izlenim edinirdi - sonra da farkinda olmadan
    ikinci rolunu geri alirdi."""
    govde = client.get(
        "/api/organizations/me/members",
        params={"role": "REFEREE", "limit": 100},
        headers=kalabalik_kurum,
    ).json()
    cift = [u for u in govde["items"] if u["email"] == "cift.rol@t3.org"]
    assert cift, "cift rollu uye REFEREE filtresinde cikmadi"
    assert set(cift[0]["roles"]) == {"REFEREE", "COMPETITION_MANAGER"}, cift[0]["roles"]


def test_toplam_FILTREDEN_SONRAKI_sayi(client, kalabalik_kurum):
    """Filtresiz toplami dondurseydik "5 sonuc" yazip 38 uyelik sayfalama
    gosterirdik."""
    govde = client.get(
        "/api/organizations/me/members",
        params={"role": "COMPETITOR"},
        headers=kalabalik_kurum,
    ).json()
    assert govde["total"] == 5


def test_arama_eposta_ve_ADDA_calisiyor(client, kalabalik_kurum):
    eposta_ile = client.get(
        "/api/organizations/me/members",
        params={"q": "yarismaci3"},
        headers=kalabalik_kurum,
    ).json()
    assert [u["email"] for u in eposta_ile["items"]] == ["yarismaci3@t3.org"]

    ad_ile = client.get(
        "/api/organizations/me/members",
        params={"q": "Çift Rollü"},
        headers=kalabalik_kurum,
    ).json()
    assert [u["email"] for u in ad_ile["items"]] == ["cift.rol@t3.org"], ad_ile


def test_arama_JOKER_kabul_etmiyor(client, kalabalik_kurum):
    """`%` LIKE jokeri; kacislanmazsa arama kutusuna `%` yazan biri filtreyi
    tamamen etkisiz kilar. Zararsiz gorunur ama "filtreledim" sanan
    sorumluya filtrelenmemis liste gostermek yanlis karar aldirir."""
    for desen in ("%", "_", "%@t3.org"):
        govde = client.get(
            "/api/organizations/me/members",
            params={"q": desen},
            headers=kalabalik_kurum,
        ).json()
        assert govde["total"] == 0, f"{desen!r} joker olarak islendi: {govde['total']}"


def test_limit_UST_SINIRI_var(client, kalabalik_kurum):
    """Istemci `limit=100000` yazip sayfalamayi etkisiz kilamamali."""
    r = client.get(
        "/api/organizations/me/members",
        params={"limit": 100000},
        headers=kalabalik_kurum,
    )
    assert r.status_code == 422, r.status_code


def test_gecersiz_rol_reddediliyor(client, kalabalik_kurum):
    """Sessizce bos liste donmek, sorumluya "bu rolde kimse yok" dedirtirdi -
    oysa rol adi yanlis yazilmisti."""
    r = client.get(
        "/api/organizations/me/members",
        params={"role": "ADMIN"},
        headers=kalabalik_kurum,
    )
    assert r.status_code == 400, r.status_code


def test_sayfalama_KURUM_sinirini_asmiyor(client, db_session, kalabalik_kurum):
    """Sayfalama eklenirken en kolay kaybedilen sey kapsam filtresidir."""
    from app import models

    kullanici_ac("yabanci@cbu.edu.tr", ["REFEREE"], "parola123", org="org-cbu")
    govde = client.get(
        "/api/organizations/me/members",
        params={"limit": 100},
        headers=kalabalik_kurum,
    ).json()
    assert not any(u["email"].endswith("@cbu.edu.tr") for u in govde["items"])
    assert govde["total"] == 38


def test_arama_TURKCE_diakritigi_gormezden_geliyor(client, kalabalik_kurum):
    """SQLite'in `lower()`i yalnizca ASCII kucultur.

    `lower(full_name) LIKE '%çift%'` yazsaydik, veri tabanindaki "Çift Rollü
    Kişi" hic eslesmezdi ve sorumlu "bu kisi kurumda yok" sonucuna varirdi.
    Bos sonuc, yanlis sonuctan daha ikna edici oldugu icin en tehlikeli hata
    sinifi. Arama artik SAKLANAN katlanmis anahtara karsi calisiyor.
    """
    for desen in ("çift", "ÇİFT", "Cift", "rollu", "ROLLÜ", "kisi", "Kişi"):
        govde = client.get(
            "/api/organizations/me/members",
            params={"q": desen},
            headers=kalabalik_kurum,
        ).json()
        assert [u["email"] for u in govde["items"]] == ["cift.rol@t3.org"], (
            f"{desen!r} eslesmedi: {govde}"
        )


def test_arama_anahtari_ad_DEGISINCE_guncelleniyor(client, db_session, kalabalik_kurum):
    """Anahtar bir olay dinleyicisiyle her yazmada hesaplaniyor.

    Elle doldurulan bir alan olsaydi, kullaniciyi yazan yerlerden birini
    (kayit, yonetici hesap acma, tohumlama, kurum acma betigi) unutmak o
    kullaniciyi aramadan SESSIZCE dusurmek demekti - ve "aramada cikmiyor"
    ile "kurumda yok" ayirt edilemez.
    """
    from app import models

    kisi = (
        db_session.query(models.User)
        .filter(models.User.email == "cift.rol@t3.org")
        .first()
    )
    kisi.full_name = "Yepyeni Ünvan"
    db_session.commit()

    govde = client.get(
        "/api/organizations/me/members",
        params={"q": "ünvan"},
        headers=kalabalik_kurum,
    ).json()
    assert [u["email"] for u in govde["items"]] == ["cift.rol@t3.org"], govde
