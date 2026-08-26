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
from .. import models, schemas, auth, tenancy

router = APIRouter(prefix="/api/assignments", tags=["Assignments"])

# Atama islemlerini yalnizca yarismayi yoneten roller yapabilir.
_YONETICI = auth.RoleChecker(list(models.YONETICI_ROLLERI))


def _rapor_getir_yetkiliyse(report_id: str, user, db: Session) -> models.Report:
    """Raporu getirir; yabanci kurumunsa YOKMUS gibi 404 doner.

    Atama uc noktalari raporu dogrudan sorguluyordu; boylece bir kurumun
    yoneticisi BASKA bir kurumun raporunun hakemini degistirebiliyordu.
    Rapor okunmuyor olsa bile bu bir sizinti: atama yaniti hakemin
    e-postasini donduruyor ve 400/404 farki raporun varligini dogruluyor.
    """
    rapor = db.query(models.Report).filter(models.Report.id == report_id).first()
    if rapor is None or not tenancy.ayni_kurum_mu(rapor, user):
        raise tenancy.yoksa_gibi_davran("Rapor bulunamadi.")
    return rapor


def _hakem_mi(db: Session, user_id: str, user) -> bool:
    """Bu kisi ISTEGIN YAPILDIGI KURUMDA hakem mi?

    Onceden kurum sorulmuyordu, yani "hakem" demek "HERHANGI bir kurumda
    hakem" demekti. Bu, bir kurumun raporunu baska kurumun hakemine atamayi
    mumkun kiliyordu - kurum sinirini asmanin en sessiz yolu, cunku atamayi
    yapan yonetici hakemin hangi kurumda oldugunu hicbir yerde gormuyordu.
    """
    return user_id in tenancy.kurumun_rolleri(db, tenancy.aktif_kurum(user), "REFEREE")


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
    # Kurumun hakemleri: bu liste ad-soyad ve E-POSTA donduruyor. Kurum
    # kapsami olmadan, herhangi bir kurumun yoneticisi butun sistemin hakem
    # rehberini indirebilirdi.
    kurum_hakemleri = set(
        tenancy.kurumun_rolleri(db, tenancy.aktif_kurum(current_user), "REFEREE")
    )

    if competition_id:
        # Yarismayi da kapidan geciriyoruz: yoksa yabanci kurumun yarisma
        # kimligi verilerek o yarismanin hakem listesi okunabilirdi.
        tenancy.yarisma_getir_yetkiliyse(competition_id, current_user, db)
        kayitlar = (
            db.query(models.CompetitionReferee)
            .filter(models.CompetitionReferee.competition_id == competition_id)
            .all()
        )
        hakemler = [k.referee for k in kayitlar if k.referee]
    else:
        hakemler = (
            db.query(models.User).filter(models.User.id.in_(kurum_hakemleri)).all()
            if kurum_hakemleri
            else []
        )
    hakemler = [h for h in hakemler if h.id in kurum_hakemleri]

    sonuc = []
    for h in hakemler:
        # YUK SAYACI DA KURUMLA SINIRLI. Kimlerin listelendigi zaten
        # kurumluydu ama sayac degildi: iki kurumda birden hakem olan biri
        # icin, B kurumunun yoneticisi A kurumundaki yukunu okuyordu -
        # ustelik sayacin zaman icindeki artisi A'nin atama hareketini de
        # ele veriyordu. Gosterge sayaclari icin ayni gerekceyle
        # kapatilmisti; burasi atlanmisti.
        q = (
            tenancy.kurum_filtresi(db.query(models.Assignment), models.Report, current_user)
            .join(models.Report, models.Assignment.report_id == models.Report.id)
            .filter(models.Assignment.referee_id == h.id)
        )
        if competition_id:
            q = q.filter(models.Report.competition_id == competition_id)
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
    yarisma = tenancy.yarisma_getir_yetkiliyse(competition_id, current_user, db)

    hakem = db.query(models.User).filter(models.User.id == govde.referee_id).first()
    # "Bu kurumun hakemi degil" ile "boyle bir kullanici yok" AYNI cevabi
    # veriyor: ayirt edilebilseydi, yonetici rastgele kimlikler deneyerek
    # sistemdeki hesaplarin varligini dogrulayabilirdi.
    if not hakem or not _hakem_mi(db, hakem.id, current_user):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Bu kurumda hakem rolune sahip boyle bir kullanici yok.",
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
    yarisma = tenancy.yarisma_getir_yetkiliyse(competition_id, current_user, db)

    hakem_kayitlari = (
        db.query(models.CompetitionReferee)
        .filter(models.CompetitionReferee.competition_id == competition_id)
        .all()
    )
    # ROLU HALA DURUYOR MU: `CompetitionReferee` satiri, kisinin hakem rolu
    # geri alindiginda SILINMIYOR. Bu liste dogrudan kullanildiginda rapor,
    # artik giris yapip goremeyecek birine atanuyordu - rapor sessizce
    # sirada kaliyor, kimse bakmadigi icin de fark edilmiyordu.
    kurum_hakemleri = set(
        tenancy.kurumun_rolleri(db, tenancy.aktif_kurum(current_user), "REFEREE")
    )
    hakemler = [
        k.referee for k in hakem_kayitlari if k.referee and k.referee.id in kurum_hakemleri
    ]
    if not hakemler:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "Bu yarismada gorevli ve hakem rolu duran kimse yok. "
                "Once hakem ekleyin."
            ),
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
        tenancy.kurum_filtresi(db.query(models.Report), models.Report, current_user)
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
    rapor = _rapor_getir_yetkiliyse(report_id, current_user, db)

    hakem = db.query(models.User).filter(models.User.id == govde.referee_id).first()
    if not hakem or not _hakem_mi(db, hakem.id, current_user):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Bu kurumda hakem rolune sahip boyle bir kullanici secin.",
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
    # Once RAPORU kapidan geciriyoruz, sonra atamaya bakiyoruz. Ters sirada
    # olsaydi yabanci kurumun raporu icin "Bu rapor icin atama yok." (404)
    # ile "atamasi kaldirilamaz" (400) farkli cevaplar verir; ikisi arasindaki
    # fark, baska kurumun raporunun ATANMIS olup olmadigini sizdirirdi.
    rapor = _rapor_getir_yetkiliyse(report_id, current_user, db)
    atama = rapor.assignment
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
