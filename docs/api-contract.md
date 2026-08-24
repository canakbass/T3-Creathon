# API Sözleşmesi (Taslak)

> Bu doküman Hasan (ai-doc-analysis), Hayrettin (ai-scoring) ve Mustafa (backend)
> arasında paylaşılacak sözleşmedir. Mustafa ve Hayrettin ile henüz resmi olarak
> onaylanmadı — taslak olarak buraya konuldu ki entegrasyon (FAZ 4) sırasında
> herkes aynı formatı bilsin.

## 1. Doküman & Şablon Analizi (Hasan — `ai-doc-analysis`)

**Giriş noktası:** `analyze_document(pdf_path: str, rules: dict) -> dict`
(bkz. `ai-doc-analysis/analyzer.py`)

**Backend'in beklediği çağrı şekli (öneri):** `POST /analyze-template` — dosya
yüklenince backend bu fonksiyonu (ya da onu saran bir HTTP endpoint'i) çağırır.

**Çıktı JSON şeması:**
```json
{
  "dil": "tr",
  "dil_uygun": true,
  "sayfa_sayisi": 12,
  "sayfa_uygun": true,
  "sablon_uygun": true,
  "eksik_basliklar": ["Sonuç"],
  "icerik_yetersiz_basliklar": [],
  "hatalar": []
}
```

| Alan | Tip | Açıklama |
|---|---|---|
| `dil` | string | ISO 639-1 dil kodu (`tr`, `en`, ...) ya da `unknown` |
| `dil_uygun` | boolean | Tespit edilen dil `kabul_edilen_diller` listesinde mi |
| `sayfa_sayisi` | int | PDF'in toplam sayfa sayısı |
| `sayfa_uygun` | boolean | Sayfa sayısı `min_sayfa`-`max_sayfa` aralığında mı |
| `sablon_uygun` | boolean | Tüm zorunlu başlıklar bulunduysa `true` |
| `eksik_basliklar` | string[] | Bulunamayan zorunlu başlıkların listesi |
| `icerik_yetersiz_basliklar` | string[] | **Bulunan** ama altında çok az metin olan başlıklar (bkz. sınırlama notu aşağıda) |
| `hatalar` | string[] | Analiz sırasında oluşan hata mesajları (normal akışta boş) |

**`icerik_yetersiz_basliklar` hakkında önemli sınırlama:** Bu sadece "başlığın
altında neredeyse hiç metin yok mu" diye bakan kaba bir kontrol — içeriğin
*kalitesini* değerlendirmiyor (o, Hayrettin'in AI kriter modülünün işi). Kalın
başlıklar arası mesafeyi ölçerek çalışıyor, `docs/mvp-rules.json`'daki
`min_bolum_karakter` (varsayılan eşik) ve `min_bolum_karakter_override`
(bölüme özel istisna — örn. "Takım Şeması" doğal olarak kısa olduğu için 0)
ile ayarlanabiliyor.

**Eşanlamlı başlıklar (`esanlamli_basliklar`):** 34 gerçek finalist raporunu
test ederken gördük ki gerçek hakemler "Kaynakça" yerine "Referanslar"/
"Kaynaklar" yazan raporları da kabul etmiş — birebir kelime eşleşmesi bu
raporları haksız yere "eksik" sayıyordu. `mvp-rules.json`'da her kanonik
başlık için bilinen varyantlar tanımlanabiliyor:
```json
"esanlamli_basliklar": {
  "Kaynakça": ["Referanslar", "Kaynaklar"],
  "Algoritmalar ve Sistem Mimarisi": ["Veri Setleri ve Algoritmalar"]
}
```
Bu ekleme sonrası 34 raporun 32'si `sablon_uygun: true` çıkıyor (öncesinde
28'di) — gerçek hakem kararına çok daha yakın bir sonuç.

**Hata durumu (PDF okunamadıysa):**
```json
{ "hata": "PDF'ten metin çıkarılamadı (taranmış/görüntü PDF olabilir)" }
```
Bu durumda backend, raporu "işlenemedi" durumuna almalı ve hakeme/yarışmacıya
bunu bildirmeli — sistem çökmemeli.

### ✅ Gerçek backend ile uyumsuzluk keşfedildi ve entegre edildi (2026-08-23)

Takımın ayrı ilerlettiği (https://github.com/mahmutconger/t3creathon_web)
backend
(`backend/app/services/ai.py`) ve veritabanı şeması (`AiAnalysis` tablosu:
`language_template_score` INTEGER kolonu) ve hakem paneli (frontend,
`src/lib/ai-analysis.ts`) benimle hiç senkron olunmadan **farklı bir format**
üzerine kurulmuş:

```json
{
  "languageTemplate": { "score": 92, "summary": "...", "findings": ["..."] },
  "contentHeading": { "score": 88, "summary": "...", "findings": ["..."] }
}
```

Bu, yukarıdaki boolean/liste tabanlı şemadan tamamen farklı — 0-100 puan +
insan-okur özet/bulgu bekliyor. Değiştirmek yerine (DB şeması + hakem paneli
zaten bu formata göre inşa edilmiş, geri almak daha maliyetli) bir **adaptör
fonksiyon** yazıldı: `analyze_document_for_ui(pdf_path, rules=None) -> dict`
(bkz. `ai-doc-analysis/analyzer.py`). Bunu çağırıp yukarıdaki iki alanı
üretiyor, backend'deki mock `analyze_document(file_path)`'in yerine
doğrudan geçebilir.

Puan bantları `src/lib/ai-analysis.ts`'teki eşiklerle hizalandı: ≥85 "yüksek
güven", 65-84 "gözden geçirilmeli", <65 "kritik". 34 gerçek raporla test
edildi: 32'si her iki alanda da 100 puan, 1'i (gerçekten eksik başlık) 80
puanla "gözden geçirilmeli" bandına, 1'i (bozuk font/yanlış dil) 60 puanla
"kritik" bandına düşüyor — beklenen davranış.

**Entegrasyon tamamlandı:** `backend/` ve `frontend/` bu repoya taşındı
(kaynak: yukarıdaki repo, commit `ef92a7f`, `master` dalı). `backend/app/services/ai.py`'deki
`analyze_document(file_path)` artık `ai-doc-analysis/analyzer.py`'deki
`analyze_document_for_ui`'ı çağırıyor. Doğrulandı: backend'in kendi pytest
suite'i (7/7 geçti) + gerçek KTR PDF'leriyle uçtan uca upload→analiz→get
akışı (doğru puanlar veritabanına yazılıp API'den döndü). Hayrettin'in
mock fonksiyonları (`evaluate_criteria`, `analyze_category_fit`,
`check_similarity`) henüz değiştirilmedi, o hâlâ kendi kısmını yazacak.

**~~Ayrıca dikkat:~~ Dil konusu kapandı (2026-08-24).** Bu bölümde daha önce
"o repodaki tüm UI metinleri İngilizce" yazıyordu; artık geçerli değil —
frontend `c348853` commit'i ile tamamen Türkçe'ye çevrildi
(`frontend/src/lib/ai-analysis.ts` etiketleri, `DECISION_LABELS`, tüm panel
metinleri). Dolayısıyla **karar Türkçe**: AI modüllerinin ürettiği tüm
özet/bulgu/gerekçe metinleri Türkçe olmalı. `ai-scoring` bu karara uyuyor.

Geriye kalan tek tutarsızlık backend tarafında: `backend/main.py`
`seed_db()` kategori adlarını İngilizce seed ediyor (`"Robotics &
Automation"`), frontend ise Türkçe adlar kullanıyor
(`criteria-template.ts` → `"Robotik ve Otomasyon"`). `ai-scoring` her iki
yazımı da tanıyor (`docs/scoring-rules.json` → `turkce_ad`), ama seed
verisinin Türkçeleştirilmesi Mustafa'nın kararı olarak duruyor.

## 2. Kategori / Benzerlik / Kriter Değerlendirme (Hayrettin — `ai-scoring`)

### ✅ Yazıldı ve backend'e entegre edildi (2026-08-24)

Modül `ai-scoring/` altında; detaylı tasarım gerekçeleri ve ölçüm sonuçları
için [`ai-scoring/README.md`](../ai-scoring/README.md).

**Backend'in çağırdığı giriş noktaları** (`backend/app/services/ai.py`
içindeki üç mock fonksiyonun yerine geçti — o dosyada artık mock yok):

```python
analyze_category_fit_for_ui(pdf_path, categories, declared_category_id=None)
    -> {"score": int, "summary": str, "findings": [str]}

check_similarity_for_ui(pdf_path, existing_paths)
    -> {"score": int, "summary": str, "findings": [str]}

evaluate_criteria_for_ui(pdf_path, criteria_list=None)
    -> {"suggested_score": int, "suggested_outcome": str, "rationale": str,
        "kriter_puanlari": [...], "guclu_yonler": [...], "gelisim_onerileri": [...],
        "motor": "llm" | "kural"}
```

`suggested_outcome` her zaman `approve` | `revise` | `reject` — frontend
`DECISION_LABELS` anahtarları bunlar, başka bir değer arayüzde `undefined`
gösterir.

**Yapılandırılmış sözleşme** (`score_report()` — bu bölümün orijinal
taslağıyla uyumlu, üzerine alanlar eklendi):

```json
{
  "kategori_onerisi": "AI & Machine Learning",
  "kategori_guven_skoru": 1.0,
  "beyan_edilen_kategori": "AI & Machine Learning",
  "beyan_edilen_kategori_puani": 100,
  "en_benzer_raporlar": [
    { "rapor_id": "RPT-2026-3210C8.pdf", "benzerlik_yuzdesi": 2.4, "konusal_benzerlik": 20.79 }
  ],
  "benzerlik_puani": 2,
  "kriter_puanlari": [
    { "kriter": "Özgünlük", "puan": 90, "agirlik": 25, "gerekce": "Ölçülen: ..." }
  ],
  "toplam_puan": 94,
  "onerilen_sonuc": "approve",
  "guclu_yonler": ["..."],
  "gelisim_onerileri": ["..."],
  "degerlendirme_motoru": "kural",
  "hatalar": []
}
```

### ⚠️ Dikkat edilmesi gereken üç nokta

**1. `similarity` ters polarite — DÜŞÜK puan İYİ sonuç.**
`frontend/src/lib/ai-analysis.ts` içinde `similarity` tek `polarity:
"negative"` kontrolü ve **kendi bantları var**: `≤15` "Özgün", `16-35`
"Gözden geçirilmeli", `>35` "Yüksek risk". Bu dosyanın Bölüm 1'inde yazan
"≥85 / 65-84 / <65" bandı yalnızca diğer **üç pozitif** kontrol için geçerli.
`check_similarity` bir **örtüşme yüzdesi** döndürür (0 = temiz, 100 = tam
kopya), kalite/güven puanı değil.

**2. Benzerlik puanı TF-IDF'ten değil birebir örtüşmeden geliyor.**
Ölçtük: birbirinden bağımsız 34 gerçek raporun TF-IDF kosinüs benzerliği
%11.9–45.2 (medyan %20.1), çünkü hepsi aynı şablonu kullanıyor. Kosinüs
intihal puanı olsaydı gerçek raporların bir kısmı `>35` "Yüksek risk"
bandında haksız yere suçlanacaktı. Aynı raporların 8 kelimelik birebir
örtüşmesi %0–7.9 (medyan %0.6). Ayrıntı: `ai-scoring/similarity.py` başındaki
not.

**3. Kriter kırılımı için veri tabanı kolonu yok.**
`evaluate_criteria` kriter bazlı puanları, `guclu_yonler` ve
`gelisim_onerileri` alanlarını döndürüyor, ama `models.AiAnalysis`'te bunlara
karşılık gelen kolon yok — dolayısıyla veri tabanına yazılmıyorlar. Bilgi
kaybolmasın diye kriter kırılımı `rationale` metninin içine gömülü geliyor
(arayüzde `rationale`'ın uzunluk sınırı yok). Kalıcı çözüm için `AiAnalysis`'e
kolon/tablo eklenmesi gerekir — **Mustafa'nın kararı**, tek taraflı şema
değişikliği yapılmadı. Frontend'de de kriter kırılımını gösteren bileşen yok;
`guclu_yonler`/`gelisim_onerileri` için doğal yer
`frontend/src/lib/competitor-feedback.ts` içindeki `strengths`/`improvements`
alanları (şu an hardcoded mock).

### Ek: backend'e geçirilen yeni parametre

`run_full_analysis` artık `declared_category_id` de alıyor ve
`backend/app/routes/reports.py` bunu `report.category_id`'den geçiriyor.
Bu olmadan kategori kontrolü yalnızca "en uygun kategori hangisi"
diyebiliyordu; asıl sorulması gereken soru "rapor **beyan edilen**
kategoriye ait mi". Parametre opsiyonel, eski dört argümanlı çağrı şekli
çalışmaya devam ediyor.

### Kural kaynağı

`ai-scoring`'in tüm eşikleri ve anahtar kelime listeleri
[`docs/scoring-rules.json`](scoring-rules.json) içinde. Sayılar tahmin değil:
34 gerçek finalist raporu ölçülerek türetildi (`python ai-scoring/calibrate.py`),
her eşiğin kaynağı dosyadaki `_kaynak` notlarında yazılı.

### Referans rubrik (Havacılıkta YZ / KTR, 2022 — puanlama örneği için)

34 gerçek finalist raporundan çıkarılan bölüm puan ağırlıkları — `kriter_puanlari`
alanının nasıl doldurulabileceğine dair somut bir örnek olarak buraya not
edildi (bkz. `ai-doc-analysis/sample_reports/havacilikta_yz_ktr/Puan_Rubrigi.md`
ve `KTR_Dogrulama.csv`). **Bu rakamların içerik kalitesine göre gerçek puan
hesaplaması Hayrettin'in modülünün işi** — burada sadece hangi bölümün kaç
puan ağırlığı olduğu listeleniyor, hesaplama/skorlama yapılmadı:

| Bölüm | Puan |
|---|---|
| Takım Şeması | 5 |
| Proje Mevcut Durum Değerlendirmesi | 15 |
| Algoritmalar ve Sistem Mimarisi | 25 |
| Özgünlük | 25 |
| Sonuçlar ve İnceleme | 25 |
| Kaynakça | 5 |
| **Toplam** | **100** |

## 3. Kural Kaynağı

Zorunlu başlıklar, kabul edilen diller ve sayfa sınırları `docs/mvp-rules.json`
dosyasında tutulur — kod içine gömülmez, böylece şartname netleştikçe sadece bu
dosya güncellenir.
