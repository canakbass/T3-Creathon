import os
import secrets
import uuid
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from ..database import get_db
from .. import models, schemas, auth

router = APIRouter(prefix="/api/auth", tags=["Authentication"])

# KENDI KENDINE KAYIT VARSAYILAN OLARAK KAPALI.
#
# NEDEN: bir raporun sonucunu TAKIM UYELIGI belirliyor ve uyelik e-postaya
# bagli. Kayit acik olsaydi, bir takim uyesinin e-postasini ILK KAYDETTIREN
# kisi o takimin sonuclarini gorurdu - e-posta dogrulamamiz yok. Ayni sekilde
# herkes kendine REFEREE rolu verip /api/reports/lookup ile her basvurunun
# kunyesini gorebilirdi.
#
# T3'un mevcut pratigi de bu: hesaplar "belirlenen mail + uretilmis guvenli
# sifre" seklinde aciliyor ve sifre kullaniciya iletiliyor (BGYS gibi diger
# sistemlerini de boyle entegre etmisler). Bizde karsiligi
# POST /api/auth/users - yalnizca yonetici cagirabiliyor.
#
# Varsayilan KAPALI olmasi bilincli: yapilandirmayi unutmak GUVENLIGI
# ARTIRIR, azaltmaz. Testler bu degiskeni acikca aciyor (bkz. conftest.py).
def _kendi_kaydi_acik() -> bool:
    return os.getenv("SELF_REGISTRATION", "0").strip().lower() in ("1", "true", "evet")


def _uret_sifre() -> str:
    """Kriptografik olarak guvenli, okunabilir gecici sifre.

    `secrets` kullaniliyor - `random` DEGIL: random tahmin edilebilir bir
    PRNG ve parola uretiminde kullanilmasi acik bir zafiyettir.
    """
    return secrets.token_urlsafe(12)


def _rol_ver(db: Session, user: models.User, roller) -> None:
    """Kullaniciya rol(leri) ekler. Zaten varsa tekrar eklemez."""
    mevcut = set(user.role_list)
    for rol in roller:
        if rol in mevcut or rol not in models.ROLLER:
            continue
        db.add(models.UserRole(id=str(uuid.uuid4()), user_id=user.id, role=rol))
        mevcut.add(rol)


@router.post(
    "/register", response_model=schemas.UserResponse, status_code=status.HTTP_201_CREATED
)
def register(user_in: schemas.UserCreate, db: Session = Depends(get_db)):
    """Yeni kullanici kaydi - VARSAYILAN OLARAK KAPALI.

    Acmak icin SELF_REGISTRATION=1. Kapali olmasinin gerekcesi icin
    yukaridaki _kendi_kaydi_acik notuna bakin; hesaplari yonetici acar
    (POST /api/auth/users).

    `roles` listesi verilebilir (bir kullanicinin birden fazla rolu olabilir).
    Geriye donuk uyumluluk icin tekil `role` alani da kabul ediliyor.
    """
    if not _kendi_kaydi_acik():
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                "Kendi kendine kayit kapali. Hesabinizi yarisma yoneticisi "
                "acar ve giris bilgileri size iletilir."
            ),
        )

    existing_user = db.query(models.User).filter(models.User.email == user_in.email).first()
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Bu e-posta adresi zaten kayitli.",
        )

    istenen_roller = list(user_in.roles) if user_in.roles else []
    if user_in.role:
        istenen_roller.append(user_in.role)
    # Tekrarlari at, sirayi koru
    istenen_roller = list(dict.fromkeys(istenen_roller))

    gecersiz = [r for r in istenen_roller if r not in models.ROLLER]
    if gecersiz:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Gecersiz rol: {', '.join(gecersiz)}. Gecerli roller: {', '.join(models.ROLLER)}.",
        )
    if not istenen_roller:
        # Rol belirtilmemisse en dusuk yetkili rolu veriyoruz - bos rolle
        # kayitli bir kullanici hicbir sey yapamaz ve kafa karistirir.
        istenen_roller = ["COMPETITOR"]

    db_user = models.User(
        id=str(uuid.uuid4()),
        email=user_in.email,
        password_hash=auth.hash_password(user_in.password),
        full_name=user_in.full_name,
    )
    db.add(db_user)
    db.flush()  # user.id kullanilabilsin diye
    _rol_ver(db, db_user, istenen_roller)
    db.commit()
    db.refresh(db_user)
    return _kullanici_yaniti(db_user)


@router.post(
    "/users", response_model=schemas.CreatedUser, status_code=status.HTTP_201_CREATED
)
def create_user(
    govde: schemas.AdminUserCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(
        auth.RoleChecker(["COMPETITION_MANAGER", "EVALUATION_MANAGER"])
    ),
):
    """Yonetici bir kullanici hesabi acar; sifreyi SISTEM uretir.

    NEDEN BOYLE: raporun sonucunu TAKIM UYELIGI belirliyor ve uyelik
    e-postaya bagli. Kullanicilar kendi kendine kayit olsaydi, bir takim
    uyesinin e-postasini ilk kaydettiren kisi o takimin sonuclarini gorurdu -
    e-posta dogrulamamiz yok. Hesabi yoneticinin acmasi bu bagi guvenilir
    kiliyor: kimlige yonetici kefil oluyor.

    T3'un mevcut pratigi de bu ("belirlenen mail + uretilmis guvenli sifre,
    kullaniciya iletiliyor").

    Sifre YALNIZCA BU YANITTA doner ve veri tabaninda yalnizca bcrypt ozeti
    saklanir - bir daha okunamaz. Kaybolursa yeni hesap degil, sifre
    sifirlama gerekir.
    """
    eposta = govde.email.strip().lower()
    if db.query(models.User).filter(models.User.email == eposta).first():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Bu e-posta adresi zaten kayitli.",
        )

    gecersiz = [r for r in govde.roles if r not in models.ROLLER]
    if gecersiz:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Gecersiz rol: {', '.join(gecersiz)}.",
        )

    sifre = _uret_sifre()
    kullanici = models.User(
        id=str(uuid.uuid4()),
        email=eposta,
        password_hash=auth.hash_password(sifre),
        full_name=govde.full_name,
    )
    db.add(kullanici)
    db.flush()
    _rol_ver(db, kullanici, govde.roles)

    # Istege bagli: ayni islemde takima ekle. Yonetici "hesabi ac + takima
    # ekle"yi iki ayri adimda yapmak zorunda kalmasin; iki adimin arasinda
    # unutulan bir uye, sonucunu hic goremeyen bir yarismaci demek.
    if govde.team_id:
        takim = db.query(models.Team).filter(models.Team.id == govde.team_id).first()
        if not takim:
            raise HTTPException(status_code=404, detail="Takim bulunamadi.")
        db.add(
            models.TeamMember(
                id=str(uuid.uuid4()),
                team_id=takim.id,
                user_id=kullanici.id,
                role=govde.team_role or "uye",
            )
        )

    db.commit()
    db.refresh(kullanici)
    return {
        "id": kullanici.id,
        "email": kullanici.email,
        "full_name": kullanici.full_name,
        "roles": kullanici.role_list,
        "team_id": govde.team_id,
        "temporary_password": sifre,
        "notice": (
            "Bu sifre YALNIZCA BURADA gorunuyor; veri tabaninda yalnizca "
            "ozeti saklaniyor. Kullaniciya guvenli bir kanaldan iletin."
        ),
    }


@router.post("/login", response_model=schemas.LoginResponse)
def login(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    """E-posta + sifre ile giris.

    Yanit, kullanicinin SAHIP OLDUGU tum rolleri de icerir. Tek rolu varsa
    token dogrudan o role gore imzalanir ve arayuz ek bir adim gostermez.
    Birden fazla rolu varsa `active_role` null doner; arayuz rol secimi
    gosterip /select-role cagirir.

    OAuth2PasswordRequestForm kullaniliyor: govde JSON DEGIL form-encoded ve
    e-posta alaninin adi `username` (OAuth2 standardi).
    """
    user = db.query(models.User).filter(models.User.email == form_data.username).first()
    if not user or not auth.verify_password(form_data.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="E-posta veya sifre hatali",
            headers={"WWW-Authenticate": "Bearer"},
        )

    roller = user.role_list
    if not roller:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Bu hesaba hicbir rol tanimlanmamis. Yonetici ile iletisime gecin.",
        )

    # OAuth2'nin `scope` alani ile dogrudan rol istenebiliyor. Arayuz rol
    # secim ekranindan sonra bunu kullaniyor, boylece ikinci bir istek
    # gerekmiyor.
    istenen = (form_data.scopes or [None])[0]
    if istenen is not None and istenen not in roller:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Bu hesabin '{istenen}' rolu yok. Sahip oldugu roller: {', '.join(roller)}.",
        )

    aktif = istenen if istenen else (roller[0] if len(roller) == 1 else None)
    token = auth.create_access_token(data={"sub": user.email, "role": aktif})

    return {
        "access_token": token,
        "token_type": "bearer",
        "roles": roller,
        "active_role": aktif,
        "user": _kullanici_yaniti(user),
    }


@router.post("/select-role", response_model=schemas.LoginResponse)
def select_role(
    secim: schemas.RoleSelection,
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    """Aktif rolu degistirir ve O ROLE gore imzalanmis YENI bir token doner.

    NEDEN YENI TOKEN: yetki kontrolu sunucu tarafinda kaliyor. Arayuz
    "ben simdi hakemim" diyerek rol degistiremez; rolu token tasiyor ve
    token'i yalnizca sunucu imzalayabiliyor.
    """
    if secim.role not in current_user.role_list:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                f"Bu hesabin '{secim.role}' rolu yok. "
                f"Sahip oldugu roller: {', '.join(current_user.role_list)}."
            ),
        )

    token = auth.create_access_token(data={"sub": current_user.email, "role": secim.role})
    return {
        "access_token": token,
        "token_type": "bearer",
        "roles": current_user.role_list,
        "active_role": secim.role,
        "user": _kullanici_yaniti(current_user),
    }


@router.get("/me", response_model=schemas.UserResponse)
def get_me(current_user: models.User = Depends(auth.get_current_user)):
    return _kullanici_yaniti(current_user)


def _kullanici_yaniti(user: models.User) -> dict:
    """UserResponse govdesi.

    `role` alani, tekil rol bekleyen eski istemciler icin duruyor: aktif rol
    varsa o, yoksa ilk rol.
    """
    roller = user.role_list
    aktif = getattr(user, "active_role", None)
    return {
        "id": user.id,
        "email": user.email,
        "full_name": user.full_name,
        "created_at": user.created_at,
        "roles": roller,
        "role": aktif or (roller[0] if roller else None),
    }
