"""Yarisma yonetimi ve sablon/kriter tanimi.

BU DOSYA "Kriter ve Sablon Tanimi" EKRANININ ARKASINDAKI EKSIK PARCAYDI.
Arayuzdeki form hicbir yere kaydetmiyordu cunku karsilik gelen bir uc nokta
yoktu. Simdi form gercekten YARISMANIN KURALLARINI belirliyor:

  * zorunlu basliklar / kabul edilen dil / sayfa siniri  -> AI'nin dil-sablon
    ve baslik-icerik kontrolleri bunlari kullaniyor (onceden tum sistem icin
    docs/mvp-rules.json'da SABITTI)
  * kriterler ve AGIRLIKLARI -> AI kriter puanlamasi bunlari kullaniyor
    (onceden docs/scoring-rules.json'da SABITTI)

Boylece MVP rol 1'in tanimi ("Yarisma Yoneticisi rapor sablonunu, kategori
bilgilerini ve degerlendirme kriterlerini tanimlar") gercekten karsilaniyor.

YARISMA ASAMALARI ve ne yapilabildigi:
  draft      hazirlik. Yarismaci goremez, rapor yukleyemez.
  open       basvuru acik. Yarismaci rapor yukler, AI analizi OTOMATIK calisir.
  closed     basvuru kapandi. Yeni yukleme yok; hakem atamasi yapilir.
  evaluating hakemler degerlendiriyor. Karar verilebilir.
  completed  bitti. Yarismaci sonucunu gorur.
"""

import json
import os
import shutil
import tempfile
import uuid
from typing import List, Optional

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    HTTPException,
    UploadFile,
    status,
)
from sqlalchemy.orm import Session

from ..database import get_db
from .. import models, schemas, auth
from ..services import ai

router = APIRouter(prefix="/api/competitions", tags=["Competitions"])

_YONETICI = auth.RoleChecker(["COMPETITION_MANAGER", "EVALUATION_MANAGER"])

# Yarismanin gecebilecegi asamalar ve siralamasi.
ASAMALAR = ("draft", "open", "closed", "evaluating", "completed")

# Bu asamalarda yarismaci rapor yukleyebilir.
YUKLEMEYE_ACIK = ("open",)


def _json_yukle(deger, varsayilan):
    if not deger:
        return varsayilan
    try:
        return json.loads(deger)
    except (json.JSONDecodeError, TypeError):
        return varsayilan


def _yanit(y: models.Competition) -> dict:
    return {
        "id": y.id,
        "name": y.name,
        "description": y.description,
        "category_id": y.category_id,
        "category_name": y.category.name if y.category else None,
        "category_label": y.category_label,
        "status": y.status,
        "submission_deadline": y.submission_deadline,
        "created_at": y.created_at,
        "report_type_name": y.report_type_name,
        "accepted_languages": _json_yukle(y.accepted_languages, ["tr"]),
        "required_headings": _json_yukle(y.required_headings, []),
        "heading_synonyms": _json_yukle(y.heading_synonyms, {}),
        "min_pages": y.min_pages,
        "max_pages": y.max_pages,
        "min_section_chars": y.min_section_chars,
        "criteria": [
            {
                "id": k.id,
                "title": k.title,
                "description": k.description,
                "weight": k.weight,
                "display_order": k.display_order,
            }
            for k in sorted(y.criteria_list, key=lambda k: k.display_order)
        ],
        "referee_count": len(y.referees),
        "report_count": len(y.reports),
    }


@router.get("", response_model=List[schemas.CompetitionResponse])
def list_competitions(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    """Yarismalari listeler.

    Yarismaci ve hakem, HAZIRLIK asamasindaki (draft) yarismalari gormez -
    yonetici hazirligini bitirmeden duyurulmus gibi gorunmemeli.
    """
    q = db.query(models.Competition)
    aktif = getattr(current_user, "active_role", None)
    if aktif not in ("COMPETITION_MANAGER", "EVALUATION_MANAGER"):
        q = q.filter(models.Competition.status != "draft")
    return [_yanit(y) for y in q.order_by(models.Competition.created_at.desc()).all()]


@router.post("", response_model=schemas.CompetitionResponse, status_code=status.HTTP_201_CREATED)
def create_competition(
    govde: schemas.CompetitionCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(_YONETICI),
):
    # Kategori artik SERBEST METIN (category_label). Eski global tabloya
    # baglanti isteğe bagli - verilirse dogrulaniyor, verilmezse sistemin
    # varsayilan kategorisine baglaniyor (Report.category_id NOT NULL oldugu
    # icin bir deger gerekiyor; bu bagimlilik ayri bir adimda kaldirilacak).
    kategori = None
    if govde.category_id:
        kategori = db.query(models.Category).filter(
            models.Category.id == govde.category_id
        ).first()
        if not kategori:
            raise HTTPException(status_code=404, detail="Kategori bulunamadi.")
    else:
        kategori = db.query(models.Category).order_by(models.Category.id).first()
        if not kategori:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Sistemde hic kategori tanimli degil; category_id verin.",
            )

    y = models.Competition(
        id=f"COMP-{str(uuid.uuid4())[:8].upper()}",
        name=govde.name,
        description=govde.description,
        category_id=kategori.id,
        category_label=govde.category_label,
        created_by_id=current_user.id,
        status="draft",
        submission_deadline=govde.submission_deadline,
    )
    db.add(y)
    db.commit()
    db.refresh(y)
    return _yanit(y)


@router.get("/{competition_id}", response_model=schemas.CompetitionResponse)
def get_competition(
    competition_id: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    y = db.query(models.Competition).filter(models.Competition.id == competition_id).first()
    if not y:
        raise HTTPException(status_code=404, detail="Yarisma bulunamadi.")
    aktif = getattr(current_user, "active_role", None)
    if y.status == "draft" and aktif not in ("COMPETITION_MANAGER", "EVALUATION_MANAGER"):
        raise HTTPException(status_code=404, detail="Yarisma bulunamadi.")
    return _yanit(y)


def _kural_degisimini_dogrula(db: Session, yarisma, onaylandi: bool) -> list:
    """Puanlama kurallari degistirilebilir mi, degistirilirse ne olur.

    NEDEN GEREKLI: sablon kurallari ve kriterler, AI analizinin puanlama
    rubrigi. Analiz edildikten SONRA degistirilince eski raporlar eski
    rubrikle, yeni raporlar yeni rubrikle puanlaniyor - yani AYNI yarismada
    iki yarismaci FARKLI kurallarla degerlendiriliyor.

    Bu teorik degil, olculdu: kriterler "Ozgunluk %70 / Kaynakca %30" iken
    yuklenen rapor 100/100 "onay" aldi; kriterler "Kaynakca %90 / Ozgunluk
    %10" yapildiktan sonra yuklenen ikinci rapor 9/100 "ret" aldi. Bir
    yarismada olabilecek en agir adaletsizlik bu.

    Kurallar:
      * Karar VERILMIS rapor varsa degisiklik yok - hakem kararlari o
        rubrige gore verildi, geriye donuk degistirmek onlari gecersiz kilar.
      * Analiz edilmis rapor varsa yonetici acikca onaylamali; onaylarsa o
        raporlarin analizi SILINIP yeniden calistiriliyor ki hepsi ayni
        rubrikle puanlansin.
      * Hic analiz yoksa serbest (normal kurulum akisi).

    Doner: yeniden analiz edilecek raporlarin listesi (bos olabilir).
    """
    raporlar = [r for r in yarisma.reports]
    kararli = [r for r in raporlar if r.final_decision is not None]
    if kararli:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"Bu yarismada {len(kararli)} rapor icin hakem karari verilmis. "
                "Puanlama kurallari degistirilemez - kararlar mevcut kurallara "
                "gore verildi ve degisiklik onlari gecersiz kilardi."
            ),
        )

    analizli = [r for r in raporlar if r.status not in ("pending",)]
    if analizli and not onaylandi:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"Bu yarismada {len(analizli)} rapor zaten analiz edildi. "
                "Kurallari degistirirseniz o raporlar ESKI kurallarla, yeni "
                "raporlar YENI kurallarla puanlanir; ayni yarismada iki "
                "yarismaci farkli olcutlerle degerlendirilmis olur. Devam "
                "etmek icin istege `confirm_reanalysis: true` ekleyin - "
                "mevcut analizler silinip yeni kurallarla yeniden calistirilir."
            ),
        )
    return analizli


def _yeniden_analiz_kuyrukla(db: Session, background_tasks: BackgroundTasks, raporlar) -> None:
    """Verilen raporlarin analizini silip yeniden calistirilmak uzere kuyruklar."""
    # Ice aktarma FONKSIYON ICINDE: routes/reports.py bu modulu (competitions)
    # zaten ice aktariyor; ust seviyede karsilikli ice aktarma dongu olusturur.
    from . import reports as reports_modulu

    for r in raporlar:
        if r.ai_analysis:
            db.delete(r.ai_analysis)
        r.status = "pending"
    db.commit()
    for r in raporlar:
        background_tasks.add_task(
            reports_modulu.run_background_analysis, r.id, r.file_path, db
        )


@router.put("/{competition_id}/template", response_model=schemas.CompetitionResponse)
def set_template(
    competition_id: str,
    govde: schemas.CompetitionTemplate,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(_YONETICI),
):
    """Yarismanin SABLON KURALLARINI belirler.

    AI'nin dil/sablon ve baslik/icerik kontrolleri bu kurallari kullanir.
    Onceden bu degerler tum sistem icin docs/mvp-rules.json'da sabitti;
    artik yarisma basina ayarlanabiliyor.
    """
    y = db.query(models.Competition).filter(models.Competition.id == competition_id).first()
    if not y:
        raise HTTPException(status_code=404, detail="Yarisma bulunamadi.")

    if govde.min_pages is not None and govde.max_pages is not None:
        if govde.min_pages > govde.max_pages:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="En az sayfa sayisi, en fazladan buyuk olamaz.",
            )

    # Sablon kurallari AI'nin dil/sablon/baslik kontrollerinin olcutu;
    # analizden sonra degistirmek raporlari farkli olcutlerle puanlar.
    yeniden = _kural_degisimini_dogrula(db, y, govde.confirm_reanalysis)

    y.report_type_name = govde.report_type_name
    y.accepted_languages = json.dumps(govde.accepted_languages, ensure_ascii=False)
    y.required_headings = json.dumps(govde.required_headings, ensure_ascii=False)
    y.heading_synonyms = json.dumps(govde.heading_synonyms or {}, ensure_ascii=False)
    y.min_pages = govde.min_pages
    y.max_pages = govde.max_pages
    y.min_section_chars = govde.min_section_chars
    db.commit()
    if yeniden:
        _yeniden_analiz_kuyrukla(db, background_tasks, yeniden)
    db.refresh(y)
    return _yanit(y)


@router.put("/{competition_id}/criteria", response_model=schemas.CompetitionResponse)
def set_criteria(
    competition_id: str,
    govde: schemas.CompetitionCriteriaSet,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(_YONETICI),
):
    """Yarismanin degerlendirme kriterlerini ve AGIRLIKLARINI belirler.

    Agirliklarin toplami 100 olmali: AI kriter puanlamasi agirlikli ortalama
    aliyor ve hakeme "bu 78 nereden geldi" sorusunun cevabini verebilmek
    icin agirliklarin anlamli bir toplami olmasi gerekiyor.
    """
    y = db.query(models.Competition).filter(models.Competition.id == competition_id).first()
    if not y:
        raise HTTPException(status_code=404, detail="Yarisma bulunamadi.")

    if not govde.criteria:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="En az bir kriter tanimlayin.",
        )
    toplam = sum(k.weight for k in govde.criteria)
    if toplam != 100:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Kriter agirliklarinin toplami 100 olmali (su an {toplam}).",
        )

    # Kriterler AI kriter puanlamasinin rubrigi; analizden sonra degistirmek
    # ayni yarismadaki raporlari FARKLI olcutlerle puanlar.
    yeniden = _kural_degisimini_dogrula(db, y, govde.confirm_reanalysis)

    # Tam degistirme: eskiler silinip yenileri yaziliyor. Kismi guncelleme
    # yerine bunu sectik cunku agirlik toplaminin 100 kalmasi gerekiyor ve
    # tek tek guncellemede ara durumlar gecersiz olurdu.
    for eski in list(y.criteria_list):
        db.delete(eski)
    db.flush()

    for i, k in enumerate(govde.criteria):
        db.add(
            models.CompetitionCriterion(
                id=str(uuid.uuid4()),
                competition_id=y.id,
                title=k.title,
                description=k.description,
                weight=k.weight,
                display_order=i,
            )
        )
    db.commit()
    if yeniden:
        _yeniden_analiz_kuyrukla(db, background_tasks, yeniden)
    db.refresh(y)
    return _yanit(y)


# Yonetici sablon dosyasi yukleyip formu otomatik doldurabilsin diye kabul
# edilen turler. .doc (eski ikili bicim) OKUNMUYOR - cikaricinin kendisi bunu
# net bir mesajla soyluyor, sessizce bos donmuyor.
_SABLON_UZANTILARI = (".docx", ".pdf")


@router.post("/{competition_id}/template/extract", response_model=schemas.TemplateExtractResult)
async def extract_template(
    competition_id: str,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(_YONETICI),
):
    """Resmi rapor sablonundan zorunlu basliklari ve kriter agirliklarini cikarir.

    KAYDETMIYOR - yalnizca oneri doner. Yonetici listeyi gorup duzenledikten
    sonra normal /template ve /criteria uc noktalariyla kaydediyor.

    NEDEN OTOMATIK KAYDETMIYORUZ: cikarim heuristik. TEKNOFEST sablonlarinda
    alt basliklar ana basliklarla AYNI Word stilini kullanabiliyor ve naif
    toplama 130 verebiliyor (olculdu: sablon_OTR_2026.docx). Cikarici bunu
    duzeltiyor ama her sablon icin garanti edemez; son soz yoneticide olmali.
    Ayrica bu, sistemin "AI karar vermez, insan karar verir" ilkesiyle de
    tutarli.
    """
    y = db.query(models.Competition).filter(models.Competition.id == competition_id).first()
    if not y:
        raise HTTPException(status_code=404, detail="Yarisma bulunamadi.")

    uzanti = os.path.splitext(file.filename or "")[1].lower()
    if uzanti not in _SABLON_UZANTILARI:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Desteklenmeyen dosya turu ({uzanti or 'bilinmiyor'}). "
                "Resmi sablonu .docx ya da .pdf olarak yukleyin."
            ),
        )

    # Gecici dosyaya yaziyoruz: cikarici bir YOL istiyor (zipfile/pdfplumber
    # ikisi de dosya yolu ile calisiyor) ve bu dosyanin saklanmasina gerek yok.
    with tempfile.NamedTemporaryFile(suffix=uzanti, delete=False) as gecici:
        shutil.copyfileobj(file.file, gecici)
        gecici_yol = gecici.name
    try:
        sonuc = ai.extract_template(gecici_yol)
    finally:
        try:
            os.remove(gecici_yol)
        except OSError:
            pass

    return {
        "required_headings": sonuc["basliklar"],
        "criteria": [
            {"title": k["baslik"], "weight": k["agirlik"]} for k in sonuc["kriterler"]
        ],
        "weight_total": sonuc["agirlik_toplami"],
        "source": sonuc["kaynak"],
        "warnings": sonuc["uyarilar"],
    }


@router.put("/{competition_id}/status", response_model=schemas.CompetitionResponse)
def set_status(
    competition_id: str,
    govde: schemas.CompetitionStatusUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(_YONETICI),
):
    """Yarismanin asamasini degistirir.

    'open' yapabilmek icin sablon kurallari ve kriterler TANIMLI olmali:
    kurallar olmadan basvuru acilirsa AI analizi neye gore kontrol
    yapacagini bilemez ve yarismaci bos bir degerlendirme alir.
    """
    y = db.query(models.Competition).filter(models.Competition.id == competition_id).first()
    if not y:
        raise HTTPException(status_code=404, detail="Yarisma bulunamadi.")
    if govde.status not in ASAMALAR:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Gecersiz asama. Gecerli asamalar: {', '.join(ASAMALAR)}.",
        )

    if govde.status == "open":
        eksikler = []
        if not _json_yukle(y.required_headings, []):
            eksikler.append("zorunlu basliklar")
        if not y.criteria_list:
            eksikler.append("degerlendirme kriterleri")
        if eksikler:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    "Basvuruyu acmadan once su tanimlar yapilmali: "
                    + ", ".join(eksikler)
                    + ". (Kriter ve Sablon Tanimi ekrani)"
                ),
            )

    # GERI DONUS KORUMASI. Asamalar arasinda ileri gitmek serbest, ama karar
    # verilmis bir yarismayi geri almak degil: 'completed' -> 'open' hicbir
    # engel olmadan calisiyordu ve sonuclar aciklandiktan SONRA basvurulari
    # yeniden aciyordu. Hakemler degerlendirmesini bitirmisken gelen yeni
    # raporlar hic degerlendirilmez, mevcut kararlar da yarim kalirdi.
    if ASAMALAR.index(govde.status) < ASAMALAR.index(y.status):
        karar_sayisi = (
            db.query(models.FinalDecision)
            .join(models.Report, models.FinalDecision.report_id == models.Report.id)
            .filter(models.Report.competition_id == competition_id)
            .count()
        )
        if karar_sayisi:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    f"Bu yarismada {karar_sayisi} hakem karari verilmis; asama "
                    f"'{y.status}' konumundan '{govde.status}' konumuna geri "
                    "alinamaz. Karar verilmis bir yarismanin basvurularini "
                    "yeniden acmak mevcut degerlendirmeleri gecersiz kilar."
                ),
            )

    y.status = govde.status
    db.commit()
    db.refresh(y)
    return _yanit(y)


def yarismanin_kurallari(y: Optional[models.Competition]) -> Optional[dict]:
    """Yarismanin sablon kurallarini ai-doc-analysis'in bekledigi bicime cevirir.

    Yarisma yoksa ya da HIC sablon tanimi yapilmadiysa None doner; o durumda
    analiz modulu docs/mvp-rules.json'daki varsayilanlari kullanir.

    ONCEDEN NE KIRIKTI: yalnizca `required_headings` bos diye TUM kurallar
    atiliyordu. Yonetici "Ingilizce de kabul, en fazla 20 sayfa" tanimlayip
    zorunlu baslik listesini bos biraksa, raporu hicbir uyari olmadan
    sabit TEKNOFEST varsayilanlarina (yalnizca Turkce, TEKNOFEST basliklari)
    gore degerlendiriliyordu - yani kendi yazdigi kurallarin tam tersine.
    Artik sablonun HERHANGI bir alani doluysa yarismanin kurallari
    kullaniliyor; baslik listesi bossa "zorunlu baslik yok" olarak
    uygulaniyor, cunku yoneticinin tanimi bu.
    """
    if y is None:
        return None
    basliklar = _json_yukle(y.required_headings, [])
    tanimli = any(
        deger is not None
        for deger in (
            y.accepted_languages,
            y.required_headings,
            y.heading_synonyms,
            y.min_pages,
            y.max_pages,
            y.min_section_chars,
        )
    )
    if not tanimli:
        return None
    return {
        "kabul_edilen_diller": _json_yukle(y.accepted_languages, ["tr"]),
        "zorunlu_basliklar": basliklar,
        "esanlamli_basliklar": _json_yukle(y.heading_synonyms, {}),
        "min_sayfa": y.min_pages if y.min_pages is not None else 0,
        "max_sayfa": y.max_pages if y.max_pages is not None else 10**9,
        "min_bolum_karakter": y.min_section_chars if y.min_section_chars is not None else 30,
    }
