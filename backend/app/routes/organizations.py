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

KURUM ACMA ARTIK BURADA - VE BU BILINCLI BIR FIKIR DEGISIKLIGI.
Onceden "bir uc noktadan kurum acilabilse hesabi olan herkes kendini
sorumlu yaptigi kiraci uretirdi" diye reddedilmisti. O gerekce ARTIK
GECERLI DEGIL: kurum yalitimi kapandi, yeni acilan kurum BOMBOS ve sahibi
baska hicbir kurumun tek kaydini goremiyor. Tehlike "kurumu olmak" degildi,
"baska kuruma ULASMAK"ti.

Yerine gecen kosullar: e-posta DOGRULANMIS olmali (yoksa sahte adreslerle
sinirsiz kiraci uretilir) ve kisi basina bir ust sinir var.
`scripts/kurum-ac.py` duruyor - sunucu erisimi olanin ilk kurumu acmasi
icin hala gerekli.
"""

import re
import uuid
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func
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


# Bir sayfada kac uye. Kurumlar buyudukce "hepsini diz" calismaz: yuzlerce
# satir hem yavas hem okunamaz. Ust sinir, istemcinin `limit=100000` yazip
# sayfalamayi etkisiz kilmasini engelliyor.
_SAYFA_VARSAYILAN = 25
_SAYFA_EN_FAZLA = 100


@router.get("/me/members", response_model=schemas.OrganizationMemberPage)
def list_members(
    role: Optional[str] = Query(default=None, description="Yalnizca bu role sahip uyeler"),
    q: Optional[str] = Query(default=None, description="E-posta ya da adda gecen metin"),
    limit: int = Query(default=_SAYFA_VARSAYILAN, ge=1, le=_SAYFA_EN_FAZLA),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(_SORUMLU),
):
    """Kurumun uyeleri - SAYFALANMIS ve rol/metin ile filtrelenebilir.

    YALNIZCA SORUMLUYA: bu liste kurumun tum e-posta rehberi. Yarisma
    yoneticisine de acsaydik, hesabi ele geciren biri once rehberi indirir
    sonra hedefli saldiriya gecerdi.

    NEDEN SAYFALAMA VERI TABANINDA, ARAYUZDE DEGIL: butun uyeleri gonderip
    tarayicida kesmek, "sayfalama" gorunumu verirken rehberin TAMAMINI yine
    de tel uzerinden gecirir. Ayrica kurum buyudukce yanit buyur ve yavaslar.

    FILTRE ROLE GORE SAYIYOR: `total`, filtre uygulandiktan SONRAKI sayidir.
    Filtresiz toplami dondurseydik "3 sonuc bulundu" yazip 40 sayfa
    gosterirdik.
    """
    kurum = _kurum(db, current_user)

    if role is not None and role not in models.ROLLER:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Gecersiz rol. Gecerli roller: {', '.join(models.ROLLER)}.",
        )

    # Bu kurumdaki roller, kullanici basina toplaniyor. Sayfalama KULLANICI
    # basina yapilmali, UserRole SATIRI basina degil: iki rolu olan bir uye
    # tek satir gorunuyor ve iki sayfaya bolunmemeli.
    uye_sorgusu = (
        db.query(models.User)
        .join(models.UserRole, models.UserRole.user_id == models.User.id)
        .filter(models.UserRole.organization_id == kurum.id)
    )

    if role:
        uye_sorgusu = uye_sorgusu.filter(models.UserRole.role == role)

    if q and q.strip():
        # Arama, SAKLANAN katlanmis anahtara karsi yapiliyor (bkz.
        # models.User.search_key). `lower(email) LIKE ...` yazsaydik Turkce
        # calismazdi: SQLite'in `lower`i yalnizca ASCII kucultur ve "çift"
        # arayan biri "Çift Rollü Kişi"yi BULAMAZDI - bos sonuc, yanlis
        # sonuctan daha ikna edici oldugu icin en tehlikeli hata sinifi.
        #
        # Joker karakterler kacisliyor: arama kutusuna `%` yazan biri
        # filtreyi tamamen etkisiz kilmamali. "Filtreledim" sanan sorumluya
        # filtresiz liste gostermek yanlis karar aldirir.
        aranan = models.turkce_katla(q.strip())
        kacisli = aranan.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        uye_sorgusu = uye_sorgusu.filter(
            func.coalesce(models.User.search_key, "").like(f"%{kacisli}%", escape="\\")
        )

    # DISTINCT: iki rolu olan uye, rol filtresi yokken JOIN yuzunden iki kez
    # gelirdi - hem sayim hem sayfa yanlis olurdu.
    uye_sorgusu = uye_sorgusu.distinct()

    toplam = uye_sorgusu.count()
    kullanicilar = (
        uye_sorgusu.order_by(models.User.email).offset(offset).limit(limit).all()
    )

    # Roller AYRI bir sorguda: rol filtresi varken JOIN'den gelen roller
    # yalnizca filtrelenmis olanlar olurdu ve satirda "bu uyenin tek rolu
    # var" gibi YANLIS bir izlenim dogardi.
    kimlikler = [u.id for u in kullanicilar]
    roller_map: dict[str, list] = {}
    if kimlikler:
        for k in (
            db.query(models.UserRole)
            .filter(
                models.UserRole.organization_id == kurum.id,
                models.UserRole.user_id.in_(kimlikler),
            )
            .all()
        ):
            roller_map.setdefault(k.user_id, []).append(k.role)

    return {
        "items": [
            {
                "id": u.id,
                "email": u.email,
                "full_name": u.full_name,
                "roles": sorted(roller_map.get(u.id, [])),
            }
            for u in kullanicilar
        ],
        "total": toplam,
        "limit": limit,
        "offset": offset,
    }


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

    db.delete(kayit)

    if role == "ORG_OWNER":
        # SILDIKTEN SONRA SAYIYORUZ, once degil.
        #
        # Once sayip sonra silmek bir TOCTOU: iki es zamanli istek de "2
        # sorumlu var" gorup ikisi de silebilir ve kurum sorumlusuz kalir.
        # SQLite'ta yazma kilidi bunu ortuyor, PostgreSQL READ COMMITTED'da
        # ortmuyor. `flush` silmeyi ayni islem icinde veri tabanina yaziyor,
        # sayim onu goruyor ve kalmadiysa islemi geri aliyoruz.
        db.flush()
        kalan = (
            db.query(models.UserRole)
            .filter(
                models.UserRole.organization_id == kurum.id,
                models.UserRole.role == "ORG_OWNER",
            )
            .count()
        )
        if kalan == 0:
            db.rollback()
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    "Kurumun son sorumlusu kaldirilamaz. Once baska bir uyeye "
                    "ORG_OWNER rolu verin; kurum sorumlusuz kalirsa uye "
                    "yonetimi kilitlenir."
                ),
            )

    db.commit()
    db.refresh(kullanici)
    return {
        "id": kullanici.id,
        "email": kullanici.email,
        "full_name": kullanici.full_name,
        "roles": kullanici.roles_in(kurum.id),
    }


# Bir kullanicinin acabilecegi en fazla kurum.
#
# Sinir olmadan bu uc bir kiraci fabrikasina donusur: her yeni kurum bos
# olsa bile veri tabaninda satir, listede kayit ve destek yuku demek.
# Ucte birakiyoruz - gercek bir kullanici (bir okul + bir sirket + bir
# deneme) bunu asmaz; asan varsa zaten bizimle konusmasi gerekiyor.
EN_FAZLA_KURUM = 3


def _slug_uret(db: Session, ad: str) -> str:
    """Kurum adindan kisa, benzersiz kimlik.

    Turkce katlaniyor (`İSTANBUL Üniversitesi` -> `istanbul-universitesi`)
    cunku slug URL'de ve gunlukte gorunuyor; diakritik birakmak ayni kuruma
    iki farkli adresten bakilmasina yol acardi.
    """
    taban = re.sub(r"[^a-z0-9]+", "-", models.turkce_katla(ad)).strip("-")[:40]
    if len(taban) < 3:
        taban = "kurum"
    aday = taban
    ek = 2
    while db.query(models.Organization).filter(models.Organization.slug == aday).first():
        aday = f"{taban}-{ek}"
        ek += 1
    return aday


@router.post("", response_model=schemas.OrganizationResponse, status_code=status.HTTP_201_CREATED)
def create_organization(
    govde: schemas.OrganizationCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    """Kullanici KENDI kurumunu acar ve sorumlusu olur.

    NEDEN E-POSTA DOGRULAMASI SART: dogrulanmamis bir adresle kurum
    acilabilseydi, sahte adreslerle sinirsiz kiraci uretilebilirdi. Ustelik
    o kurumun sorumlusu, ulasilamayan bir posta kutusuna bagli olurdu -
    sifresini unuttugunda kurtarmanin yolu kalmazdi.

    YENI KURUM BOMBOS ACILIYOR: hicbir yarisma, hicbir rapor, hicbir uye.
    Sahibi baska hicbir kurumun tek kaydini goremez - kurum kapisi zaten
    tokenden gelen kuruma bakiyor ve bu kurum onun disinda hicbir sey
    icermiyor.

    BU UC KULLANICININ BASKA KURUMLARDAKI KONUMUNU DEGISTIRMIYOR: baska bir
    kurumda yarismaci olan biri burada kendi kurumunun sorumlusu olur ama
    orada yarismaci kalmaya devam eder.
    """
    if not current_user.email_verified:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                "Kurum acmadan once e-posta adresinizi dogrulamaniz gerekiyor. "
                "Giris ekranindan yeni bir dogrulama baglantisi isteyebilirsiniz."
            ),
        )

    ad = (govde.name or "").strip()
    if len(ad) < 3:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Kurum adi en az 3 karakter olmali.",
        )

    sahip_oldugu = (
        db.query(models.UserRole)
        .filter(
            models.UserRole.user_id == current_user.id,
            models.UserRole.role == "ORG_OWNER",
        )
        .count()
    )
    if sahip_oldugu >= EN_FAZLA_KURUM:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"En fazla {EN_FAZLA_KURUM} kurum acabilirsiniz. Daha fazlasi "
                "icin bizimle iletisime gecin."
            ),
        )

    kurum = models.Organization(
        id=f"org-{uuid.uuid4().hex[:10]}",
        name=ad,
        slug=_slug_uret(db, ad),
    )
    db.add(kurum)
    db.flush()
    db.add(
        models.UserRole(
            id=str(uuid.uuid4()),
            user_id=current_user.id,
            organization_id=kurum.id,
            role="ORG_OWNER",
        )
    )
    db.commit()
    db.refresh(current_user)
    return {
        "id": kurum.id,
        "name": kurum.name,
        "slug": kurum.slug,
        "my_roles": current_user.roles_in(kurum.id),
        "member_count": 1,
    }
