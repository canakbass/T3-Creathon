import json
import os
import shutil
import uuid
import datetime
from pathlib import Path
import anyio.to_thread
from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Form, BackgroundTasks
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from typing import List, Optional

from ..database import get_db
from .. import models, schemas, auth
from ..services import ai
from . import competitions

router = APIRouter(prefix="/api/reports", tags=["Reports"])

UPLOAD_DIR = "uploads"
if not os.path.exists(UPLOAD_DIR):
    os.makedirs(UPLOAD_DIR)


def _dosyayi_diske_yaz(upload: UploadFile, hedef_yol: str) -> None:
    """Yuklenen dosyayi diske kopyalar. Bloklayan is - ayri bir is
    parcaciginda cagrilmali (bkz. upload_report)."""
    with open(hedef_yol, "wb") as buffer:
        shutil.copyfileobj(upload.file, buffer)

def _attach_analysis_results(report: models.Report) -> models.Report:
    """AiAnalysis kaydinin duz kolonlarini, API'nin dondugu ic ice `results`
    sozlugune cevirip nesneye ekler.

    NEDEN GEREKLI: schemas.AiAnalysisResponse `results: Dict[str, AiCheckResult]`
    alanini ZORUNLU tutuyor, ama models.AiAnalysis'te `results` diye bir
    kolon yok - veri tabaninda her kontrol dort ayri duz kolonda duruyor
    (language_template_score, ..._summary, ..._findings). Yani bu alanin
    her yanit oncesi elle uretilmesi sart.

    ONCEDEN NE KIRIKTI: bu donusum yalnizca get_report icinde yapiliyordu.
    list_reports (GET /api/reports) ayni ReportResponse semasini kullaniyor
    ama donusumu yapmiyordu; dolayisiyla veri tabaninda analiz edilmis TEK
    BIR rapor olur olmaz endpoint ResponseValidationError ile HTTP 500
    veriyordu ("Field required: ai_analysis.results"). Hakem panosunun ana
    listesi tam da bu endpoint'i kullaniyor. Mevcut testler yakalamamisti
    cunku analiz sonrasi liste endpoint'ini hic cagirmiyorlardi.

    Anahtar adlari camelCase: frontend/src/lib/ai-analysis.ts icindeki
    CHECK_KEYS ile birebir ayni olmali.
    """
    # Atama bilgisini yaniti hazirlarken ekliyoruz: yonetici paneli her rapor
    # icin ayri bir istek atmak zorunda kalmasin (N+1).
    atama = report.assignment
    setattr(report, "assigned_referee_id", atama.referee_id if atama else None)
    setattr(
        report,
        "assigned_referee_email",
        atama.referee.email if atama and atama.referee else None,
    )

    analysis = report.ai_analysis
    if not analysis:
        return report

    def _findings(deger):
        if not deger:
            return []
        try:
            return json.loads(deger)
        except (json.JSONDecodeError, TypeError):
            # Bozuk JSON yuzunden tum endpoint dusmesin - hakem en azindan
            # puani ve ozeti gorsun.
            return ["Bulgular okunamadi (veri tabanindaki kayit bozuk)."]

    setattr(
        analysis,
        "results",
        {
            "languageTemplate": {
                "score": analysis.language_template_score,
                "summary": analysis.language_template_summary,
                "findings": _findings(analysis.language_template_findings),
            },
            "contentHeading": {
                "score": analysis.content_heading_score,
                "summary": analysis.content_heading_summary,
                "findings": _findings(analysis.content_heading_findings),
            },
            "categoryMatch": {
                "score": analysis.category_match_score,
                "summary": analysis.category_match_summary,
                "findings": _findings(analysis.category_match_findings),
            },
            "similarity": {
                "score": analysis.similarity_score,
                "summary": analysis.similarity_summary,
                "findings": _findings(analysis.similarity_findings),
            },
        },
    )
    return report


def run_background_analysis(report_id: str, file_path: str, db: Session):
    try:
        # Get category information
        categories = db.query(models.Category).all()
        # description de geciyoruz: docs/scoring-rules.json'da anahtar kelime
        # tanimi olmayan (Yarisma Yoneticisi'nin sonradan ekledigi) bir
        # kategori icin ai-scoring, kategori adi+aciklamasi uzerinden
        # karakter n-gram benzerligine dusuyor - aciklama olmadan o yedek
        # yontemin elinde neredeyse hic sinyal kalmaz.
        categories_dict = [
            {"id": c.id, "name": c.name, "description": c.description} for c in categories
        ]
        
        # Get existing report files (for similarity checking)
        other_reports = db.query(models.Report).filter(models.Report.id != report_id).all()
        existing_paths = [r.file_path for r in other_reports if os.path.exists(r.file_path)]
        
        report = db.query(models.Report).filter(models.Report.id == report_id).first()

        # Kriterler: rapor bir YARISMAYA bagliysa o yarismanin kriterleri
        # (agirliklariyla birlikte) kullaniliyor. Degilse eski kategori
        # bazli kriter tablosuna dusuluyor.
        if report.competition and report.competition.criteria_list:
            criteria_dict = [
                {"id": k.id, "title": k.title, "weight": k.weight, "max_score": 100}
                for k in sorted(report.competition.criteria_list, key=lambda k: k.display_order)
            ]
        else:
            criteria = db.query(models.Criteria).filter(
                models.Criteria.category_id == report.category_id
            ).all()
            criteria_dict = [
                {"id": cr.id, "title": cr.title, "max_score": cr.max_score} for cr in criteria
            ]

        # Sablon kurallari: yarisma kendi kurallarini tanimladiysa ONLAR
        # kullaniliyor. Onceden bu degerler tum sistem icin
        # docs/mvp-rules.json'da SABITTI; artik her yarisma kendi zorunlu
        # basliklarini, dilini ve sayfa sinirini belirleyebiliyor.
        rules = competitions.yarismanin_kurallari(report.competition)

        # Run AI analysis.
        # declared_category_id: yarismacinin yukleme sirasinda sectigi
        # kategori. Bu olmadan kategori kontrolu yalnizca "en uygun kategori
        # hangisi" diyebiliyordu; asil sorulmasi gereken soru "rapor BEYAN
        # EDILEN kategoriye ait mi" oldugu icin bu bilgiyi da geciyoruz.
        analysis_data = ai.run_full_analysis(
            file_path=file_path,
            db_categories=categories_dict,
            existing_files=existing_paths,
            criteria_list=criteria_dict,
            declared_category_id=report.category_id,
            rules=rules,
        )
        
        # Save analysis results
        db_analysis = models.AiAnalysis(
            id=str(uuid.uuid4()),
            report_id=report_id,
            analyzed_at=datetime.datetime.now(datetime.UTC).replace(tzinfo=None),
            engine_version="eval-engine v1.0",
            suggested_outcome=analysis_data["suggested_outcome"],
            suggested_score=analysis_data["suggested_score"],
            rationale=analysis_data["rationale"],
            
            language_template_score=analysis_data["language_template"]["score"],
            language_template_summary=analysis_data["language_template"]["summary"],
            language_template_findings=json.dumps(analysis_data["language_template"]["findings"]),
            
            content_heading_score=analysis_data["content_heading"]["score"],
            content_heading_summary=analysis_data["content_heading"]["summary"],
            content_heading_findings=json.dumps(analysis_data["content_heading"]["findings"]),
            
            category_match_score=analysis_data["category_match"]["score"],
            category_match_summary=analysis_data["category_match"]["summary"],
            category_match_findings=json.dumps(analysis_data["category_match"]["findings"]),
            
            similarity_score=analysis_data["similarity"]["score"],
            similarity_summary=analysis_data["similarity"]["summary"],
            similarity_findings=json.dumps(analysis_data["similarity"]["findings"])
        )
        
        db.add(db_analysis)
        
        # Update report status to analyzed
        report.status = "analyzed"
        db.commit()
    except Exception as e:
        print(f"Error analyzing report {report_id}: {str(e)}")
        # In a real app we'd log this, and set report status to error
        report = db.query(models.Report).filter(models.Report.id == report_id).first()
        if report:
            report.status = "error"
            db.commit()


@router.post("/upload", response_model=schemas.ReportResponse, status_code=status.HTTP_201_CREATED)
async def upload_report(
    background_tasks: BackgroundTasks,
    project_name: str = Form(...),
    category_id: str = Form(None),
    competition_id: str = Form(None),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.RoleChecker(["COMPETITION_MANAGER", "COMPETITOR"]))
):
    """Rapor yukler ve AI analizini arka planda baslatir.

    `competition_id` verilirse yarismanin asamasi kontrol edilir ve kategori
    yarismadan alinir - yarismacinin kategori secmesine gerek kalmaz.
    Yarisma verilmezse eski davranis (kategori dogrudan secilir) surdurulur.
    """
    competition = None
    if competition_id:
        competition = db.query(models.Competition).filter(
            models.Competition.id == competition_id
        ).first()
        if not competition:
            raise HTTPException(status_code=404, detail="Yarisma bulunamadi.")

        # Yarismacinin rapor yukleyebilmesi yarismanin ASAMASINA bagli.
        # Yonetici test/duzeltme amaciyla her asamada yukleyebilir.
        aktif = getattr(current_user, "active_role", None)
        if aktif == "COMPETITOR" and competition.status not in ("open",):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    f"'{competition.name}' yarismasina su anda basvuru "
                    f"yapilamiyor (asama: {competition.status})."
                ),
            )
        # Kategori yarismadan geliyor - yarismacinin ayrica secmesine gerek yok.
        category_id = competition.category_id

    if not category_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="category_id ya da competition_id verilmeli.",
        )

    category = db.query(models.Category).filter(models.Category.id == category_id).first()
    if not category:
        raise HTTPException(status_code=404, detail="Category not found.")

    # Check file extension
    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in [".pdf", ".doc", ".docx"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Unsupported file type. Upload a PDF or Word document."
        )
        
    report_id = f"RPT-2026-{str(uuid.uuid4())[:6].upper()}"
    file_path = os.path.join(UPLOAD_DIR, f"{report_id}{ext}")

    # Dosyayi diske YAZARKEN olay dongusunu (event loop) bloklamiyoruz.
    #
    # Onceki hali `with open(...) as buffer: buffer.write(await file.read())`
    # seklindeydi. Iki sorunu vardi (SonarQube: "Use an asynchronous file API
    # instead of synchronous open() in this async function"):
    #   1. open()/write() bloklayan sistem cagrilaridir. Bu fonksiyon
    #      `async def` oldugu icin olay dongusunun kendi is parcaciginda
    #      calisiyordu - yani buyuk bir PDF yazilirken sunucu O ANDA baska
    #      HICBIR istege yanit veremiyordu.
    #   2. `await file.read()` dosyanin TAMAMINI bellege aliyordu.
    #
    # anyio.to_thread.run_sync bloklayan isi ayri bir is parcacigina
    # tasiyor; shutil.copyfileobj ise parca parca kopyaladigi icin dosya
    # bellege sigmak zorunda kalmiyor. anyio yeni bir bagimlilik degil -
    # starlette (dolayisiyla FastAPI) zaten ona bagli.
    await anyio.to_thread.run_sync(_dosyayi_diske_yaz, file, file_path)

    # Create Report record (status = pending)
    db_report = models.Report(
        id=report_id,
        project_name=project_name,
        category_id=category_id,
        status="pending",
        file_path=file_path,
        # Diskteki ad RPT-2026-XXXXXX.pdf seklinde normalize ediliyor;
        # indirme sirasinda kullaniciya kendi verdigi adi gosterebilmek
        # icin orijinali de sakliyoruz.
        original_filename=file.filename,
        competition_id=competition.id if competition else None,
        submitted_by_id=current_user.id,
        submission_date=datetime.datetime.now(datetime.UTC).replace(tzinfo=None)
    )
    
    db.add(db_report)
    db.commit()
    db.refresh(db_report)
    
    # Run analysis in background
    background_tasks.add_task(run_background_analysis, report_id, file_path, db)
    
    return db_report


@router.get("", response_model=List[schemas.ReportResponse])
def list_reports(
    status: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user)
):
    query = db.query(models.Report)

    # Rol bazli filtreleme, isteğin AKTIF ROLUNE gore yapiliyor.
    # Cok-rollu bir kullanici hakem rolundeyken yarismaci raporlarini
    # gormemeli; hangi rolle hareket ettigi belirleyici.
    aktif_rol = getattr(current_user, "active_role", None)
    if aktif_rol == "COMPETITOR":
        query = query.filter(models.Report.submitted_by_id == current_user.id)
    elif aktif_rol == "REFEREE":
        # Hakem yalnizca KENDISINE ATANMIS raporlari gorur.
        #
        # Gecis notu: atamasi HIC OLMAYAN raporlar da gosteriliyor. Sebep,
        # atama sistemi yeni eklendi ve daha once yuklenmis raporlarin
        # atamasi yok; bunlari gizlemek eski verinin kaybolmasi gibi
        # gorunurdu. Yarisma akisi tam oturunca (her rapor bir yarismaya
        # bagli ve dagitim yapiliyor) bu gevsetme kaldirilabilir.
        query = query.outerjoin(models.Assignment).filter(
            (models.Assignment.referee_id == current_user.id)
            | (models.Assignment.id.is_(None))
        )

    if status:
        query = query.filter(models.Report.status == status)

    # ai_analysis.results her yanit oncesi uretilmek zorunda (bkz.
    # _attach_analysis_results). Bu eksik oldugu icin endpoint, analiz
    # edilmis ilk rapordan sonra HTTP 500 veriyordu.
    return [_attach_analysis_results(r) for r in query.all()]


@router.get("/{report_id}", response_model=schemas.ReportResponse)
def get_report(
    report_id: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user)
):
    report = db.query(models.Report).filter(models.Report.id == report_id).first()
    if not report:
        raise HTTPException(status_code=404, detail="Report not found.")
        
    # Yarismaci yalnizca KENDI raporunu gorebilir.
    if (
        getattr(current_user, "active_role", None) == "COMPETITOR"
        and report.submitted_by_id != current_user.id
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Bu rapora erisim yetkiniz yok.",
        )
        
    # ai_analysis.results semada zorunlu ama veri tabaninda kolon degil -
    # yanit oncesi duz kolonlardan uretiliyor (bkz. _attach_analysis_results).
    return _attach_analysis_results(report)


def _rapora_erisebilir_mi(report: models.Report, user: models.User) -> bool:
    """Bu kullanici bu raporun DOSYASINI gorebilir mi.

    - Yarismaci: yalnizca kendi raporu
    - Hakem: yalnizca kendisine ATANMIS rapor (atama yoksa goremez)
    - Yarisma/Degerlendirme Yoneticisi: hepsi
    """
    aktif = getattr(user, "active_role", None)
    if aktif in ("COMPETITION_MANAGER", "EVALUATION_MANAGER"):
        return True
    if aktif == "COMPETITOR":
        return report.submitted_by_id == user.id
    if aktif == "REFEREE":
        return report.assignment is not None and report.assignment.referee_id == user.id
    return False


@router.get("/{report_id}/file")
def get_report_file(
    report_id: str,
    download: bool = False,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    """Raporun kendisini (PDF/Word) servis eder.

    NEDEN EKLENDI: boyle bir uc nokta HIC YOKTU. Hakem, okuyamadigi bir
    raporu degerlendiriyordu - sistemde yalnizca AI'nin ozeti vardi, belgenin
    kendisi yoktu. Bir hakem karar destek sisteminde bu temel bir eksik.

    `download=false` (varsayilan) tarayicinin gomulu goruntuleyicisinde
    acilmasi icin `inline` doner; `download=true` indirme baslatir.
    """
    report = db.query(models.Report).filter(models.Report.id == report_id).first()
    if not report:
        raise HTTPException(status_code=404, detail="Rapor bulunamadi.")

    if not _rapora_erisebilir_mi(report, current_user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Bu raporun dosyasina erisim yetkiniz yok.",
        )

    # Yol dogrulamasi: file_path veri tabanindan geliyor ama yine de
    # UPLOAD_DIR disina cikmadigini kontrol ediyoruz. Veri tabanina bir
    # sekilde "../../etc/passwd" yazilsa bile dosya servis edilmemeli.
    kok = Path(UPLOAD_DIR).resolve()
    try:
        hedef = Path(report.file_path).resolve()
        hedef.relative_to(kok)
    except (ValueError, OSError):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Rapor dosyasinin yolu gecersiz.",
        )

    if not hedef.is_file():
        raise HTTPException(
            status_code=404,
            detail="Rapor kaydi var ama dosya diskte bulunamadi.",
        )

    uzanti = hedef.suffix.lower()
    medya_tipi = {
        ".pdf": "application/pdf",
        ".doc": "application/msword",
        ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    }.get(uzanti, "application/octet-stream")

    # Kullaniciya gosterilecek ad: yukleyenin verdigi orijinal ad varsa o,
    # yoksa rapor kimligi. Diskteki ad her zaman normalize edilmis.
    gosterim_adi = report.original_filename or f"{report.id}{uzanti}"

    # Dosya adini HER IKI durumda da veriyoruz: Starlette, filename=None
    # oldugunda Content-Disposition basligini hic gondermiyor ve tarayicinin
    # varsayilanina kaliyoruz. Basligi acikca gondermek, gomulu
    # goruntuleyicide acilmasini garantiliyor.
    return FileResponse(
        path=str(hedef),
        media_type=medya_tipi,
        filename=gosterim_adi,
        content_disposition_type="attachment" if download else "inline",
    )


@router.post("/{report_id}/rationale-draft", response_model=schemas.RationaleDraft)
def rationale_draft(
    report_id: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.RoleChecker(["REFEREE"])),
):
    """Hakemin gerekcesi icin AI TASLAGI uretir.

    ETIK CERCEVE - bu uc noktanin tasarimi bilincli:

    Gerekce, bir insanin raporu GERCEKTEN inceledi̇gi̇ni̇n kanitidir. AI'nin
    gerekceyi hayalet yazar gibi yazmasi, projenin ana ilkesini ("AI karar
    verici degildir") terse cevirirdi. Bu yuzden:

      * Taslak OTOMATIK DOLDURULMUYOR - hakem acikca istemek zorunda.
      * Taslak yeni bir yargi URETMIYOR; yalnizca analizin ZATEN buldugu
        somut bulgulari duzenli bir metne donusturuyor. Yani hakemin
        okudugu seyleri toparliyor, onun yerine karar vermiyor.
      * Metnin basinda AI tarafindan uretildigi yaziyor.
      * Karar kaydedilirken bu metnin taslaktan gelip gelmedigi ve hakemin
        DEGISTIRIP degistirmedigi veri tabaninda saklaniyor
        (FinalDecision.rationale_ai_drafted / rationale_edited_by_referee).
        Sonradan itiraz olursa "bu gerekceyi kim yazdi" sorusunun cevabi
        kayitli.
    """
    report = db.query(models.Report).filter(models.Report.id == report_id).first()
    if not report:
        raise HTTPException(status_code=404, detail="Rapor bulunamadi.")
    if not _rapora_erisebilir_mi(report, current_user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Bu rapor size atanmamis.",
        )
    if not report.ai_analysis:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Bu rapor icin henuz AI analizi yok; taslak uretilemez.",
        )

    a = report.ai_analysis
    kontroller = [
        ("Dil ve şablon uyumu", a.language_template_score, a.language_template_summary,
         a.language_template_findings, False),
        ("İçerik ve başlık kontrolü", a.content_heading_score, a.content_heading_summary,
         a.content_heading_findings, False),
        ("Kategori uyumu", a.category_match_score, a.category_match_summary,
         a.category_match_findings, False),
        # Benzerlik TERS polarite: dusuk puan iyi sonuc.
        ("Benzerlik / intihal", a.similarity_score, a.similarity_summary,
         a.similarity_findings, True),
    ]

    guclu, zayif = [], []
    for ad, puan, ozet, bulgular_json, ters in kontroller:
        iyi = (puan <= 15) if ters else (puan >= 85)
        satir = f"{ad}: {puan}/100 — {(ozet or '').strip()}"
        (guclu if iyi else zayif).append(satir)

    parcalar = [
        "[Bu taslak AI analizinden üretilmiştir. Göndermeden önce kendi "
        "değerlendirmenizi ekleyin ve gerekli düzeltmeleri yapın.]",
        "",
    ]
    if guclu:
        parcalar.append("Güçlü bulunan noktalar:")
        parcalar += [f"- {s}" for s in guclu]
        parcalar.append("")
    if zayif:
        parcalar.append("Gözden geçirilmesi gereken noktalar:")
        parcalar += [f"- {s}" for s in zayif]
        parcalar.append("")

    # Kriter kirilimi zaten AI gerekcesinin icinde; hakeme oldugu gibi
    # veriyoruz ki puanin nasil olustugunu gorebilsin.
    if a.rationale:
        parcalar.append("Motorun kriter değerlendirmesi:")
        parcalar.append(a.rationale.strip())

    return {
        "draft": "\n".join(parcalar).strip(),
        "notice": (
            "Bu metin AI analizinden üretilmiş bir TASLAKTIR. Nihai gerekçe "
            "sizin değerlendirmenizdir; gönderdiğiniz metnin taslaktan "
            "değiştirilip değiştirilmediği kayıt altına alınır."
        ),
        "suggested_score": a.suggested_score,
        "suggested_outcome": a.suggested_outcome,
    }


@router.post("/{report_id}/decision", response_model=schemas.FinalDecisionResponse)
def submit_decision(
    report_id: str,
    decision_in: schemas.FinalDecisionCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.RoleChecker(["REFEREE"]))
):
    # Verify report exists
    report = db.query(models.Report).filter(models.Report.id == report_id).first()
    if not report:
        raise HTTPException(status_code=404, detail="Report not found.")
        
    # Ensure it's analyzed first
    if report.status == "pending":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Report must be analyzed by AI before referee decision can be made."
        )
        
    # Check if decision already exists
    existing_decision = db.query(models.FinalDecision).filter(models.FinalDecision.report_id == report_id).first()
    if existing_decision:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="A decision has already been submitted for this report."
        )
        
    # Create decision
    decision_id = str(uuid.uuid4())
    db_decision = models.FinalDecision(
        id=decision_id,
        report_id=report_id,
        referee_id=current_user.id,
        outcome=decision_in.outcome,
        final_score=decision_in.final_score,
        rationale=decision_in.rationale,
        # Denetim izi: gerekce AI taslagindan mi geldi, hakem degistirdi mi.
        # Sonradan itiraz olursa "bu gerekceyi kim yazdi" sorusunun cevabi
        # kayitli olsun diye saklaniyor (bkz. rationale-draft uc noktasi).
        rationale_ai_drafted=decision_in.rationale_ai_drafted,
        rationale_edited_by_referee=decision_in.rationale_edited_by_referee,
        submitted_at=datetime.datetime.now(datetime.UTC).replace(tzinfo=None)
    )
    
    # Update report status
    report.status = decision_in.outcome # approve, reject, revise -> maps to status
    if decision_in.outcome == "approve":
        report.status = "approved"
    elif decision_in.outcome == "reject":
        report.status = "rejected"
        
    db.add(db_decision)
    db.commit()
    db.refresh(db_decision)
    return db_decision
