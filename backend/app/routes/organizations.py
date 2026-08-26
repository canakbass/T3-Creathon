"""Kurum sorumlusunun (ORG_OWNER) kendi kurumunu yonetmesi.

KULLANICININ ISTEDIGI SEY: "asdfghjkl hesabi gibi superuserlar olmali, bu
superuserlar her role bakabilmeli ve KENDI KURUMUNDAKI hakemler, yoneticiler,
degerlendirme yoneticileri gibi herkesi degistirebilmeli, ekleyebilmeli."

NEDEN GEREKIYORDU: dort rol "bu kurumda kim ne yapar" sorusunu cevapliyordu
ama "bu kurumda KIM VAR" sorusunu kimse cevaplamiyordu. Hesap acma yetkisi
yarisma yoneticisindeydi ve her yonetici sinirsiz yonetici uretebiliyordu -
yetki zinciri kendi kendini cogaltiyordu. Kurum sorumlusu bu zincirin kokunu
tutuyor.

"SUPERUSER" AMA KURUM ICINDE. Bu rol sistem yoneticisi DEGIL: baska bir
kurumun tek bir kaydini bile goremez. Her uc nokta kurumu TOKENDEN aliyor;
yol ya da govdede kurum kimligi kabul eden bir uc nokta YOK - olsaydi
"superuser" sifati kurum sinirini asmanin anahtari olurdu.

BURADA OLMAYAN SEY: kurum ACMA. Bir uc noktadan kurum acilabilse, hesabi
olan herkes yeni kiraci uretebilirdi; ustelik kendini o kurumun sorumlusu
yapardi. Kurum acmak bir isletme karari - `scripts/kurum-ac.py` ile
yapiliyor.
"""

import uuid
from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from ..database import get_db
from .. import models, schemas, auth, tenancy

router = APIRouter(prefix="/api/organizations", tags=["Organizations"])

_SORUMLU = auth.RoleChecker(["ORG_OWNER"])


def _kurum(db: Session, current_user) -> models.Organization:
    kurum_id = tenancy.aktif_kurum(current_user)
    kurum = (
        db.query(models.Organization)
        .filter(models.Organization.id == kurum_id)
        .first()
        if kurum_id
        else None
    )
    if kurum is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "Aktif kurum belirsiz. Cikip tekrar giris yapin "
                "(kurum secimi token'da tasiniyor)."
            ),
        )
    return kurum


@router.get("/me", response_model=schemas.OrganizationResponse)
def get_my_organization(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    """"Kimin yarismasi bu tam olarak??" sorusunun cevabi.

    Her role acik (yalnizca sorumluya degil): arayuz "T3 Vakfi adina
    calisiyorsunuz" yazabilsin. Kullanici hangi kurum adina islem yaptigini
    her an gormeli - yanlis kurumda islem yapmak baska bir kurumun verisine
    dokunmak demek.
    """
    kurum = _kurum(db, current_user)
    return {
        "id": kurum.id,
        "name": kurum.name,
        "slug": kurum.slug,
        "my_roles": current_user.roles_in(kurum.id),
        "member_count": len(
            {
                r.user_id
                for r in db.query(models.UserRole)
                .filter(models.UserRole.organization_id == kurum.id)
                .all()
            }
        ),
    }


@router.get("/me/members", response_model=List[schemas.OrganizationMember])
def list_members(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(_SORUMLU),
):
    """Kurumun uyeleri ve rolleri.

    YALNIZCA SORUMLUYA: bu liste kurumun tum e-posta rehberi. Yarisma
    yoneticisine de acsaydik, hesabi ele geciren biri once rehberi indirir
    sonra hedefli saldiriya gecerdi.
    """
    kurum = _kurum(db, current_user)
    kayitlar = (
        db.query(models.UserRole)
        .filter(models.UserRole.organization_id == kurum.id)
        .all()
    )
    roller_map: dict[str, list] = {}
    for k in kayitlar:
        roller_map.setdefault(k.user_id, []).append(k.role)

    if not roller_map:
        return []
    kullanicilar = (
        db.query(models.User).filter(models.User.id.in_(list(roller_map))).all()
    )
    return sorted(
        (
            {
                "id": u.id,
                "email": u.email,
                "full_name": u.full_name,
                "roles": sorted(roller_map.get(u.id, [])),
            }
            for u in kullanicilar
        ),
        key=lambda x: x["email"],
    )


def _uye_getir(db: Session, user_id: str, kurum_id: str) -> models.User:
    """Kurumun uyesi olan kullaniciyi getirir.

    KURUMUN UYESI OLMAYAN "YOK"TUR. Baska kurumun kullanicisi icin ayri bir
    mesaj donseydi, sorumlu rastgele kimlikler deneyerek sistemdeki butun
    hesaplari sayabilirdi (varlik kahini).
    """
    kullanici = db.query(models.User).filter(models.User.id == user_id).first()
    if kullanici is None or not kullanici.roles_in(kurum_id):
        raise tenancy.yoksa_gibi_davran("Bu kurumda boyle bir uye yok.")
    return kullanici


@router.post(
    "/me/members/{user_id}/roles",
    response_model=schemas.OrganizationMember,
    status_code=status.HTTP_201_CREATED,
)
def grant_role(
    user_id: str,
    govde: schemas.RoleGrant,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(_SORUMLU),
):
    """Kurum uyesine rol ekler. Yalnizca BU kurumda gecerli olur.

    Ayni kisi baska bir kurumda bambaska rollere sahip olabilir ve buradan
    verilen rol oraya GECMEZ: A kurumundaki hakemlik B kurumunda hicbir sey
    ifade etmiyor.
    """
    kurum = _kurum(db, current_user)
    if govde.role not in models.ROLLER:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Gecersiz rol. Gecerli roller: {', '.join(models.ROLLER)}.",
        )
    kullanici = _uye_getir(db, user_id, kurum.id)
    if govde.role in kullanici.roles_in(kurum.id):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Bu uye bu kurumda zaten bu role sahip.",
        )
    db.add(
        models.UserRole(
            id=str(uuid.uuid4()),
            user_id=kullanici.id,
            organization_id=kurum.id,
            role=govde.role,
        )
    )
    db.commit()
    db.refresh(kullanici)
    return {
        "id": kullanici.id,
        "email": kullanici.email,
        "full_name": kullanici.full_name,
        "roles": kullanici.roles_in(kurum.id),
    }


@router.delete("/me/members/{user_id}/roles/{role}", response_model=schemas.OrganizationMember)
def revoke_role(
    user_id: str,
    role: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(_SORUMLU),
):
    """Kurum uyesinin rolunu kaldirir.

    IKI KORUMA:

    1. SON SORUMLU KALDIRILAMAZ. Kurum sorumlusuz kalirsa uye yonetimi
       tamamen kilitlenir ve kurtarmanin API yolu yoktur - veri tabanina elle
       girmek gerekir. Bu, tek bir yanlis tiklamayla ulasilabilecek bir durum
       olmamali.

    2. KENDI SORUMLULUGUNU KALDIRMAK: engellenmiyor ama 1. kural yine
       gecerli. Yani devri once yeni sorumluyu atayarak yapiyorsunuz;
       "kendini kilitleme" ihtimali kalmiyor.
    """
    kurum = _kurum(db, current_user)
    kullanici = _uye_getir(db, user_id, kurum.id)
    kayit = (
        db.query(models.UserRole)
        .filter(
            models.UserRole.user_id == kullanici.id,
            models.UserRole.organization_id == kurum.id,
            models.UserRole.role == role,
        )
        .first()
    )
    if kayit is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Bu uyenin bu kurumda boyle bir rolu yok.",
        )

    if role == "ORG_OWNER":
        sorumlu_sayisi = (
            db.query(models.UserRole)
            .filter(
                models.UserRole.organization_id == kurum.id,
                models.UserRole.role == "ORG_OWNER",
            )
            .count()
        )
        if sorumlu_sayisi <= 1:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    "Kurumun son sorumlusu kaldirilamaz. Once baska bir uyeye "
                    "ORG_OWNER rolu verin; kurum sorumlusuz kalirsa uye "
                    "yonetimi kilitlenir."
                ),
            )

    db.delete(kayit)
    db.commit()
    db.refresh(kullanici)
    return {
        "id": kullanici.id,
        "email": kullanici.email,
        "full_name": kullanici.full_name,
        "roles": kullanici.roles_in(kurum.id),
    }
