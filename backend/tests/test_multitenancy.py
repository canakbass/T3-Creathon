"""Kurumlar arasi yalitim (multi-tenancy) testleri.

NEDEN AYRI BIR DOSYA: kismi cok-kurumluluk, HIC YOKTAN daha tehlikelidir.
Kurum alani eklenip TEK BIR filtre unutulursa sessiz bir sizinti olusur ve
kimse fark etmez - cunku hicbir mevcut test iki kurumlu bir dunya
kurmuyordu. Bu dosyanin tek isi o dunyayi kurup her kapiyi denemek.

Kullanicinin tespitleri (hepsi hakli, hepsi burada sinaniyor):
  A) "a kurumundaki kisi b kurumundaki dosyalari goruntuleyememeli"
  B) "ayni maile bagliysam ne olacak" -> ayni kisi farkli kurumlarda farkli
     rollere sahip olabilmeli
  C) "rastgele hakem hesabi actim herkesin verisini okuyabilir hale
     geliyorum"
"""

import io
import uuid

import pytest


def _kullanici_kur(db_session, eposta, org_id, rol, sifre="parola123"):
    """Kurum uyeligiyle birlikte kullanici olusturur.

    Dogrudan veri tabanina yaziyoruz: BASKA BIR KURUMA kullanici acacak bir
    API ucu YOK ve olmamali - olsaydi "baska kuruma kullanici acma" ucu olur,
    yani kurum sinirini asan bir kapi.
    """
    from app import auth as A
    from app import models

    kullanici = models.User(
        id=str(uuid.uuid4()), email=eposta, password_hash=A.hash_password(sifre)
    )
    db_session.add(kullanici)
    db_session.flush()
    db_session.add(
        models.UserRole(
            id=str(uuid.uuid4()), user_id=kullanici.id, organization_id=org_id, role=rol
        )
    )
    db_session.commit()
    return kullanici


def _giris(client, eposta, sifre="parola123"):
    j = client.post(
        "/api/auth/login", data={"username": eposta, "password": sifre}
    ).json()
    return {"Authorization": f"Bearer {j['access_token']}"}, j


@pytest.fixture
def iki_kurum(client, db_session):
    """A kurumunda bir rapor; B kurumunda bir yonetici, bir hakem, bir takim."""
    from app import models

    # --- A kurumu (org-t3) ---
    _kullanici_kur(db_session, "a.yonetici@t3.org", "org-t3", "COMPETITION_MANAGER")
    _kullanici_kur(db_session, "a.yarismaci@t3.org", "org-t3", "COMPETITOR")
    a_yonetici, _ = _giris(client, "a.yonetici@t3.org")

    db_session.add(
        models.Team(id="takim-a", name="A Takımı", organization_id="org-t3")
    )
    db_session.flush()
    db_session.add(
        models.TeamMember(
            id=str(uuid.uuid4()),
            team_id="takim-a",
            user_id=db_session.query(models.User)
            .filter(models.User.email == "a.yarismaci@t3.org")
            .first()
            .id,
            role="kaptan",
        )
    )
    db_session.commit()

    # --- B kurumu (org-cbu) ---
    _kullanici_kur(db_session, "b.yonetici@cbu.edu.tr", "org-cbu", "COMPETITION_MANAGER")
    _kullanici_kur(db_session, "b.hakem@cbu.edu.tr", "org-cbu", "REFEREE")
    _kullanici_kur(db_session, "b.yarismaci@cbu.edu.tr", "org-cbu", "COMPETITOR")
    b_yonetici, _ = _giris(client, "b.yonetici@cbu.edu.tr")
    b_hakem, _ = _giris(client, "b.hakem@cbu.edu.tr")
    b_yarismaci, _ = _giris(client, "b.yarismaci@cbu.edu.tr")

    db_session.add(
        models.Team(id="takim-b", name="B Takımı", organization_id="org-cbu")
    )
    db_session.commit()

    # --- A kurumunda bir yarisma + rapor ---
    kat = client.post(
        "/api/categories",
        json={"name": "AI & Machine Learning", "description": "NN."},
        headers=a_yonetici,
    ).json()["id"]
    yar = client.post(
        "/api/competitions",
        json={"name": "A Kurumu Yarışması", "category_label": "Lise", "category_id": kat},
        headers=a_yonetici,
    ).json()["id"]
    client.put(
        f"/api/competitions/{yar}/template",
        json={"required_headings": ["Özgünlük"], "min_pages": 1, "max_pages": 80},
        headers=a_yonetici,
    )
    client.put(
        f"/api/competitions/{yar}/criteria",
        json={"criteria": [{"title": "Özgünlük", "weight": 100}]},
        headers=a_yonetici,
    )
    client.put(f"/api/competitions/{yar}/status", json={"status": "open"}, headers=a_yonetici)

    yukleme = client.post(
        "/api/reports/upload",
        data={
            "project_name": "A Kurumu Gizli Proje",
            "competition_id": yar,
            "team_id": "takim-a",
        },
        files={"file": ("a.pdf", io.BytesIO(b"%PDF-1.4 Mock"), "application/pdf")},
        headers=a_yonetici,
    )
    assert yukleme.status_code == 201, yukleme.text[:200]

    # Her kurumun bir sorumlusu: uye yonetimini yalnizca o yapabiliyor.
    _kullanici_kur(db_session, "a.sorumlu@t3.org", "org-t3", "ORG_OWNER")
    _kullanici_kur(db_session, "b.sorumlu@cbu.edu.tr", "org-cbu", "ORG_OWNER")
    a_sorumlu, _ = _giris(client, "a.sorumlu@t3.org")
    b_sorumlu, _ = _giris(client, "b.sorumlu@cbu.edu.tr")

    return {
        "a_yonetici": a_yonetici,
        "a_sorumlu": a_sorumlu,
        "b_yonetici": b_yonetici,
        "b_sorumlu": b_sorumlu,
        "b_hakem": b_hakem,
        "b_yarismaci": b_yarismaci,
        "yar_id": yar,
        "rapor_id": yukleme.json()["id"],
    }


# --- A maddesi: baska kurumun verisi gorunmemeli --------------------------

@pytest.mark.parametrize("rol", ["b_hakem", "b_yonetici", "b_yarismaci"])
def test_baska_kurum_raporu_goremiyor(client, iki_kurum, rol):
    rid = iki_kurum["rapor_id"]
    basliklar = iki_kurum[rol]
    assert client.get(f"/api/reports/{rid}", headers=basliklar).status_code == 404
    assert client.get(f"/api/reports/{rid}/file", headers=basliklar).status_code == 404
    assert all(x["id"] != rid for x in client.get("/api/reports", headers=basliklar).json())


def test_yabanci_kurumda_404_VE_AYNI_GOVDE(client, iki_kurum):
    """Uc uc nokta da BIREBIR ayni cevabi vermeli.

    Kurum ICINDE 403 dogru tercih: kimlikler tahmin edilebilir, net mesaj
    hakeme yardim eder. Kurum SINIRINDA ise 403 "bu kimlik baska bir kurumda
    VAR" bilgisini ONAYLAR - varlik kahini (oracle) olur. Uc noktalardan
    biri 403 digeri 404 dondururse, saldirgan ikisini karsilastirarak baska
    kurumun rapor kimliklerini dogrular.

    Onceden get_report_file ve rationale_draft kendi sorgularini yapiyordu ve
    403 donuyordu; ucu de artik ayni kapidan geciyor.
    """
    rid, b = iki_kurum["rapor_id"], iki_kurum["b_hakem"]
    yanitlar = [
        client.get(f"/api/reports/{rid}", headers=b),
        client.get(f"/api/reports/{rid}/file", headers=b),
        client.post(f"/api/reports/{rid}/rationale-draft", headers=b),
    ]
    for r in yanitlar:
        assert r.status_code == 404, f"{r.request.url} -> {r.status_code}"
    govdeler = {r.json().get("detail") for r in yanitlar}
    assert len(govdeler) == 1, f"uc nokta FARKLI mesaj donduruyor: {govdeler}"


def test_arama_yabanci_kurumu_BOS_liste_donduruyor(client, iki_kurum):
    """Arama bir LISTE ucu; sozlesmesi zaten "eslesme yoksa 200 + []".

    403 "bu kayit var ama senin degil" demektir; e-posta anahtariyla
    birlesince "bu kisinin sistemde basvurusu var mi" kahinine donusur -
    baska bir kurumun katilimci listesini sizdirmak demektir.
    """
    b = iki_kurum["b_hakem"]
    for params in (
        {"report_id": iki_kurum["rapor_id"]},
        {"team_id": "takim-a"},
        {"email": "a.yarismaci@t3.org"},
    ):
        r = client.get("/api/reports/lookup", params=params, headers=b)
        assert r.status_code == 200, (params, r.text[:200])
        assert r.json() == [], f"yabanci kurum aramada gorundu: {params}"


def test_reanalyze_yabanci_kurumda_404(client, iki_kurum):
    """Bu uc nokta hem OKUYOR (yanitla takim adi + atanan hakem) hem YIKICI
    YAZIYOR (AiAnalysis kaydini siliyor). Kapiya bagli olmasaydi tek istekte
    baska kurumun analizini silip verisini okumak mumkun olurdu."""
    r = client.post(
        f"/api/reports/{iki_kurum['rapor_id']}/reanalyze", headers=iki_kurum["b_yonetici"]
    )
    assert r.status_code == 404, f"HTTP {r.status_code}"


# --- Kilit fazla siki olmamali -------------------------------------------

def test_kendi_kurumu_HALA_calisiyor(client, iki_kurum):
    """Fazla siki bir kilit, acik kadar kotudur."""
    rid, a = iki_kurum["rapor_id"], iki_kurum["a_yonetici"]
    assert client.get(f"/api/reports/{rid}", headers=a).status_code == 200
    assert client.get(f"/api/reports/{rid}/file", headers=a).status_code == 200
    assert any(x["id"] == rid for x in client.get("/api/reports", headers=a).json())
    assert len(
        client.get("/api/reports/lookup", params={"report_id": rid}, headers=a).json()
    ) == 1


# --- B maddesi: ayni kisi iki kurumda ------------------------------------

def test_ayni_kisi_iki_kurumda_farkli_rol(client, db_session, iki_kurum):
    """"ben hem TEKNOFEST yarismasi icin hem de odev sonucu kontrolu icin
    ayni maile bagliysam? o zaman ne olacak?"

    Cevap: ayni hesap, A kurumunda hakem, B kurumunda yarismaci olabilir ve
    her kurumda YALNIZCA o kurumdaki rolunun yetkisine sahiptir.
    """
    from app import models

    kisi = _kullanici_kur(db_session, "cift@her-yerde.org", "org-t3", "REFEREE")
    db_session.add(
        models.UserRole(
            id=str(uuid.uuid4()),
            user_id=kisi.id,
            organization_id="org-cbu",
            role="COMPETITOR",
        )
    )
    db_session.commit()

    _, giris = _giris(client, "cift@her-yerde.org")
    # Iki secenek var -> otomatik secim YAPILMAMALI
    assert giris["active_role"] is None
    assert giris["active_organization_id"] is None
    assert {u["organization_id"] for u in giris["memberships"]} == {"org-t3", "org-cbu"}

    tok = {"Authorization": f"Bearer {giris['access_token']}"}
    # A kurumunda hakem olarak
    r = client.post(
        "/api/auth/select-role",
        json={"role": "REFEREE", "organization_id": "org-t3"},
        headers=tok,
    )
    assert r.status_code == 200, r.text[:200]
    assert r.json()["active_organization_id"] == "org-t3"

    # AYNI rolu B kurumunda isterse REDDEDILMELI - A'daki hakemligi B'de
    # hicbir sey ifade etmiyor.
    r = client.post(
        "/api/auth/select-role",
        json={"role": "REFEREE", "organization_id": "org-cbu"},
        headers=tok,
    )
    assert r.status_code == 403, f"A kurumundaki rol B kurumunda gecerli sayildi ({r.status_code})"


def test_birden_fazla_kurumda_ayni_rol_varsa_SECIM_zorunlu(client, db_session, iki_kurum):
    """Yanlis kurumda islem yapmak, baska bir kurumun verisine dokunmak
    demek - belirsizlikte tahmin etmiyoruz."""
    from app import models

    kisi = _kullanici_kur(db_session, "iki.hakem@her-yerde.org", "org-t3", "REFEREE")
    db_session.add(
        models.UserRole(
            id=str(uuid.uuid4()),
            user_id=kisi.id,
            organization_id="org-cbu",
            role="REFEREE",
        )
    )
    db_session.commit()

    _, giris = _giris(client, "iki.hakem@her-yerde.org")
    tok = {"Authorization": f"Bearer {giris['access_token']}"}
    r = client.post("/api/auth/select-role", json={"role": "REFEREE"}, headers=tok)
    assert r.status_code == 400, f"kurum secmeden gecti (HTTP {r.status_code})"
    assert "organization_id" in r.json()["detail"]


def test_kurumdan_cikarilinca_eski_token_gecersiz(client, db_session, iki_kurum):
    """Kullanici kurumdan cikarildiginda elindeki token o yetkiyi kullanmaya
    DEVAM EDEMEMELI. Roldeki mevcut korumanin kurum karsiligi."""
    from app import models

    kisi = _kullanici_kur(db_session, "gidici@t3.org", "org-t3", "REFEREE")
    tok, _ = _giris(client, "gidici@t3.org")
    assert client.get("/api/reports", headers=tok).status_code == 200

    db_session.query(models.UserRole).filter(
        models.UserRole.user_id == kisi.id
    ).delete()
    db_session.commit()

    r = client.get("/api/reports", headers=tok)
    assert r.status_code == 403, f"uyelik silindi ama token calisiyor (HTTP {r.status_code})"


# --- Benzerlik havuzu kurumlar arasi olmamali ----------------------------

def test_benzerlik_havuzu_kurumla_sinirli(client, db_session, iki_kurum):
    """Iki sebep: (1) GIZLILIK - bulgu metni karsilastirilan raporun kimligini
    tasiyor, kurumlar arasi havuz bir kurumun basvuru kimliklerini digerine
    sizdirir. (2) DOGRULUK - esikler tek bir yarismanin 34 gercek raporunda
    kalibre edildi; baska kurumlarin farkli sablonlu belgeleri havuza
    karisinca hakeme gosterilen referans cumlesi yalan olur.
    """
    from app import models

    a_rapor = (
        db_session.query(models.Report)
        .filter(models.Report.id == iki_kurum["rapor_id"])
        .first()
    )
    assert a_rapor.organization_id == "org-t3", "rapor kuruma baglanmadi"

    # B kurumunda AYNI icerikle bir rapor
    yar_b = client.post(
        "/api/competitions",
        json={"name": "B Kurumu Yarışması", "category_label": "Vize"},
        headers=iki_kurum["b_yonetici"],
    ).json()["id"]
    client.put(
        f"/api/competitions/{yar_b}/template",
        json={"required_headings": ["Özgünlük"], "min_pages": 1, "max_pages": 80},
        headers=iki_kurum["b_yonetici"],
    )
    client.put(
        f"/api/competitions/{yar_b}/criteria",
        json={"criteria": [{"title": "Özgünlük", "weight": 100}]},
        headers=iki_kurum["b_yonetici"],
    )
    client.put(
        f"/api/competitions/{yar_b}/status",
        json={"status": "open"},
        headers=iki_kurum["b_yonetici"],
    )
    r = client.post(
        "/api/reports/upload",
        data={"project_name": "B Raporu", "competition_id": yar_b, "team_id": "takim-b"},
        files={"file": ("b.pdf", io.BytesIO(b"%PDF-1.4 Mock"), "application/pdf")},
        headers=iki_kurum["b_yonetici"],
    )
    assert r.status_code == 201, r.text[:200]

    b_rapor = (
        db_session.query(models.Report).filter(models.Report.id == r.json()["id"]).first()
    )
    assert b_rapor.organization_id == "org-cbu"

    # B'nin analizinde A'nin rapor kimligi GECMEMELI
    detay = client.get(
        f"/api/reports/{r.json()['id']}", headers=iki_kurum["b_yonetici"]
    ).json()
    bulgular = detay["ai_analysis"]["results"]["similarity"]["findings"]
    assert not any(
        iki_kurum["rapor_id"] in x for x in bulgular
    ), f"baska kurumun rapor kimligi bulgulara sizdi: {bulgular}"


# --- Yarisma: yabanci kurumun kurallarini DEGISTIREMEZ ------------------

def test_baska_kurumun_yarismasini_goremiyor(client, iki_kurum):
    y, b = iki_kurum["yar_id"], iki_kurum["b_yonetici"]
    assert client.get(f"/api/competitions/{y}", headers=b).status_code == 404
    assert all(x["id"] != y for x in client.get("/api/competitions", headers=b).json())


def test_baska_kurumun_yarismasini_DEGISTIREMIYOR(client, iki_kurum):
    """En agir bulgu buydu: olculdu, uc istekte de HTTP 200 donuyordu.

    Baska kurumun yoneticisi sablonu, kriterleri ve asamayi
    degistirebiliyordu. Kriter agirliklarini degistirmek o yarismanin
    puanlama rubrigini degistirmek demek - yani baska bir kurumun
    degerlendirme sonuclarini disaridan bozmak.
    """
    y, b = iki_kurum["yar_id"], iki_kurum["b_yonetici"]
    saldirilar = [
        client.put(
            f"/api/competitions/{y}/template",
            json={"required_headings": ["Ele Gecirildi"], "min_pages": 1, "max_pages": 5},
            headers=b,
        ),
        client.put(
            f"/api/competitions/{y}/criteria",
            json={"criteria": [{"title": "Ele Gecirildi", "weight": 100}]},
            headers=b,
        ),
        client.put(f"/api/competitions/{y}/status", json={"status": "completed"}, headers=b),
    ]
    for r in saldirilar:
        assert r.status_code == 404, f"{r.request.url} -> {r.status_code}"

    # Ve gercekten DEGISMEMIS olmali - 404 donup yine de yazan bir uc nokta
    # en kotusu olurdu.
    kalan = client.get(f"/api/competitions/{y}", headers=iki_kurum["a_yonetici"]).json()
    assert kalan["required_headings"] == ["Özgünlük"]
    assert [k["title"] for k in kalan["criteria"]] == ["Özgünlük"]
    assert kalan["status"] == "open"


def test_yeni_yarisma_OLUSTURANIN_kurumuna_baglaniyor(client, iki_kurum):
    """"yonetici olarak yarisma baslattim ama kimin yarismasi bu tam
    olarak??" - cevabi artik yanitta duruyor."""
    r = client.post(
        "/api/competitions",
        json={"name": "B'nin Yarışması", "category_label": "Vize"},
        headers=iki_kurum["b_yonetici"],
    )
    assert r.status_code == 201, r.text[:200]
    assert r.json()["organization_id"] == "org-cbu"
    # A kurumu bunu gormemeli
    assert all(
        x["id"] != r.json()["id"]
        for x in client.get("/api/competitions", headers=iki_kurum["a_yonetici"]).json()
    )


# --- Hakem atama: kurumlar arasi atama yapilamaz -------------------------

def test_hakem_listesi_yalnizca_KENDI_kurumunu_gosteriyor(client, iki_kurum):
    """Bu liste ad-soyad ve E-POSTA donduruyor; kapsamsiz hali, herhangi bir
    kurumun yoneticisine tum sistemin hakem rehberini verirdi."""
    epostalar = {
        h["email"] for h in client.get("/api/assignments/referees", headers=iki_kurum["b_yonetici"]).json()
    }
    assert "b.hakem@cbu.edu.tr" in epostalar
    assert not any(e.endswith("@t3.org") for e in epostalar), epostalar


def test_yabanci_kurumun_hakemi_yarismaya_EKLENEMIYOR(client, db_session, iki_kurum):
    """Onceden "hakem" demek "HERHANGI bir kurumda hakem" demekti; bir
    kurumun raporu baska kurumun hakemine atanabiliyordu."""
    from app import models

    b_hakem_id = (
        db_session.query(models.User)
        .filter(models.User.email == "b.hakem@cbu.edu.tr")
        .first()
        .id
    )
    r = client.post(
        f"/api/assignments/competitions/{iki_kurum['yar_id']}/referees",
        json={"referee_id": b_hakem_id},
        headers=iki_kurum["a_yonetici"],
    )
    assert r.status_code == 400, f"yabanci kurumun hakemi eklendi (HTTP {r.status_code})"


def test_yabanci_kurumun_yarismasina_hakem_EKLENEMIYOR(client, db_session, iki_kurum):
    from app import models

    b_hakem_id = (
        db_session.query(models.User)
        .filter(models.User.email == "b.hakem@cbu.edu.tr")
        .first()
        .id
    )
    r = client.post(
        f"/api/assignments/competitions/{iki_kurum['yar_id']}/referees",
        json={"referee_id": b_hakem_id},
        headers=iki_kurum["b_yonetici"],
    )
    assert r.status_code == 404, f"HTTP {r.status_code}"
    r = client.post(
        f"/api/assignments/competitions/{iki_kurum['yar_id']}/auto-assign",
        headers=iki_kurum["b_yonetici"],
    )
    assert r.status_code == 404, f"HTTP {r.status_code}"


def test_yabanci_kurumun_raporunun_hakemi_DEGISTIRILEMIYOR(client, db_session, iki_kurum):
    from app import models

    b_hakem_id = (
        db_session.query(models.User)
        .filter(models.User.email == "b.hakem@cbu.edu.tr")
        .first()
        .id
    )
    rid = iki_kurum["rapor_id"]
    r = client.put(
        f"/api/assignments/{rid}",
        json={"referee_id": b_hakem_id},
        headers=iki_kurum["b_yonetici"],
    )
    assert r.status_code == 404, f"HTTP {r.status_code}"
    # Atama silme de ayni kapidan gecmeli - PUT kapali DELETE acik olsaydi
    # saldirgan raporu atamasiz birakip sureci durdurabilirdi.
    assert (
        client.delete(f"/api/assignments/{rid}", headers=iki_kurum["b_yonetici"]).status_code
        == 404
    )


# --- Gosterge ve kategori ------------------------------------------------

def test_gosterge_sayaci_yabanci_raporu_SAYMIYOR(client, iki_kurum):
    """Sayilar zararsiz gorunuyor ama kac basvuru alindigi kuruma ait bir
    bilgi; ustelik sayacin artisi baska kurumun hareketini ele verir."""
    b = client.get("/api/dashboard/stats", headers=iki_kurum["b_yonetici"]).json()
    assert b["total_reports"] == 0, b
    a = client.get("/api/dashboard/stats", headers=iki_kurum["a_yonetici"]).json()
    assert a["total_reports"] == 1, a


def test_kategori_listesi_kurumla_sinirli(client, iki_kurum):
    adlar = {
        k["name"] for k in client.get("/api/categories", headers=iki_kurum["b_yonetici"]).json()
    }
    assert "AI & Machine Learning" not in adlar, adlar


# --- C maddesi: "rastgele hakem hesabi actim herkesin verisini okuyorum" --

def test_acilan_hesap_ACANIN_kurumuna_dusuyor(client, db_session, iki_kurum):
    """Onceden hesap her zaman VARSAYILAN kuruma (org-t3) aciliyordu.

    Yani B kurumunun yoneticisi A kurumuna hakem hesabi aciyordu ve o hesap
    A kurumunun butun raporlarini okuyabiliyordu. Kullanicinin tarif ettigi
    durumun birebir kendisi.
    """
    from app import models

    r = client.post(
        "/api/auth/users",
        json={"email": "yeni.hakem@cbu.edu.tr", "roles": ["REFEREE"]},
        headers=iki_kurum["b_yonetici"],
    )
    assert r.status_code == 201, r.text[:200]

    kullanici = (
        db_session.query(models.User)
        .filter(models.User.email == "yeni.hakem@cbu.edu.tr")
        .first()
    )
    assert kullanici.roles_in("org-cbu") == ["REFEREE"]
    assert kullanici.roles_in("org-t3") == [], "hesap YABANCI kuruma dustu"

    # Ve o hesapla A kurumunun raporu gorunmuyor
    tok, _ = _giris(client, "yeni.hakem@cbu.edu.tr", r.json()["temporary_password"])
    assert (
        client.get(f"/api/reports/{iki_kurum['rapor_id']}", headers=tok).status_code == 404
    )


def test_yonetici_YONETICI_uretemiyor(client, iki_kurum):
    """Yetki YUKARI DOGRU dagitilamaz.

    Onceden her yarisma yoneticisi sinirsiz yonetici uretebiliyordu; tek bir
    yonetici hesabi ele gecirildiginde saldirgan kendine kalici yetki
    basabilir, hatta kurumu tamamen ele gecirebilirdi.
    """
    for rol in ("COMPETITION_MANAGER", "EVALUATION_MANAGER", "ORG_OWNER"):
        r = client.post(
            "/api/auth/users",
            json={"email": f"sahte.{rol.lower()}@cbu.edu.tr", "roles": [rol]},
            headers=iki_kurum["b_yonetici"],
        )
        assert r.status_code == 403, f"{rol} uretildi (HTTP {r.status_code})"
        assert "ORG_OWNER" in r.json()["detail"]


def test_kurum_sorumlusu_yonetici_urretebiliyor(client, iki_kurum):
    """Kilit fazla siki olmamali: sorumlu ekibini kurabilmeli."""
    r = client.post(
        "/api/auth/users",
        json={"email": "yeni.yonetici@cbu.edu.tr", "roles": ["COMPETITION_MANAGER"]},
        headers=iki_kurum["b_sorumlu"],
    )
    assert r.status_code == 201, r.text[:200]
    assert r.json()["roles"] == ["COMPETITION_MANAGER"]


def test_yabanci_kurumun_takimina_uye_EKLENEMIYOR(client, iki_kurum):
    """Eklenen kisi o takimin BUTUN basvuru sonuclarini gorurdu."""
    r = client.post(
        "/api/auth/users",
        json={"email": "sizinti@cbu.edu.tr", "roles": ["COMPETITOR"], "team_id": "takim-a"},
        headers=iki_kurum["b_yonetici"],
    )
    assert r.status_code == 404, f"yabanci takima uye eklendi (HTTP {r.status_code})"


def test_ayni_eposta_ikinci_kurumda_sifresi_DEGISMIYOR(client, db_session, iki_kurum):
    """"hem TEKNOFEST yarismasi icin hem de odev kontrolu icin ayni maile
    bagliysam?" - cevap: ayni hesap, yeni kurumda yeni uyelik.

    Yeni hesap acilsa iki ayri sifre olurdu (ayni e-posta iki kayit).
    Mevcut sifre DEGISTIRILSE, bir kurumun yoneticisi o kisinin baska
    kurumdaki oturumunu dusurebilirdi - kurumlar arasi bir saldiri.
    """
    from app import models

    onceki = (
        db_session.query(models.User)
        .filter(models.User.email == "a.yarismaci@t3.org")
        .first()
        .password_hash
    )

    r = client.post(
        "/api/auth/users",
        json={"email": "a.yarismaci@t3.org", "roles": ["COMPETITOR"]},
        headers=iki_kurum["b_yonetici"],
    )
    assert r.status_code == 201, r.text[:200]
    assert r.json()["temporary_password"] is None
    assert r.json()["roles"] == ["COMPETITOR"]  # YALNIZCA bu kurumdaki roller

    db_session.expire_all()
    kullanici = (
        db_session.query(models.User)
        .filter(models.User.email == "a.yarismaci@t3.org")
        .first()
    )
    assert kullanici.password_hash == onceki, "baska kurumun sifresi degistirildi"
    assert set(kullanici.roles_in("org-t3")) == {"COMPETITOR"}
    assert set(kullanici.roles_in("org-cbu")) == {"COMPETITOR"}

    # Kendi kurumunda ikinci kez eklenirse hata
    r = client.post(
        "/api/auth/users",
        json={"email": "a.yarismaci@t3.org", "roles": ["COMPETITOR"]},
        headers=iki_kurum["b_yonetici"],
    )
    assert r.status_code == 400


# --- Kurum sorumlusu: kendi kurumu, YALNIZCA kendi kurumu ---------------

def test_uye_listesi_yalnizca_KENDI_kurumu(client, iki_kurum):
    r = client.get("/api/organizations/me/members", headers=iki_kurum["b_sorumlu"])
    assert r.status_code == 200, r.text[:200]
    # Yanit artik SAYFALANMIS: {items, total, limit, offset}
    epostalar = {u["email"] for u in r.json()["items"]}
    assert "b.hakem@cbu.edu.tr" in epostalar
    assert not any(e.endswith("@t3.org") for e in epostalar), epostalar


def test_uye_listesi_yoneticiye_KAPALI(client, iki_kurum):
    """Bu liste kurumun tum e-posta rehberi; yonetici hesabi ele geciren biri
    once rehberi indirir, sonra hedefli saldiriya gecerdi."""
    assert (
        client.get("/api/organizations/me/members", headers=iki_kurum["b_yonetici"]).status_code
        == 403
    )


def test_sorumlu_YABANCI_kurumun_uyesine_rol_veremiyor(client, db_session, iki_kurum):
    """Kurumun uyesi olmayan "yok"tur: ayri bir mesaj donseydi sorumlu
    rastgele kimlikler deneyerek sistemdeki tum hesaplari sayabilirdi."""
    from app import models

    a_hakem_id = (
        db_session.query(models.User)
        .filter(models.User.email == "a.yarismaci@t3.org")
        .first()
        .id
    )
    r = client.post(
        f"/api/organizations/me/members/{a_hakem_id}/roles",
        json={"role": "COMPETITION_MANAGER"},
        headers=iki_kurum["b_sorumlu"],
    )
    assert r.status_code == 404, f"HTTP {r.status_code}"
    # Ve gercekten verilmemis olmali
    db_session.expire_all()
    kullanici = db_session.query(models.User).filter(models.User.id == a_hakem_id).first()
    assert kullanici.roles_in("org-t3") == ["COMPETITOR"]
    assert kullanici.roles_in("org-cbu") == []


def test_sorumlu_kendi_kurumunda_rol_verip_alabiliyor(client, db_session, iki_kurum):
    from app import models

    hakem_id = (
        db_session.query(models.User)
        .filter(models.User.email == "b.hakem@cbu.edu.tr")
        .first()
        .id
    )
    r = client.post(
        f"/api/organizations/me/members/{hakem_id}/roles",
        json={"role": "COMPETITION_MANAGER"},
        headers=iki_kurum["b_sorumlu"],
    )
    assert r.status_code == 201, r.text[:200]
    assert set(r.json()["roles"]) == {"REFEREE", "COMPETITION_MANAGER"}

    r = client.delete(
        f"/api/organizations/me/members/{hakem_id}/roles/COMPETITION_MANAGER",
        headers=iki_kurum["b_sorumlu"],
    )
    assert r.status_code == 200, r.text[:200]
    assert r.json()["roles"] == ["REFEREE"]


def test_kurumun_SON_sorumlusu_kaldirilamiyor(client, db_session, iki_kurum):
    """Kurum sorumlusuz kalirsa uye yonetimi kilitlenir ve kurtarmanin API
    yolu yoktur - veri tabanina elle girmek gerekir. Tek bir yanlis
    tiklamayla ulasilabilecek bir durum olmamali."""
    from app import models

    sorumlu_id = (
        db_session.query(models.User)
        .filter(models.User.email == "b.sorumlu@cbu.edu.tr")
        .first()
        .id
    )
    r = client.delete(
        f"/api/organizations/me/members/{sorumlu_id}/roles/ORG_OWNER",
        headers=iki_kurum["b_sorumlu"],
    )
    assert r.status_code == 400, f"kurum sorumlusuz kaldi (HTTP {r.status_code})"
    assert "son sorumlusu" in r.json()["detail"].lower()


def test_sorumlu_kendi_kurumunda_HER_ROLE_bakabiliyor(client, iki_kurum):
    """"bu superuserlar her role bakabilmeli."

    Taviz DEGIL: sorumlu o rolu kendine zaten verebiliyor, engellemek
    yalnizca iki fazladan tiklama saglardi. Onemli olan, secilen rolle
    yapilan isteklerin GERCEKTEN calismasi - token dogrulamasi bunu
    reddederse secim ekrani calisir gorunup sistem kullanilamaz olurdu.
    """
    tok = iki_kurum["b_sorumlu"]
    r = client.post(
        "/api/auth/select-role",
        json={"role": "COMPETITION_MANAGER", "organization_id": "org-cbu"},
        headers=tok,
    )
    assert r.status_code == 200, r.text[:200]
    yonetici_tok = {"Authorization": f"Bearer {r.json()['access_token']}"}
    # Yonetici rolu gerektiren bir uc nokta gercekten calisiyor mu
    assert client.get("/api/dashboard/stats", headers=yonetici_tok).status_code == 200


def test_sorumlu_BASKA_kurumda_rol_secemiyor(client, iki_kurum):
    """Sinir aynen duruyor: "superuser" sifati kurum sinirini asmanin
    anahtari degil."""
    r = client.post(
        "/api/auth/select-role",
        json={"role": "COMPETITION_MANAGER", "organization_id": "org-t3"},
        headers=iki_kurum["b_sorumlu"],
    )
    assert r.status_code == 403, f"HTTP {r.status_code}"


def test_kurum_bilgisi_her_role_acik(client, iki_kurum):
    """Kullanici hangi kurum adina islem yaptigini her an gormeli - yanlis
    kurumda islem yapmak baska bir kurumun verisine dokunmak demek."""
    for rol in ("b_hakem", "b_yarismaci", "b_yonetici", "b_sorumlu"):
        r = client.get("/api/organizations/me", headers=iki_kurum[rol])
        assert r.status_code == 200, (rol, r.text[:200])
        assert r.json()["id"] == "org-cbu"
        assert r.json()["name"]


def test_rol_kapisi_kurum_kapisindan_ONCE_ama_KAHIN_DEGIL(client, iki_kurum):
    """/rationale-draft yalnizca hakeme acik ve ROL kapisi KURUM kapisindan
    once calisiyor: yonetici ile denenirse kurum kapisina hic ulasilmiyor.

    BU BIR SIZINTI DEGIL ve bu test onu KILITLIYOR: rol reddi, raporun var
    olup olmadigi hakkinda hicbir sey soylememeli. Kendi kurumundaki rapor,
    yabanci kurumun raporu ve hic olmayan bir kimlik icin CEVAP AYNI olmali.
    Biri digerinden ayrilirsa, rol kapisi farkinda olmadan bir varlik kahini
    haline gelir.
    """
    yonetici = iki_kurum["b_yonetici"]

    # B kurumunun KENDI raporu
    yar_b = client.post(
        "/api/competitions",
        json={"name": "B Yarışması", "category_label": "Vize"},
        headers=yonetici,
    ).json()["id"]
    client.put(
        f"/api/competitions/{yar_b}/template",
        json={"required_headings": ["Özgünlük"], "min_pages": 1, "max_pages": 80},
        headers=yonetici,
    )
    client.put(
        f"/api/competitions/{yar_b}/criteria",
        json={"criteria": [{"title": "Özgünlük", "weight": 100}]},
        headers=yonetici,
    )
    client.put(f"/api/competitions/{yar_b}/status", json={"status": "open"}, headers=yonetici)
    kendi = client.post(
        "/api/reports/upload",
        data={"project_name": "B Raporu", "competition_id": yar_b, "team_id": "takim-b"},
        files={"file": ("b.pdf", io.BytesIO(b"%PDF-1.4 Mock"), "application/pdf")},
        headers=yonetici,
    )
    assert kendi.status_code == 201, kendi.text[:200]

    hedefler = {
        "kendi kurumu": kendi.json()["id"],
        "yabanci kurum": iki_kurum["rapor_id"],
        "hic olmayan": "RPT-0000-XXXXXX",
    }
    yanitlar = {
        ad: client.post(f"/api/reports/{rid}/rationale-draft", headers=yonetici)
        for ad, rid in hedefler.items()
    }
    durumlar = {ad: r.status_code for ad, r in yanitlar.items()}
    govdeler = {r.json().get("detail") for r in yanitlar.values()}
    assert set(durumlar.values()) == {403}, durumlar
    assert len(govdeler) == 1, f"rol reddi raporun varligini sizdiriyor: {govdeler}"


# --- Yazma yolu: en agir acik buradaydi ---------------------------------

def test_yabanci_kurumun_TAKIMINA_rapor_ENJEKTE_edilemiyor(client, db_session, iki_kurum):
    """Olculdu: CBU yoneticisi `team_id=team-glieser` gonderip T3 kurumuna
    rapor ENJEKTE etti (HTTP 201), rapor T3'un listesinde gorundu ve yanit
    T3'un takim adini geri verdi.

    Okuma yolu bastan sona kapatilmisti; YAZMA yolu atlanmisti. Tek guvence
    "yonetici misin"di - "BURADA yonetici misin" degil. Uc ayri sonucu vardi:
      (a) yabanci kurumun degerlendirme kuyruguna belge sokmak - o kurumun
          kendi hakemlerine atanir,
      (b) yabanci kurumun INTIHAL HAVUZUNA girmek: bir belgenin kopyasini
          yukleyip o kurumun gercek basvurularini intihalci gostermek,
      (c) 201/404 farkiyla yabanci takim kimliklerini saymak.
    """
    from app import models

    r = client.post(
        "/api/reports/upload",
        data={
            "project_name": "ENJEKTE",
            "competition_id": iki_kurum["yar_id"],
            "team_id": "takim-a",
        },
        files={"file": ("x.pdf", io.BytesIO(b"%PDF-1.4 Mock"), "application/pdf")},
        headers=iki_kurum["b_yonetici"],
    )
    assert r.status_code == 404, f"yabanci kuruma rapor enjekte edildi (HTTP {r.status_code})"
    assert (
        db_session.query(models.Report)
        .filter(models.Report.project_name == "ENJEKTE")
        .count()
        == 0
    ), "istek reddedildi ama kayit yine de olustu"


def test_yabanci_TAKIM_ile_var_olmayan_takim_AYIRT_EDILEMIYOR(client, iki_kurum):
    """Ayirt edilebilseydi yonetici rastgele kimlik deneyerek baska
    kurumlarin takim listesini cikarabilirdi (olculdu: var olmayan takim
    404, A kurumunun takimi 201 + takim ADI)."""
    yanitlar = []
    for tid in ("takim-yok-boyle", "takim-a"):
        yanitlar.append(
            client.post(
                "/api/reports/upload",
                data={
                    "project_name": "SONDA",
                    "competition_id": iki_kurum["yar_id"],
                    "team_id": tid,
                },
                files={"file": ("x.pdf", io.BytesIO(b"%PDF-1.4 Mock"), "application/pdf")},
                headers=iki_kurum["b_yonetici"],
            )
        )
    assert {r.status_code for r in yanitlar} == {404}, [r.status_code for r in yanitlar]
    assert len({r.json().get("detail") for r in yanitlar}) == 1, [
        r.json().get("detail") for r in yanitlar
    ]


def test_yabanci_YARISMAYA_rapor_eklenemiyor(client, iki_kurum):
    """Kendi takimiyla ama BASKA kurumun yarismasina yuklemek de kapali.

    Bu, okuma sizintisindan once bir BOZMA araci: yabanci yarismanin rapor
    sayisini artirmak, o yarismanin kriterlerini kilitliyor
    (_kural_degisimini_dogrula "zaten analiz edilmis rapor var" diyip 409
    donuyor). Kurum kendi kriterini degistiremez hale geliyordu.
    """
    r = client.post(
        "/api/reports/upload",
        data={
            "project_name": "KILITLE",
            "competition_id": iki_kurum["yar_id"],
            "team_id": "takim-b",
        },
        files={"file": ("x.pdf", io.BytesIO(b"%PDF-1.4 Mock"), "application/pdf")},
        headers=iki_kurum["b_yonetici"],
    )
    assert r.status_code == 404, f"HTTP {r.status_code}"


# --- Kurumsuz token: secim yapmamak DAHA COK yetki veriyordu -------------

def test_KURUMSUZ_token_hicbir_sey_goremiyor(client, iki_kurum):
    """Olculdu: org iddiasi tasimayan imzali bir token butun raporlari,
    baska kurumun yarismasini ve ozel kategorilerini goruyordu.

    Sebep: her kurum filtresi "kullanicinin kurumu yoksa filtreleme" diye
    kisa devre yapiyordu. Yani KURUM SECMEMEK, kurum secmekten DAHA COK
    yetki veriyordu - `_rol_yoksa_reddet`in rol icin kapattigi hatanin
    kurum karsiligi.
    """
    from app import auth as A

    sahte = A.create_access_token(
        data={"sub": "b.yonetici@cbu.edu.tr", "role": "COMPETITION_MANAGER", "org": None}
    )
    kurumsuz = {"Authorization": f"Bearer {sahte}"}
    for yol in ("/api/reports", "/api/competitions", "/api/categories", "/api/dashboard/stats"):
        r = client.get(yol, headers=kurumsuz)
        assert r.status_code == 403, f"{yol} -> HTTP {r.status_code} {r.text[:120]}"
    assert (
        client.get(f"/api/reports/{iki_kurum['rapor_id']}", headers=kurumsuz).status_code
        == 403
    )


def test_rol_SECMEMIS_token_da_veri_goremiyor(client, db_session, iki_kurum):
    """Rol secilmemis token gecerli kalmali (secim ekrani gosterilirken elde
    duruyor) ama HICBIR veri ucundan gecmemeli."""
    from app import models

    kisi = _kullanici_kur(db_session, "cok.rollu@cbu.edu.tr", "org-cbu", "REFEREE")
    db_session.add(
        models.UserRole(
            id=str(uuid.uuid4()),
            user_id=kisi.id,
            organization_id="org-cbu",
            role="COMPETITOR",
        )
    )
    db_session.commit()

    _, giris = _giris(client, "cok.rollu@cbu.edu.tr")
    assert giris["active_role"] is None
    tok = {"Authorization": f"Bearer {giris['access_token']}"}
    # /me ve /select-role calismali
    assert client.get("/api/auth/me", headers=tok).status_code == 200
    # Veri uclari kapali
    for yol in ("/api/reports", "/api/competitions", "/api/categories"):
        assert client.get(yol, headers=tok).status_code == 403, yol


# --- Kendi kendine kayit ayricalikli rol veremez -------------------------

@pytest.mark.parametrize(
    "rol", ["ORG_OWNER", "COMPETITION_MANAGER", "EVALUATION_MANAGER", "REFEREE", "COMPETITOR"]
)
def test_kendi_kaydi_HICBIR_ROL_vermiyor(client, db_session, rol):
    """Kara liste degil BEYAZ LISTE - aslinda hic liste yok, rol YOK.

    Once yalnizca AYRICALIKLI_ROLLER engelleniyordu ve bu YETMIYORDU:
    `REFEREE` o listede degil, yani kendine hakem rolu veren biri
    /api/reports/lookup ile kurumun BUTUN basvuru kunyelerini okuyabilirdi.
    Ustelik kara liste, ROLLER'a yeni bir rol eklendiginde SESSIZCE acilir.

    Rol artik yalnizca iki yolla geliyor: kurum sorumlusu verir, ya da
    DOGRULANMIS e-posta bir bekleyen takim uyeligiyle eslesir.
    """
    from app import models

    eposta = f"tirmanan.{rol.lower()}@test.org"
    r = client.post(
        "/api/auth/register",
        json={"email": eposta, "password": "parola1234", "roles": [rol]},
    )
    assert r.status_code == 202, r.text[:200]

    kullanici = (
        db_session.query(models.User).filter(models.User.email == eposta).first()
    )
    assert kullanici.role_list == [], f"{rol} kendi kendine alindi"
    assert kullanici.roles_in("org-t3") == []


def test_kendi_kaydi_HICBIR_KURUMA_yazmiyor(client, db_session):
    """Onceden varsayilan kuruma yaziliyordu, yani "kayit formu = T3 Vakfi
    uyeligi" demekti - kendi kendine kayit, kurum sinirini asmanin yeni bir
    yolu olurdu."""
    from app import models

    client.post(
        "/api/auth/register",
        json={"email": "kurumsuz@test.org", "password": "parola1234"},
    )
    kullanici = (
        db_session.query(models.User).filter(models.User.email == "kurumsuz@test.org").first()
    )
    assert db_session.query(models.UserRole).filter(
        models.UserRole.user_id == kullanici.id
    ).count() == 0


# --- Mevcut hesabin GERCEK ADI sizmiyor ---------------------------------

def test_mevcut_hesabin_GERCEK_ADI_sizmiyor(client, db_session, iki_kurum):
    """Onceden yanit `mevcut.full_name` donuyordu: cagirinin hic vermedigi,
    BASKA BIR KURUMUN kaydindan okunan bir bilgi. Yani herhangi bir kurumun
    yoneticisi rastgele bir e-posta deneyip o kisinin gercek adini
    ogrenebiliyordu (olculdu: "TAHMIN" gonderildi, "Demo Yarismaci" dondu).
    """
    from app import models

    kisi = (
        db_session.query(models.User)
        .filter(models.User.email == "a.yarismaci@t3.org")
        .first()
    )
    kisi.full_name = "Gizli Gercek Ad"
    db_session.commit()

    r = client.post(
        "/api/auth/users",
        json={"email": "a.yarismaci@t3.org", "full_name": "TAHMIN", "roles": ["COMPETITOR"]},
        headers=iki_kurum["b_yonetici"],
    )
    assert r.status_code == 201, r.text[:200]
    assert r.json()["full_name"] != "Gizli Gercek Ad", "baska kurumun kaydindaki ad sizdi"


# --- Arama jokerleri --------------------------------------------------

def test_arama_JOKER_kabul_etmiyor(client, iki_kurum):
    """Ucun savunmasi "arama TAM ESLESME, joker yok" iddiasina dayaniyor.

    `ilike` LIKE'in `%` ve `_` jokerlerini yorumluyordu; `?email=%` tek bir
    istekle rastgele bir kullaniciyi getiriyordu. Kurum filtresi yine de
    tutuyordu - ama iki savunmadan birinin calismadigini bilmeden digerine
    guvenmis oluyorduk.
    """
    for desen in ("%", "%@t3.org", "_.yarismaci@t3.org"):
        r = client.get(
            "/api/reports/lookup", params={"email": desen}, headers=iki_kurum["a_yonetici"]
        )
        assert r.status_code == 200, (desen, r.text[:120])
        assert r.json() == [], f"joker {desen!r} eslesti: {r.json()}"

    # TAM eslesme hala calismali (buyuk/kucuk harf duyarsiz)
    r = client.get(
        "/api/reports/lookup",
        params={"email": "A.Yarismaci@T3.ORG"},
        headers=iki_kurum["a_yonetici"],
    )
    assert len(r.json()) == 1, r.json()
