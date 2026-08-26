"""KATI_KURUM (STRICT_TENANCY) bayragi gercekten kapatiyor mu?

DENENMEMIS BIR BAYRAK, CALISMAYAN BIR BAYRAKTIR. Bu bayrak gecis donemi
bitince acilacak: kurum alanlari zorunlu hale geldiginde "kurumu bos kayit
herkese acik" toleransi kalkmali. O gun gelene kadar kimse denemezse,
acildiginda ya hicbir sey degismez ya da her sey birden kirilir.

Nitekim denenince bir delik cikti: `kayit_kurum == kullanici_kurum`
karsilastirmasi None'i None'e ESITLIYORDU, yani bayragin kapatmasi gereken
tek durum (kurumsuz kayit + kurumsuz token) bayrak acikken bile aciktan
geciyordu. Gevsek modda ayni girdi zaten toleransla gectigi icin bu, bayrak
denenmeden fark edilemezdi.
"""

import importlib

import pytest


class _SahteKayit:
    def __init__(self, kurum):
        self.organization_id = kurum


class _SahteKullanici:
    def __init__(self, kurum):
        self.active_org_id = kurum


@pytest.fixture
def kati(monkeypatch):
    """Modulu KATI modda yeniden yukler ve testten sonra ESKI HALINE getirir.

    NEDEN BU KADAR DIKKAT: `KATI_KURUM` modul seviyesinde, ice aktarma
    aninda okunuyor. `importlib.reload` cagirip geri almazsak modul KATI
    halde kalir ve ALFABETIK OLARAK SONRAKI test dosyalari sessizce bozulur.
    Bu tuzaga bu projede bir kez dusuldu (test_storage.py, sahte Supabase
    ortam degiskenleriyle): monkeypatch ortami geri aldi ama modul
    seviyesindeki degerleri geri almadi ve dokuz test baska bir dosyada
    patladi. Bu yuzden burada `yield`'den sonra ACIKCA yeniden yukluyoruz.
    """
    from app import tenancy

    monkeypatch.setenv("STRICT_TENANCY", "1")
    importlib.reload(tenancy)
    assert tenancy.KATI_KURUM is True, "bayrak acilmadi; test anlamsiz olurdu"
    yield tenancy
    monkeypatch.undo()
    importlib.reload(tenancy)
    assert tenancy.KATI_KURUM is False, "modul KATI halde kaldi - sonraki testler bozulur"


@pytest.mark.parametrize(
    "ad, kayit_kurum, kullanici_kurum, beklenen",
    [
        ("kayit kurumsuz, kullanici kurumlu", None, "org-t3", False),
        ("kayit kurumlu, kullanici kurumsuz", "org-t3", None, False),
        # ASIL SINANAN: None == None esitlenmemeli.
        ("ikisi de kurumsuz", None, None, False),
        ("ayni kurum", "org-t3", "org-t3", True),
        ("farkli kurum", "org-t3", "org-cbu", False),
    ],
)
def test_kati_modda_kurumsuz_kayit_KAPALI(kati, ad, kayit_kurum, kullanici_kurum, beklenen):
    sonuc = kati.ayni_kurum_mu(_SahteKayit(kayit_kurum), _SahteKullanici(kullanici_kurum))
    assert sonuc is beklenen, ad


def test_kati_modda_kurumsuz_istek_HIC_ROL_gormuyor(kati):
    """Kurum kimligi olmayan bir istek KATI modda bos liste almali.

    Kontrol sorgudan ONCE geliyor: "once kapsamsiz sorguyu kur, sonra
    vazgec" sirasi, ileride birinin araya bir satir eklemesiyle kapsamsiz
    sorgunun calismasina yol acabilirdi. `db=None` gecmek bunu kanitliyor -
    sorgu kurulsaydi AttributeError alirdik.
    """
    assert kati.kurumun_rolleri(None, None, "REFEREE") == []


def test_gevsek_modda_tolerans_GERI_GELIYOR(kati):
    """Bayrak kapatilinca gecis toleransi geri donmeli.

    Tek yonlu bir bayrak (acilip kapanmayan) geri alinamaz demektir; bir
    aksaklikta kapatabilmek sart.
    """
    import importlib as _il

    from app import tenancy

    _il.reload(tenancy)  # kati fixture'i STRICT_TENANCY=1 birakti
    assert tenancy.KATI_KURUM is True
    # Simdi elle kapatiyoruz
    import os

    os.environ["STRICT_TENANCY"] = "0"
    _il.reload(tenancy)
    try:
        assert tenancy.KATI_KURUM is False
        assert tenancy.ayni_kurum_mu(_SahteKayit(None), _SahteKullanici("org-t3")) is True
    finally:
        os.environ["STRICT_TENANCY"] = "1"
        _il.reload(tenancy)
