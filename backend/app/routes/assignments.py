"""Rapor-hakem atamasi.

NEDEN VAR: onceden atama diye bir sey YOKTU - her hakem her raporu
goruyordu. Gercek bir degerlendirme surecinde raporlar hakemler arasinda
dagitilir ve her hakem yalnizca kendi sorumlulugundakini gorur.

AKIS:
  1. Yarisma Yoneticisi yarismaya hakem ekler (POST /referees)
  2. Raporlar geldikce otomatik dagitilir (POST /auto-assign) - en az yuku
     olan hakeme gider, boylece dagilim dengeli kalir
  3. Yonetici gerekirse tek bir raporun hakemini degistirir (PUT /{report_id})
"""

import hashlib
import uuid
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from ..database import get_db
from .. import models, schemas, auth

router = APIRouter(prefix="/api/assignments", tags=["Assignments"])

# Atama islemlerini yalnizca yarismayi yoneten roller yapabilir.
_YONETICI = auth.RoleChecker(["COMPETITION_MANAGER", "EVALUATION_MANAGER"])


def _hakem_mi(db: Session, user_id: str) -> bool:
    return (
        db.query(models.UserRole)
        .filter(models.UserRole.user_id == user_id, models.UserRole.role == "REFEREE")
        .first()
        is not None
    )


@router.get("/referees", response_model=List[schemas.RefereeSummary])
def list_referees(
    competition_id: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(_YONETICI),
):
    """Hakemleri ve uzerlerindeki rapor sayisini listeler.

    `competition_id` verilirse yalnizca o yarismada gorevli hakemler doner.
    Yuk bilgisi, yoneticinin dagilimi gorup elle mudahale edebilmesi icin.
    """
    if competition_id:
        kayitlar = (
            db.query(models.CompetitionReferee)
            .filter(models.CompetitionReferee.competition_id == competition_id)
            .all()
        )
        hakemler = [k.referee for k in kayitlar if k.referee]
    else:
        hakem_idleri = [
            r.user_id
            for r in db.query(models.UserRole)
            .filter(models.UserRole.role == "REFEREE")
            .all()
        ]
        hakemler = (
            db.query(models.User).filter(models.User.id.in_(hakem_idleri)).all()
            if hakem_idleri
            else []
        )

    sonuc = []
    for h in hakemler:
        q = db.query(models.Assignment).filter(models.Assignment.referee_id == h.id)
        if competition_id:
            q = q.join(models.Report).filter(models.Report.competition_id == competition_id)
        sonuc.append(
            {
                "id": h.id,
                "email": h.email,
                "full_name": h.full_name,
                "assigned_count": q.count(),
            }
        )
    # En az yuklu once: yonetici kime atayacagina bakarken faydali
    sonuc.sort(key=lambda x: x["assigned_count"])
    return sonuc


@router.post(
    "/competitions/{competition_id}/referees",
    status_code=status.HTTP_201_CREATED,
    response_model=schemas.RefereeSummary,
)
def add_referee_to_competition(
    competition_id: str,
    govde: schemas.RefereeAdd,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(_YONETICI),
):
    """Yarismaya hakem ekler. Atama yalnizca bu listedekilere yapilabilir."""
    yarisma = db.query(models.Competition).filter(
        models.Competition.id == competition_id
    ).first()
    if not yarisma:
        raise HTTPException(status_code=404, detail="Yarisma bulunamadi.")

    hakem = db.query(models.User).filter(models.User.id == govde.referee_id).first()
    if not hakem:
        raise HTTPException(status_code=404, detail="Kullanici bulunamadi.")
    if not _hakem_mi(db, hakem.id):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"{hakem.email} hakem rolune sahip degil.",
        )

    zaten = (
        db.query(models.CompetitionReferee)
        .filter(
            models.CompetitionReferee.competition_id == competition_id,
            models.CompetitionReferee.referee_id == hakem.id,
        )
        .first()
    )
    if zaten:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Bu hakem yarismada zaten gorevli.",
        )

    db.add(
        models.CompetitionReferee(
            id=str(uuid.uuid4()), competition_id=competition_id, referee_id=hakem.id
        )
    )
    db.commit()
    return {
        "id": hakem.id,
        "email": hakem.email,
        "full_name": hakem.full_name,
        "assigned_count": 0,
    }


@router.post(
    "/competitions/{competition_id}/auto-assign",
    response_model=schemas.AutoAssignResult,
)
def auto_assign(
    competition_id: str,
    secenekler: Optional[schemas.AutoAssignOptions] = None,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(_YONETICI),
):
    """Yarismanin ATANMAMIS raporlarini hakemler arasinda dengeli dagitir.

    Dagitim, "en az yuku olana ver" kuralina gore yapiliyor. Bu, mevcut
    yuku de hesaba kattigi icin elle yapilmis atamalardan sonra calistirilsa
    bile dengeyi bozmuyor. ZATEN ATANMIS raporlara dokunmuyor - yoneticinin
    elle yaptigi atama korunur.
    """
    yarisma = db.query(models.Competition).filter(
        models.Competition.id == competition_id
    ).first()
    if not yarisma:
        raise HTTPException(status_code=404, detail="Yarisma bulunamadi.")

    hakem_kayitlari = (
        db.query(models.CompetitionReferee)
        .filter(models.CompetitionReferee.competition_id == competition_id)
        .all()
    )
    hakemler = [k.referee for k in hakem_kayitlari if k.referee]
    if not hakemler:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Bu yarismada gorevli hakem yok. Once hakem ekleyin.",
        )

    secenekler = secenekler or schemas.AutoAssignOptions()
    havuz_daraltildi = False

    # HAVUZU ELLE SEC: yonetici "bu dagitima yalnizca su hakemler girsin"
    # diyebilmeli (uzmanlik alani, musaitlik, cikar catismasi...).
    if secenekler.referee_ids:
        istenen = set(secenekler.referee_ids)
        gorevli_kimlikler = {h.id for h in hakemler}
        yabanci = istenen - gorevli_kimlikler
        if yabanci:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    f"{len(yabanci)} hakem bu yarismada gorevli degil. "
                    "Once yarismaya ekleyin."
                ),
            )
        hakemler = [h for h in hakemler if h.id in istenen]
        havuz_daraltildi = True

    atanmamis = (
        db.query(models.Report)
        .outerjoin(models.Assignment)
        .filter(
            models.Report.competition_id == competition_id,
            models.Assignment.id.is_(None),
        )
        .order_by(models.Report.submission_date)
        .all()
    )

    # Mevcut yuk (bu yarismadaki)
    yuk = {}
    for h in hakemler:
        yuk[h.id] = (
            db.query(models.Assignment)
            .join(models.Report)
            .filter(
                models.Assignment.referee_id == h.id,
                models.Report.competition_id == competition_id,
            )
            .count()
        )

    # "EN AZ YUKLU N HAKEM": kullanicinin "rastgele en az projeden sorumlu
    # olan hakeme direkt ekleyebilsin" istegi. Yuk hesaplandiktan SONRA
    # uygulaniyor - once yuke gore siralayip sonra kesiyoruz.
    if secenekler.limit_least_loaded:
        hakemler = sorted(hakemler, key=lambda h: (yuk[h.id], h.email))[
            : secenekler.limit_least_loaded
        ]
        havuz_daraltildi = True

    yeni = []
    atlanan = []
    for rapor in atanmamis:
        # CIKAR CATISMASI: raporu yukleyen kisi kendi raporunun hakemi
        # olamaz. Ayni hesabin hem COMPETITOR hem REFEREE rolu olabildigi
        # icin bu gercek bir durum (deneme hesaplarinda oldugu gibi) -
        # onceden bir kullanici kendi raporunu yukleyip kendine atanip
        # kendine 100 verebiliyordu.
        uygun = [h for h in hakemler if not rapor.cikar_catismasi_var_mi(h)]
        if not uygun:
            atlanan.append(
                {
                    "report_id": rapor.id,
                    "reason": (
                        "Havuzdaki tek uygun hakem raporun sahibi takimda; cikar "
                        "catismasi nedeniyle atanmadi. "
                        + (
                            "Dagitim havuzunu genisletin ya da bu raporu elle atayin."
                            if havuz_daraltildi
                            else "Yarismaya baska bir hakem ekleyin."
                        )
                    ),
                }
            )
            continue
        # En az yuklu hakem. Esitlikte RAPOR BAZLI deterministik secim:
        # alfabetik e-posta siralamasi, esit yuklu hakemler arasinda hep
        # ayni kisiyi one aliyordu - yani "adi 'a' ile baslayan hakem" her
        # esitligi kazaniyordu. Rapor kimligiyle harmanlanmis sira hem
        # dagilimi esitliyor hem de tekrarlanabilir kaliyor (ayni girdi ->
        # ayni dagitim; testler ve denetim icin sart).
        hedef = min(
            uygun,
            key=lambda h: (
                yuk[h.id],
                hashlib.sha256(f"{rapor.id}:{h.id}".encode()).hexdigest(),
            ),
        )
        db.add(
            models.Assignment(
                id=str(uuid.uuid4()),
                report_id=rapor.id,
                referee_id=hedef.id,
                assigned_by_id=current_user.id,
                auto_assigned=True,
            )
        )
        yuk[hedef.id] += 1
        yeni.append({"report_id": rapor.id, "referee_id": hedef.id, "referee_email": hedef.email})

    db.commit()
    return {
        "assigned": len(yeni),
        "assignments": yeni,
        "skipped": atlanan,
        "load": [
            {"referee_id": h.id, "email": h.email, "assigned_count": yuk[h.id]}
            for h in sorted(hakemler, key=lambda x: x.email)
        ],
    }


@router.put("/{report_id}", response_model=schemas.AssignmentResponse)
def reassign(
    report_id: str,
    govde: schemas.AssignmentUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(_YONETICI),
):
    """Bir raporun sorumlu hakemini degistirir (ya da ilk kez atar).

    Yonetici, dagitim otomatik yapilmis olsa bile tek tek mudahale
    edebilmeli - orn. cikar catismasi ya da uzmanlik alani nedeniyle.
    """
    rapor = db.query(models.Report).filter(models.Report.id == report_id).first()
    if not rapor:
        raise HTTPException(status_code=404, detail="Rapor bulunamadi.")

    hakem = db.query(models.User).filter(models.User.id == govde.referee_id).first()
    if not hakem or not _hakem_mi(db, hakem.id):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Gecerli bir hakem secin.",
        )

    # CIKAR CATISMASI: kimse kendi raporunun hakemi olamaz. Elle atamada da
    # gecerli - otomatik dagitimda engelleyip burada birakmak, kurali tek
    # bir tiklamayla asilabilir hale getirirdi.
    if rapor.cikar_catismasi_var_mi(hakem):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "Bir hakem kendi takiminin (ya da kendi yukledigi) raporunu "
                "degerlendiremez (cikar catismasi). Baska bir hakem secin."
            ),
        )

    # Karar verilmis raporun hakemi degistirilemez: karar zaten kayitli ve
    # baska bir hakeme devretmek denetim izini bozar.
    if rapor.final_decision is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Bu rapor icin nihai karar verilmis; hakemi degistirilemez.",
        )

    # Hakem, yarismanin GOREVLI HAKEM listesinde olmali. Arayuz zaten
    # yalnizca bu listeyi gosteriyor; API'de kontrol yoktu, yani dogrudan
    # istekle listede olmayan birine atama yapilabiliyordu. O kisi
    # auto-assign'in yuk hesabina hic girmedigi icin dagitim da bozulurdu.
    if rapor.competition_id:
        gorevli = (
            db.query(models.CompetitionReferee)
            .filter(
                models.CompetitionReferee.competition_id == rapor.competition_id,
                models.CompetitionReferee.referee_id == hakem.id,
            )
            .first()
        )
        if not gorevli:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    "Bu hakem yarismanin gorevli hakem listesinde degil. "
                    "Once hakemi yarismaya ekleyin."
                ),
            )

    atama = rapor.assignment
    if atama:
        atama.referee_id = hakem.id
        atama.assigned_by_id = current_user.id
        atama.auto_assigned = False
    else:
        atama = models.Assignment(
            id=str(uuid.uuid4()),
            report_id=rapor.id,
            referee_id=hakem.id,
            assigned_by_id=current_user.id,
            auto_assigned=False,
        )
        db.add(atama)
    db.commit()
    db.refresh(atama)
    return _atama_yaniti(atama)


@router.delete("/{report_id}", status_code=status.HTTP_204_NO_CONTENT)
def unassign(
    report_id: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(_YONETICI),
):
    """Atamayi kaldirir (rapor tekrar dagitilmamis havuza doner)."""
    atama = db.query(models.Assignment).filter(
        models.Assignment.report_id == report_id
    ).first()
    if not atama:
        raise HTTPException(status_code=404, detail="Bu rapor icin atama yok.")

    # PUT'taki "karar verilmis rapor devredilemez" kuralinin ayni gerekcesi
    # burada da gecerli - ustelik DELETE + PUT ikilisi o kurali tamamen
    # atlatmanin yolu oluyordu: once atamayi sil, sonra baskasina ata.
    # Karar kaydi hangi hakemin verdigini tutuyor ama atamanin silinmesi
    # "bu raporu kim degerlendirdi" izini kopariyor.
    if atama.report and atama.report.final_decision is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "Bu rapor icin nihai karar verilmis; atamasi kaldirilamaz "
                "(denetim izi korunur)."
            ),
        )

    db.delete(atama)
    db.commit()


def _atama_yaniti(atama: models.Assignment) -> dict:
    return {
        "report_id": atama.report_id,
        "referee_id": atama.referee_id,
        "referee_email": atama.referee.email if atama.referee else None,
        "assigned_at": atama.assigned_at,
        "auto_assigned": atama.auto_assigned,
    }
