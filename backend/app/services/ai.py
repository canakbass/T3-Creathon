import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

# Iki AI modulu de gercek kod olarak entegre edildi:
#   ai-doc-analysis (Hasan)  -> analyze_document          [2026-08-23]
#   ai-scoring      (Hayrettin) -> analyze_category_fit,
#                                  check_similarity,
#                                  evaluate_criteria      [2026-08-24]
# Bu dosyada artik mock fonksiyon YOK; `random` bagimliligi da kalkti
# (mock'lar rastgele puan uretiyordu, bu yuzden ayni rapor her analizde
# farkli puan aliyordu - hakem karar destek sisteminde kabul edilemez).

_REPO_KOKU = Path(__file__).resolve().parents[3]
for _modul_yolu in (_REPO_KOKU / "ai-doc-analysis", _REPO_KOKU / "ai-scoring"):
    if str(_modul_yolu) not in sys.path:
        sys.path.insert(0, str(_modul_yolu))

from analyzer import analyze_document_for_ui as _hasan_analyze_document  # noqa: E402
from scorer import (  # noqa: E402
    analyze_category_fit_for_ui as _hayrettin_category,
    check_similarity_for_ui as _hayrettin_similarity,
    evaluate_criteria_for_ui as _hayrettin_criteria,
    llm_available,
    saglayici_durumu,
    load_rules,
    load_scoring_rules,
)


def analyze_document(file_path: str) -> Dict[str, Any]:
    """Hasan's Module: gercek dil/sablon/baslik/icerik kontrolu.

    ai-doc-analysis/analyzer.py -> analyze_document_for_ui() cagriliyor; o
    fonksiyon zaten bu backend'in bekledigi
    {"languageTemplate": {score, summary, findings}, "contentHeading": {...}}
    formatinda donuyor (bkz. docs/api-contract.md - "Gercek backend ile
    uyumsuzluk kesfedildi" notu). Kurallar (zorunlu basliklar, kabul edilen
    diller vb.) docs/mvp-rules.json'dan okunuyor; rules=None verilince
    analyzer kendi varsayilanini kullanir.
    """
    return _hasan_analyze_document(file_path)


def evaluate_criteria(
    file_path: str,
    criteria_list: List[Dict[str, Any]],
    rules: Optional[dict] = None,
    scoring_rules: Optional[dict] = None,
) -> Dict[str, Any]:
    """Hayrettin's Module: rubrik tabanli kriter degerlendirmesi (MVP madde 5).

    ANTHROPIC_API_KEY tanimliysa Claude API ile, degilse deterministik kural
    motoruyla calisir (bkz. ai-scoring/criteria.py). Her iki durumda da
    agirlikli toplam kod tarafinda hesaplanir, boylece puanin nasil
    olustugu denetlenebilir kalir.

    {"suggested_score", "suggested_outcome", "rationale"} doner - run_full_analysis
    bunlari kullaniyor. Ayrica kriter_puanlari / guclu_yonler /
    gelisim_onerileri de donuyor (api-contract.md Bolum 2); veri tabani
    semasinda henuz karsilik gelen kolon yok, bkz. asagidaki not.
    """
    return _hayrettin_criteria(file_path, criteria_list, rules, scoring_rules)


def analyze_category_fit(
    file_path: str,
    categories: List[Dict[str, Any]],
    declared_category_id: Optional[str] = None,
    rules: Optional[dict] = None,
    scoring_rules: Optional[dict] = None,
) -> Dict[str, Any]:
    """Hayrettin's Module: kategori uygunlugu (MVP madde 3).

    declared_category_id verilirse "rapor BEYAN EDILEN kategoriye ait mi"
    sorusu yanitlanir - dogru soru bu. Verilmezse modul yalnizca "en uygun
    kategori hangisi" onerisini puanlar ve bunu bulgularinda acikca belirtir
    (o durum kategori uygunlugunun DOGRULANMASI degildir).
    """
    return _hayrettin_category(
        file_path, categories, declared_category_id, rules, scoring_rules
    )


def check_similarity(
    file_path: str,
    existing_reports_paths: List[str],
    rules: Optional[dict] = None,
    scoring_rules: Optional[dict] = None,
) -> Dict[str, Any]:
    """Hayrettin's Module: benzerlik / intihal analizi (MVP madde 4).

    DIKKAT - bu kontrol ters polarite: DUSUK puan IYI sonuc demek
    (frontend/src/lib/ai-analysis.ts, similarity -> polarity "negative";
    <=15 "Ozgun", 16-35 "Gozden gecirilmeli", >35 "Yuksek risk").

    Puan, TF-IDF konusal benzerlikten DEGIL birebir kelime ortusmesinden
    geliyor; nedeni ai-scoring/similarity.py basindaki olcumde anlatiliyor
    (ayni sablonu kullanan bagimsiz raporlarin konusal benzerligi %45'e
    kadar cikiyor, birebir ortusmesi ise %8'i gecmiyor).
    """
    return _hayrettin_similarity(file_path, existing_reports_paths, rules, scoring_rules)


def run_full_analysis(
    file_path: str,
    db_categories: List[Dict[str, Any]],
    existing_files: List[str],
    criteria_list: List[Dict[str, Any]],
    declared_category_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Dort kontrolu tek AiAnalysis yukune birlestirir.

    Kurallar (docs/mvp-rules.json, docs/scoring-rules.json) burada BIR KEZ
    okunup alt modullere paylastiriliyor - aksi halde her kontrol ayni iki
    dosyayi diskten yeniden okurdu.

    declared_category_id opsiyonel: eski cagri sekli (dort argument) da
    calismaya devam etsin diye. Verilmediginde kategori kontrolu bunu
    kendi bulgularinda acikca belirtiyor.

    NOT - kriter kirilimi: evaluate_criteria, kriter bazli puanlari
    (kriter_puanlari) ve yarismaciya gosterilecek guclu_yonler /
    gelisim_onerileri alanlarini da donuyor, ama models.AiAnalysis'te
    bunlar icin kolon YOK, dolayisiyla veri tabanina yazilmiyorlar. Bu
    bilginin kaybolmamasi icin kriter kirilimi `rationale` metninin icine
    gomulu geliyor (bkz. ai-scoring/criteria.py _build_rationale). Kalici
    cozum icin AiAnalysis'e bir kolon/tablo eklenmesi gerekir - bunu
    Mustafa ile konusmak lazim, tek tarafli sema degisikligi yapmadim.
    """
    rules = load_rules()
    scoring_rules = load_scoring_rules()

    doc_res = analyze_document(file_path)
    cat_res = analyze_category_fit(
        file_path, db_categories, declared_category_id, rules, scoring_rules
    )
    sim_res = check_similarity(file_path, existing_files, rules, scoring_rules)
    eval_res = evaluate_criteria(file_path, criteria_list, rules, scoring_rules)

    return {
        "suggested_score": eval_res["suggested_score"],
        "suggested_outcome": eval_res["suggested_outcome"],
        "rationale": eval_res["rationale"],
        "language_template": doc_res["languageTemplate"],
        "content_heading": doc_res["contentHeading"],
        "category_match": cat_res,
        "similarity": sim_res,
    }


def engine_info() -> Dict[str, Any]:
    """Hangi degerlendirme motorunun aktif oldugunu bildirir.

    Demo sirasinda ve hata ayiklamada "su an LLM mi kural motoru mu
    calisiyor" sorusunu tek cagriyla yanitlamak icin. Hakem panelinde
    gosterilmiyor; gerekce metni bu bilgiyi zaten iceriyor.
    """
    kullanilabilir, aciklama = saglayici_durumu()
    return {
        "kriter_motoru": "llm" if kullanilabilir else "kural-tabanli",
        "saglayici": aciklama,
        "llm_kullanilabilir": kullanilabilir,
    }
