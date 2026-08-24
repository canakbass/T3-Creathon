"""Kriter bazli degerlendirme (MVP madde 5): puan + gerekce.

IKI MOTOR VAR:

  1. "kural" - VARSAYILAN. Olculebilir sinyallere dayali deterministik
               degerlendirme. Tamamen YEREL calisir; hicbir veri disari
               cikmaz.
  2. "llm"   - AI_SCORING_LLM=claude ya da =gemini ile ACIKCA acilirsa
               devreye girer. Bolum metinlerini ve rubrigi gonderip her
               kriter icin puan + gerekce istiyoruz. Saglayici ayrintilari
               llm.py'de.

NEDEN VARSAYILAN KURAL MOTORU (sadece bir yedek degil):
  * Gizlilik. LLM kullanmak rapor METNINI ucuncu tarafa gondermek demek.
    Creathon sartnamesi "erisilen T3 Vakfi verileri ucuncu taraflarla
    paylasilamaz" diyor ve KVKK uyumu sart kosuyor. Yerel motor bu sorunu
    tamamen ortadan kaldiriyor - bu bir eksiklik degil, AVANTAJ.
    Ayrintili uyari icin llm.py basina bakin.
  * Dayaniklilik. Demo Day'de internet kesilse, kredi bitse ya da API
    gecici hata verse sistem CALISMAYA DEVAM ETMELI. Tek motorlu bir
    tasarimda MVP madde 5 juri onunde comebilir.
  * Tekrarlanabilirlik. Kural motoru deterministik: ayni rapor her zaman
    ayni puani alir. Bir degerlendirme sisteminde bu onemli bir ozellik.

ONEMLI - IS BOLUMU: LLM motoru bile TOPLAM PUANI HESAPLAMIYOR. LLM sadece
her bolumun kalitesine 0-100 arasi puan verir; agirlikli toplama her zaman
kod tarafinda yapilir (rubrik agirliklari docs/scoring-rules.json'da).
Sebep: dil modelleri aritmetikte ve agirlik uygulamada tutarsiz olabilir,
ayrica puanin nasil olustugu DENETLENEBILIR kalmali - hakem "bu 78 nereden
geldi" diye sordugunda cevabin kodda ve config'de olmasi lazim.

HER IKI MOTORDA DA: uretilen sey bir ONERIDIR. Nihai karar hakemde
(bkz. docs/PROJECT_CONTEXT.md Bolum 1 KRITIK ILKE).
"""

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from text_utils import (  # noqa: E402
    KAYNAK_DESENLERI,
    SAYI_DESENI,
    count_matches,
    load_rules,
    normalize_for_matching,
    read_report,
)
from llm import degerlendir, llm_available, saglayici_durumu  # noqa: E402,F401

DEFAULT_SCORING_RULES_PATH = (
    Path(__file__).resolve().parent.parent / "docs" / "scoring-rules.json"
)

# LLM saglayici secimi, model adlari ve tum API ayrintilari llm.py'de.
# Bu dosya yalnizca "hangi motorla puanladik" bilgisini tasiyor.


def load_scoring_rules(path=DEFAULT_SCORING_RULES_PATH):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# Olculebilir sinyaller
# ---------------------------------------------------------------------------


def _distinct_term_count(normalized_text, terimler):
    """Metinde KAC FARKLI terim geciyor. Tekrar sayisini degil cesitliligi
    olcuyoruz: "model" kelimesini 80 kez yazan bolum 80 kat teknik degil.

    Iki taraf da normalize_for_matching ile katlanmis olmali - config'deki
    terimler ASCII yazili ('ogrenme orani'), rapor metni diakritikli
    ('öğrenme oranı'); katlamazsak eslesme sessizce sifir doner.
    """
    return sum(1 for t in terimler if normalize_for_matching(t) in normalized_text)


def _measure_section(bolum_metni, tanim, scoring_rules):
    """Bir bolumun olculebilir sinyallerini hesaplar (her biri 0-1 arasi).

    Ayrica ham olcumleri de doner ki gerekce metninde gercek sayilari
    gosterebilelim - hakem "neden bu puan" diye sordugunda cevap somut olsun.
    """
    normalized = normalize_for_matching(bolum_metni)
    uzunluk = len(bolum_metni)
    ham = {"karakter": uzunluk}
    sinyaller = {}

    beklenen_karakter = tanim.get("beklenen_karakter") or 1
    sinyaller["doluluk"] = min(1.0, uzunluk / beklenen_karakter)

    if "beklenen_kanit_yogunlugu" in tanim:
        sayi_adedi = count_matches(SAYI_DESENI, bolum_metni)
        yogunluk = sayi_adedi / (uzunluk / 1000) if uzunluk else 0.0
        ham["sayi_adedi"] = sayi_adedi
        ham["sayi_yogunlugu"] = round(yogunluk, 2)
        sinyaller["kanit"] = min(1.0, yogunluk / tanim["beklenen_kanit_yogunlugu"])

    if "beklenen_teknik_terim" in tanim:
        adet = _distinct_term_count(normalized, scoring_rules["teknik_terimler"]["kelimeler"])
        ham["teknik_terim"] = adet
        sinyaller["teknik"] = min(1.0, adet / tanim["beklenen_teknik_terim"])

    if "beklenen_ozgunluk_ifadesi" in tanim:
        adet = _distinct_term_count(
            normalized, scoring_rules["ozgunluk_ifadeleri"]["kelimeler"]
        )
        ham["ozgunluk_ifadesi"] = adet
        sinyaller["ozgunluk_dili"] = min(1.0, adet / tanim["beklenen_ozgunluk_ifadesi"])

    if "beklenen_atif" in tanim:
        adet = count_matches(KAYNAK_DESENLERI, bolum_metni)
        ham["atif"] = adet
        sinyaller["atif"] = min(1.0, adet / tanim["beklenen_atif"])

    return sinyaller, ham


_SINYAL_ADLARI = {
    "doluluk": "bölüm uzunluğu",
    "kanit": "sayısal kanıt yoğunluğu",
    "teknik": "teknik terim çeşitliliği",
    "ozgunluk_dili": "özgünlük argümanı",
    "atif": "kaynak/atıf sayısı",
}


def _rule_score_section(baslik, bolum_metni, tanim, scoring_rules):
    """Tek bir bolumu kural motoruyla puanlar."""
    if bolum_metni is None:
        return {
            "kriter": baslik,
            "puan": 0,
            "agirlik": tanim["agirlik"],
            "gerekce": (
                f"\"{baslik}\" bölümü raporda bulunamadı; bu kriter "
                "değerlendirilemedi ve 0 puan verildi."
            ),
            "olculdu": False,
        }

    sinyaller, ham = _measure_section(bolum_metni, tanim, scoring_rules)
    agirliklar = tanim["sinyaller"]

    toplam_agirlik = sum(agirliklar.values()) or 1.0
    puan = 100 * sum(
        agirliklar.get(ad, 0) * deger for ad, deger in sinyaller.items()
    ) / toplam_agirlik

    # Gerekce: hangi sinyal ne kadar tuttu, ham sayilarla
    parcalar = []
    for ad in agirliklar:
        if ad not in sinyaller:
            continue
        yuzde = round(100 * sinyaller[ad])
        parcalar.append(f"{_SINYAL_ADLARI.get(ad, ad)} %{yuzde}")

    olcumler = []
    olcumler.append(f"{ham['karakter']} karakter (beklenen ≥{tanim['beklenen_karakter']})")
    if "sayi_yogunlugu" in ham:
        olcumler.append(
            f"1000 karakterde {ham['sayi_yogunlugu']} sayısal değer "
            f"(beklenen ≥{tanim['beklenen_kanit_yogunlugu']})"
        )
    if "teknik_terim" in ham:
        olcumler.append(
            f"{ham['teknik_terim']} farklı teknik terim "
            f"(beklenen ≥{tanim['beklenen_teknik_terim']})"
        )
    if "ozgunluk_ifadesi" in ham:
        olcumler.append(
            f"{ham['ozgunluk_ifadesi']} farklı özgünlük ifadesi "
            f"(beklenen ≥{tanim['beklenen_ozgunluk_ifadesi']})"
        )
    if "atif" in ham:
        olcumler.append(f"{ham['atif']} atıf (beklenen ≥{tanim['beklenen_atif']})")

    return {
        "kriter": baslik,
        "puan": int(round(puan)),
        "agirlik": tanim["agirlik"],
        "gerekce": (
            f"Ölçülen: {', '.join(olcumler)}. "
            f"Sinyal karşılanma oranları: {', '.join(parcalar)}."
        ),
        "olculdu": True,
    }


# ---------------------------------------------------------------------------
# LLM motoru
# ---------------------------------------------------------------------------

_LLM_SISTEM_PROMPT = """Sen TEKNOFEST yarışma raporlarını değerlendiren bir \
hakem yardımcısısın. Nihai kararı SEN VERMİYORSUN — bir insan hakem senin \
değerlendirmeni okuyup kendi kararını verecek. Bu yüzden her puana somut, \
rapordan alıntıya dayalı bir gerekçe yaz.

Kurallar:
- Sana verilen rubrikteki her kriter için 0-100 arası bir puan ver.
- Gerekçeler Türkçe, en fazla 2 cümle ve SOMUT olsun ("yöntem iyi açıklanmış" \
değil, "YOLOv5 mimarisi ve hiperparametreleri tablo halinde verilmiş" gibi).
- Bir bölüm boş ya da anlamsızsa düşük puan ver ve nedenini yaz.
- Toplam puanı SEN HESAPLAMA; sadece kriter bazlı puanları ver.
- Rapordan emin olmadığın bir şeyi uydurma; bilgi yoksa bunu gerekçede belirt."""

_LLM_CIKTI_SEMASI = {
    "type": "object",
    "properties": {
        "kriter_puanlari": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "kriter": {"type": "string"},
                    "puan": {"type": "integer"},
                    "gerekce": {"type": "string"},
                },
                "required": ["kriter", "puan", "gerekce"],
                "additionalProperties": False,
            },
        },
        "guclu_yonler": {"type": "array", "items": {"type": "string"}},
        "gelisim_onerileri": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["kriter_puanlari", "guclu_yonler", "gelisim_onerileri"],
    "additionalProperties": False,
}


def _llm_evaluate(bolumler, rubrik, eksik_bolumler):
    """Secili LLM saglayicisiyla kriter degerlendirmesi.

    Saglayici secimi (Claude / Gemini / kapali) ve tum API ayrintilari
    llm.py'de; burasi yalnizca istemi kuruyor. Basarisiz olursa
    (None, hata) doner ve cagiran taraf kural motoruna duser.
    """
    rubrik_metni = "\n".join(
        f"- {t['kriter']} (rapordaki ağırlığı {t['agirlik']} puan)" for t in rubrik
    )
    bolum_metni = "\n\n".join(
        f"### {baslik}\n{(bolumler.get(baslik) or '(bu bölüm raporda bulunamadı)').strip()}"
        for baslik in [t["kriter"] for t in rubrik]
    )
    eksik_notu = (
        f"\n\nDİKKAT: şu bölümler raporda hiç bulunamadı: {', '.join(eksik_bolumler)}."
        if eksik_bolumler
        else ""
    )

    kullanici_mesaji = (
        f"Aşağıdaki rubriğe göre raporu değerlendir.\n\n"
        f"RUBRİK:\n{rubrik_metni}\n\n"
        f"RAPOR BÖLÜMLERİ:\n{bolum_metni}{eksik_notu}"
    )

    return degerlendir(_LLM_SISTEM_PROMPT, kullanici_mesaji, _LLM_CIKTI_SEMASI)


# ---------------------------------------------------------------------------
# Ana giris noktalari
# ---------------------------------------------------------------------------


def _match_db_criteria(criteria_list, rubrik, scoring_rules):
    """Backend'in veritabanindan gecirdigi kriterleri rubrik kalemleriyle
    eslestirir.

    NEDEN GEREKIYOR: Yarisma Yoneticisi kriterleri arayuzden tanimliyor
    (rol 1'in gorevi) ve backend seed'i su an INGILIZCE kriterler iceriyor
    ("Technical Novelty" gibi). Bunlarin bir kismi bizim olculebilir rubrik
    kalemlerimize karsilik geliyor, bir kismi (orn. "Ethical & Data Privacy")
    otomatik olculemiyor.

    Olculemeyen bir kriter icin SAYI URETMIYORUZ. Bir hakem karar destek
    sisteminde uydurma puan, puan vermemekten daha kotudur - o kriter
    "hakem degerlendirmeli" olarak isaretlenip aciga cikariliyor.
    """
    eslesmeler = scoring_rules.get("kriter_eslesmeleri", {})
    rubrik_adlari = {t["kriter"] for t in rubrik}

    eslesen = {}
    olculemeyen = []
    for kriter in criteria_list or []:
        baslik = (kriter.get("title") or "").strip()
        if not baslik:
            continue
        if baslik in rubrik_adlari:
            eslesen[baslik] = baslik
            continue
        hedef = eslesmeler.get(baslik)
        if hedef and hedef in rubrik_adlari:
            eslesen[baslik] = hedef
        else:
            olculemeyen.append(baslik)
    return eslesen, olculemeyen


def evaluate_criteria(
    pdf_path,
    criteria_list=None,
    rules=None,
    scoring_rules=None,
    motor="otomatik",
):
    """Raporu rubrige gore degerlendirir.

    motor: "otomatik" (API varsa LLM, yoksa kural), "kural", "llm".

    Doner:
      {
        "motor": "llm" | "kural",
        "kriter_puanlari": [{"kriter","puan","agirlik","gerekce"}],
        "toplam_puan": int,                # 0-100, agirlikli
        "onerilen_sonuc": "approve"|"revise"|"reject",
        "gerekce": str,
        "guclu_yonler": [str],
        "gelisim_onerileri": [str],
        "eksik_bolumler": [str],
        "olculemeyen_kriterler": [str],
        "uyarilar": [str],
      }
    ya da rapor okunamadiysa {"hata": "..."}.
    """
    if rules is None:
        rules = load_rules()
    if scoring_rules is None:
        scoring_rules = load_scoring_rules()

    rapor = read_report(pdf_path, rules)
    if "hata" in rapor:
        return {"hata": rapor["hata"]}

    rubrik = scoring_rules["kriter_rubrigi"]["bolumler"]
    bolumler = rapor["bolumler"]
    eksik_bolumler = [t["kriter"] for t in rubrik if t["kriter"] not in bolumler]

    _, olculemeyen = _match_db_criteria(criteria_list, rubrik, scoring_rules)

    uyarilar = []
    kullanilan_motor = "kural"
    llm_veri = None

    if motor in ("otomatik", "llm"):
        kullanilabilir, saglayici_aciklamasi = saglayici_durumu()
        if kullanilabilir:
            llm_veri, llm_hata = _llm_evaluate(bolumler, rubrik, eksik_bolumler)
            if llm_veri is not None:
                kullanilan_motor = "llm"
            else:
                uyarilar.append(
                    f"LLM değerlendirmesi yapılamadı ({llm_hata}); kural tabanlı "
                    "yedek motora düşüldü."
                )
        elif motor == "llm":
            # Kullanici acikca LLM istedi ama kullanilamiyor - nedenini
            # sessizce yutmuyoruz, hakem hangi motorun calistigini bilmeli.
            uyarilar.append(
                f"LLM motoru istendi ama kullanılamıyor ({saglayici_aciklamasi}); "
                "kural tabanlı yedek motora düşüldü."
            )

    # --- Kriter puanlarini uret ------------------------------------------
    if kullanilan_motor == "llm":
        llm_puanlari = {
            (k.get("kriter") or "").strip(): k for k in llm_veri.get("kriter_puanlari", [])
        }
        kriter_puanlari = []
        for tanim in rubrik:
            ad = tanim["kriter"]
            llm_kalem = llm_puanlari.get(ad)
            if llm_kalem is None:
                # LLM bir kriteri atlamis - kural motoruyla dolduruyoruz ki
                # agirlikli toplam eksik kalmasin
                yedek = _rule_score_section(
                    ad, bolumler.get(ad), tanim, scoring_rules
                )
                yedek["gerekce"] = (
                    "Claude API bu kriter için puan döndürmedi; kural tabanlı ölçüm "
                    "kullanıldı. " + yedek["gerekce"]
                )
                kriter_puanlari.append(yedek)
                continue
            puan = max(0, min(100, int(llm_kalem.get("puan", 0))))
            kriter_puanlari.append(
                {
                    "kriter": ad,
                    "puan": puan,
                    "agirlik": tanim["agirlik"],
                    "gerekce": (llm_kalem.get("gerekce") or "").strip()
                    or "Gerekçe döndürülmedi.",
                    "olculdu": ad in bolumler,
                }
            )
        guclu_yonler = [s for s in llm_veri.get("guclu_yonler", []) if s]
        gelisim_onerileri = [s for s in llm_veri.get("gelisim_onerileri", []) if s]
    else:
        kriter_puanlari = [
            _rule_score_section(t["kriter"], bolumler.get(t["kriter"]), t, scoring_rules)
            for t in rubrik
        ]
        guclu_yonler, gelisim_onerileri = _derive_feedback(kriter_puanlari)

    # --- Agirlikli toplam (HER ZAMAN kod tarafinda) ----------------------
    agirlik_toplami = sum(k["agirlik"] for k in kriter_puanlari) or 1
    toplam_puan = int(
        round(sum(k["puan"] * k["agirlik"] for k in kriter_puanlari) / agirlik_toplami)
    )

    esikler = scoring_rules["karar_esikleri"]
    if toplam_puan >= esikler["onay"]:
        onerilen_sonuc = "approve"
    elif toplam_puan >= esikler["revizyon"]:
        onerilen_sonuc = "revise"
    else:
        onerilen_sonuc = "reject"

    if olculemeyen:
        uyarilar.append(
            "Yarışma Yöneticisi'nin tanımladığı şu kriterler için otomatik ölçüm yok, "
            "hakem elle değerlendirmeli: " + ", ".join(olculemeyen) + "."
        )

    return {
        "motor": kullanilan_motor,
        "kriter_puanlari": kriter_puanlari,
        "toplam_puan": toplam_puan,
        "onerilen_sonuc": onerilen_sonuc,
        "gerekce": _build_rationale(
            kriter_puanlari, toplam_puan, onerilen_sonuc, kullanilan_motor,
            eksik_bolumler, uyarilar, esikler,
        ),
        "guclu_yonler": guclu_yonler,
        "gelisim_onerileri": gelisim_onerileri,
        "eksik_bolumler": eksik_bolumler,
        "olculemeyen_kriterler": olculemeyen,
        "uyarilar": uyarilar,
    }


def _derive_feedback(kriter_puanlari):
    """Kural motorunda guclu yonler / gelisim onerilerini kriter puanlarindan
    turetir (LLM motorunda bunlari modelin kendisi yaziyor)."""
    siralı = sorted(kriter_puanlari, key=lambda k: k["puan"], reverse=True)
    guclu = [
        f"{k['kriter']}: {k['puan']}/100 — bu bölüm beklenen düzeyi karşılıyor."
        for k in siralı
        if k["puan"] >= 80
    ][:3]
    gelisim = []
    for k in reversed(siralı):
        if k["puan"] >= 65:
            continue
        if not k["olculdu"]:
            gelisim.append(
                f"{k['kriter']}: bölüm raporda bulunamadı — şablondaki başlıkla eklenmeli."
            )
        else:
            gelisim.append(f"{k['kriter']}: {k['puan']}/100 — {k['gerekce']}")
        if len(gelisim) == 3:
            break
    return guclu, gelisim


def _build_rationale(
    kriter_puanlari, toplam_puan, onerilen_sonuc, motor, eksik_bolumler, uyarilar, esikler
):
    """Hakem panelinde tek paragraf olarak gosterilecek gerekce metni.

    Kriter bazli dokum buraya gomuluyor cunku arayuzde kriter kirilimini
    gosteren bir bilesen HENUZ YOK (bkz. docs/api-contract.md Bolum 2) -
    aksi halde bu bilgi hic goruntulenmezdi.
    """
    motor_adi = (
        f"{saglayici_durumu()[1]} ile rubrik tabanlı değerlendirme"
        if motor == "llm"
        else "kural tabanlı ölçüm (LLM devre dışı)"
    )
    sonuc_adi = {"approve": "onay", "revise": "revizyon", "reject": "ret"}[onerilen_sonuc]

    dokum = "; ".join(
        f"{k['kriter']} {k['puan']}/100 (ağırlık {k['agirlik']})" for k in kriter_puanlari
    )

    satirlar = [
        f"Ağırlıklı toplam {toplam_puan}/100 — önerilen sonuç: {sonuc_adi} "
        f"(eşikler: ≥{esikler['onay']} onay, ≥{esikler['revizyon']} revizyon). "
        f"Değerlendirme yöntemi: {motor_adi}.",
        f"Kriter kırılımı — {dokum}.",
    ]
    if eksik_bolumler:
        satirlar.append(
            "Raporda bulunamayan bölümler: " + ", ".join(eksik_bolumler) + "."
        )
    satirlar.extend(uyarilar)
    satirlar.append(
        "Bu bir ÖNERİDİR; nihai puan ve karar hakemin takdirindedir."
    )
    return " ".join(satirlar)


def evaluate_criteria_for_ui(
    pdf_path, criteria_list=None, rules=None, scoring_rules=None, motor="otomatik"
):
    """Backend'in bekledigi {"suggested_score","suggested_outcome","rationale"}
    formatini doner (bkz. backend/app/services/ai.py run_full_analysis).

    Ek olarak kriter_puanlari / guclu_yonler / gelisim_onerileri de
    donuyor: backend bunlari su an kullanmiyor ama api-contract.md Bolum 2
    bunlari sozlesmenin parcasi olarak tanimliyor ve yarismaci geri
    bildirim ekrani (frontend competitor-feedback) icin dogal kaynak.
    """
    sonuc = evaluate_criteria(pdf_path, criteria_list, rules, scoring_rules, motor)

    if "hata" in sonuc:
        return {
            "suggested_score": 0,
            "suggested_outcome": "revise",
            "rationale": (
                f"Rapor otomatik olarak değerlendirilemedi: {sonuc['hata']} "
                "Puan üretilmedi (0 gösteriliyor); bu bir kalite değerlendirmesi "
                "DEĞİLDİR. Hakem raporu elle incelemeli."
            ),
            "kriter_puanlari": [],
            "guclu_yonler": [],
            "gelisim_onerileri": [],
            "motor": "yok",
        }

    return {
        "suggested_score": sonuc["toplam_puan"],
        "suggested_outcome": sonuc["onerilen_sonuc"],
        "rationale": sonuc["gerekce"],
        "kriter_puanlari": sonuc["kriter_puanlari"],
        "guclu_yonler": sonuc["guclu_yonler"],
        "gelisim_onerileri": sonuc["gelisim_onerileri"],
        "motor": sonuc["motor"],
    }
