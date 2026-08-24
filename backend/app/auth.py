import datetime
import os
import warnings
import jwt
import bcrypt
from dotenv import load_dotenv
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session
from typing import List

from .database import get_db
from . import models, schemas

load_dotenv()  # backend/.env varsa JWT_SECRET_KEY'i oradan okur

_DEV_ONLY_FALLBACK_SECRET = "super-secret-t3-creathon-key-dev-only-not-for-production-use"

SECRET_KEY = os.environ.get("JWT_SECRET_KEY")
if not SECRET_KEY:
    warnings.warn(
        "JWT_SECRET_KEY ortam degiskeni ayarlanmamis - gelistirme icin sabit "
        "bir anahtara geri donuluyor. Bu anahtar public repoda duruyor, "
        "gercek/demo kullanimda MUTLAKA `JWT_SECRET_KEY` ortam degiskenini "
        "ayarlayin (bkz. backend/README.md).",
        RuntimeWarning,
    )
    SECRET_KEY = _DEV_ONLY_FALLBACK_SECRET

ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="api/auth/login")

def hash_password(password: str) -> str:
    pwd_bytes = password.encode('utf-8')
    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(pwd_bytes, salt)
    return hashed.decode('utf-8')

def verify_password(plain_password: str, hashed_password: str) -> bool:
    pwd_bytes = plain_password.encode('utf-8')
    hashed_bytes = hashed_password.encode('utf-8')
    return bcrypt.checkpw(pwd_bytes, hashed_bytes)

def create_access_token(data: dict, expires_delta: datetime.timedelta = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.datetime.now(datetime.UTC).replace(tzinfo=None) + expires_delta
    else:
        expire = datetime.datetime.now(datetime.UTC).replace(tzinfo=None) + datetime.timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)) -> models.User:
    """Token'i dogrular ve kullaniciyi doner.

    Token'daki AKTIF ROL, donen nesneye gecici bir nitelik olarak
    (`active_role`) ekleniyor. Boylece rotalar ve RoleChecker "bu istek
    hangi rolle yapiliyor" sorusunu yanitlayabiliyor.

    Aktif rol, kullanicinin veri tabanindaki roller listesine karsi da
    DOGRULANIYOR: bir kullanicinin rolu geri alindiginda elindeki eski
    token o rolu kullanmaya devam edememeli.
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        email: str = payload.get("sub")
        if email is None:
            raise credentials_exception
        token_data = schemas.TokenData(email=email, role=payload.get("role"))
    except jwt.PyJWTError:
        raise credentials_exception

    user = db.query(models.User).filter(models.User.email == token_data.email).first()
    if user is None:
        raise credentials_exception

    aktif_rol = token_data.role
    if aktif_rol is not None and aktif_rol not in user.role_list:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                f"Bu hesap artik '{aktif_rol}' rolune sahip degil. "
                "Lutfen tekrar giris yapin."
            ),
        )

    # SQLAlchemy nesnesine gecici nitelik: veri tabanina yazilmaz.
    user.active_role = aktif_rol
    return user


def get_active_role(current_user: models.User = Depends(get_current_user)) -> str:
    """Istegin yapildigi aktif rol."""
    return getattr(current_user, "active_role", None)


class RoleChecker:
    def __init__(self, allowed_roles: List[str]):
        self.allowed_roles = allowed_roles

    def __call__(self, current_user: models.User = Depends(get_current_user)):
        aktif = getattr(current_user, "active_role", None)

        # Token'da rol yoksa (cok-rollu kullanici henuz rol secmemis) ya da
        # aktif rol izinli degilse reddediyoruz. Kullanicinin BASKA bir rolu
        # izinli olsa bile: hangi rolle hareket ettigi acik olmali, aksi
        # halde "yanlislikla yonetici yetkisiyle islem yapma" mumkun olurdu.
        if aktif is None:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=(
                    "Bu istek icin aktif bir rol secilmemis. "
                    "/api/auth/select-role ile rolunuzu secin."
                ),
            )
        if aktif not in self.allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=(
                    f"'{aktif}' rolu bu islemi yapamaz. "
                    f"Izinli roller: {', '.join(self.allowed_roles)}."
                ),
            )
        return current_user
