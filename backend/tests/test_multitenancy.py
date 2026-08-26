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

    return {
        "a_yonetici": a_yonetici,
        "b_yonetici": b_yonetici,
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
