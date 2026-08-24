import os

from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

# .env'i BURADA yukluyoruz.
#
# NEDEN BURADA: app/auth.py da load_dotenv() cagiriyor, ama main.py once
# `app.database`'i import ediyor. Yani bu modul yuklenirken .env HENUZ
# OKUNMAMIS oluyordu ve DATABASE_URL sessizce gorunmez kaliyordu - ekip
# .env'e Supabase adresini yazip hicbir hata gormeden SQLite'a yazmaya
# devam ederdi.
load_dotenv()

# Yerel gelistirme ve testler: DATABASE_URL yoksa eskisi gibi SQLite.
SQLALCHEMY_DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./sql_app.db")

if SQLALCHEMY_DATABASE_URL.startswith("sqlite"):
    # check_same_thread SADECE SQLite icin gecerli; Postgres surucusune
    # verilirse TypeError firlatir.
    engine = create_engine(
        SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False}
    )
else:
    # Surucuyu acikca sabitliyoruz. Supabase panosu "postgresql://" ya da
    # "postgres://" seklinde bir adres veriyor; SQLAlchemy'nin varsayilan
    # surucu secimine birakmak yerine psycopg2'yi zorunlu kiliyoruz.
    for _onek in ("postgresql+psycopg2://", "postgresql://", "postgres://"):
        if SQLALCHEMY_DATABASE_URL.startswith(_onek):
            SQLALCHEMY_DATABASE_URL = (
                "postgresql+psycopg2://" + SQLALCHEMY_DATABASE_URL[len(_onek):]
            )
            break

    engine = create_engine(
        SQLALCHEMY_DATABASE_URL,
        pool_size=5,
        max_overflow=5,
        pool_timeout=30,
        # Supavisor bosta kalan baglantilari kapatiyor; havuzdaki olu
        # baglantilar "server closed the connection unexpectedly" verir.
        pool_recycle=1800,
        pool_pre_ping=True,
        connect_args={
            # Supabase TLS'i ZORUNLU KILMIYOR ve libpq varsayilani "prefer" -
            # yani sessizce sifrelenmemis baglantiya duser. Acikca istiyoruz.
            "sslmode": "require",
            "connect_timeout": 10,
            "application_name": "t3-creathon-backend",
        },
    )

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


# Dependency to get db session
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
