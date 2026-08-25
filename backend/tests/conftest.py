import pytest
from fastapi.testclient import TestClient
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

    takim = models.Team(id="test-takim", name="Test Takımı", external_ref="KYS-TEST-1")
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

    takim = models.Team(id="rakip-takim", name="Rakip Takım", external_ref="KYS-TEST-2")
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
