#!/usr/bin/env python3
"""Ucdan uca sistem testi - CALISAN bir backend'e karsi.

Birim testleri modulleri tek tek dogruluyor; bu betik ise gercek HTTP
uzerinden, dort rolun tamamiyla, bir yarismanin bastan sona akisini
kosturuyor. Demo oncesi "sistem gercekten calisiyor mu" sorusunun cevabi.

Kullanim:
    scripts/dev-backend.sh start
    .venv/bin/python scripts/e2e-test.py
    scripts/dev-backend.sh stop

Ortam degiskeni:
    E2E_BASE_URL   varsayilan http://127.0.0.1:8000

Cikis kodu 0 ise her sey gecti. Betik veri tabanina yaziyor; temiz bir
sonuc icin once backend/sql_app.db silinip sunucu yeniden baslatilabilir.
"""

import io
import os
import sys
import time
import uuid
from pathlib import Path

try:
    import httpx
except ImportError:  # pragma: no cover
    print("httpx kurulu degil:  .venv/bin/pip install httpx")
    sys.exit(2)

KOK = Path(__file__).resolve().parent.parent
ORNEK_RAPORLAR = sorted(
    (KOK / "ai-doc-analysis/sample_reports/havacilikta_yz_ktr/reports").glob("*.pdf")
)
TEMEL = os.getenv("E2E_BASE_URL", "http://127.0.0.1:8000")

gecti = 0
kaldi = 0
_baslik_yazildi = set()


def bolum(ad):
    if ad not in _baslik_yazildi:
        print(f"\n--- {ad} ---")
        _baslik_yazildi.add(ad)


def kontrol(ad, kosul, ayrinti=""):
    global gecti, kaldi
    if kosul:
        gecti += 1
        print(f"  gecti  {ad}")
    else:
        kaldi += 1
        print(f"  KALDI  {ad}  {ayrinti}")


c = httpx.Client(base_url=TEMEL, timeout=180)
# Her kosuda benzersiz e-posta: betik ayni veri tabanina birden fazla kez
# calistirilabilsin ("bu e-posta zaten kayitli" hatasi almadan).
EK = uuid.uuid4().hex[:8]


def kaydol_giris(rol_listesi, etiket, acan_basliklar=None):
    """Hesap acar ve giris yapar.

    Kendi kendine kayit URUNDE KAPALI (bkz. routes/auth.py): raporun sonucunu
    takim uyeligi belirliyor ve uyelik e-postaya bagli; kayit acik olsaydi bir
    takim uyesinin e-postasini ilk kaydettiren kisi o takimin sonuclarini
    gorurdu. Bu yuzden hesaplari YONETICI aciyor ve sifreyi SISTEM uretiyor -
    T3'un mevcut pratigi de bu.

    Ilk yonetici seed'den geliyor (manager@teknofest.org); ondan sonraki tum
    hesaplar onun uzerinden aciliyor.
    """
    eposta = f"e2e_{etiket}_{EK}@test.org"
    r = c.post(
        "/api/auth/users",
        json={"email": eposta, "roles": rol_listesi},
        headers=acan_basliklar,
    )
    assert r.status_code == 201, f"hesap acilamadi: {r.text[:200]}"
    sifre = r.json()["temporary_password"]
    j = c.post("/api/auth/login", data={"username": eposta, "password": sifre}).json()
    tok = {"Authorization": f"Bearer {j['access_token']}"}
    return eposta, j, tok


def rol_sec(giris, rol):
    tok = {"Authorization": f"Bearer {giris['access_token']}"}
    y = c.post("/api/auth/select-role", json={"role": rol}, headers=tok).json()
    return {"Authorization": f"Bearer {y['access_token']}"}


def analiz_bekle(rapor_id, basliklar, saniye=150):
    t0 = time.time()
    while time.time() - t0 < saniye:
        d = c.get(f"/api/reports/{rapor_id}", headers=basliklar).json()
        if d.get("status") != "pending":
            return d
        time.sleep(1)
    return c.get(f"/api/reports/{rapor_id}", headers=basliklar).json()


def main():
    if not ORNEK_RAPORLAR:
        print("ornek PDF bulunamadi; ai-doc-analysis/sample_reports eksik.")
        return 2
    try:
        c.get("/docs")
    except Exception as exc:
        print(f"backend'e ulasilamadi ({TEMEL}): {exc}")
        print("once:  scripts/dev-backend.sh start")
        return 2

    # ---------------------------------------------------------------- roller
    bolum("Kimlik ve roller")
    # Ilk yonetici SEED'den geliyor - kendi kendine kayit kapali oldugu icin
    # bir yerden baslamak gerekiyor.
    yon_giris = c.post(
        "/api/auth/login",
        data={"username": "manager@teknofest.org", "password": "password123"},
    ).json()
    yonetici = {"Authorization": f"Bearer {yon_giris['access_token']}"}
    kontrol("yonetici girisi", yon_giris.get("active_role") == "COMPETITION_MANAGER")
    kontrol(
        "token KURUMU tasiyor",
        yon_giris.get("active_organization_id") == "org-t3",
        f"kurum={yon_giris.get('active_organization_id')}",
    )

    # KURUM SORUMLUSU: ayricalikli rolleri (yonetici, degerlendirme yoneticisi,
    # kurum sorumlusu) YALNIZCA o verebiliyor. Yarisma yoneticisi bunlari
    # dagitabilseydi, tek bir yonetici hesabi ele gecirildiginde saldirgan
    # kendine sinirsiz yonetici uretebilirdi - yetki yukari dogru
    # dagitilamaz.
    sorumlu_giris = c.post(
        "/api/auth/login",
        data={
            "username": "asdfghjkl@gmail.com",
            "password": "asdfghjkl",
            "scope": "org-t3:ORG_OWNER",
        },
    ).json()
    sorumlu = {"Authorization": f"Bearer {sorumlu_giris['access_token']}"}
    kontrol("kurum sorumlusu girisi", sorumlu_giris.get("active_role") == "ORG_OWNER")
    kontrol(
        "yonetici AYRICALIKLI rol veremiyor",
        c.post(
            "/api/auth/users",
            json={"email": f"yetki_{EK}@test.org", "roles": ["COMPETITION_MANAGER"]},
            headers=yonetici,
        ).status_code
        == 403,
    )
    kontrol(
        "kendi kendine kayit KAPALI",
        c.post(
            "/api/auth/register",
            json={"email": "davetsiz@test.org", "password": "p", "roles": ["REFEREE"]},
        ).status_code
        == 403,
    )

    # Yarismaci taraflari SEED'lenmis takim uyeleri.
    #
    # NEDEN kaydol_giris DEGIL: rapor artik bir TAKIMA ait ve takim
    # olusturma icin API ucu YOK (bilincli: gercek kayitlar TEKNOFEST'in
    # kendi sisteminde/KYS'de tutuluyor, biz o veriyi tuketiyoruz). Bu
    # yuzden E2E, demo edilecek seed verisinin ta kendisini kullaniyor:
    #   team-glieser -> competitor@ (kaptan) + competitor2@ (uye)
    #   team-adyu    -> competitor@ (uye)     <- ayni kisi IKI takimda
    #   team-zebot   -> rakip@                <- digerlerini GOREMEZ
    def _giris(eposta, sifre="password123"):
        j = c.post("/api/auth/login", data={"username": eposta, "password": sifre}).json()
        return {"Authorization": f"Bearer {j['access_token']}"}

    TAKIM = "team-glieser"
    yarismaci = _giris("competitor2@teknofest.org")   # yalnizca team-glieser
    takim_arkadasi = _giris("competitor@teknofest.org")  # glieser + adyu
    rakip = _giris("rakip@teknofest.org")             # team-zebot

    hakem1_eposta, h1_giris, _ = kaydol_giris(["REFEREE"], "hakem1", yonetici)
    hakem1 = rol_sec(h1_giris, "REFEREE")
    hakem2_eposta, h2_giris, _ = kaydol_giris(["REFEREE"], "hakem2", yonetici)
    hakem2 = rol_sec(h2_giris, "REFEREE")

    # Cok rollu hesap: rol secmeden hicbir sey goremez.
    _, cok_giris, cok_tok = kaydol_giris(
        ["COMPETITOR", "REFEREE", "COMPETITION_MANAGER", "EVALUATION_MANAGER"],
        "cok",
        sorumlu,  # ayricalikli roller yalnizca kurum sorumlusundan
    )
    kontrol("cok rollu hesapta otomatik rol atanmiyor", cok_giris.get("active_role") is None)
    kontrol(
        "rol secmeden rapor listelenemiyor",
        c.get("/api/reports", headers=cok_tok).status_code == 403,
    )

    # ------------------------------------------------------------- yarisma
    bolum("Yarisma kurulumu")
    kat_id = c.get("/api/categories", headers=yonetici).json()[0]["id"]
    yar_id = c.post(
        "/api/competitions",
        json={"name": f"E2E Yarismasi {EK}", "category_id": kat_id},
        headers=yonetici,
    ).json()["id"]

    r = c.put(f"/api/competitions/{yar_id}/status", json={"status": "open"}, headers=yonetici)
    kontrol("kriter/sablon tanimlanmadan basvuru acilamiyor", r.status_code == 400, r.text[:80])

    c.put(
        f"/api/competitions/{yar_id}/template",
        json={
            "required_headings": ["Özgünlük", "Kaynakça"],
            "accepted_languages": ["tr"],
            "min_pages": 1,
            "max_pages": 80,
        },
        headers=yonetici,
    )
    r = c.put(
        f"/api/competitions/{yar_id}/criteria",
        json={"criteria": [{"title": "A", "weight": 150}, {"title": "B", "weight": -50}]},
        headers=yonetici,
    )
    kontrol("negatif agirlik reddediliyor", r.status_code == 422, f"HTTP {r.status_code}")

    r = c.put(
        f"/api/competitions/{yar_id}/criteria",
        json={
            "criteria": [
                {"title": "Özgünlük", "weight": 70},
                {"title": "Kaynakça", "weight": 30},
            ]
        },
        headers=yonetici,
    )
    kontrol("gecerli kriterler kaydediliyor", r.status_code == 200, r.text[:80])

    r = c.put(f"/api/competitions/{yar_id}/status", json={"status": "open"}, headers=yonetici)
    kontrol("tanimlar tamamlaninca basvuru aciliyor", r.status_code == 200, r.text[:80])

    # ------------------------------------------------------------ yukleme
    bolum("Rapor aktarimi ve AI analizi")

    # Sartname AKIS 03'te yarismacinin YUKLEME ADIMI YOK; yukleme AKIS 01'de
    # yoneticide ("raporlari sisteme aktarir").
    with open(ORNEK_RAPORLAR[0], "rb") as f:
        yasak = c.post(
            "/api/reports/upload",
            data={"project_name": "Olmamali", "competition_id": yar_id, "team_id": TAKIM},
            files={"file": (ORNEK_RAPORLAR[0].name, f, "application/pdf")},
            headers=yarismaci,
        )
    kontrol(
        "YARISMACI rapor yukleyemiyor",
        yasak.status_code == 403,
        f"HTTP {yasak.status_code}",
    )

    with open(ORNEK_RAPORLAR[0], "rb") as f:
        yukleme = c.post(
            "/api/reports/upload",
            data={"project_name": "E2E Projesi", "competition_id": yar_id, "team_id": TAKIM},
            files={"file": (ORNEK_RAPORLAR[0].name, f, "application/pdf")},
            headers=yonetici,
        )
    kontrol("yonetici rapor aktarabiliyor", yukleme.status_code == 201, yukleme.text[:120])
    rapor_id = yukleme.json()["id"]
    kontrol("yukleme hemen 'pending' donuyor", yukleme.json()["status"] == "pending")

    detay = analiz_bekle(rapor_id, yonetici)
    kontrol("analiz tamamlandi", detay["status"] == "analyzed", detay["status"])
    analiz = detay.get("ai_analysis") or {}
    sonuclar = analiz.get("results", {})
    kontrol(
        "dort kontrolun hepsi uretildi",
        set(sonuclar) == {"languageTemplate", "contentHeading", "categoryMatch", "similarity"},
        str(list(sonuclar)),
    )
    gerekce = analiz.get("rationale", "")
    kontrol(
        "puan YARISMANIN kriterlerinden hesaplandi",
        "ağırlık 70" in gerekce and "Takım Şeması" not in gerekce,
        gerekce[:160],
    )
    kontrol(
        "gerekce nihai kararin hakemde oldugunu soyluyor",
        "hakemin" in gerekce,
        gerekce[-120:],
    )

    # ------------------------------------------------------------- atama
    bolum("Hakem atamasi")
    hakemler = c.get("/api/assignments/referees", headers=yonetici).json()
    h1_id = next(h["id"] for h in hakemler if h["email"] == hakem1_eposta)
    h2_id = next(h["id"] for h in hakemler if h["email"] == hakem2_eposta)

    r = c.put(f"/api/assignments/{rapor_id}", json={"referee_id": h1_id}, headers=yonetici)
    kontrol("gorevli olmayan hakeme atama reddediliyor", r.status_code == 400, r.text[:80])

    c.post(
        f"/api/assignments/competitions/{yar_id}/referees",
        json={"referee_id": h1_id},
        headers=yonetici,
    )
    r = c.put(f"/api/assignments/{rapor_id}", json={"referee_id": h1_id}, headers=yonetici)
    kontrol("gorevli hakeme atama yapiliyor", r.status_code == 200, r.text[:80])

    # ------------------------------------------------------------- yetki
    bolum("Yetki sinirlari")
    kontrol(
        "atanmamis hakem raporu goremiyor",
        c.get(f"/api/reports/{rapor_id}", headers=hakem2).status_code == 403,
    )
    kontrol(
        "atanmamis hakem dosyayi indiremiyor",
        c.get(f"/api/reports/{rapor_id}/file", headers=hakem2).status_code == 403,
    )
    kontrol(
        "atanmamis hakem karar veremiyor",
        c.post(
            f"/api/reports/{rapor_id}/decision",
            json={
                "outcome": "approve",
                "final_score": 95,
                "rationale": "Bana atanmayan rapora karar verme denemesi, yeterince uzun.",
            },
            headers=hakem2,
        ).status_code
        == 403,
    )
    kontrol(
        "atanmamis hakem listede gormuyor",
        all(x["id"] != rapor_id for x in c.get("/api/reports", headers=hakem2).json()),
    )
    kontrol(
        "atanan hakem raporu goruyor",
        c.get(f"/api/reports/{rapor_id}", headers=hakem1).status_code == 200,
    )
    kontrol(
        "atanan hakem DOSYAYI indirebiliyor",
        c.get(f"/api/reports/{rapor_id}/file", headers=hakem1).status_code == 200,
    )
    kontrol(
        "yarismaci kendi raporunu goruyor",
        c.get(f"/api/reports/{rapor_id}", headers=yarismaci).status_code == 200,
    )

    # ---------------------------------------------------------- takim
    bolum("Takim gorunurlugu")
    kontrol(
        "takim ARKADASI raporu goruyor (yukleyen o degil)",
        c.get(f"/api/reports/{rapor_id}", headers=takim_arkadasi).status_code == 200,
    )
    kontrol(
        "takim arkadasi DOSYAYI indirebiliyor",
        c.get(f"/api/reports/{rapor_id}/file", headers=takim_arkadasi).status_code == 200,
    )
    kontrol(
        "BASKA takimdan biri goremiyor",
        c.get(f"/api/reports/{rapor_id}", headers=rakip).status_code == 403,
    )
    kontrol(
        "baska takim listede de gormuyor",
        all(x["id"] != rapor_id for x in c.get("/api/reports", headers=rakip).json()),
    )
    kontrol(
        "rapor TAKIM ADIYLA donuyor",
        c.get(f"/api/reports/{rapor_id}", headers=yonetici).json().get("team_name") == "Glieser",
    )
    with open(ORNEK_RAPORLAR[2], "rb") as f:
        sahipsiz = c.post(
            "/api/reports/upload",
            data={"project_name": "Sahipsiz", "competition_id": yar_id},
            files={"file": (ORNEK_RAPORLAR[2].name, f, "application/pdf")},
            headers=yonetici,
        )
    kontrol(
        "yonetici TAKIMSIZ rapor aktaramiyor",
        sahipsiz.status_code == 400,
        f"HTTP {sahipsiz.status_code}",
    )
    kontrol(
        "takim arkadasi da yukleyemiyor (rol degil, akis geregi)",
        c.post(
            "/api/reports/upload",
            data={"project_name": "Olmamali", "competition_id": yar_id, "team_id": TAKIM},
            files={"file": ("x.pdf", io.BytesIO(b"%PDF-1.4 Mock"), "application/pdf")},
            headers=takim_arkadasi,
        ).status_code
        == 403,
    )

    # ------------------------------------------------------------- karar
    bolum("Hakem karari")
    taslak = c.post(f"/api/reports/{rapor_id}/rationale-draft", headers=hakem1)
    kontrol("AI gerekce taslagi uretiliyor", taslak.status_code == 200, taslak.text[:80])
    if taslak.status_code == 200:
        kontrol(
            "taslak AI tarafindan uretildigini yaziyor",
            "AI" in taslak.json().get("notice", "") + taslak.json().get("draft", ""),
        )

    for govde, ad in [
        ({"outcome": "SACMA", "final_score": 50, "rationale": "x" * 40}, "gecersiz outcome"),
        ({"outcome": "approve", "final_score": 500, "rationale": "x" * 40}, "arali disi puan"),
        ({"outcome": "approve", "final_score": 80, "rationale": "kisa"}, "cok kisa gerekce"),
    ]:
        kontrol(
            f"{ad} reddediliyor",
            c.post(f"/api/reports/{rapor_id}/decision", json=govde, headers=hakem1).status_code
            == 422,
        )

    r = c.post(
        f"/api/reports/{rapor_id}/decision",
        json={
            "outcome": "revise",
            "final_score": 72,
            "rationale": "Yontem bolumu yeterli ancak bulgular kismi genisletilmeli.",
            "rationale_ai_drafted": True,
            "rationale_edited_by_referee": True,
        },
        headers=hakem1,
    )
    kontrol("atanan hakem karar verebiliyor", r.status_code == 200, r.text[:120])
    kontrol(
        "rapor durumu karara gore guncellendi",
        c.get(f"/api/reports/{rapor_id}", headers=yonetici).json()["status"] == "revise",
    )
    kontrol(
        "ayni rapora ikinci karar verilemiyor",
        c.post(
            f"/api/reports/{rapor_id}/decision",
            json={
                "outcome": "approve",
                "final_score": 90,
                "rationale": "Ikinci karar denemesi, yeterince uzun bir gerekce metni.",
            },
            headers=hakem1,
        ).status_code
        == 400,
    )

    # --------------------------------------------------------- butunluk
    bolum("Veri butunlugu")
    kontrol(
        "karar verilmis raporun hakemi degistirilemiyor",
        c.put(f"/api/assignments/{rapor_id}", json={"referee_id": h2_id}, headers=yonetici).status_code
        == 400,
    )
    kontrol(
        "karar verilmis raporun atamasi silinemiyor",
        c.delete(f"/api/assignments/{rapor_id}", headers=yonetici).status_code == 400,
    )
    c.put(f"/api/competitions/{yar_id}/status", json={"status": "completed"}, headers=yonetici)
    kontrol(
        "sonuclar aciklandiktan sonra basvurular yeniden acilamiyor",
        c.put(
            f"/api/competitions/{yar_id}/status", json={"status": "open"}, headers=yonetici
        ).status_code
        == 400,
    )

    # Yarisma kapandiktan sonra YARISMACI yukleyememeli. (Yonetici,
    # test/duzeltme amaciyla her asamada yukleyebiliyor - bilincli istisna,
    # bkz. routes/reports.py upload_report.)
    # NOT: "kapali yarismaya yarismaci yukleyemez" kontrolu KALDIRILDI -
    # yarismaci artik HICBIR asamada yukleyemiyor, o yuzden asamaya bagli
    # bir kural kalmadi. Yoneticiye asama kisiti bilincli olarak YOK: gercek
    # akista raporlar basvuru kapandiktan SONRA toplu aktariliyor.
    with open(ORNEK_RAPORLAR[1], "rb") as f:
        kapali_aktarim = c.post(
            "/api/reports/upload",
            data={"project_name": "Kapali Asama", "competition_id": yar_id, "team_id": TAKIM},
            files={"file": (ORNEK_RAPORLAR[1].name, f, "application/pdf")},
            headers=yonetici,
        )
    kontrol(
        "yonetici KAPALI asamada da aktarabiliyor",
        kapali_aktarim.status_code == 201,
        f"HTTP {kapali_aktarim.status_code}",
    )

    # ------------------------------------------------------- yarismaci gorunumu
    bolum("Yarismaci gorunumu")
    y_detay = c.get(f"/api/reports/{rapor_id}", headers=yarismaci)
    kontrol("yarismaci sonucunu gorebiliyor", y_detay.status_code == 200)
    if y_detay.status_code == 200:
        kontrol(
            "yarismacinin gordugu karar hakemin verdigi karar",
            (y_detay.json().get("final_decision") or {}).get("final_score") == 72,
        )

    # ------------------------------------------------------------ intihal
    bolum("Intihal kontrolu")
    with open(ORNEK_RAPORLAR[0], "rb") as f:
        kopya = c.post(
            "/api/reports/upload",
            data={
                "project_name": "Kopya Proje",
                "competition_id": yar_id,
                # BASKA takim: ayni takimin raporlari karsilastirmadan
                # cikariliyor (bir takimin On Tasarim / Final Tasarim
                # raporlari ayni basvurunun iki asamasi, intihal degil).
                # Gercek intihal senaryosu iki FARKLI takim gerektiriyor.
                "team_id": "team-zebot",
            },
            files={"file": ("kopya.pdf", f, "application/pdf")},
            headers=yonetici,
        )
    if kopya.status_code == 201:
        kd = analiz_bekle(kopya.json()["id"], yonetici)
        benzerlik = (kd.get("ai_analysis") or {}).get("results", {}).get("similarity", {})
        kontrol(
            "birebir kopya yuksek benzerlik puani aliyor",
            benzerlik.get("score", 0) > 35,
            str(benzerlik.get("score")),
        )
    else:
        # Yarisma 'completed' asamasinda oldugu icin yukleme reddedilebilir -
        # bu da dogru davranis.
        kontrol(
            "kapali yarismaya yukleme reddediliyor",
            kopya.status_code == 400,
            kopya.text[:80],
        )

    # Ayni takim iki asama gonderirse INTIHAL SAYILMAMALI (sartname iki
    # raporu da zorunlu kiliyor).
    #
    # BASKA BIR BELGE kullaniyoruz (ORNEK_RAPORLAR[3]): yukarida "Kopya
    # Proje" testi ORNEK_RAPORLAR[0]'i team-zebot adina yukledi. Ayni belgeyi
    # burada tekrar kullansaydik, Glieser'in ikinci asamasi kendi raporuyla
    # DEGIL Zebot'un kopyasiyla eslesir ve test yanlis sebeple duserdi -
    # ustelik o eslesme dogru davranis olurdu.
    def _asama_yukle(ad, dosya):
        with open(dosya, "rb") as f:
            return c.post(
                "/api/reports/upload",
                data={"project_name": ad, "competition_id": yar_id, "team_id": TAKIM},
                files={"file": (f"{ad}.pdf", f, "application/pdf")},
                headers=yonetici,
            )

    ilk_asama = _asama_yukle("Glieser Birinci Asama", ORNEK_RAPORLAR[3])
    if ilk_asama.status_code == 201:
        analiz_bekle(ilk_asama.json()["id"], yonetici)
    kendi = _asama_yukle("Glieser Ikinci Asama", ORNEK_RAPORLAR[3])
    if kendi.status_code == 201:
        kd2 = analiz_bekle(kendi.json()["id"], yonetici)
        b2 = (kd2.get("ai_analysis") or {}).get("results", {}).get("similarity", {})
        kontrol(
            "takimin KENDI raporu intihal sayilmiyor",
            b2.get("score") == 0,
            str(b2.get("score")),
        )
        kontrol(
            "dislama bulgularda aciga cikariliyor",
            any("karşılaştırma dışı" in x for x in b2.get("findings", [])),
        )

    print(f"\n{'=' * 52}\n{gecti} gecti, {kaldi} kaldi")
    return 1 if kaldi else 0


if __name__ == "__main__":
    sys.exit(main())
