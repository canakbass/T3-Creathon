"""Takim sahipligi ve gorunurlugu.

NEDEN VAR: TEKNOFEST'te basvuruyu bir KISI degil bir TAKIM yapiyor (2026
Genel Sartname: takim kaptani + uyeler + en fazla bir danisman; kayitlar
KYS/t3kys.com'da). Sistemde ise rapor yalnizca `submitted_by_id` ile bir
kisiye bagliydi ve bunun iki somut sonucu vardi:

  * Takim arkadasi kendi takiminin sonucunu GOREMIYORDU.
  * Sartname AKIS 01 yarisma yoneticisinin "raporlari sisteme aktardigini"
    soyluyor; yonetici aktarinca `submitted_by_id` YONETICI oluyor ve
    raporun sonucunu HICBIR yarismaci goremiyordu. Kullanicinin "yoneticinin
    elle ekledigi raporlarin sonuclari..." sikayeti tam olarak buydu.

Takim YONETIMI bu sistemin isi degil - CRUD ucu yok, kayitlar disaridan
besleniyor. Testler de bu yuzden dogrudan veri tabanina yaziyor.
"""

import io
import uuid
from pathlib import Path

import pytest

from tests.conftest import kullanici_ac

# Gercek bir TEKNOFEST finalist raporu. Sahte "%PDF-1.4 Mock" baytlariyla
# benzerlik modulu daha en basta "PDF okunamadi" dalina giriyor ve
# karsilastirma HIC yapilmiyor - o durumda kimlik sizintisi testi yanlis
# sebeple gecerdi.
GERCEK_RAPOR = (
    Path(__file__).resolve().parents[2]
    / "ai-doc-analysis" / "sample_reports" / "havacilikta_yz_ktr" / "reports"
    / "KTR_00_YXpGnt7IevOLKmM75xNlXyQlgHmz2bTM.pdf"
)


def _kaydol_ve_giris(client, email, roller, sifre="password"):
    kullanici_ac(email, roller, sifre)
    return client.post(
        "/api/auth/login", data={"username": email, "password": sifre}
    ).json()


def _rolle(giris, client, rol):
    tok = {"Authorization": f"Bearer {giris['access_token']}"}
    if giris.get("active_role") == rol:
        return tok
    r = client.post("/api/auth/select-role", json={"role": rol}, headers=tok)
    assert r.status_code == 200, r.text[:200]
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def _takim_kur(db_session, takim_id, ad, uyeler):
    """uyeler: [(user_id, gorev)] — CRUD ucu yok, dogrudan veri tabanina."""
    from app import models

    db_session.add(models.Team(id=takim_id, name=ad, external_ref=f"KYS-{takim_id}"))
    db_session.flush()
    for user_id, gorev in uyeler:
        db_session.add(
            models.TeamMember(
                id=str(uuid.uuid4()), team_id=takim_id, user_id=user_id, role=gorev
            )
        )
    db_session.commit()


def _kullanici_id(db_session, eposta):
    from app import models

    return db_session.query(models.User).filter(models.User.email == eposta).first().id


@pytest.fixture
def sahne(client, db_session):
    """Bir yarisma, iki takim, yoneticinin AKTARDIGI bir rapor."""
    yonetici = _rolle(
        _kaydol_ve_giris(client, "yon@test.org", ["COMPETITION_MANAGER"]),
        client,
        "COMPETITION_MANAGER",
    )
    kaptan_giris = _kaydol_ve_giris(client, "kaptan@test.org", ["COMPETITOR"])
    arkadas_giris = _kaydol_ve_giris(client, "arkadas@test.org", ["COMPETITOR"])
    rakip_giris = _kaydol_ve_giris(client, "rakip@test.org", ["COMPETITOR"])
    kaptan = _rolle(kaptan_giris, client, "COMPETITOR")
    arkadas = _rolle(arkadas_giris, client, "COMPETITOR")
    rakip = _rolle(rakip_giris, client, "COMPETITOR")

    _takim_kur(
        db_session,
        "takim-a",
        "Glieser",
        [
            (_kullanici_id(db_session, "kaptan@test.org"), "kaptan"),
            (_kullanici_id(db_session, "arkadas@test.org"), "uye"),
        ],
    )
    _takim_kur(
        db_session, "takim-b", "Zebot", [(_kullanici_id(db_session, "rakip@test.org"), "kaptan")]
    )

    kat_id = client.post(
        "/api/categories",
        json={"name": "AI & Machine Learning", "description": "Neural networks."},
        headers=yonetici,
    ).json()["id"]
    yar_id = client.post(
        "/api/competitions",
        json={"name": "Havacılıkta Yapay Zeka", "category_id": kat_id},
        headers=yonetici,
    ).json()["id"]
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
    client.put(f"/api/competitions/{yar_id}/status", json={"status": "open"}, headers=yonetici)

    # YONETICI takim adina aktariyor (sartname AKIS 01)
    yukleme = client.post(
        "/api/reports/upload",
        data={"project_name": "Glieser KTR", "competition_id": yar_id, "team_id": "takim-a"},
        files={"file": ("r.pdf", io.BytesIO(b"%PDF-1.4 Mock"), "application/pdf")},
        headers=yonetici,
    )
    assert yukleme.status_code == 201, yukleme.text[:200]

    return {
        "yonetici": yonetici,
        "kaptan": kaptan,
        "arkadas": arkadas,
        "rakip": rakip,
        "yar_id": yar_id,
        "rapor_id": yukleme.json()["id"],
    }


# --- Sahiplik -------------------------------------------------------------

def test_yonetici_takimsiz_rapor_aktaramaz(client, sahne):
    """Sahipsiz rapor OLUSMAMALI.

    Aksi halde rapor sisteme girer, analiz edilir, hakem karar verir ve
    sonucu HICBIR yarismaci goremez - sartname AKIS 03 karsilanmaz.
    """
    r = client.post(
        "/api/reports/upload",
        data={"project_name": "Sahipsiz", "competition_id": sahne["yar_id"]},
        files={"file": ("r.pdf", io.BytesIO(b"%PDF-1.4 Mock"), "application/pdf")},
        headers=sahne["yonetici"],
    )
    assert r.status_code == 400, f"sahipsiz rapor olusturuldu (HTTP {r.status_code})"
    assert "team_id" in r.json()["detail"]


def test_rapor_takim_adiyla_donuyor(client, sahne):
    d = client.get(f"/api/reports/{sahne['rapor_id']}", headers=sahne["yonetici"]).json()
    assert d["team_id"] == "takim-a"
    assert d["team_name"] == "Glieser"


# --- Gorunurluk -----------------------------------------------------------

def test_takimdaki_herkes_sonucu_goruyor(client, sahne):
    """Kullanicinin istegi: "takimdaki herkes takimin basvuru sonuclarini
    goruntuleyebilsin". Raporu YONETICI aktardi - yani kaptan da arkadas da
    yukleyen DEGIL; erisim takim uyeliginden geliyor."""
    rid = sahne["rapor_id"]
    for etiket in ("kaptan", "arkadas"):
        assert client.get(f"/api/reports/{rid}", headers=sahne[etiket]).status_code == 200, etiket
        assert client.get(f"/api/reports/{rid}/file", headers=sahne[etiket]).status_code == 200, etiket
        assert any(x["id"] == rid for x in client.get("/api/reports", headers=sahne[etiket]).json())


def test_baska_takim_goremiyor(client, sahne):
    """"eger bir takimda degilsen o takimin soncunu gorememelisin"."""
    rid = sahne["rapor_id"]
    assert client.get(f"/api/reports/{rid}", headers=sahne["rakip"]).status_code == 403
    assert client.get(f"/api/reports/{rid}/file", headers=sahne["rakip"]).status_code == 403
    assert client.get("/api/reports", headers=sahne["rakip"]).json() == []


def test_yarismaci_RAPOR_YUKLEYEMEZ(client, sahne):
    """Sartname AKIS 03'te yarismacinin YUKLEME ADIMI YOK.

    AKIS 03 (Yarismaci): "Degerlendirme tamamlanir -> sonucunu goruntuler ->
    guclu ve gelisime acik yonlerini inceler -> onerileri gorur."
    AKIS 01 (Yarisma Yoneticisi): "...raporlari sisteme aktarir..."

    Yarismaci bu sistemde yalnizca SONUC GORUNTULEYEN taraf. Gercek hayatta
    da raporlar TEKNOFEST'in kendi sistemine (KYS) teslim ediliyor; bizim
    sistem o raporlari degerlendiren yardimci katman, toplama noktasi degil.

    Onceden yarismaci kendi raporunu yukleyebiliyordu ve bu iki ek kural
    gerektiriyordu (baskasinin takimi adina yukleyememe, iki takimliysa
    secim yapma). Yetki kalkinca o kurallar da gereksizlesti - kaldirildi.
    """
    for etiket in ("kaptan", "arkadas", "rakip"):
        r = client.post(
            "/api/reports/upload",
            data={
                "project_name": "Yarismaci Denemesi",
                "competition_id": sahne["yar_id"],
                "team_id": "takim-a",
            },
            files={"file": ("r.pdf", io.BytesIO(b"%PDF-1.4 Mock"), "application/pdf")},
            headers=sahne[etiket],
        )
        assert r.status_code == 403, f"{etiket} rapor yukleyebildi (HTTP {r.status_code})"


# --- Cikar catismasi ------------------------------------------------------

def test_takim_uyesi_hakem_kendi_takiminin_raporunu_degerlendiremez(
    client, db_session, sahne
):
    """REGRESYON: takim kavrami, kapatilmis cikar catismasi acigini GERI ACTI.

    Cikar catismasi kontrolu `hakem.id == rapor.submitted_by_id` bakiyordu.
    Rapor yonetici tarafindan aktarilinca `submitted_by_id` YONETICI oluyor;
    takimin bir uyesi ayni zamanda REFEREE rolune sahipse kontrol BOSA
    DUSUYOR ve kisi kendi takiminin raporunu onaylayabiliyordu.

    Kural artik Report.cikar_catismasi_var_mi'da tek yerde tanimli ve uc
    kapida birden uygulaniyor: otomatik dagitim, elle atama, karar.
    """
    ic_giris = _kaydol_ve_giris(client, "icerideki@test.org", ["COMPETITOR", "REFEREE"])
    ic_hakem = _rolle(ic_giris, client, "REFEREE")
    from app import models

    db_session.add(
        models.TeamMember(
            id=str(uuid.uuid4()),
            team_id="takim-a",
            user_id=_kullanici_id(db_session, "icerideki@test.org"),
            role="uye",
        )
    )
    db_session.commit()

    yonetici, rid = sahne["yonetici"], sahne["rapor_id"]
    hakemler = client.get("/api/assignments/referees", headers=yonetici).json()
    ic_id = next(h["id"] for h in hakemler if h["email"] == "icerideki@test.org")
    client.post(
        f"/api/assignments/competitions/{sahne['yar_id']}/referees",
        json={"referee_id": ic_id},
        headers=yonetici,
    )

    # 1) Otomatik dagitim ona VERMEMELI
    oto = client.post(
        f"/api/assignments/competitions/{sahne['yar_id']}/auto-assign", headers=yonetici
    ).json()
    assert oto["assigned"] == 0, f"kendi takiminin raporu otomatik atandi: {oto}"
    assert len(oto["skipped"]) == 1

    # 2) Elle atama REDDETMELI
    elle = client.put(
        f"/api/assignments/{rid}", json={"referee_id": ic_id}, headers=yonetici
    )
    assert elle.status_code == 400, f"kendi takiminin raporuna atandi (HTTP {elle.status_code})"

    # 3) Karar da REDDEDILMELI (ikinci kapi - geri alinamayan eylem)
    karar = client.post(
        f"/api/reports/{rid}/decision",
        json={
            "outcome": "approve",
            "final_score": 100,
            "rationale": "Kendi takimimin raporuna 100 veriyorum, gerekce yeterince uzun.",
        },
        headers=ic_hakem,
    )
    assert karar.status_code == 403, (
        f"KENDI TAKIMININ RAPORUNU ONAYLADI (HTTP {karar.status_code})"
    )


def test_ilgisiz_hakem_normal_degerlendirebiliyor(client, sahne):
    """Kilit fazla siki olmamali: takimla ilgisi olmayan hakem calisabilmeli."""
    _kaydol_ve_giris(client, "disarki@test.org", ["REFEREE"])
    yonetici, rid = sahne["yonetici"], sahne["rapor_id"]
    hakemler = client.get("/api/assignments/referees", headers=yonetici).json()
    dis_id = next(h["id"] for h in hakemler if h["email"] == "disarki@test.org")
    client.post(
        f"/api/assignments/competitions/{sahne['yar_id']}/referees",
        json={"referee_id": dis_id},
        headers=yonetici,
    )
    r = client.put(f"/api/assignments/{rid}", json={"referee_id": dis_id}, headers=yonetici)
    assert r.status_code == 200, r.text[:200]


# --- Kendi kendine intihal --------------------------------------------------

def test_takimin_kendi_raporu_intihal_sayilmiyor(client, sahne):
    """REGRESYON: takimin kendi onceki raporu %100 intihal olarak isaretleniyordu.

    Sartname madde 5 "BASVURULAR ARASINDA yuksek benzerlik" diyor. Bir
    takimin iki raporu iki ayri BASVURU degil, ayni basvurunun iki asamasi -
    ustelik teknik sartname madde 5 ikisini de ZORUNLU kiliyor: "On Tasarim
    Raporu yarisma katilimi ve Final Tasarim Raporu puanlandirma surecinde
    kullanilacagi icin IKI RAPORUN DA teslim edilmesi sarttir."

    Yani duzeltmeden once sistem, sartnamenin ZORUNLU tuttugu davranisi
    intihal olarak isaretliyordu. Demo'da jurinin gorebilecegi en kotu
    yanlis pozitif buydu.
    """
    ayni_icerik = b"%PDF-1.4 ayni proje metni tekrar tekrar ayni proje metni"

    def _yukle(ad, takim, basliklar):
        r = client.post(
            "/api/reports/upload",
            data={"project_name": ad, "competition_id": sahne["yar_id"], "team_id": takim},
            files={"file": (f"{ad}.pdf", io.BytesIO(ayni_icerik), "application/pdf")},
            headers=basliklar,
        )
        assert r.status_code == 201, r.text[:200]
        return client.get(f"/api/reports/{r.json()['id']}", headers=sahne["yonetici"]).json()

    _yukle("Glieser OTR", "takim-a", sahne["yonetici"])
    ftr = _yukle("Glieser FTR", "takim-a", sahne["yonetici"])

    benzerlik = ftr["ai_analysis"]["results"]["similarity"]
    assert benzerlik["score"] == 0, (
        f"takimin KENDI raporu intihal sayildi (puan {benzerlik['score']})"
    )
    # Sessizce dislamiyoruz: hakem neyin karsilastirilmadigini bilmeli.
    # "%0 benzerlik" ile "kendi takiminin raporu haric %0" ayni sey degil.
    assert any(
        "karşılaştırma dışı" in b for b in benzerlik["findings"]
    ), benzerlik["findings"]


def test_baska_takimin_kopyasi_HALA_yakalaniyor(client, sahne):
    """Kilit fazla gevsek olmamali: dislama YALNIZCA ayni takim icin."""
    ayni_icerik = b"%PDF-1.4 ozgun olmayan metin ozgun olmayan metin tekrar"

    def _yukle(ad, takim):
        r = client.post(
            "/api/reports/upload",
            data={"project_name": ad, "competition_id": sahne["yar_id"], "team_id": takim},
            files={"file": (f"{ad}.pdf", io.BytesIO(ayni_icerik), "application/pdf")},
            headers=sahne["yonetici"],
        )
        assert r.status_code == 201, r.text[:200]
        return client.get(f"/api/reports/{r.json()['id']}", headers=sahne["yonetici"]).json()

    _yukle("Ozgun Rapor", "takim-a")
    kopya = _yukle("Kopya Rapor", "takim-b")
    # Sahte PDF baytlariyla metin cikarilamadigi icin puanin kendisi
    # guvenilir degil; kritik olan AYNI TAKIM dislamasinin buraya
    # SIZMAMASI - yani karsilastirma kumesinin bos kalmamasi.
    benzerlik = kopya["ai_analysis"]["results"]["similarity"]
    assert not any(
        "karşılaştırma dışı" in b for b in benzerlik["findings"]
    ), f"baska takimin raporu da dislandi: {benzerlik['findings']}"


# --- Hesap acma: kimlige YONETICI kefil olur -------------------------------

def test_yonetici_hesap_acinca_takim_erisimi_otomatik(client, sahne):
    """Yonetici hesabi acar, sifreyi SISTEM uretir, uye takimin sonucunu gorur.

    NEDEN BOYLE: raporun sonucunu TAKIM UYELIGI belirliyor ve uyelik
    e-postaya bagli. Kullanicilar kendi kendine kayit olsaydi, bir takim
    uyesinin e-postasini ILK KAYDETTIREN kisi o takimin sonuclarini gorurdu -
    e-posta dogrulamamiz yok. Hesabi yoneticinin acmasi bu bagi guvenilir
    kiliyor: kimlige yonetici kefil oluyor.

    T3'un mevcut pratigi de bu: "belirlenen mail + uretilmis guvenli sifre,
    kullaniciya iletiliyor".
    """
    r = client.post(
        "/api/auth/users",
        json={
            "email": "Yeni.Uye@Takim.ORG",
            "full_name": "Yeni Üye",
            "roles": ["COMPETITOR"],
            "team_id": "takim-a",
            "team_role": "uye",
        },
        headers=sahne["yonetici"],
    )
    assert r.status_code == 201, r.text[:300]
    d = r.json()

    # E-posta normalize edilmeli - "Yeni.Uye@Takim.ORG" ile giris denemesi
    # kucuk harfli kayda dusmeli, aksi halde ayni kisi icin iki hesap olusur.
    assert d["email"] == "yeni.uye@takim.org"
    assert len(d["temporary_password"]) >= 12
    assert "YALNIZCA" in d["notice"]

    giris = client.post(
        "/api/auth/login",
        data={"username": "yeni.uye@takim.org", "password": d["temporary_password"]},
    )
    assert giris.status_code == 200, giris.text[:200]
    uye = {"Authorization": f"Bearer {giris.json()['access_token']}"}

    # Hicbir sey yuklemedi ama TAKIMIN raporunu goruyor.
    assert client.get(f"/api/reports/{sahne['rapor_id']}", headers=uye).status_code == 200


def test_kendi_kendine_kayit_URUNDE_kapali(client, monkeypatch):
    """Varsayilan KAPALI olmasi bilincli: yapilandirmayi unutmak guvenligi
    ARTIRIR, azaltmaz.

    Acik olsaydi herkes kendine REFEREE rolu verip /api/reports/lookup ile
    her basvurunun kunyesini gorebilirdi.
    """
    monkeypatch.setenv("SELF_REGISTRATION", "0")
    r = client.post(
        "/api/auth/register",
        json={"email": "davetsiz@test.org", "password": "parola", "roles": ["REFEREE"]},
    )
    assert r.status_code == 403, f"kendi kendine kayit acikti (HTTP {r.status_code})"
    assert "yonetici" in r.json()["detail"].lower()


def test_yarismaci_hesap_acamaz(client, sahne):
    """Hesap acmak YONETICI isi - aksi halde kefalet zinciri kirilir."""
    r = client.post(
        "/api/auth/users",
        json={"email": "sahte@test.org", "roles": ["COMPETITOR"]},
        headers=sahne["kaptan"],
    )
    assert r.status_code == 403, f"yarismaci hesap acabildi (HTTP {r.status_code})"


def test_ayni_eposta_iki_kez_acilamaz(client, sahne):
    govde = {"email": "tek@test.org", "roles": ["COMPETITOR"]}
    assert client.post("/api/auth/users", json=govde, headers=sahne["yonetici"]).status_code == 201
    ikinci = client.post("/api/auth/users", json=govde, headers=sahne["yonetici"])
    assert ikinci.status_code == 400
    assert "zaten kayitli" in ikinci.json()["detail"]


# --- Benzerlik bulgularinda kimlik sizintisi -------------------------------

@pytest.mark.skipif(not GERCEK_RAPOR.exists(), reason="referans KTR raporu bulunamadi")
def test_yarismaci_baska_basvurunun_KIMLIGINI_gormuyor(client, sahne):
    """OLCULEN SIZINTI: benzerlik bulgusu karsilastirilan raporun KIMLIGINI
    metne basiyordu.

    ai-scoring/similarity.py karsilastirilan dosyanin ADINI kullaniyor; dosya
    adi da RPT-2026-XXXXXX.pdf, yani rapor kimliginin ta kendisi. Bulgu
    metni "RPT-2026-06BBC8.pdf: %100.0 birebir ortusme" seklinde kaydediliyor
    ve bu bulgu YARISMACIYA da gidiyor - kendi raporunun analizinde BASKA BIR
    TAKIMIN basvuru kimligini okuyor. Canli sistemde dogrulandi.

    Hakem icin bu bilgi GEREKLI (intihal suphesini takip etmeli), o yuzden
    yalnizca COMPETITOR icin maskeleniyor. Ortusme YUZDESI duruyor:
    yarismacinin "raporum baska bir basvuruyla ortusuyor" bilgisini gormesi
    dogru, HANGI basvuru oldugunu bilmesi degil.
    """
    def _yukle(ad, takim):
        with open(GERCEK_RAPOR, "rb") as f:
            r = client.post(
                "/api/reports/upload",
                data={
                    "project_name": ad,
                    "competition_id": sahne["yar_id"],
                    "team_id": takim,
                },
                files={"file": (f"{ad}.pdf", f, "application/pdf")},
                headers=sahne["yonetici"],
            )
        assert r.status_code == 201, r.text[:200]
        return r.json()["id"]

    _yukle("Ilk Basvuru", "takim-a")
    kopya_id = _yukle("Kopya Basvuru", "takim-b")

    # rakip@ takim-b uyesi -> kendi raporunu goruyor
    yarismaci_gorunum = client.get(
        f"/api/reports/{kopya_id}", headers=sahne["rakip"]
    ).json()["ai_analysis"]["results"]["similarity"]
    assert not any(
        "RPT-" in b for b in yarismaci_gorunum["findings"]
    ), f"yarismaci baska basvurunun kimligini gordu: {yarismaci_gorunum['findings']}"

    # Yonetici/hakem icin kimlik DURMALI - aksi halde intihal takip edilemez.
    yonetici_gorunum = client.get(
        f"/api/reports/{kopya_id}", headers=sahne["yonetici"]
    ).json()["ai_analysis"]["results"]["similarity"]
    assert any(
        "RPT-" in b for b in yonetici_gorunum["findings"]
    ), "hakem/yonetici icin de maskelenmis - intihal takip edilemez"


def test_reanalyze_yetki_kapisindan_geciyor(client, sahne):
    """REGRESYON: reanalyze raporu DOGRUDAN kimlikle cekiyordu.

    Tek kontrol RoleChecker'di - yani "rolun var mi", "bu rapor senin mi"
    degil. Diger sekiz uc noktanin hepsi _rapor_getir_yetkiliyse kapisindan
    geciyor; tek istisna birakmak, kurum kapsami eklendiginde SESSIZ bir
    yazma deligi olurdu (baska kurumun AiAnalysis kaydini siler ve yanitla
    takim adini sizdirirdi).
    """
    # Yarismaci hicbir kosulda reanalyze edememeli.
    r = client.post(f"/api/reports/{sahne['rapor_id']}/reanalyze", headers=sahne["kaptan"])
    assert r.status_code == 403, f"yarismaci reanalyze cagirabildi (HTTP {r.status_code})"

    # Olmayan rapor 404 - kapinin ilk adimi.
    assert client.post(
        "/api/reports/RPT-YOK/reanalyze", headers=sahne["yonetici"]
    ).status_code == 404


# --- Roller artik KURUMA bagli ---------------------------------------------

def test_roller_kuruma_bagli(client, db_session, sahne):
    """Rol artik GLOBAL degil, KURUM ICINDE gecerli.

    Kullanicinin sordugu senaryo: "ben hem TEKNOFEST yarismasi icin hem de
    odev sonucu kontrolu icin ayni maile bagliysam?" Cevap: ayni kisi A
    kurumunda hakem, B kurumunda yarismaci olabilmeli.

    Onceden UserRole(user_id, role) benzersizligi bunu IMKANSIZ kiliyordu -
    bir kurumda hakem olan HER kurumda hakemdi.
    """
    from app import models

    org_a = models.Organization(id="org-a", name="A Kurumu", slug="a-kurumu")
    org_b = models.Organization(id="org-b", name="B Kurumu", slug="b-kurumu")
    db_session.add_all([org_a, org_b])
    db_session.flush()

    kisi = models.User(
        id="u-cift", email="cift.kurum@test.org", password_hash="x", full_name="Çift Kurum"
    )
    db_session.add(kisi)
    db_session.flush()
    db_session.add_all([
        models.UserRole(id="ur1", user_id=kisi.id, organization_id="org-a", role="REFEREE"),
        models.UserRole(id="ur2", user_id=kisi.id, organization_id="org-b", role="COMPETITOR"),
    ])
    db_session.commit()
    db_session.refresh(kisi)

    # AYNI kisi, FARKLI kurumlarda FARKLI roller
    assert kisi.roles_in("org-a") == ["REFEREE"]
    assert kisi.roles_in("org-b") == ["COMPETITOR"]
    # A kurumundaki hakemligi B kurumunda hicbir sey ifade etmiyor
    assert "REFEREE" not in kisi.roles_in("org-b")


def test_kurum_secilmemisse_HICBIR_rol(client, db_session):
    """Eksik baglam, "filtre yoklugu" degil "erisim yoklugu" anlamina gelmeli.

    Rolde ogrenilen dersin birebir tekrari: rol secmemis token tum raporlari
    listeliyordu cunku `if rol == ...` zinciri hicbir dala girmiyordu.
    """
    from app import models

    kisi = models.User(id="u-x", email="x@test.org", password_hash="x")
    db_session.add(kisi)
    db_session.flush()
    db_session.add(
        models.UserRole(id="ur-x", user_id=kisi.id, organization_id="org-t3", role="REFEREE")
    )
    db_session.commit()
    db_session.refresh(kisi)

    assert kisi.roles_in(None) == [], "kurum secilmemisken rol donduruldu"
    assert kisi.roles_in("olmayan-kurum") == []


def test_memberships_kurum_adiyla_donuyor(client, db_session, sahne):
    """Giris ekrani "hangi kurum adina" sorusunu sorabilmeli: rol tek basina
    bir kimlik degil, "T3 Vakfi'nda hakem" bir kimlik."""
    from app import models

    kisi = db_session.query(models.User).filter(
        models.User.email == "yon@test.org"
    ).first()
    assert kisi is not None, 'sahne fixture yoneticiyi olusturmali'
    uyelikler = kisi.memberships
    assert len(uyelikler) >= 1
    assert uyelikler[0]["organization_id"] == "org-t3"
    assert uyelikler[0]["organization_name"] == "T3 Vakfı"
    assert "COMPETITION_MANAGER" in uyelikler[0]["roles"]
