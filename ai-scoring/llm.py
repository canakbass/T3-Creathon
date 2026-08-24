"""Saglayicidan bagimsiz LLM katmani (Claude API ve Google Gemini).

kriter degerlendirmesi (criteria.py) bu modulu cagiriyor; hangi saglayicinin
kullanildigini bilmesi gerekmiyor.

============================================================================
GIZLILIK UYARISI - BUNU OKUMADAN LLM'I ACMAYIN
============================================================================
Bu katman rapor METNINI ucuncu taraf bir sunucuya gonderir. Creathon
sartnamesi iki sey soyluyor (bkz. docs/CLAUDE.md Bolum 1):

  * "Program suresince erisilen T3 Vakfi verileri ucuncu taraflarla
     paylasilamaz."
  * Cozum 6698 sayili KVKK'ya uygun olmali.

Google Gemini'nin UCRETSIZ katmani bu iki maddeyle CELISIYOR. Google'in
kendi kosullari (https://ai.google.dev/gemini-api/terms):

  - "Google uses the content you submit to the Services and any generated
     responses to provide, improve, and develop Google products"
  - "human reviewers may read, annotate, and process your API input and output"
  - "Do not submit sensitive, confidential, or personal information to the
     Unpaid Services."

UCRETLI katmanda bunlarin hicbiri gecerli degil ("Google doesn't use your
prompts or responses to improve our products"). AEA/Isvicre/Birlesik Krallik
kullanicilari ucretsiz katmanda da ucretli korumalari aliyor - TURKIYE BU
LISTEDE DEGIL.

Bu yuzden:
  * VARSAYILAN motor, tamamen YEREL calisan kural motorudur. Hicbir veri
    disari cikmaz. Bu bir eksiklik degil, bu proje icin bir AVANTAJ.
  * LLM yalnizca ortam degiskeniyle ACIKCA acildiginda devreye girer.
  * Ucretsiz Gemini katmani kullanilacaksa AI_SCORING_LLM_ONAY=evet
    ayarlanmali - bilincsizce acilmasin diye.
============================================================================

Kullanim:
    AI_SCORING_LLM=gemini  GOOGLE_API_KEY=...  python ai-scoring/scorer.py rapor.pdf
    AI_SCORING_LLM=claude  ANTHROPIC_API_KEY=...
    AI_SCORING_LLM=kural   (varsayilan - LLM hic cagrilmaz)
"""

import json
import os

# Saglayici basina varsayilan model. Ortam degiskeniyle degistirilebilir.
CLAUDE_VARSAYILAN_MODEL = "claude-opus-5"
GEMINI_VARSAYILAN_MODEL = "gemini-2.5-flash"

AZAMI_TOKEN = 16000


def _env(ad, varsayilan=None):
    deger = os.environ.get(ad)
    return deger.strip() if deger and deger.strip() else varsayilan


def secili_saglayici():
    """Hangi motor kullanilacak: "claude" | "gemini" | "kural".

    AI_SCORING_LLM acikca verilmisse o kullanilir. Verilmemisse KURAL
    motoruna duseriz - anahtar ortamda duruyor diye rapor metnini
    kendiliginden disari gondermek dogru olmaz, bu bilincli bir karar
    olmali (yukaridaki gizlilik uyarisi).
    """
    istenen = (_env("AI_SCORING_LLM") or "kural").lower()
    return istenen if istenen in ("claude", "gemini", "kural") else "kural"


def _gemini_anahtari():
    # SDK once GOOGLE_API_KEY'e, sonra GEMINI_API_KEY'e bakiyor
    # (google/genai/_api_client.py). Ayni sirayi izliyoruz.
    return _env("GOOGLE_API_KEY") or _env("GEMINI_API_KEY")


def saglayici_durumu():
    """Secili saglayici gercekten kullanilabilir mi.

    Doner: (kullanilabilir: bool, aciklama: str)
    """
    saglayici = secili_saglayici()

    if saglayici == "kural":
        return False, "AI_SCORING_LLM ayarlanmamis; kural tabanli motor kullaniliyor"

    if saglayici == "claude":
        try:
            import anthropic  # noqa: F401
        except ImportError:
            return False, "anthropic SDK kurulu degil (pip install anthropic)"
        if not _env("ANTHROPIC_API_KEY"):
            return False, "ANTHROPIC_API_KEY tanimli degil"
        return True, f"Claude API ({_env('AI_SCORING_MODEL', CLAUDE_VARSAYILAN_MODEL)})"

    # gemini
    try:
        from google import genai  # noqa: F401
    except ImportError:
        return False, "google-genai SDK kurulu degil (pip install google-genai)"
    if not _gemini_anahtari():
        return False, "GOOGLE_API_KEY / GEMINI_API_KEY tanimli degil"
    if (_env("AI_SCORING_LLM_ONAY") or "").lower() not in ("evet", "yes", "true", "1"):
        return False, (
            "Gemini acik ama AI_SCORING_LLM_ONAY=evet ayarlanmamis. Google'in "
            "UCRETSIZ katmani gonderilen icerigi urunlerini gelistirmek icin "
            "kullaniyor ve insan incelemesine aciyor; Creathon sartnamesi "
            "verilerin ucuncu taraflarla paylasilmamasini sart kosuyor. "
            "Bilerek acmak icin AI_SCORING_LLM_ONAY=evet verin (ya da ucretli "
            "katman kullanin)."
        )
    return True, f"Google Gemini ({_env('AI_SCORING_MODEL', GEMINI_VARSAYILAN_MODEL)})"


def llm_available():
    """Geriye donuk uyumluluk icin - criteria.py bunu kullaniyordu."""
    return saglayici_durumu()[0]


# ---------------------------------------------------------------------------
# Claude
# ---------------------------------------------------------------------------


def _claude_degerlendir(sistem, kullanici, sema):
    import anthropic

    model = _env("AI_SCORING_MODEL", CLAUDE_VARSAYILAN_MODEL)
    try:
        client = anthropic.Anthropic()
        yanit = client.messages.create(
            model=model,
            max_tokens=AZAMI_TOKEN,
            system=sistem,
            messages=[{"role": "user", "content": kullanici}],
            output_config={"format": {"type": "json_schema", "schema": sema}},
        )
    except anthropic.AuthenticationError:
        return None, "Claude API kimlik dogrulamasi basarisiz (ANTHROPIC_API_KEY gecersiz)"
    except anthropic.RateLimitError:
        return None, "Claude API hiz sinirina takildi"
    except anthropic.NotFoundError:
        return None, f"Claude modeli bulunamadi: {model} (AI_SCORING_MODEL ile degistirin)"
    except anthropic.APIStatusError as e:
        return None, f"Claude API hatasi (HTTP {e.status_code})"
    except anthropic.APIConnectionError:
        return None, "Claude API'ye ag baglantisi kurulamadi"
    except Exception as e:
        return None, f"Claude API beklenmeyen hata: {type(e).__name__}"

    if getattr(yanit, "stop_reason", None) == "refusal":
        return None, "Claude API istegi guvenlik nedeniyle reddetti"

    try:
        metin = next(b.text for b in yanit.content if b.type == "text")
        return json.loads(metin), None
    except (StopIteration, json.JSONDecodeError, AttributeError):
        return None, "Claude API yaniti beklenen JSON formatinda degil"


# ---------------------------------------------------------------------------
# Gemini
# ---------------------------------------------------------------------------


def _gemini_semasini_temizle(sema):
    """Gemini'nin response_schema'si JSON Schema'nin tamamini desteklemiyor.

    `additionalProperties` gibi anahtarlar reddedilebiliyor; ozyinelemeli
    olarak temizliyoruz. Anlami degistirmiyor - zaten alanlarin tamami
    `required` listesinde.
    """
    if isinstance(sema, dict):
        return {
            k: _gemini_semasini_temizle(v)
            for k, v in sema.items()
            if k not in ("additionalProperties", "$schema", "definitions", "$defs")
        }
    if isinstance(sema, list):
        return [_gemini_semasini_temizle(v) for v in sema]
    return sema


def _gemini_degerlendir(sistem, kullanici, sema):
    from google import genai
    from google.genai import errors, types

    model = _env("AI_SCORING_MODEL", GEMINI_VARSAYILAN_MODEL)
    try:
        client = genai.Client(api_key=_gemini_anahtari())
        yanit = client.models.generate_content(
            model=model,
            contents=kullanici,
            config=types.GenerateContentConfig(
                system_instruction=sistem,
                # Bu ikisi birlikte Gemini'yi semaya uyan JSON uretmeye zorluyor.
                response_mime_type="application/json",
                response_schema=_gemini_semasini_temizle(sema),
                max_output_tokens=AZAMI_TOKEN,
            ),
        )
    except errors.ClientError as e:
        kod = getattr(e, "code", None)
        if kod == 400 and "API key" in str(e):
            return None, "Gemini API anahtari gecersiz (GOOGLE_API_KEY)"
        if kod == 404:
            return None, (
                f"Gemini modeli bulunamadi: {model}. Hesabinizda hangi modellerin "
                "oldugunu gormek icin: python -c \"from google import genai; "
                "print([m.name for m in genai.Client().models.list()])\" "
                "ve AI_SCORING_MODEL ile degistirin."
            )
        if kod == 429:
            return None, "Gemini API kota/hiz sinirina takildi (ucretsiz katman gunluk limiti olabilir)"
        return None, f"Gemini istemci hatasi (HTTP {kod})"
    except errors.ServerError as e:
        return None, f"Gemini sunucu hatasi (HTTP {getattr(e, 'code', '5xx')})"
    except Exception as e:
        return None, f"Gemini beklenmeyen hata: {type(e).__name__}"

    metin = getattr(yanit, "text", None)
    if not metin:
        # Guvenlik filtresi ya da bos yanit
        return None, "Gemini bos yanit dondu (guvenlik filtresi olabilir)"
    try:
        return json.loads(metin), None
    except json.JSONDecodeError:
        return None, "Gemini yaniti beklenen JSON formatinda degil"


# ---------------------------------------------------------------------------
# Ortak giris noktasi
# ---------------------------------------------------------------------------


def degerlendir(sistem, kullanici, sema):
    """Secili saglayiciya yapilandirilmis bir JSON istegi gonderir.

    Doner: (veri: dict | None, hata: str | None)
    Hicbir zaman istisna firlatmaz - cagiran taraf kural motoruna duser.
    """
    kullanilabilir, aciklama = saglayici_durumu()
    if not kullanilabilir:
        return None, aciklama

    saglayici = secili_saglayici()
    if saglayici == "claude":
        return _claude_degerlendir(sistem, kullanici, sema)
    if saglayici == "gemini":
        return _gemini_degerlendir(sistem, kullanici, sema)
    return None, "LLM saglayicisi secili degil"
