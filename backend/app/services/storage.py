"""Rapor dosyasi depolama katmani.

SUPABASE_URL + SUPABASE_SECRET_KEY tanimliysa Supabase Storage (OZEL bucket);
degilse eskisi gibi yerel disk (backend/uploads). Testler ve yerel
gelistirme hicbir sey ayarlamadan calisir.

models.Report.file_path'te saklanan referans:
  yerel    -> "uploads/RPT-2026-ABC123.pdf"   (mevcut kayitlar aynen calisir)
  supabase -> "sb://RPT-2026-ABC123.pdf"

NEDEN YEREL DISK YETMIYOR: Render/Railway gibi ucretsiz barindirma
katmanlarinda dosya sistemi GECICI - her yeniden dagitimda yuklenen tum
raporlar silinir. Supabase Storage kalici.

EN KRITIK NOKTA - `local_path()`:
AI hatti (ai-scoring, pdfplumber) YEREL BIR DOSYA YOLU istiyor.
reports.py'deki benzerlik kontrolu `os.path.exists(r.file_path)` ile
filtreliyor; file_path bir "sb://" anahtari olursa bu HER ZAMAN False
doner, liste sessizce bosalir ve **intihal kontrolu hicbir hata vermeden
"benzer rapor yok" demeye baslar**. Bu yuzden Supabase nesneleri analiz
oncesi gecici bir dosyaya indiriliyor.
"""

import os
import shutil
import tempfile
from contextlib import contextmanager
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

UPLOAD_DIR = os.getenv("UPLOAD_DIR", "uploads")
BUCKET = os.getenv("SUPABASE_BUCKET", "reports")
SCHEME = "sb://"

_CACHE = Path(
    os.getenv("REPORT_CACHE_DIR", str(Path(tempfile.gettempdir()) / "t3-reports"))
)

_URL = os.getenv("SUPABASE_URL")
_KEY = os.getenv("SUPABASE_SECRET_KEY")

MEDIA_TYPES = {
    ".pdf": "application/pdf",
    ".doc": "application/msword",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}


def enabled() -> bool:
    """Supabase Storage yapilandirilmis mi."""
    return bool(_URL and _KEY)


def media_type(ref: str) -> str:
    return MEDIA_TYPES.get(Path(ref).suffix.lower(), "application/octet-stream")


def is_remote(ref: str) -> bool:
    return bool(ref) and ref.startswith(SCHEME)


_client = None


def _storage():
    global _client
    if _client is None:
        from supabase import create_client

        _client = create_client(_URL, _KEY)
    return _client.storage


def _bucket():
    return _storage().from_(BUCKET)


def ensure_bucket() -> None:
    """Baslangicta bir kez cagriliyor. Bucket zaten varsa sessizce geciyor.

    `allowed_mime_types` BILEREK verilmiyor: reports.py .pdf'in yani sira
    .doc ve .docx de kabul ediyor; bucket'i PDF'e kisitlamak her Word
    yuklemesini 400 ile reddettirirdi.
    """
    if not enabled():
        os.makedirs(UPLOAD_DIR, exist_ok=True)
        return
    from storage3.exceptions import StorageApiError

    try:
        _storage().create_bucket(
            BUCKET,
            options={"public": False, "file_size_limit": 50 * 1024 * 1024},
        )
    except StorageApiError as exc:
        # 409 Duplicate = bucket zaten var, sorun degil.
        if str(getattr(exc, "status", "")) not in ("409", "400"):
            raise
    except Exception:
        # Bucket olusturulamadi ama uygulama acilmali - ilk yuklemede
        # gercek hata zaten yuzeye cikacak.
        pass


def save(local_tmp_path: str, filename: str) -> str:
    """Gecici dosyayi kalici depoya tasir ve file_path referansini doner."""
    if not enabled():
        os.makedirs(UPLOAD_DIR, exist_ok=True)
        hedef = os.path.join(UPLOAD_DIR, filename)
        shutil.move(local_tmp_path, hedef)
        return hedef

    with open(local_tmp_path, "rb") as fh:
        _bucket().upload(
            path=filename,
            # str/Path verilirse storage3 dosyayi open() edip HIC KAPATMIYOR;
            # acik dosya nesnesi verip kendimiz kapatiyoruz.
            file=fh,
            # Bu sozluk her cagrida YENIDEN kuruluyor: storage3
            # `_upload_or_update` icinde .pop() ile sozlugu DEGISTIRIYOR,
            # modul duzeyinde tutulursa ikinci yukleme content-type'ini
            # sessizce kaybeder.
            file_options={
                # Verilmezse storage3 varsayilani "text/plain;charset=UTF-8" -
                # yani PDF'ler duz metin olarak saklanir ve bozuk iner.
                "content-type": media_type(filename),
                "upsert": "false",  # bool degil, STRING bekleniyor
                "cache-control": "3600",
            },
        )
    os.remove(local_tmp_path)
    return SCHEME + filename


def read_bytes(ref: str) -> bytes:
    if is_remote(ref):
        return _bucket().download(ref[len(SCHEME):])
    return Path(ref).read_bytes()


def exists(ref: str) -> bool:
    if is_remote(ref):
        try:
            return bool(_bucket().download(ref[len(SCHEME):]))
        except Exception:
            return False
    return os.path.exists(ref)


@contextmanager
def local_path(ref: str):
    """AI hatti icin YEREL bir dosya yolu saglar.

    Yerel referanslarda yolun kendisini verir. Supabase referanslarinda
    nesneyi gecici bir dosyaya indirir. Bu olmadan benzerlik/intihal
    kontrolu SESSIZCE devre disi kalirdi (bkz. modul basindaki not).
    """
    if not is_remote(ref):
        yield ref
        return
    _CACHE.mkdir(parents=True, exist_ok=True)
    hedef = _CACHE / ref[len(SCHEME):]
    if not hedef.exists():
        hedef.write_bytes(_bucket().download(ref[len(SCHEME):]))
    yield str(hedef)


def signed_url(ref: str, expires_in: int = 120) -> str:
    """Imzali gecici baglanti.

    SU AN KULLANILMIYOR - bilincli. Raporlar gizli ve tek yetki kapisi
    uygulamanin kendi kontrolu (_rapora_erisebilir_mi). Imzali baglanti o
    kapiyi atlatir; bagi ele geciren herkes dosyaya erisir. Egress maliyeti
    sorun olursa yeniden degerlendirilebilir.
    """
    res = _bucket().create_signed_url(ref[len(SCHEME):], expires_in)
    # dict doner ve anahtar "signedURL" - buyuk harfli URL.
    return res["signedURL"]


def delete(ref: str) -> None:
    if is_remote(ref):
        _bucket().remove([ref[len(SCHEME):]])  # tek dosya icin bile LISTE
    elif os.path.exists(ref):
        os.remove(ref)
