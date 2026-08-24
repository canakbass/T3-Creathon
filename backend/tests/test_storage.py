"""Depolama katmani testleri.

EN KRITIK DAVRANIS: `local_path()`. AI hatti (pdfplumber) YEREL bir dosya
yolu istiyor. Supabase Storage devreye girdiginde file_path bir "sb://"
anahtari oluyor; bu katman nesneyi gecici bir dosyaya indirmezse benzerlik
/ intihal kontrolu HICBIR HATA VERMEDEN "benzer rapor yok" demeye baslar.
Sessizce bozulan bir guvenlik kontrolu, gurultulu bozulan bir kontrolden
cok daha tehlikeli - o yuzden burada acikca sinaniyor.
"""

import importlib
import os
from pathlib import Path

import pytest

from app.services import storage as storage_modulu


@pytest.fixture
def storage(tmp_path, monkeypatch):
    """Supabase YAPILANDIRILMAMIS haliyle temiz bir modul."""
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    monkeypatch.delenv("SUPABASE_SECRET_KEY", raising=False)
    monkeypatch.setenv("UPLOAD_DIR", str(tmp_path / "uploads"))
    monkeypatch.setenv("REPORT_CACHE_DIR", str(tmp_path / "cache"))
    return importlib.reload(storage_modulu)


def test_supabase_yapilandirilmamissa_kapali(storage):
    assert storage.enabled() is False


def test_yerel_kayit_dosyayi_uploads_altina_tasiyor(storage, tmp_path):
    gecici = tmp_path / "gecici.pdf"
    gecici.write_bytes(b"%PDF-1.4 test")

    ref = storage.save(str(gecici), "RPT-2026-AAA111.pdf")

    assert not ref.startswith("sb://"), "yerel modda uzak referans uretilmemeli"
    assert Path(ref).is_file()
    assert Path(ref).read_bytes() == b"%PDF-1.4 test"
    # Gecici dosya tasindi, ortada kalmadi.
    assert not gecici.exists()


def test_yerel_referans_uzak_sayilmiyor(storage):
    assert storage.is_remote("uploads/RPT-2026-AAA111.pdf") is False
    assert storage.is_remote("sb://RPT-2026-AAA111.pdf") is True
    assert storage.is_remote("") is False


def test_local_path_yerel_referansta_yolun_kendisini_veriyor(storage, tmp_path):
    dosya = tmp_path / "rapor.pdf"
    dosya.write_bytes(b"%PDF")

    with storage.local_path(str(dosya)) as yol:
        assert yol == str(dosya)


def test_media_type_uzantidan_cozuluyor(storage):
    assert storage.media_type("a.pdf") == "application/pdf"
    assert storage.media_type("a.doc") == "application/msword"
    assert storage.media_type("a.docx").endswith("wordprocessingml.document")
    # Taninmayan uzanti indirmeyi bozmamali.
    assert storage.media_type("a.xyz") == "application/octet-stream"


def test_read_bytes_yerel_dosyayi_okuyor(storage, tmp_path):
    dosya = tmp_path / "r.pdf"
    dosya.write_bytes(b"icerik")
    assert storage.read_bytes(str(dosya)) == b"icerik"


def test_yerel_silme(storage, tmp_path):
    dosya = tmp_path / "r.pdf"
    dosya.write_bytes(b"x")
    storage.delete(str(dosya))
    assert not dosya.exists()
    # Olmayan dosyayi silmek patlamamali.
    storage.delete(str(dosya))


# --- Supabase yapilandirilmis gibi davranarak, AG'A CIKMADAN ---------------


@pytest.fixture
def uzak_storage(tmp_path, monkeypatch):
    """Supabase yapilandirilmis gorunen, ama bucket'i taklit edilmis modul."""
    monkeypatch.setenv("SUPABASE_URL", "https://ornek.supabase.co")
    monkeypatch.setenv("SUPABASE_SECRET_KEY", "sb_secret_sahte")
    monkeypatch.setenv("REPORT_CACHE_DIR", str(tmp_path / "cache"))
    modul = importlib.reload(storage_modulu)

    class SahteBucket:
        def __init__(self):
            self.indirilen = []
            self.yuklenen = []
            self.silinen = []

        def download(self, key):
            self.indirilen.append(key)
            return b"%PDF-1.4 uzak icerik"

        def upload(self, path, file, file_options):
            self.yuklenen.append((path, file.read(), dict(file_options)))

        def remove(self, keys):
            self.silinen.append(keys)

    sahte = SahteBucket()
    monkeypatch.setattr(modul, "_bucket", lambda: sahte)
    return modul, sahte


def test_uzak_yapilandirmada_acik(uzak_storage):
    modul, _ = uzak_storage
    assert modul.enabled() is True


def test_uzak_kayit_sb_referansi_uretiyor_ve_content_type_veriyor(uzak_storage, tmp_path):
    modul, sahte = uzak_storage
    gecici = tmp_path / "gecici.pdf"
    gecici.write_bytes(b"%PDF-1.4 test")

    ref = modul.save(str(gecici), "RPT-2026-BBB222.pdf")

    assert ref == "sb://RPT-2026-BBB222.pdf"
    assert not gecici.exists(), "gecici dosya temizlenmeli"

    yol, icerik, secenekler = sahte.yuklenen[0]
    assert yol == "RPT-2026-BBB222.pdf"
    assert icerik == b"%PDF-1.4 test"
    # content-type VERILMEZSE storage3 varsayilani "text/plain" - PDF'ler
    # bozuk iner. Acikca verildigini dogruluyoruz.
    assert secenekler["content-type"] == "application/pdf"
    # upsert bool degil STRING olmali.
    assert secenekler["upsert"] == "false"


def test_upload_secenekleri_her_cagrida_YENIDEN_kuruluyor(uzak_storage, tmp_path):
    """storage3 `_upload_or_update` icinde secenekler sozlugunu .pop() ile
    DEGISTIRIYOR. Sozluk modul duzeyinde tutulsaydi ikinci yukleme
    content-type'ini sessizce kaybederdi."""
    modul, sahte = uzak_storage
    for i in range(2):
        gecici = tmp_path / f"g{i}.pdf"
        gecici.write_bytes(b"%PDF")
        modul.save(str(gecici), f"R{i}.pdf")

    assert len(sahte.yuklenen) == 2
    for _, _, secenekler in sahte.yuklenen:
        assert secenekler["content-type"] == "application/pdf"


def test_local_path_uzak_nesneyi_YEREL_DOSYAYA_indiriyor(uzak_storage):
    """Bu olmadan benzerlik kontrolu sessizce devre disi kalirdi."""
    modul, sahte = uzak_storage

    with modul.local_path("sb://RPT-2026-CCC333.pdf") as yol:
        assert os.path.isfile(yol), "AI hatti GERCEK bir dosya yolu istiyor"
        assert Path(yol).read_bytes() == b"%PDF-1.4 uzak icerik"

    assert sahte.indirilen == ["RPT-2026-CCC333.pdf"]


def test_local_path_ayni_nesneyi_ikinci_kez_indirmiyor(uzak_storage):
    modul, sahte = uzak_storage
    with modul.local_path("sb://ayni.pdf"):
        pass
    with modul.local_path("sb://ayni.pdf"):
        pass
    assert sahte.indirilen == ["ayni.pdf"], "onbellek calismali"


def test_uzak_silme_LISTE_gonderiyor(uzak_storage):
    modul, sahte = uzak_storage
    modul.delete("sb://silinecek.pdf")
    # storage3 tek dosya icin bile liste bekliyor.
    assert sahte.silinen == [["silinecek.pdf"]]
