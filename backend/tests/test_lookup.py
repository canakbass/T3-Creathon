"""Rapor arama (lookup) ve dagitim havuzu secenekleri.

ARAMA NEDEN AYRI BIR UC NOKTA: hakem kendisine ATANMAMIS raporlari da
arayabilmeli ("bu basvuruya kim bakiyor?"). Ama bu bir GEVSETME - ayni
oturumda tam tersi bir acik kapatildi: atanmamis hakem baska bir
yarismacinin tam AI analizini okuyabiliyordu (bkz. test_authorization.py).

Gevsetmeyi savunulabilir kilan uc sey ve bu dosyanin bekcilik ettigi sey:
  1. Yanit KUNYE ile sinirli - ai_analysis / final_decision / dosya YOK.
  2. Arama TAM ESLESME - substring/joker/bos sorgu yok.
  3. Atanmamis erisimler iz birakiyor (ReportAccessLog).
"""

import io
import uuid

import pytest


def _kaydol_ve_giris(client, email, roller, sifre="password"):
    client.post(
        "/api/auth/register", json={"email": email, "password": sifre, "roles": roller}
    )
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
def sahne(client, db_session):
    from app import models

    yonetici = _kaydol_ve_giris(client, "y@t.org", ["COMPETITION_MANAGER"])
    atanan = _kaydol_ve_giris(client, "atanan@t.org", ["REFEREE"])
    yabanci = _kaydol_ve_giris(client, "yabanci@t.org", ["REFEREE"])
    yarismaci = _kaydol_ve_giris(client, "yarismaci@t.org", ["COMPETITOR"])

    kullanici = (
        db_session.query(models.User)
        .filter(models.User.email == "yarismaci@t.org")
        .first()
    )
    db_session.add(models.Team(id="tkm", name="Glieser", external_ref="KYS-1"))
    db_session.flush()
    db_session.add(
        models.TeamMember(
            id=str(uuid.uuid4()), team_id="tkm", user_id=kullanici.id, role="kaptan"
        )
    )
    db_session.commit()

    kat = client.post(
        "/api/categories",
        json={"name": "AI & Machine Learning", "description": "NN."},
        headers=yonetici,
    ).json()["id"]
    yar = client.post(
        "/api/competitions",
        json={"name": "Havacılıkta Yapay Zeka", "category_id": kat},
        headers=yonetici,
    ).json()["id"]
    client.put(
        f"/api/competitions/{yar}/template",
        json={"required_headings": ["Özgünlük"], "min_pages": 1, "max_pages": 80},
        headers=yonetici,
    )
    client.put(
        f"/api/competitions/{yar}/criteria",
        json={"criteria": [{"title": "Özgünlük", "weight": 100}]},
        headers=yonetici,
    )
    client.put(f"/api/competitions/{yar}/status", json={"status": "open"}, headers=yonetici)

    # Raporu YONETICI aktariyor (sartname AKIS 01) - yarismacinin yukleme
    # yetkisi yok.
    yukleme = client.post(
        "/api/reports/upload",
        data={"project_name": "Glieser KTR", "competition_id": yar, "team_id": "tkm"},
        files={"file": ("r.pdf", io.BytesIO(b"%PDF-1.4 Mock"), "application/pdf")},
        headers=yonetici,
    )
    assert yukleme.status_code == 201, yukleme.text[:200]
    rid = yukleme.json()["id"]

    hakemler = client.get("/api/assignments/referees", headers=yonetici).json()
    atanan_id = next(h["id"] for h in hakemler if h["email"] == "atanan@t.org")
    client.post(
        f"/api/assignments/competitions/{yar}/referees",
        json={"referee_id": atanan_id},
        headers=yonetici,
    )
    client.put(f"/api/assignments/{rid}", json={"referee_id": atanan_id}, headers=yonetici)

    return {
        "yonetici": yonetici,
        "atanan": atanan,
        "yabanci": yabanci,
        "yarismaci": yarismaci,
        "yar_id": yar,
        "rapor_id": rid,
    }


# --- Rota sirasi ----------------------------------------------------------

def test_lookup_report_id_rotasina_dusmuyor(client, sahne):
    """TUZAK: FastAPI rotalari TANIM SIRASINA gore esler.

    /lookup, @router.get("/{report_id}")'den SONRA tanimlansaydi istek
    get_report(report_id="lookup") olarak eslesir ve "Report not found" 404'u
    donerdi. Hata mesaji yetkilendirmeyi hic akla getirmez - sessiz ve uzun
    suren bir hata olurdu.
    """
    r = client.get(
        "/api/reports/lookup",
        params={"report_id": sahne["rapor_id"]},
        headers=sahne["yabanci"],
    )
    assert r.status_code != 404, "/lookup, /{report_id} olarak eslesti"
    assert r.status_code == 200, r.text[:200]


# --- Ne goruyor, ne gormuyor ----------------------------------------------

def test_atanmamis_hakem_yalnizca_kunye_goruyor(client, sahne):
    d = client.get(
        "/api/reports/lookup",
        params={"report_id": sahne["rapor_id"]},
        headers=sahne["yabanci"],
    ).json()[0]

    assert d["access"] == "metadata_only"
    # Aramanin asil cevabi: "bu rapora kim bakiyor?"
    assert d["assigned_referee_email"] == "atanan@t.org"
    assert d["team_name"] == "Glieser"
    assert d["competition_name"] == "Havacılıkta Yapay Zeka"

    # KAPATILAN ACIK GERI ACILMAMALI: degerlendirme icerigi SIZMAMALI.
    for sizinti in ("ai_analysis", "final_decision", "file_path", "submitted_by_id"):
        assert sizinti not in d, f"{sizinti} kunye yanitinda sizdi"


def test_arama_tam_detay_yetkisi_VERMIYOR(client, sahne):
    """Arama bir kapi acmiyor; yalnizca kimlik cozumluyor."""
    rid, yabanci = sahne["rapor_id"], sahne["yabanci"]
    client.get("/api/reports/lookup", params={"report_id": rid}, headers=yabanci)
    assert client.get(f"/api/reports/{rid}", headers=yabanci).status_code == 403
    assert client.get(f"/api/reports/{rid}/file", headers=yabanci).status_code == 403
    assert client.post(
        f"/api/reports/{rid}/rationale-draft", headers=yabanci
    ).status_code == 403


def test_atanmis_hakem_icin_access_assigned(client, sahne):
    d = client.get(
        "/api/reports/lookup",
        params={"report_id": sahne["rapor_id"]},
        headers=sahne["atanan"],
    ).json()[0]
    assert d["access"] == "assigned"


def test_onay_ret_ayrimi_sizmiyor(client, sahne):
    """Bir raporun ONAYLANIP onaylanmadigi, o rapora atanmamis bir hakemin
    bilmesi gereken bir sey degil - durum "degerlendirildi"ye coktürülüyor."""
    client.post(
        f"/api/reports/{sahne['rapor_id']}/decision",
        json={
            "outcome": "reject",
            "final_score": 20,
            "rationale": "Yetersiz bulundu, gerekce yeterince uzun bir metin.",
        },
        headers=sahne["atanan"],
    )
    d = client.get(
        "/api/reports/lookup",
        params={"report_id": sahne["rapor_id"]},
        headers=sahne["yabanci"],
    ).json()[0]
    assert d["evaluation_state"] == "degerlendirildi"
    assert "reject" not in str(d) and "rejected" not in str(d)


# --- Arama olcutleri ------------------------------------------------------

@pytest.mark.parametrize(
    "params, aciklama",
    [
        ({}, "bos sorgu"),
        ({"report_id": "x", "team_id": "y"}, "coklu olcut"),
    ],
)
def test_gecersiz_sorgu_reddediliyor(client, sahne, params, aciklama):
    """Bos sorgu = envanter tarama. Tam olarak BIR olcut zorunlu."""
    r = client.get("/api/reports/lookup", params=params, headers=sahne["yabanci"])
    assert r.status_code == 422, f"{aciklama} kabul edildi (HTTP {r.status_code})"


def test_takim_ve_eposta_ile_bulunuyor(client, sahne):
    for params in ({"team_id": "tkm"}, {"email": "yarismaci@t.org"}):
        r = client.get("/api/reports/lookup", params=params, headers=sahne["yabanci"])
        assert r.status_code == 200
        assert any(x["report_id"] == sahne["rapor_id"] for x in r.json()), params


def test_eposta_buyuk_kucuk_harf_duyarsiz(client, sahne):
    r = client.get(
        "/api/reports/lookup",
        params={"email": "YARISMACI@T.ORG"},
        headers=sahne["yabanci"],
    )
    assert r.status_code == 200 and len(r.json()) == 1


def test_olmayan_kayit_bos_donuyor(client, sahne):
    for params in ({"email": "yok@yok.org"}, {"team_id": "olmayan"}, {"report_id": "RPT-YOK"}):
        assert client.get(
            "/api/reports/lookup", params=params, headers=sahne["yabanci"]
        ).json() == [], params


# --- Yetki ----------------------------------------------------------------

def test_yarismaci_arama_yapamaz(client, sahne):
    """Kullanicinin istegi: "ayni aramayi basvuran YARISMACI HARIC her rol
    yapabilecek." Arayuzde dugmeyi gizlemek yeterli olmazdi."""
    r = client.get(
        "/api/reports/lookup",
        params={"report_id": sahne["rapor_id"]},
        headers=sahne["yarismaci"],
    )
    assert r.status_code == 403, f"yarismaci arama yapabildi (HTTP {r.status_code})"


def test_yonetici_arayabiliyor(client, sahne):
    r = client.get(
        "/api/reports/lookup",
        params={"team_id": "tkm"},
        headers=sahne["yonetici"],
    )
    assert r.status_code == 200
    assert r.json()[0]["access"] == "assigned"


# --- Denetim izi ----------------------------------------------------------

def test_atanmamis_erisim_iz_birakiyor(client, db_session, sahne):
    """Iz birakmayan bir gevsetme, kapattigimiz acigin kucuk bir kopyasi olurdu."""
    from app import models

    onceki = db_session.query(models.ReportAccessLog).count()
    client.get(
        "/api/reports/lookup",
        params={"report_id": sahne["rapor_id"]},
        headers=sahne["yabanci"],
    )
    kayitlar = db_session.query(models.ReportAccessLog).all()
    assert len(kayitlar) == onceki + 1, "atanmamis erisim loglanmadi"
    assert kayitlar[-1].lookup_by == "report_id"


def test_atanmis_erisim_loglanmiyor(client, db_session, sahne):
    """Atanmis hakemin kendi raporunu okumasi normal is akisi. Loglanirsa
    kayit gurultuye boğulur ve icinden gercek anormallik secilemez."""
    from app import models

    onceki = db_session.query(models.ReportAccessLog).count()
    client.get(
        "/api/reports/lookup",
        params={"report_id": sahne["rapor_id"]},
        headers=sahne["atanan"],
    )
    assert db_session.query(models.ReportAccessLog).count() == onceki


# --- Dagitim havuzu secenekleri ------------------------------------------

def _hakem_ekle(client, sahne, eposta):
    _kaydol_ve_giris(client, eposta, ["REFEREE"])
    hakemler = client.get("/api/assignments/referees", headers=sahne["yonetici"]).json()
    hid = next(h["id"] for h in hakemler if h["email"] == eposta)
    client.post(
        f"/api/assignments/competitions/{sahne['yar_id']}/referees",
        json={"referee_id": hid},
        headers=sahne["yonetici"],
    )
    return hid


def _rapor_ekle(client, sahne, ad):
    r = client.post(
        "/api/reports/upload",
        data={"project_name": ad, "competition_id": sahne["yar_id"], "team_id": "tkm"},
        files={"file": (f"{ad}.pdf", io.BytesIO(b"%PDF-1.4 Mock"), "application/pdf")},
        headers=sahne["yonetici"],
    )
    assert r.status_code == 201, r.text[:200]
    return r.json()["id"]


def test_havuz_elle_secilebiliyor(client, sahne):
    """Kullanicinin istegi: "HANGILERININ eklenecegini de belirleyebilsin"."""
    a = _hakem_ekle(client, sahne, "h_a@t.org")
    _hakem_ekle(client, sahne, "h_b@t.org")
    for i in range(4):
        _rapor_ekle(client, sahne, f"R{i}")

    d = client.post(
        f"/api/assignments/competitions/{sahne['yar_id']}/auto-assign",
        json={"referee_ids": [a]},
        headers=sahne["yonetici"],
    ).json()
    assert d["assigned"] == 4, d
    assert {x["referee_id"] for x in d["assignments"]} == {a}


def test_havuza_gorevli_olmayan_hakem_secilemez(client, sahne):
    r = client.post(
        f"/api/assignments/competitions/{sahne['yar_id']}/auto-assign",
        json={"referee_ids": ["olmayan-id"]},
        headers=sahne["yonetici"],
    )
    assert r.status_code == 400
    assert "gorevli degil" in r.json()["detail"]


def test_en_az_yuklu_n_hakem(client, sahne):
    """Kullanicinin istegi: "rastgele EN AZ PROJEDEN SORUMLU olan hakeme
    direkt ekleyebilsin" + "KAC HAKEM eklenecegini belirleyebilsin"."""
    _hakem_ekle(client, sahne, "h_c@t.org")
    _hakem_ekle(client, sahne, "h_d@t.org")
    for i in range(3):
        _rapor_ekle(client, sahne, f"S{i}")

    d = client.post(
        f"/api/assignments/competitions/{sahne['yar_id']}/auto-assign",
        json={"limit_least_loaded": 1},
        headers=sahne["yonetici"],
    ).json()
    assert d["assigned"] == 3, d
    assert len({x["referee_email"] for x in d["assignments"]}) == 1


def test_parametresiz_cagri_eski_davranisi_koruyor(client, sahne):
    """Kilit fazla siki olmamali: govdesiz cagri calismali ve yuku
    DENGELI dagitmali."""
    _hakem_ekle(client, sahne, "h_e@t.org")
    _hakem_ekle(client, sahne, "h_f@t.org")
    for i in range(4):
        _rapor_ekle(client, sahne, f"T{i}")

    d = client.post(
        f"/api/assignments/competitions/{sahne['yar_id']}/auto-assign",
        headers=sahne["yonetici"],
    ).json()
    assert d["assigned"] == 4, d
    yukler = [x["assigned_count"] for x in d["load"]]
    assert max(yukler) - min(yukler) <= 1, f"yuk dengesiz: {yukler}"


# --- Liste filtreleri -----------------------------------------------------

def test_filtreler_yetkinin_USTUNE_biniyor(client, sahne):
    """KRITIK: filtre daraltir, GENISLETMEZ.

    Hakem `competition_id` vererek kendisine ATANMAMIS raporlari
    goremez - _erisim_filtresi her halukarda uygulaniyor. Filtreyi yetki
    kontrolunun yerine gecirmek, bu oturumda kapatilan acigin (atanmamis
    hakem her raporu goruyordu) yeni bir kapisi olurdu.
    """
    yabanci = sahne["yabanci"]  # hicbir rapora atanmamis hakem
    for q in (
        {},
        {"competition_id": sahne["yar_id"]},
        {"undecided": "true"},
        {"active_only": "true"},
        {"category_label": "Lise"},
    ):
        r = client.get("/api/reports", params=q, headers=yabanci)
        assert r.status_code == 200, (q, r.text[:200])
        assert r.json() == [], f"filtre yetkiyi gevsetti: {q}"


def test_undecided_karar_verilmisleri_eliyor(client, sahne):
    yonetici, rid = sahne["yonetici"], sahne["rapor_id"]
    once = client.get("/api/reports", params={"undecided": "true"}, headers=yonetici).json()
    assert any(x["id"] == rid for x in once)

    client.post(
        f"/api/reports/{rid}/decision",
        json={
            "outcome": "approve",
            "final_score": 88,
            "rationale": "Rapor beklenen duzeyi karsiliyor, gerekce yeterince uzun.",
        },
        headers=sahne["atanan"],
    )
    sonra = client.get("/api/reports", params={"undecided": "true"}, headers=yonetici).json()
    assert all(x["id"] != rid for x in sonra), "karar verilmis rapor hala 'degerlendirilmemis'te"


def test_competition_ve_kategori_filtresi(client, sahne):
    yonetici = sahne["yonetici"]
    kendi = client.get(
        "/api/reports", params={"competition_id": sahne["yar_id"]}, headers=yonetici
    ).json()
    assert any(x["id"] == sahne["rapor_id"] for x in kendi)

    baskasi = client.get(
        "/api/reports", params={"competition_id": "OLMAYAN"}, headers=yonetici
    ).json()
    assert baskasi == []

    # Bu yarismanin kategori etiketi yok -> etikete gore filtre bos donmeli
    assert client.get(
        "/api/reports", params={"category_label": "Lise"}, headers=yonetici
    ).json() == []
