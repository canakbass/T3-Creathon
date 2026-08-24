# ai-scoring — Hayrettin

MVP'nin 3, 4 ve 5. maddelerini karşılayan modül: **kategori uygunluğu**,
**benzerlik/intihal analizi** ve **kriter bazlı değerlendirme (puan + gerekçe)**.

> **Temel ilke:** Bu modül karar vermez, **öneri üretir**. Nihai puan ve karar
> her zaman hakemdedir. Modülün ürettiği her metin bunu açıkça söyler, ve
> ölçemediği bir şeye puan vermek yerine "hakem elle değerlendirmeli" der.

## Kurulum ve çalıştırma

```bash
pip install -r ai-scoring/requirements.txt

# Test paketi (34 gerçek finalist raporu + saldırgan vakalar)
python ai-scoring/tests/test_scorer.py

# Tek bir raporu komut satırından incele
python ai-scoring/scorer.py rapor.pdf [karsilastirilacak1.pdf ...]

# Eşikleri yeniden ölçmek/doğrulamak için
python ai-scoring/calibrate.py
```

`scikit-learn` ve `anthropic` **zorunlu değil** — ikisi de yoksa sistem
çalışmaya devam eder, sadece ilgili ek sinyali kaybeder ve bunu hakeme
söyler (aşağıda "İki motor" ve "Bağımlılıklar").

## Dosyalar

| Dosya | İş |
|---|---|
| `scorer.py` | Ana giriş noktası; backend bunu import ediyor |
| `category.py` | Kategori uygunluğu (MVP 3) |
| `similarity.py` | Benzerlik / intihal (MVP 4) |
| `criteria.py` | Kriter değerlendirmesi (MVP 5), Claude API + kural motoru |
| `text_utils.py` | PDF okuma, bölümleme, normalizasyon, n-gram |
| `calibrate.py` | Eşikleri 34 gerçek rapordan ölçen betik |
| `tests/test_scorer.py` | 76 test |

Kurallar koda gömülmedi, **`docs/scoring-rules.json`** içinde tutuluyor —
Yarışma Yöneticisi her yarışma için kod değiştirmeden ayarlayabilsin diye
(bkz. `docs/PROJECT_CONTEXT.md` Bölüm 8, "Standartlık").

PDF metin çıkarma ve bölümleme işi sıfırdan yazılmadı; Hasan'ın
`ai-doc-analysis/analyzer.py` modülü import ediliyor. Bunun için o dosyaya
`find_sections()` adında ortak bir fonksiyon eklendi (mevcut `check_content`
artık onu kullanıyor) — Hasan'ın 32 testi bu değişiklikten sonra da geçiyor.

## Backend'in çağırdığı üç fonksiyon

Hasan'ın `analyze_document_for_ui` desenini izliyorlar: hakem panelinin
beklediği `{"score", "summary", "findings"}` formatında dönüyorlar, tek
argümanla çağrılabiliyorlar ve **hiçbiri istisna fırlatmıyor** — tek bozuk
PDF tüm analiz hattını düşürmemeli.

```python
analyze_category_fit_for_ui(pdf_path, categories, declared_category_id=None)
check_similarity_for_ui(pdf_path, existing_paths)
evaluate_criteria_for_ui(pdf_path, criteria_list=None)   # suggested_score/outcome/rationale
```

Ayrıca `score_report()`, `docs/api-contract.md` Bölüm 2'deki yapılandırılmış
sözleşmeyi döner (`kategori_onerisi`, `en_benzer_raporlar`, `kriter_puanlari`,
`guclu_yonler`, `gelisim_onerileri`).

---

## Eşikler tahmin değil, ölçüm

Elimizde 34 gerçek TEKNOFEST finalist raporu var (Havacılıkta YZ / KTR 2022 —
gerçek hakemlerin kabul ettiği raporlar). Bütün eşikler `calibrate.py` ile
bu raporlar ölçülerek belirlendi. Her eşiğin nereden geldiği
`docs/scoring-rules.json` içindeki `_kaynak` notlarında yazılı.

### Benzerlik: en kritik tasarım kararı

İlk akla gelen yol, iki raporun TF-IDF kosinüs benzerliğini "intihal oranı"
olarak vermekti. Ölçtük:

| Ölçüm (birbirinden **bağımsız** 34 gerçek rapor) | Aralık | Medyan |
|---|---|---|
| TF-IDF kosinüs benzerliği | %11.9 – **%45.2** | %20.1 |
| 8 kelimelik birebir örtüşme | %0.0 – **%7.9** | %0.6 |

Kosinüs benzerliği yüksek çünkü hepsi **aynı şablonu ve aynı alan
terminolojisini** kullanıyor — yani "aynı konuda yazılmış" demek,
"kopyalanmış" demek değil. Frontend'in intihal bandı `>35` "Yüksek risk"
olduğu için (`frontend/src/lib/ai-analysis.ts`), kosinüs kullanılsaydı
**gerçek ve masum raporların bir kısmı intihalle suçlanacaktı.** Bir hakem
karar destek sisteminde bu, sistemi kullanılamaz kılan türde bir hata.

Bu yüzden:

- **Puanı belirleyen sinyal:** birebir kelime örtüşmesi (8-gram *kapsama*)
- **Hakeme bağlam olarak gösterilen:** konusal (TF-IDF) benzerlik

Kapsama (containment) oranı kullanılıyor, Jaccard değil: 3 sayfalık bir rapor
30 sayfalık bir rapordan tamamen kopyalanmış olabilir; Jaccard bunu büyük
belgenin boyutu yüzünden kaçırır.

Doğrulandı — bkz. test paketi:

| Vaka | Sonuç | Frontend bandı |
|---|---|---|
| İki bağımsız gerçek rapor | %2.4 | Özgün |
| 34 gerçek raporun en kötüsü | %8 | Özgün |
| Yarısı kopyalanmış rapor | %50.9 | Yüksek risk |
| Birebir kopyalanmış rapor | %100 | Yüksek risk |

> **Ters polarite:** Benzerlik, frontend'de tek "negatif polarite" kontrolü —
> **düşük puan iyi sonuç** demek (`≤15` Özgün, `16-35` Gözden geçirilmeli,
> `>35` Yüksek risk). Diğer üç kontrolün bandı farklı (`≥85` / `65-84` / `<65`).

### Kategori uygunluğu

Sorulan soru: *"rapor **beyan edilen** kategoriye mi ait?"* — "en uygun
kategori hangisi" değil. Bir İHA-yapay zeka raporu hem Robotik hem Yapay
Zeka kategorisine meşru şekilde uyar; ikinci bir makul kategorinin varlığı
kusur değildir. Bu yüzden puanı, beyan edilen kategorinin **mutlak** eşleşme
gücü belirliyor; başka bir kategorinin daha iyi eşleşmesi ceza olarak düşüyor.

Backend'in seed kategorileri **İngilizce** (`"Robotics & Automation"`),
raporlar ise **Türkçe** — düz kelime eşleşmesi sıfır sonuç verir. Bu yüzden
her kategori için Türkçe anahtar kelime listesi config'de tutuluyor.

34 rapor üzerinde ölçüm (doğru kategori: AI & Machine Learning):

| Kategori | min | p25 | medyan | max |
|---|---|---|---|---|
| **AI & Machine Learning** | 0.179 | 0.402 | **0.482** | 0.643 |
| Robotics & Automation | 0.083 | 0.125 | 0.125 | 0.292 |
| HealthTech / Sustainability / FinTech / Game Design | | | ≤0.091 | |

**34/34 rapor doğru kategoriye atanıyor.** Aynı raporlar FinTech olarak beyan
edilseydi puan 10 (kritik banda) olurdu — test paketinde doğrulanıyor.

Config'de anahtar kelime tanımı **olmayan** bir kategori için karakter n-gram
TF-IDF yedeğine düşülüyor ve bulgularda bunun zayıf bir yöntem olduğu açıkça
yazılıyor — hakem, puanın nasıl üretildiğini bilmeli.

### Kriter değerlendirmesi

Rubrik ağırlıkları `docs/api-contract.md`'deki referans rubrikten (Takım
Şeması 5, Proje Mevcut Durum 15, Algoritmalar 25, Özgünlük 25, Sonuçlar 25,
Kaynakça 5 = 100). Her bölüm ölçülebilir sinyallerle puanlanıyor: bölüm
uzunluğu, sayısal kanıt yoğunluğu, teknik terim çeşitliliği, özgünlük
argümanı, atıf sayısı. Her sinyalin "yeterli" eşiği, 34 gerçek raporun o
sinyaldeki **25. yüzdelik dilimi** — yani "gerçek finalistlerin en zayıf
%25'i kadar" bir alt sınır. Amaç iyi raporu ödüllendirmek değil, kabul
edilebilir alt sınırın altını fark etmek.

34 gerçek finalist raporunda sonuç: toplam puan **75–100** (medyan 91),
hiçbiri `reject` almıyor. Bu doğru davranış (hepsi gerçekten finale kalmış
raporlar), ama tek başına bir şey kanıtlamaz — her şeye 100 veren bir sistem
de aynı sonucu verirdi. Bu yüzden testlerin ağırlığı saldırgan vakalarda ve
puanların gerçekten dağıldığını doğrulayan kontrollerde.

---

## İki motor: yerel kural motoru (varsayılan) + isteğe bağlı LLM

Kriter değerlendirmesi **varsayılan olarak tamamen yerel** çalışır. LLM
yalnızca `AI_SCORING_LLM` ortam değişkeniyle açıkça açılırsa devreye girer.
Hangi motorun kullanıldığı hakeme gösterilen gerekçe metninde yazılı.

```bash
# Varsayılan — hiçbir veri dışarı çıkmaz
python ai-scoring/scorer.py rapor.pdf

# Claude API
AI_SCORING_LLM=claude ANTHROPIC_API_KEY=... python ai-scoring/scorer.py rapor.pdf

# Google Gemini (aşağıdaki gizlilik uyarısını okuyun)
AI_SCORING_LLM=gemini GOOGLE_API_KEY=... AI_SCORING_LLM_ONAY=evet \
  python ai-scoring/scorer.py rapor.pdf
```

Model `AI_SCORING_MODEL` ile değiştirilebilir (varsayılanlar:
`claude-opus-5`, `gemini-2.5-flash`).

### ⚠️ Gizlilik: LLM açmadan önce okuyun

LLM kullanmak, rapor **metnini üçüncü taraf bir sunucuya göndermek**
demektir. Creathon şartnamesi iki şey söylüyor (bkz. `docs/CLAUDE.md`):
*"Program süresince erişilen T3 Vakfı verileri üçüncü taraflarla
paylaşılamaz"* ve çözümün KVKK'ya uygun olması.

Google Gemini'nin **ücretsiz** katmanı bununla çelişiyor
([resmi koşullar](https://ai.google.dev/gemini-api/terms)):

> "Google uses the content you submit to the Services and any generated
> responses to provide, improve, and develop Google products" · "human
> reviewers may read, annotate, and process your API input and output" ·
> **"Do not submit sensitive, confidential, or personal information to the
> Unpaid Services."**

Ücretli katmanda bunların hiçbiri geçerli değil. AEA/İsviçre/Birleşik
Krallık kullanıcıları ücretsiz katmanda da ücretli korumaları alıyor —
**Türkiye bu listede değil.**

Bu yüzden ücretsiz Gemini için `AI_SCORING_LLM_ONAY=evet` şart koşuluyor:
kimse bunu farkında olmadan açmasın diye. **Yerel kural motoru bu sorunu
tamamen ortadan kaldırıyor — bu bir eksiklik değil, bu proje için bir
avantaj ve Demo Day'de anlatılmaya değer.**

### Neden yerel motor varsayılan

- **Gizlilik.** Yukarıdaki madde.
- **Dayanıklılık.** Demo Day'de internet kesilse, kredi bitse veya API
  geçici hata verse sistem çalışmaya devam etmeli. Tek motorlu bir
  tasarımda MVP madde 5 jüri önünde çökebilir.
- **Tekrarlanabilirlik.** Kural motoru deterministik: aynı rapor her zaman
  aynı puanı alır. Bir değerlendirme sisteminde bu önemli bir özellik.

**Her iki motorda da toplam puanı kod hesaplıyor.** LLM sadece her bölümün
kalitesine 0–100 puan verir; ağırlıklı toplama her zaman kodda yapılır.
Sebep: dil modelleri aritmetikte tutarsız olabilir, ve hakem *"bu 78 nereden
geldi"* diye sorduğunda cevabın kodda ve config'de olması gerekir.

## Bağımlılıklar ve zarif bozulma

| Eksikse | Ne olur |
|---|---|
| `AI_SCORING_LLM` ayarlanmamış | Kural motoru çalışır (varsayılan ve tercih edilen durum) |
| SDK yok / API key yok / kota bitti | Kriter değerlendirmesi kural motoruna düşer, **nedeni** gerekçede belirtilir |
| `scikit-learn` yok | Konusal benzerlik ve karakter n-gram yedeği atlanır; **benzerlik puanı etkilenmez** (saf Python) |
| PDF okunamıyor | Puan 0 döner, ama özet/bulgular bunun bir **analiz hatası** olduğunu, kalite değerlendirmesi olmadığını söyler |
| Karşılaştırılacak rapor yok | Benzerlik 0 döner, bulgularda bunun "özgünlük kanıtlandı" anlamına **gelmediği** yazılır |

## Bilinen sınırlamalar

- **Benzerlik yalnızca sistemdeki diğer raporlara bakıyor.** Kamuya açık
  kaynaklara / internete karşı intihal kontrolü yok. Hakem panelindeki
  metinler bu yüzden "önceki başvurularla" diyor, "internetle" demiyor.
- **Anahtar kelime listeleri Havacılıkta YZ raporları üzerinde kalibre
  edildi.** Başka bir yarışma kategorisi için `docs/scoring-rules.json`
  güncellenmeli; `calibrate.py` bunu yeniden ölçmek için hazır.
- **Kriter kırılımı veri tabanına yazılmıyor.** `models.AiAnalysis`'te
  karşılık gelen kolon yok, bu yüzden kriter bazlı puanlar `rationale`
  metninin içine gömülü geliyor. Kalıcı çözüm için şema değişikliği gerekiyor
  (Mustafa ile konuşulmalı — tek taraflı şema değişikliği yapılmadı).
- **Özgünlük dili sinyali zayıf.** Ölçtük: listedeki 27 ifadeden yalnızca
  13'ü 34 raporda hiç geçiyor, medyan isabet 1. Bu yüzden ağırlığı 0.3'ten
  0.2'ye düşürüldü. Claude API motoru bu kriterde belirgin şekilde daha iyi.
- **Ölçülemeyen kriterlere puan verilmiyor.** Örnek: "Ethical & Data Privacy
  Considerations" metinden güvenilir ölçülemez (bir raporun "KVKK" yazması,
  veri gizliliğini ele aldığını kanıtlamaz). Bu kriterler bilinçli olarak
  hakeme bırakılıyor — uydurma puan, puan vermemekten daha kötüdür.
