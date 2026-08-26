import os
import uuid

import pytest
from fastapi.testclient import TestClient

# Kendi kendine kayit URUNDE KAPALI (bkz. routes/auth.py). Testlerin cogu
# kullanici olusturmak icin /register kullaniyor; burada ACIKCA aciyoruz.
# Varsayilanin kapali olmasi bilincli: yapilandirmayi unutmak guvenligi
# ARTIRIR, azaltmaz.
os.environ.setdefault("SELF_REGISTRATION", "1")
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app import models  # noqa: F401  (Base.metadata'nin tablolari tanimasi icin)
from main import app

# Test veri tabani BELLEKTE tutuluyor, diskte dosya olarak degil.
#
# NEDEN DEGISTI: onceki hali "sqlite:///./test_temp.db" dosyasini
# kullaniyor ve her testin sonunda os.remove ile SILIYORDU. Ama motorun
# baglanti havuzu (connection pool) o dosyaya ait acik bir tanitici
# tutmaya devam ediyor; dosya silindiginde havuzdaki baglanti artik var
# olmayan bir inode'a bakiyor ve SQLite bunu "attempt to write a readonly
# database" olarak bildiriyor. Sonuc: ilk test geciyor, sonraki BUTUN
# testler setup asamasinda patliyordu (1 gecti / 6 hata). Testler tek tek
# calistirildiginda gectigi icin hata uzun sure gorunmez kaldi -
# README'de "7/7 gecti" yaziyordu.
#
# StaticPool + ":memory:" bu sinifin hatalarini kokten bitiriyor:
#   * silinecek dosya yok, dolayisiyla bayat tanitici da yok
#   * StaticPool tek bir baglantiyi paylasir; bu SART, cunku her yeni
#     baglanti kendi bos ":memory:" veri tabanini acardi ve TestClient
#     istekleri baska bir is parcaciginda calistigi icin tablolari
#     bulamazdi
#   * diske hic yazilmadigi icin testler belirgin sekilde hizli
SQLALCHEMY_DATABASE_URL = "sqlite://"

engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def kullanici_ac(email, roller, sifre="password", org="org-t3"):
    """Kullaniciyi VERI TABANINA dogrudan yazar; API'ye dokunmaz.

    NEDEN API DEGIL: testler uzun sure /api/auth/register kullaniyordu ve o
    uc nokta govdeden gelen HERHANGI bir rolu kabul ediyordu - yani testler
    kurulum icin bir URUN ACIGINA dayaniyordu. Acik kapatilinca (ayricalikli
    roller kendi kendine alinamaz) 38 test birden dustu. Bu, kurulumun
    uretim yolundan gecmesinin neden kotu bir fikir oldugunun kaniti: bir
    guvenlik duzeltmesi, hicbir iliskisi olmayan testleri kirmis gibi
    gorunuyor ve duzeltmeyi geri almak cazip hale geliyor.

    Kurulum artik urunun izin verdigi seyden BAGIMSIZ. Gercek kayit yolunun
    kendi testleri ayrica duruyor (test_auth.py).
    """
    from app import auth as A
    from app import models

    db = TestingSessionLocal()
    try:
        kullanici = models.User(
            id=str(uuid.uuid4()), email=email, password_hash=A.hash_password(sifre)
        )
        db.add(kullanici)
        db.flush()
        for rol in roller:
            db.add(
                models.UserRole(
                    id=str(uuid.uuid4()),
                    user_id=kullanici.id,
                    organization_id=org,
                    role=rol,
                )
            )
        db.commit()
        return kullanici.id
    finally:
        db.close()


@pytest.fixture(scope="function")
def db_session():
    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()
        # Tablolari dusurmek testler arasi izolasyonu sagliyor: StaticPool
        # ayni baglantiyi paylastigi icin bellekteki veri aksi halde bir
        # sonraki teste sizardi (orn. "bu e-posta zaten kayitli" hatalari).
        Base.metadata.drop_all(bind=engine)


@pytest.fixture(scope="function", autouse=True)
def kurumlar(db_session):
    """Her test veri tabaninda VARSAYILAN KURUM bulunsun.

    NEDEN AUTOUSE: uygulama acilisindaki seed_db GERCEK veri tabanina
    yaziyor, testlerin bellek icindeki veri tabanina degil. Bu yuzden
    testlerde hic Organization kaydi yoktu ve yeni acilan hesaplarin
    rolleri organization_id=None ile olusuyordu.

    Bugun bu zararsiz (yetki kontrolu hala kuruma bakmiyor) ama kurum
    kapisi devreye girdiginde her test SESSIZCE "kurumsuz kullanici"
    uretmeye devam eder ve hepsi 403 alirdi - hata da testin kendisinde
    degil altyapida olurdu. Tuzagi simdiden kapatiyoruz.
    """
    from app import models

    if db_session.query(models.Organization).count() == 0:
        db_session.add_all([
            models.Organization(id="org-t3", name="T3 Vakfı", slug="t3-vakfi"),
            models.Organization(
                id="org-cbu", name="Manisa Celal Bayar Üniversitesi", slug="cbu"
            ),
        ])
        db_session.commit()
    return db_session.query(models.Organization).all()


@pytest.fixture(scope="function")
def demo_takim(db_session):
    """Yoneticinin rapor aktarabilmesi icin bir takim.

    NEDEN GEREKLI: yonetici aktariminda `team_id` ZORUNLU. Sartname AKIS 01
    yoneticinin "raporlari sisteme aktardigini" soyluyor; ama rapor bir
    takima baglanmazsa sahipsiz kalir ve sonucunu hicbir yarismaci goremez -
    AKIS 03 ("yarismaci sonucunu goruntuler") karsilanmaz.

    Takim olusturma icin API UCU YOK ve olmayacak: gercek kayitlar
    TEKNOFEST'in kendi sisteminde (KYS) tutuluyor, biz o veriyi tuketiyoruz.
    Bu yuzden testlerde de dogrudan veri tabanina yaziyoruz.
    """
    from app import models

    takim = models.Team(
        id="test-takim", name="Test Takımı", external_ref="KYS-TEST-1",
        organization_id="org-t3",
    )
    db_session.add(takim)
    db_session.commit()
    return takim


@pytest.fixture(scope="function")
def rakip_takim(db_session):
    """Ikinci bir takim - INTIHAL senaryolari icin sart.

    Ayni takimin raporlari benzerlik karsilastirmasindan cikariliyor (bir
    takimin On Tasarim / Final Tasarim raporlari ayni basvurunun iki asamasi,
    intihal degil). Dolayisiyla "kopya yakalaniyor mu" testleri iki FARKLI
    takim kullanmak zorunda - aksi halde test, dislama yuzunden bosa gecer.
    """
    from app import models

    takim = models.Team(
        id="rakip-takim", name="Rakip Takım", external_ref="KYS-TEST-2",
        organization_id="org-t3",
    )
    db_session.add(takim)
    db_session.commit()
    return takim


@pytest.fixture(scope="function")
def client(db_session):
    def override_get_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
