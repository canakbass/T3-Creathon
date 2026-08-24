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
import uuid
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from ..database import get_db
from .. import models, schemas, auth

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
        "status": y.status,
        "submission_deadline": y.submission_deadline,
        "created_at": y.created_at,
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
    kategori = db.query(models.Category).filter(
        models.Category.id == govde.category_id
    ).first()
    if not kategori:
        raise HTTPException(status_code=404, detail="Kategori bulunamadi.")

    y = models.Competition(
        id=f"COMP-{str(uuid.uuid4())[:8].upper()}",
        name=govde.name,
        description=govde.description,
        category_id=govde.category_id,
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


@router.put("/{competition_id}/template", response_model=schemas.CompetitionResponse)
def set_template(
    competition_id: str,
    govde: schemas.CompetitionTemplate,
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

    y.accepted_languages = json.dumps(govde.accepted_languages, ensure_ascii=False)
    y.required_headings = json.dumps(govde.required_headings, ensure_ascii=False)
    y.heading_synonyms = json.dumps(govde.heading_synonyms or {}, ensure_ascii=False)
    y.min_pages = govde.min_pages
    y.max_pages = govde.max_pages
    y.min_section_chars = govde.min_section_chars
    db.commit()
    db.refresh(y)
    return _yanit(y)


@router.put("/{competition_id}/criteria", response_model=schemas.CompetitionResponse)
def set_criteria(
    competition_id: str,
    govde: schemas.CompetitionCriteriaSet,
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
    db.refresh(y)
    return _yanit(y)


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

    y.status = govde.status
    db.commit()
    db.refresh(y)
    return _yanit(y)


def yarismanin_kurallari(y: Optional[models.Competition]) -> Optional[dict]:
    """Yarismanin sablon kurallarini ai-doc-analysis'in bekledigi bicime cevirir.

    Yarisma yoksa ya da kurallari tanimli degilse None doner; o durumda
    analiz modulu docs/mvp-rules.json'daki varsayilanlari kullanir.
    """
    if y is None:
        return None
    basliklar = _json_yukle(y.required_headings, [])
    if not basliklar:
        return None
    return {
        "kabul_edilen_diller": _json_yukle(y.accepted_languages, ["tr"]),
        "zorunlu_basliklar": basliklar,
        "esanlamli_basliklar": _json_yukle(y.heading_synonyms, {}),
        "min_sayfa": y.min_pages if y.min_pages is not None else 0,
        "max_sayfa": y.max_pages if y.max_pages is not None else 10**9,
        "min_bolum_karakter": y.min_section_chars if y.min_section_chars is not None else 30,
    }
