"""Dosya adindan takim turetme - uctan uca.

KULLANICININ ISTEGI: "yonetici raporu teslim eden kisilerin mailini girsin ya
da GONDERILEN DOSYALAR UZERINDEN isimlendirilebilsin; atiyorum
`232805068@ogr.cbu.edu.tr_canakbasforspecial@gmail.com` bu isimli dosya iki
kisiden olusan bir takimi temsil ediyor."

Ve sikayeti: yukleme ekraninda "takim kimligi" istemek SACMA - yoneticinin
elinde olmayan bir bilgi.

GUVENLIK EKSENI: uyelik artik E-POSTAYA bagli. Bu, "bir takim uyesinin
e-postasini ILK KAYDETTIREN kisi o takimin sonuclarini gorur" acigini geri
getirebilecek bir degisiklik. Bu dosyanin yarisi o acigin kapali kaldigini
sinamak icin var.
"""

import io
import uuid

import pytest

from tests.conftest import kullanici_ac


def _giris(client, eposta, sifre="parola123"):
    j = client.post(
        "/api/auth/login", data={"username": eposta, "password": sifre}
    ).json()
    return {"Authorization": f"Bearer {j['access_token']}"}


def _pdf():
    return {"file": ("x.pdf", io.BytesIO(b"%PDF-1.4 Mock"), "application/pdf")}


def _adli_pdf(ad):
    return {"file": (ad, io.BytesIO(b"%PDF-1.4 Mock"), "application/pdf")}


@pytest.fixture
def yonetici(client, db_session):
    kullanici_ac("yonetici@t3.org", ["COMPETITION_MANAGER"], "parola123")
    return _giris(client, "yonetici@t3.org")


@pytest.fixture
def acik_yarisma(client, yonetici):
    kat = client.post(
        "/api/categories", json={"name": "AI", "description": "x"}, headers=yonetici
    ).json()["id"]
    y = client.post(
        "/api/competitions",
        json={"name": "Yarışma", "category_label": "Lise", "category_id": kat},
        headers=yonetici,
    ).json()["id"]
    client.put(
        f"/api/competitions/{y}/template",
        json={"required_headings": ["Özgünlük"], "min_pages": 1, "max_pages": 80},
        headers=yonetici,
    )
    client.put(
        f"/api/competitions/{y}/criteria",
        json={"criteria": [{"title": "Özgünlük", "weight": 100}]},
        headers=yonetici,
    )
    client.put(f"/api/competitions/{y}/status", json={"status": "open"}, headers=yonetici)
    return y


def _yukle(client, yonetici, yarisma, dosya_adi, **ekstra):
    veri = {"competition_id": yarisma}
    veri.update(ekstra)
    return client.post(
        "/api/reports/upload", data=veri, files=_adli_pdf(dosya_adi), headers=yonetici
    )


# --- Temel akis ----------------------------------------------------------

def test_dosya_adindan_IKI_KISILIK_takim(client, db_session, yonetici, acik_yarisma):
    """Kullanicinin verdigi gercek ornek."""
    from app import models

    r = _yukle(
        client,
        yonetici,
        acik_yarisma,
        "232805068@ogr.cbu.edu.tr_canakbasforspecial@gmail.com.pdf",
    )
    assert r.status_code == 201, r.text[:300]

    rapor = db_session.query(models.Report).filter(models.Report.id == r.json()["id"]).first()
    assert rapor.team_id is not None, "takim turetilmedi"
    assert rapor.team.member_emails == {
        "232805068@ogr.cbu.edu.tr",
        "canakbasforspecial@gmail.com",
    }
    # Hicbiri kayitli degil - ikisi de BEKLEYEN uye.
    assert rapor.team.bekleyen_sayisi == 2
    assert rapor.team.member_ids == set(), "kimligi olmayan uyeler kimlik kumesine girdi"


def test_takim_kimligi_ARTIK_ZORUNLU_DEGIL(client, yonetici, acik_yarisma):
    """Kullanicinin sikayeti buydu: yoneticinin elinde olmayan bir bilgi."""
    r = _yukle(client, yonetici, acik_yarisma, "ogrenci2@cbu.edu.tr.docx")
    assert r.status_code == 201, r.text[:300]


def test_ayni_EKIP_ikinci_raporda_AYNI_takima_dusuyor(
    client, db_session, yonetici, acik_yarisma
):
    """Anahtar siradan bagimsiz. Olmasaydi ayni ekip icin ikinci bir takim
    acilir, ekibin raporlari iki takima dagilir ve uyeler birbirinin sonucunu
    goremezdi."""
    from app import models

    ilk = _yukle(client, yonetici, acik_yarisma, "ali@x.com_veli@y.com.pdf")
    # Sira DEGISIK, buyuk harf farkli
    ikinci = _yukle(client, yonetici, acik_yarisma, "VELI@y.com_Ali@X.com.pdf")
    assert ilk.status_code == 201 and ikinci.status_code == 201, ikinci.text[:200]

    a = db_session.query(models.Report).filter(models.Report.id == ilk.json()["id"]).first()
    b = db_session.query(models.Report).filter(models.Report.id == ikinci.json()["id"]).first()
    assert a.team_id == b.team_id, "ayni ekip iki takima dagildi"
    assert db_session.query(models.Team).count() == 1


def test_ELLE_girilen_epostalar_dosya_adindan_ONCELIKLI(
    client, db_session, yonetici, acik_yarisma
):
    """Yonetici acikca yazdiysa en guvenilir kaynak odur."""
    from app import models

    r = _yukle(
        client,
        yonetici,
        acik_yarisma,
        "yanlis@dosya.com.pdf",
        member_emails="dogru@takim.org, ikinci@takim.org",
    )
    assert r.status_code == 201, r.text[:300]
    rapor = db_session.query(models.Report).filter(models.Report.id == r.json()["id"]).first()
    assert rapor.team.member_emails == {"dogru@takim.org", "ikinci@takim.org"}


def test_proje_adi_dosya_adindan_TURETILIYOR(client, db_session, yonetici, acik_yarisma):
    from app import models

    r = _yukle(client, yonetici, acik_yarisma, "Yapay Zeka Projesi ali@x.com.pdf")
    assert r.status_code == 201, r.text[:300]
    rapor = db_session.query(models.Report).filter(models.Report.id == r.json()["id"]).first()
    assert rapor.project_name == "Yapay Zeka Projesi"
    assert rapor.team.member_emails == {"ali@x.com"}


def test_ALT_CIZGIYLE_bitisik_proje_adi_ACGOZLU_okunuyor(
    client, db_session, yonetici, acik_yarisma
):
    """BILINEN VE KABUL EDILEN belirsizlik.

    `Yapay Zeka Projesi_ali@x.com` icinde `Projesi_ali` mi yerel kisim, `ali`
    mi? Regex bunu karara baglayamaz - ve `ali_veli@x.com` GERCEK bir adres
    oldugu icin acgozlu okuma dogru varsayilan. Yanlis varsayilan secmek,
    mesru adresleri ikiye bolmek demekti.

    Sessiz kalmiyoruz: ayristirici uyari uretiyor ve yonetici onaylamadan
    hicbir sey kesinlesmiyor. Bu test o davranisi KILITLIYOR - biri "duzeltip"
    yerel kismi kirpmaya kalkarsa `ali_veli@x.com` bozulur.
    """
    from app import models
    from app.dosya_adi import cozumle

    sonuc = cozumle("Yapay Zeka Projesi_ali@x.com.pdf")
    assert sonuc["epostalar"] == ["projesi_ali@x.com"]
    assert sonuc["proje_adi"] == "Yapay Zeka"
    assert any("duzeltin" in u for u in sonuc["uyarilar"]), sonuc["uyarilar"]

    # Yonetici e-postayi elle yazarak duzeltebiliyor - kacis yolu var.
    r = _yukle(
        client,
        yonetici,
        acik_yarisma,
        "Yapay Zeka Projesi_ali@x.com.pdf",
        member_emails="ali@x.com",
        project_name="Yapay Zeka Projesi",
    )
    assert r.status_code == 201
    rapor = db_session.query(models.Report).filter(models.Report.id == r.json()["id"]).first()
    assert rapor.team.member_emails == {"ali@x.com"}
    assert rapor.project_name == "Yapay Zeka Projesi"


def test_hicbir_kaynak_yoksa_NE_YAPACAGINI_soyluyor(client, yonetici, acik_yarisma):
    """"team_id zorunlu" demek, yoneticiden elinde olmayan bir bilgiyi
    istemekti."""
    r = _yukle(client, yonetici, acik_yarisma, "matematik_rapor.docx")
    assert r.status_code == 400
    detay = r.json()["detail"].lower()
    assert "e-posta" in detay and "girin" in detay, detay


def test_gecersiz_eposta_SESSIZCE_atilmiyor(client, yonetici, acik_yarisma):
    """Sessizce atilsaydi yonetici eksik bir takimi onaylamis olurdu."""
    r = _yukle(
        client, yonetici, acik_yarisma, "x.pdf", member_emails="iyi@takim.org, bozukadres"
    )
    assert r.status_code == 400
    assert "bozukadres" in r.json()["detail"]


# --- GUVENLIK: dogrulanmamis e-posta BAGLANMAZ --------------------------

def test_DOGRULANMAMIS_hesap_takima_BAGLANMIYOR(
    client, db_session, yonetici, acik_yarisma
):
    """En kritik kural.

    Uyelik e-postaya bagli. Dogrulanmamis bir adresi baglamak, "bir takim
    uyesinin e-postasini ILK KAYDETTIREN kisi o takimin sonuclarini gorur"
    acigini geri acardi - kayit ucunu kapatmamizin tek sebebi buydu.
    """
    from app import models

    kimlik = kullanici_ac("davetsiz@x.com", ["COMPETITOR"], "parola123")
    kisi = db_session.query(models.User).filter(models.User.id == kimlik).first()
    kisi.email_verified = False
    db_session.commit()

    r = _yukle(client, yonetici, acik_yarisma, "davetsiz@x.com.pdf")
    assert r.status_code == 201

    rapor = db_session.query(models.Report).filter(models.Report.id == r.json()["id"]).first()
    uye = rapor.team.members[0]
    assert uye.email == "davetsiz@x.com"
    assert uye.user_id is None, "dogrulanmamis hesap takima baglandi"
    # Ve gercekten goremiyor
    tok = _giris(client, "davetsiz@x.com")
    assert client.get(f"/api/reports/{rapor.id}", headers=tok).status_code == 403


def test_DOGRULANMIS_hesap_HEMEN_baglaniyor(client, db_session, yonetici, acik_yarisma):
    """Kilit fazla siki olmamali: dogrulanmis kisi kendi raporunu gormeli."""
    from app import models

    kimlik = kullanici_ac("dogrulanmis@x.com", ["COMPETITOR"], "parola123")
    kisi = db_session.query(models.User).filter(models.User.id == kimlik).first()
    kisi.email_verified = True
    db_session.commit()

    r = _yukle(client, yonetici, acik_yarisma, "dogrulanmis@x.com.pdf")
    assert r.status_code == 201

    rapor = db_session.query(models.Report).filter(models.Report.id == r.json()["id"]).first()
    assert rapor.team.members[0].user_id == kimlik
    tok = _giris(client, "dogrulanmis@x.com")
    assert client.get(f"/api/reports/{rapor.id}", headers=tok).status_code == 200


def test_turetilen_takim_YUKLEYENIN_kurumunda(client, db_session, yonetici, acik_yarisma):
    from app import models

    r = _yukle(client, yonetici, acik_yarisma, "a@x.com.pdf")
    rapor = db_session.query(models.Report).filter(models.Report.id == r.json()["id"]).first()
    assert rapor.team.organization_id == "org-t3"
    assert rapor.organization_id == "org-t3"


# --- GUVENLIK: cikar catismasi SESSIZCE ACILMAMALI ----------------------

def test_BEKLEYEN_uye_olan_hakem_kendi_takimini_DEGERLENDIREMIYOR(
    client, db_session, yonetici, acik_yarisma
):
    """SESSIZ ACILMA (fail-open) testi.

    `cikar_catismasi_var_mi` yalnizca `user_id` kumesine bakiyordu. Hakemin
    e-postasi takimda BEKLEYEN uye olarak duruyorsa (user_id bos) kimlik
    kumesinde bulunmaz, fonksiyon "yukleyen mi" dalina duser, rapor yonetici
    tarafindan aktarildigi icin o da False doner ve sonuc "catisma yok"
    olurdu. Yani kisi KENDI TAKIMININ raporunu degerlendirebilirdi - tam
    olarak bu kontrolun engellemek icin var oldugu sey.

    Ustelik test yakalamazdi: mevcut testler uyelikleri `user_id` ile
    kuruyordu.
    """
    from app import models

    hakem_id = kullanici_ac("hakem@x.com", ["REFEREE"], "parola123")
    # Hakemin e-postasi takimda ama hesabi BAGLI DEGIL (dogrulanmamis)
    kisi = db_session.query(models.User).filter(models.User.id == hakem_id).first()
    kisi.email_verified = False
    db_session.commit()

    r = _yukle(client, yonetici, acik_yarisma, "hakem@x.com_arkadas@x.com.pdf")
    assert r.status_code == 201
    rapor = db_session.query(models.Report).filter(models.Report.id == r.json()["id"]).first()
    assert rapor.team.members[0].user_id is None, "test onkosulu bozuldu"

    hakem = db_session.query(models.User).filter(models.User.id == hakem_id).first()
    assert rapor.cikar_catismasi_var_mi(hakem) is True, (
        "hakem KENDI takiminin raporunu degerlendirebiliyor - kural sessizce acilmis"
    )


def test_ELLE_ATAMA_da_bekleyen_uyeyi_engelliyor(client, db_session, yonetici, acik_yarisma):
    """Otomatik dagitimda engelleyip elle atamada birakmak, kurali tek
    tiklamayla asilabilir hale getirirdi."""
    from app import models

    hakem_id = kullanici_ac("hakem2@x.com", ["REFEREE"], "parola123")
    r = _yukle(client, yonetici, acik_yarisma, "hakem2@x.com.pdf")
    rid = r.json()["id"]

    client.post(
        f"/api/assignments/competitions/{acik_yarisma}/referees",
        json={"referee_id": hakem_id},
        headers=yonetici,
    )
    atama = client.put(
        f"/api/assignments/{rid}", json={"referee_id": hakem_id}, headers=yonetici
    )
    assert atama.status_code == 400, f"cikar catismasi gecti (HTTP {atama.status_code})"
    assert "catisma" in atama.json()["detail"].lower()


# --- Kume tuzaklari ------------------------------------------------------

def test_bekleyen_uyeler_kimlik_kumesinde_COKUSMUYOR(client, db_session, yonetici, acik_yarisma):
    """`{m.user_id for m in members}` None'lari elemezse bes bekleyen uye TEK
    BIR None'a cokusur ve `len()` artik uye sayisi olmaz."""
    from app import models

    r = _yukle(client, yonetici, acik_yarisma, "a@x.com_b@x.com_c@x.com.pdf")
    rapor = db_session.query(models.Report).filter(models.Report.id == r.json()["id"]).first()
    assert len(rapor.team.members) == 3
    assert rapor.team.member_ids == set()
    assert len(rapor.team.member_emails) == 3


def test_iki_takimin_KESISIMI_bos_kaliyor(client, db_session, yonetici, acik_yarisma):
    """None'lar elenmezse iki takimin kesisimi `{None}` olur ve bos olmadigi
    icin "bu takimlar uye paylasiyor" yanlis pozitifi uretirdi."""
    from app import models

    a = _yukle(client, yonetici, acik_yarisma, "p@x.com.pdf")
    b = _yukle(client, yonetici, acik_yarisma, "q@y.com.pdf")
    ra = db_session.query(models.Report).filter(models.Report.id == a.json()["id"]).first()
    rb = db_session.query(models.Report).filter(models.Report.id == b.json()["id"]).first()
    assert ra.team.member_ids & rb.team.member_ids == set()


def test_ayni_adres_takima_IKI_KEZ_eklenmiyor(client, db_session, yonetici, acik_yarisma):
    """SQL'de `NULL = NULL` bilinmez, yani eski (team_id, user_id) kisiti
    bekleyen satirlar icin TAMAMEN devre disi kalirdi ve ayni adres ayni
    takima yuzlerce kez eklenebilirdi. Asil kisit artik (team_id, email)."""
    from app import models

    _yukle(client, yonetici, acik_yarisma, "tek@x.com_TEK@X.com.pdf")
    takim = db_session.query(models.Team).first()
    assert len(takim.members) == 1, [m.email for m in takim.members]


# --- Kurumlar arasi ------------------------------------------------------

def test_turetilen_takim_YABANCI_kuruma_gorunmuyor(client, db_session, yonetici, acik_yarisma):
    from app import models

    kullanici_ac("b.yonetici@cbu.edu.tr", ["COMPETITION_MANAGER"], "parola123", org="org-cbu")
    b = _giris(client, "b.yonetici@cbu.edu.tr")

    r = _yukle(client, yonetici, acik_yarisma, "gizli@t3.org.pdf")
    rid = r.json()["id"]
    assert client.get(f"/api/reports/{rid}", headers=b).status_code == 404


def test_ayni_eposta_kumesi_FARKLI_kurumda_AYRI_takim(
    client, db_session, yonetici, acik_yarisma
):
    """Takim anahtari kurum icinde benzersiz. Kurumlar arasi paylasilsaydi,
    bir kurumun yoneticisi digerinin takimina rapor ekleyebilirdi."""
    from app import models

    kullanici_ac("b.yonetici@cbu.edu.tr", ["COMPETITION_MANAGER"], "parola123", org="org-cbu")
    b = _giris(client, "b.yonetici@cbu.edu.tr")
    yar_b = client.post(
        "/api/competitions",
        json={"name": "B Yarışması", "category_label": "Vize"},
        headers=b,
    ).json()["id"]
    client.put(
        f"/api/competitions/{yar_b}/template",
        json={"required_headings": ["A"], "min_pages": 1, "max_pages": 9},
        headers=b,
    )
    client.put(
        f"/api/competitions/{yar_b}/criteria",
        json={"criteria": [{"title": "A", "weight": 100}]},
        headers=b,
    )
    client.put(f"/api/competitions/{yar_b}/status", json={"status": "open"}, headers=b)

    _yukle(client, yonetici, acik_yarisma, "ortak@x.com.pdf")
    _yukle(client, b, yar_b, "ortak@x.com.pdf")

    takimlar = db_session.query(models.Team).all()
    assert len(takimlar) == 2, [(t.id, t.organization_id) for t in takimlar]
    assert {t.organization_id for t in takimlar} == {"org-t3", "org-cbu"}
