"""ai-scoring ana giris noktasi (Hayrettin'in modulu).

MVP maddeleri 3, 4 ve 5'i karsilar:
  3. Kategori uygunlugu     -> category.py
  4. Benzerlik analizi      -> similarity.py
  5. Kriter degerlendirmesi -> criteria.py

Backend bu dosyadaki uc `*_for_ui` fonksiyonunu cagiriyor
(bkz. backend/app/services/ai.py). Hasan'in modulundeki
`analyze_document_for_ui` ile ayni deseni izliyorlar: her biri hakem
panelinin bekledigi formatta doner, tek argumanla cagirilabilir ve
hicbiri istisna firlatmaz - hata durumunda bile bir sonuc doner, cunku
tek bir bozuk PDF tum analiz hattini dusurmemeli.

Ayrica `score_report()`, docs/api-contract.md Bolum 2'de tanimlanan
yapilandirilmis sozlesmeyi doner (kategori_onerisi, en_benzer_raporlar,
kriter_puanlari, guclu_yonler, gelisim_onerileri).
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from text_utils import load_rules  # noqa: E402
from category import (  # noqa: E402
    analyze_category,
    analyze_category_fit_for_ui,
    load_scoring_rules,
)
from similarity import analyze_similarity, check_similarity_for_ui  # noqa: E402
from criteria import (  # noqa: E402
    evaluate_criteria,
    evaluate_criteria_for_ui,
    llm_available,
    saglayici_durumu,
)

__all__ = [
    "analyze_category_fit_for_ui",
    "check_similarity_for_ui",
    "evaluate_criteria_for_ui",
    "score_report",
    "llm_available",
    "saglayici_durumu",
    "load_rules",
    "load_scoring_rules",
]


def score_report(
    pdf_path,
    categories=None,
    declared_category_id=None,
    existing_paths=None,
    criteria_list=None,
    rules=None,
    scoring_rules=None,
    motor="otomatik",
):
    """Uc analizi birlikte kosar ve api-contract.md Bolum 2 sozlesmesini doner.

    Kurallar ve config bir kez okunup uc alt module paylastiriliyor - her
    modul kendi basina cagirildiginda da calisiyor, ama birlikte
    cagirildiginda ayni dosyayi uc kez okumasin diye.
    """
    if rules is None:
        rules = load_rules()
    if scoring_rules is None:
        scoring_rules = load_scoring_rules()

    kategori = (
        analyze_category(pdf_path, categories, declared_category_id, rules, scoring_rules)
        if categories
        else {"hata": "Kategori tanimi verilmedi."}
    )
    benzerlik = analyze_similarity(pdf_path, existing_paths or [], rules, scoring_rules)
    kriterler = evaluate_criteria(pdf_path, criteria_list, rules, scoring_rules, motor)

    return {
        "kategori_onerisi": kategori.get("kategori_onerisi"),
        "kategori_guven_skoru": kategori.get("kategori_guven_skoru"),
        "beyan_edilen_kategori": kategori.get("beyan_edilen"),
        "beyan_edilen_kategori_puani": kategori.get("beyan_edilen_puani"),
        "en_benzer_raporlar": benzerlik.get("en_benzer_raporlar", []),
        "benzerlik_puani": benzerlik.get("benzerlik_puani"),
        "kriter_puanlari": kriterler.get("kriter_puanlari", []),
        "toplam_puan": kriterler.get("toplam_puan"),
        "onerilen_sonuc": kriterler.get("onerilen_sonuc"),
        "guclu_yonler": kriterler.get("guclu_yonler", []),
        "gelisim_onerileri": kriterler.get("gelisim_onerileri", []),
        "degerlendirme_motoru": kriterler.get("motor"),
        "hatalar": [
            m["hata"]
            for m in (kategori, benzerlik, kriterler)
            if isinstance(m, dict) and "hata" in m
        ],
    }


if __name__ == "__main__":
    import json

    if len(sys.argv) < 2:
        print("Kullanim: python scorer.py <pdf_dosya_yolu> [karsilastirilacak.pdf ...]")
        sys.exit(1)

    hedef = sys.argv[1]
    digerleri = sys.argv[2:]

    # Backend'in seed kategorileriyle ayni liste - komut satirindan hizli
    # deneme yapabilmek icin.
    ornek_kategoriler = [
        {"id": f"cat-{i}", "name": ad}
        for i, ad in enumerate(load_scoring_rules()["kategori"]["anahtar_kelimeler"], 1)
    ]

    _kullanilabilir, _aciklama = saglayici_durumu()
    print(f"Kriter motoru: {_aciklama}\n")
    sonuc = score_report(hedef, categories=ornek_kategoriler, existing_paths=digerleri)
    print(json.dumps(sonuc, ensure_ascii=False, indent=2))
