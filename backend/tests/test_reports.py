import io
import os
from pathlib import Path

import pytest

# Gercek bir TEKNOFEST finalist raporu - AI modullerinin sahte "%PDF-1.4
# Mock" baytlari yerine gercek metin uzerinde calistigini dogrulamak icin.
GERCEK_RAPOR = (
    Path(__file__).resolve().parents[2]
    / "ai-doc-analysis" / "sample_reports" / "havacilikta_yz_ktr" / "reports"
    / "KTR_00_YXpGnt7IevOLKmM75xNlXyQlgHmz2bTM.pdf"
)


def _kaydol_ve_giris(client, email, rol):
    client.post(
        "/api/auth/register", json={"email": email, "password": "password", "role": rol}
    )
    r = client.post(
        "/api/auth/login", data={"username": email, "password": "password"}
    )
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def test_report_lifecycle(client):
    # 1. Register users (competitor & referee)
    client.post(
        "/api/auth/register",
        json={"email": "comp@test.org", "password": "password", "role": "COMPETITOR"}
    )
    client.post(
        "/api/auth/register",
        json={"email": "ref@test.org", "password": "password", "role": "REFEREE"}
    )
    client.post(
        "/api/auth/register",
        json={"email": "manager@test.org", "password": "password", "role": "COMPETITION_MANAGER"}
    )

    # Login competitor
    comp_login = client.post("/api/auth/login", data={"username": "comp@test.org", "password": "password"})
    comp_token = comp_login.json()["access_token"]

    # Login referee
    ref_login = client.post("/api/auth/login", data={"username": "ref@test.org", "password": "password"})
    ref_token = ref_login.json()["access_token"]

    # Login manager
    manager_login = client.post("/api/auth/login", data={"username": "manager@test.org", "password": "password"})
    manager_token = manager_login.json()["access_token"]

    # 2. Seed a category
    cat_res = client.post(
        "/api/categories",
        json={"name": "Robotics & Automation", "description": "Drone systems"},
        headers={"Authorization": f"Bearer {manager_token}"}
    )
    assert cat_res.status_code == 201
    cat_id = cat_res.json()["id"]

    # Seed a criterion template for the category
    crit_res = client.post(
        "/api/criteria",
        json={"category_id": cat_id, "title": "Template Compliance", "description": "Form check", "max_score": 100},
        headers={"Authorization": f"Bearer {manager_token}"}
    )
    assert crit_res.status_code == 201

    # 3. Upload a report
    file_data = io.BytesIO(b"%PDF-1.4 Mock PDF Content")
    upload_res = client.post(
        "/api/reports/upload",
        data={"project_name": "Autonomous Drone V1", "category_id": cat_id},
        files={"file": ("drone_report.pdf", file_data, "application/pdf")},
        headers={"Authorization": f"Bearer {comp_token}"}
    )
    
    assert upload_res.status_code == 201
    report_data = upload_res.json()
    report_id = report_data["id"]
    assert report_data["project_name"] == "Autonomous Drone V1"
    
    # The HTTP response of the upload endpoint returns immediately with "pending"
    assert report_data["status"] == "pending"

    # 4. Get report details as referee
    detail_res = client.get(
        f"/api/reports/{report_id}",
        headers={"Authorization": f"Bearer {ref_token}"}
    )
    assert detail_res.status_code == 200
    detail_data = detail_res.json()
    assert detail_data["status"] == "analyzed"
    assert detail_data["ai_analysis"] is not None
    assert detail_data["ai_analysis"]["suggested_outcome"] in ["approve", "reject", "revise"]
    assert "languageTemplate" in detail_data["ai_analysis"]["results"]
    
    # 5. Submit referee decision
    decision_res = client.post(
        f"/api/reports/{report_id}/decision",
        json={"outcome": "approve", "final_score": 90, "rationale": "Excellent methodology and clear results."},
        headers={"Authorization": f"Bearer {ref_token}"}
    )
    assert decision_res.status_code == 200
    decision_data = decision_res.json()
    assert decision_data["outcome"] == "approve"
    assert decision_data["final_score"] == 90

    # Verify report status is now "approved"
    status_check_res = client.get(
        f"/api/reports/{report_id}",
        headers={"Authorization": f"Bearer {ref_token}"}
    )
    assert status_check_res.json()["status"] == "approved"


def test_report_list_serializes_analysis(client):
    """REGRESYON: GET /api/reports, analiz edilmis rapor varsa HTTP 500 veriyordu.

    schemas.AiAnalysisResponse `results` alanini zorunlu tutuyor ama bu bir
    veri tabani kolonu degil - yanit oncesi duz kolonlardan uretilmesi
    gerekiyor. Bu donusum yalnizca get_report'ta yapiliyordu, list_reports'ta
    yapilmiyordu; sonuc olarak veri tabaninda analiz edilmis ILK rapor
    olusur olmaz liste endpoint'i ResponseValidationError ile duşuyordu
    ("Field required: ai_analysis.results").

    Bu, hakem panosunun ana listesini kullanilamaz kiliyordu. Onceki testler
    yakalamamisti cunku analiz SONRASI liste endpoint'ini hic cagirmiyorlardi -
    bu testin varlik sebebi tam olarak o bosluk.
    """
    manager = _kaydol_ve_giris(client, "liste_manager@test.org", "COMPETITION_MANAGER")
    referee = _kaydol_ve_giris(client, "liste_referee@test.org", "REFEREE")

    cat = client.post(
        "/api/categories",
        json={"name": "AI & Machine Learning", "description": "Neural networks, vision."},
        headers=manager,
    )
    assert cat.status_code == 201
    cat_id = cat.json()["id"]

    upload = client.post(
        "/api/reports/upload",
        data={"project_name": "Liste Serilestirme Testi", "category_id": cat_id},
        files={"file": ("r.pdf", io.BytesIO(b"%PDF-1.4 Mock"), "application/pdf")},
        headers=manager,
    )
    assert upload.status_code == 201
    report_id = upload.json()["id"]

    # Analizin gerceklestigini teyit et - yoksa test bosa doner ve
    # regresyonu kacirir (analiz yoksa endpoint zaten hic patlamiyordu).
    detay = client.get(f"/api/reports/{report_id}", headers=referee)
    assert detay.status_code == 200
    assert detay.json()["ai_analysis"] is not None, (
        "analiz olusmadi - bu test analiz VARKEN listenin calistigini dogrulamali"
    )

    liste = client.get("/api/reports", headers=referee)
    assert liste.status_code == 200, f"liste endpoint'i patladi: {liste.text[:300]}"

    kayit = next(r for r in liste.json() if r["id"] == report_id)
    assert kayit["ai_analysis"] is not None
    # Frontend'in CHECK_KEYS'i (frontend/src/lib/ai-analysis.ts) ile birebir
    assert set(kayit["ai_analysis"]["results"]) == {
        "languageTemplate", "contentHeading", "categoryMatch", "similarity",
    }
    for kontrol in kayit["ai_analysis"]["results"].values():
        assert isinstance(kontrol["score"], int)
        assert isinstance(kontrol["findings"], list)

    # status filtresi de ayni serilestirme yolunu kullaniyor
    filtreli = client.get("/api/reports?status=analyzed", headers=referee)
    assert filtreli.status_code == 200, f"filtreli liste patladi: {filtreli.text[:300]}"


@pytest.mark.skipif(not GERCEK_RAPOR.exists(), reason="referans KTR raporu bulunamadi")
def test_real_pdf_produces_real_ai_scores(client):
    """Gercek bir PDF ile analiz hattinin GERCEKTEN calistigini dogrular.

    Bu test onemli cunku diger testler sahte bayt ("%PDF-1.4 Mock")
    yukluyor; o durumda tum AI modulleri hata yoluna girip 0 puan donuyor
    ve modullerin gercekten bir sey OLCUP olcmedigi hic sinanmiyor. Burada
    beklenen degerler, ai-scoring/tests/test_scorer.py'de 34 gercek rapor
    uzerinde olculen davranisla ayni.
    """
    manager = _kaydol_ve_giris(client, "gercek_manager@test.org", "COMPETITION_MANAGER")
    referee = _kaydol_ve_giris(client, "gercek_referee@test.org", "REFEREE")

    cat_id = client.post(
        "/api/categories",
        json={
            "name": "AI & Machine Learning",
            "description": "Neural networks, NLP models, computer vision pipelines.",
        },
        headers=manager,
    ).json()["id"]

    with open(GERCEK_RAPOR, "rb") as f:
        upload = client.post(
            "/api/reports/upload",
            data={"project_name": "IHA Nesne Tespiti", "category_id": cat_id},
            files={"file": (GERCEK_RAPOR.name, f, "application/pdf")},
            headers=manager,
        )
    assert upload.status_code == 201
    report_id = upload.json()["id"]

    detay = client.get(f"/api/reports/{report_id}", headers=referee).json()
    assert detay["status"] == "analyzed"
    analiz = detay["ai_analysis"]
    sonuclar = analiz["results"]

    # Hasan'in modulu: gercek Turkce rapor, sablona uygun -> tam puan
    assert sonuclar["languageTemplate"]["score"] == 100
    assert sonuclar["contentHeading"]["score"] == 100

    # Hayrettin'in modulu: dogru kategoride beyan edildi -> yuksek guven
    assert sonuclar["categoryMatch"]["score"] >= 85, sonuclar["categoryMatch"]

    # Karsilastirilacak baska rapor yok -> 0, ama bulgularda bunun
    # "ozgunluk kanitlandi" ANLAMINA GELMEDIGI yazmali
    assert sonuclar["similarity"]["score"] == 0
    assert any("GELMEZ" in b for b in sonuclar["similarity"]["findings"])

    # Kriter degerlendirmesi gercek bir puan uretmis olmali (mock degil)
    assert 0 < analiz["suggested_score"] <= 100
    assert analiz["suggested_outcome"] in ("approve", "revise", "reject")
    assert "Kriter kırılımı" in analiz["rationale"]
    # AI'nin nihai karar verici OLMADIGI gerekcede acikca yazili olmali
    assert "hakemin" in analiz["rationale"]

    # Ayni rapor ikinci kez yuklenirse intihal olarak yakalanmali
    with open(GERCEK_RAPOR, "rb") as f:
        kopya = client.post(
            "/api/reports/upload",
            data={"project_name": "Kopya Proje", "category_id": cat_id},
            files={"file": ("kopya.pdf", f, "application/pdf")},
            headers=manager,
        )
    assert kopya.status_code == 201
    kopya_analiz = client.get(
        f"/api/reports/{kopya.json()['id']}", headers=referee
    ).json()["ai_analysis"]
    # frontend bandi: >35 "Yuksek risk"
    assert kopya_analiz["results"]["similarity"]["score"] > 35, (
        kopya_analiz["results"]["similarity"]
    )
