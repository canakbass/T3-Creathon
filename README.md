# teknofest-degerlendirme

T3 Vakfı Yapay Zeka Creathonu — Problem 4: TEKNOFEST rapor değerlendirme
sürecini destekleyen, **AI'nın nihai karar vermediği** bir karar destek
sistemi. AI sadece analiz/öneri üretir, nihai kararı her zaman hakem verir.

Proje bağlamı, ekip, kararlar ve zaman planı için: [`docs/CLAUDE.md`](docs/CLAUDE.md)
ve [`docs/PROJECT_CONTEXT.md`](docs/PROJECT_CONTEXT.md).

## Klasörler ve sorumluluklar

| Klasör | Kişi | İçerik | Durum |
|---|---|---|---|
| `ai-doc-analysis/` | Hasan | Dil/şablon/başlık kontrolü + şablondan otomatik çıkarım | ✅ Çalışıyor, gerçek veriyle test edildi (46 test) |
| `ai-scoring/` | Hayrettin | Kategori, benzerlik, kriter puanlama | ✅ Çalışıyor, backend'e entegre edildi (102 test) — mock'lar kaldırıldı |
| `backend/` | Mustafa | FastAPI — API, veri modeli, auth, yarışma/takım/atama | ✅ Çalışıyor (93 test); SQLite veya Supabase Postgres |
| `frontend/` | Mahmut | Next.js — rol bazlı paneller | ✅ Backend'e bağlı (123 test); tüm mock veri kaldırıldı |
| `docs/` | — | Ortak dokümanlar, API sözleşmesi, MVP kuralları | Güncel |

## MVP'nin 6 zorunlu maddesi — hepsi tamam

| # | Madde | Durum |
|---|---|---|
| 1 | Dil/şablon kontrolü | ✅ Hasan — gerçek kod, uçtan uca çalışıyor |
| 2 | Başlık/içerik kontrolü | ✅ Hasan — gerçek kod, uçtan uca çalışıyor |
| 3 | Kategori uygunluğu | ✅ Hayrettin — gerçek kod, uçtan uca çalışıyor |
| 4 | Benzerlik analizi | ✅ Hayrettin — gerçek kod, uçtan uca çalışıyor |
| 5 | AI kriter değerlendirmesi (puan + gerekçe) | ✅ Hayrettin — gerçek kod, uçtan uca çalışıyor |
| 6 | Hakemin görüp nihai kararı verebildiği arayüz | ✅ Arayüz canlı API'ye bağlı, hakem AI önerisini ezebiliyor |

**Demo akışı (gerçek veriyle doğrulandı):**

1. **Yarışma Yöneticisi** giriş yapar → yarışma oluşturur → "Kriter ve Şablon
   Tanımı" ekranından zorunlu başlıkları ve kriter ağırlıklarını girer →
   başvuruyu açar. (Kurallar tanımlanmadan başvuru **açılamıyor** — AI neye
   göre kontrol yapacağını bilemez.)
2. **Yarışmacı** giriş yapar → açık yarışmayı seçip **kendi raporunu yükler**
   → AI analizi otomatik başlar (~2 sn). Yönetici tek tek dosya yüklemiyor.
3. **Yarışma Yöneticisi** hakemleri yarışmaya ekler → "Dengeli dağıt" ile
   raporlar hakemler arasında paylaştırılır → gerekirse tek tek sorumlu
   hakem değiştirilir.
4. **Hakem** giriş yapar → **yalnızca kendisine atanan** raporları görür →
   raporun **kendisini panelde okur/indirir** → dört AI kontrolünü ve "AI
   Dördüncü Göz" önerisini görür → isterse AI'dan gerekçe **taslağı** ister
   → kendi puanını verip AI önerisini ezer.
5. **Yarışmacı** sonucunu, güçlü yönlerini ve gelişim önerilerini görür.
   Benzerlik/intihal verisi ve AI'nın önerdiği puan yarışmacıya
   **gösterilmez**.
6. **Değerlendirme Yöneticisi** tamamlanma oranını izler.

**Çok rollü test hesabı:** `asdfghjkl@gmail.com` / `asdfghjkl` — dört rolün
hepsine sahip. Girişte rol seçim ekranı çıkar; tek hesapla tüm akış
denenebilir.

### Yarışma aşamaları

`draft` → `open` → `closed` → `evaluating` → `completed`

Yarışmacı **yalnızca `open`** aşamasında rapor yükleyebilir; yönetici test
ve düzeltme için her aşamada yükleyebilir. `open`'a geçmek için şablon
kuralları ve kriterler tanımlı olmalı.

**Not:** `backend/` ve `frontend/`, Mahmut/Mustafa'nın ayrı ilerlettiği
[t3creathon_web](https://github.com/mahmutconger/t3creathon_web) reposundan
bu monorepoya taşındı (2026-08-23). O repo artık kullanılmıyor — bundan
sonra tüm çalışma buradan devam etmeli, yoksa tekrar ayrışırız.

## Şu ana kadar tamamlanan: `ai-doc-analysis` + backend entegrasyonu

Rapor yüklendiğinde çalışan ilk kontrol katmanı. PDF'i alır, 5 şeyi kontrol
edip JSON döner: dil uygunluğu, sayfa sayısı uygunluğu, şablon uygunluğu
(zorunlu başlıklar), içeriği zayıf bölümler, hatalar.

**Referans veri seti:** TEKNOFEST Havacılıkta Yapay Zeka Yarışması, Kritik
Tasarım Raporu (KTR), 2022 sezonu — **34 gerçek finalist raporu** (uydurma
değil, TEKNOFEST'in kendi Derece Listesi'nden). Detay: [`ai-doc-analysis/README.md`](ai-doc-analysis/README.md).

**Son test sonucu** (`python ai-doc-analysis/tests/test_analyzer.py`):

```
32 başarılı, 0 başarısız
```

**34 gerçek rapor üzerinde toplu sonuç:**

| Sonuç | Adet | Açıklama |
|---|---|---|
| Tam uygun | 32/34 | Dil, sayfa sayısı, şablon, içerik — hepsi geçti |
| Gerçekten eksik bölüm | 1/34 | KTR_12 — "Kaynakça" (ya da eşanlamlısı) hiç yok |
| Kaynak dosya hatası | 1/34 | KTR_08 — PDF'in kendi font kodlaması bozuk (bizim kodun sorunu değil) |

Bu oranlar gerçek hakem kararlarına kasıtlı olarak yakınlaştırıldı: sistem,
"Kaynakça" yerine "Referanslar" yazan bir raporu artık haksız yere
reddetmiyor (bkz. `docs/mvp-rules.json` → `esanlamli_basliklar`).

**Backend entegrasyonu:** Ayrı ilerleyen repoyu incelerken, backend + hakem
panelinin benim modülümden **farklı bir JSON formatı** (0-100 puan +
özet/bulgu) beklediği ortaya çıktı — birbirimizden habersiz farklı
sözleşmeler üzerine çalışmışız. `analyze_document_for_ui()` adlı bir
adaptör yazıp `backend/app/services/ai.py`'ye bağladım, backend'in kendi
test suite'i (7/7) ve gerçek KTR PDF'leriyle uçtan uca (upload→analiz→get)
doğrulandı. Detay: `docs/api-contract.md` Bölüm 1.

## Hayrettin — `ai-scoring` tamamlandı (2026-08-24)

MVP'nin 3, 4 ve 5. maddeleri artık gerçek kod. `backend/app/services/ai.py`
içindeki üç mock fonksiyon (`evaluate_criteria`, `analyze_category_fit`,
`check_similarity`) kaldırıldı — o dosyada artık hiç mock yok, `random`
bağımlılığı da gitti (mock'lar rastgele puan üretiyordu, yani aynı rapor her
analizde farklı puan alıyordu).

Modülün tasarım gerekçeleri, ölçüm sonuçları ve bilinen sınırlamaları:
[`ai-scoring/README.md`](ai-scoring/README.md). En kritik iki karar:

- **Benzerlik puanı TF-IDF kosinüs benzerliğinden DEĞİL birebir kelime
  örtüşmesinden hesaplanıyor.** Ölçtük: birbirinden bağımsız 34 gerçek
  raporun kosinüs benzerliği %11.9–45.2 (hepsi aynı şablonu kullandığı için).
  Kosinüs intihal puanı olarak kullanılsaydı **gerçek ve masum raporların bir
  kısmı intihalle suçlanacaktı.** Aynı raporların birebir örtüşmesi %0–7.9.
- **Ölçülemeyen kritere puan verilmiyor.** Örn. "Ethical & Data Privacy"
  metinden güvenilir ölçülemez; sistem uydurma puan üretmek yerine "hakem
  elle değerlendirmeli" diyor.

Tüm eşikler `docs/scoring-rules.json`'da ve tahmin değil — 34 gerçek rapor
ölçülerek belirlendi (`python ai-scoring/calibrate.py`).

## Mustafa — backend'de iki hata düzeltildi

**1. `GET /api/reports` analiz edilmiş rapor varken HTTP 500 veriyordu.**
`schemas.AiAnalysisResponse` `results` alanını zorunlu tutuyor ama bu bir
veri tabanı kolonu değil — yanıt öncesi düz kolonlardan üretilmesi gerekiyor.
Bu dönüşüm sadece `get_report`'ta yapılıyordu, `list_reports`'ta
yapılmıyordu. Sonuç: veri tabanında analiz edilmiş **ilk** rapor oluşur
olmaz liste endpoint'i düşüyordu — yani **hakem panosunun ana listesi
kullanılamaz durumdaydı.** Dönüşüm `_attach_analysis_results()` yardımcısına
çıkarıldı, iki endpoint de onu kullanıyor. Kalıcı regresyon testi eklendi
(`test_report_list_serializes_analysis`).

**2. Backend test paketi aslında geçmiyordu.** README "7/7 geçti" diyordu
ama gerçek sonuç **1 geçti / 6 hata**'ydı. Sebep `tests/conftest.py`: her
testin sonunda `test_temp.db` dosyası siliniyor, ama SQLAlchemy'nin bağlantı
havuzu o dosyaya ait açık bir tanıtıcı tutmaya devam ediyor → sonraki
testler "attempt to write a readonly database" ile patlıyordu. Testler
**tek tek** çalıştırıldığında geçtiği için hata uzun süre görünmez kaldı.
Bellekte `StaticPool` kullanımına geçildi; şimdi gerçekten 9/9 geçiyor.

Sıradaki (senin kararın): `models.AiAnalysis`'e kriter kırılımı için kolon
eklemek. `evaluate_criteria` kriter bazlı puanları ve yarışmacıya
gösterilecek `guclu_yonler`/`gelisim_onerileri` alanlarını döndürüyor ama
şemada yer olmadığı için kaydedilemiyorlar; şimdilik `rationale` metninin
içine gömülü geliyorlar. Tek taraflı şema değişikliği yapmadım.

## Mahmut — frontend backend'e bağlandı (2026-08-24)

Arayüz artık gerçek API'yi kullanıyor. Tüm mock veri uygulamadan kaldırıldı
(mock sabitleri yalnızca test fixture'ı olarak duruyor).

**Eklenen API katmanı** — `frontend/src/lib/api/`:

| Dosya | İş |
|---|---|
| `client.ts` | Tek `fetch` sarmalayıcı: token enjeksiyonu, `ApiError`/`NetworkError` ayrımı, 401'de oturum düşürme |
| `types.ts` | Backend'in tel formatı (snake_case). Bileşenler bu tipleri hiç görmez |
| `mappers.ts` | Tel → arayüz tipi çevirisi |
| `index.ts` | Uç nokta fonksiyonları + `pollUntilAnalyzed` |
| `errors.ts` | Hata → Türkçe cümle |

**Çözülen üç şekil uyuşmazlığı:** isimlendirme (snake_case ↔ camelCase),
yuvalama (backend `suggested_score/outcome/rationale`'ı **düz** verir, arayüz
`suggestion: {score, outcome, rationale}` bekler), ve kimlik (backend
`category_id` verir, arayüz kategori **adı** gösterir — `/api/categories`'ten
haritalanıyor).

**Bağlanan ekranlar:** giriş (gerçek JWT), hakem panosu + rapor detayı +
nihai karar, rapor yükleme (gerçek multipart), yarışmacı sonuç paneli,
değerlendirme yöneticisi istatistikleri.

**Dikkat edilmesi gereken üç nokta:**

- **Analiz asenkron.** `POST /api/reports/upload` hemen `status: "pending"`
  döner; analiz arka planda çalışır (gerçek PDF'te ~2 sn). `pollUntilAnalyzed`
  bunu hallediyor — yükleme sonrası tek istek atmak boş sonuç verir.
- **`generateStaticParams` kaldırıldı.** Rapor detay sayfası MOCK_REPORTS
  kimliklerinden statik üretiliyordu, yani gerçek bir `RPT-2026-XXXXXX`
  kimliğiyle açıldığında 404 veriyordu. Artık dinamik. JWT localStorage'da
  durduğu için veri çekme **istemcide** olmak zorunda — sunucu bileşeni
  token'a erişemez.
- **CORS.** Backend yalnızca `http://localhost:3000`'e izin veriyor
  (`backend/main.py`). Frontend'i başka bir porttan servis ederseniz orayı da
  güncelleyin. Doğrulandı: `Authorization` başlığı için preflight geçiyor,
  yabancı origin 400 alıyor.

**Dil konusu kapandı:** senin arayüzü Türkçe'ye çevirmenle (`c348853`)
tutarsızlık bitti, tüm AI çıktıları da Türkçe.

### Hâlâ açık olan (senin kararın)

- `criteria-template-form.tsx` (Yarışma Yöneticisi'nin kriter tanımlama
  formu) hâlâ hiçbir yere kaydetmiyor — backend'de o şekle karşılık gelen bir
  uç nokta yok (`POST /api/criteria` farklı bir şema bekliyor: tek kriter,
  `category_id`+`title`+`max_score`). Bu MVP maddesi değil, o yüzden
  dokunmadım.
- Yarışmacının **kendi** raporunu yükleyebileceği bir ekran yok; yükleme
  yalnızca Yarışma Yöneticisi panelinde. Backend her iki role de izin
  veriyor (`RoleChecker(["COMPETITION_MANAGER", "COMPETITOR"])`).

## TEKNOFEST'in gerçek yapısına uyum (2026-08-26)

Elimizdeki örnek veri paketinin içindeki **resmî TEKNOFEST belgeleri**
okundu (`ai-doc-analysis/sample_reports/havacilikta_yz_ktr/`) ve sistem
onlara göre düzeltildi. Aşağıdaki her madde varsayım değil, şartnameden
veya resmî şablon dosyasından alıntıyla doğrulanmış.

### "Kategori" TEKNOFEST'te ne demek?

**Katılımcı seviyesi** demek — teknoloji alanı değil.

- `sartname_genel_2026.pdf`: *"Mezun **kategorisi** lise mezunu ve üniversite
  mezunlarını kapsamaktadır."*
- Aynı belge: *"Yarışmacılar aynı proje ile yalnızca tek bir **kategoriye**
  veya tek bir **yarışmaya** başvurabilir"* — kategori ve yarışma ayrı şeyler.
- `sartname_teknik_2026.pdf`: "kategori" kelimesi **sıfır kez** geçiyor.

Teknoloji alanını **yarışmanın kendisi** belirliyor ("Havacılıkta Yapay Zeka
Yarışması"). Bizdeki 6 İngilizce kategori (`Robotics & Automation`,
`FinTech`, `Game Design`…) TEKNOFEST'le ilgisiz.

Bulunan somut hata: yönetici kategoriyi **iki kez** seçiyordu ve ikincisi
(şablon formundaki) hiçbir yere kaydedilmiyordu — zorunlu bir alan
dolduruluyor, veri çöpe gidiyordu. Kaldırıldı.

### Bir yarışmanın kaç şablonu var?

**En az iki.** `sartname_teknik_2026.pdf` madde 5: *"Yarışmacı takımlardan
**iki ayrı doküman** yazmaları beklenmektedir… Ön Tasarım Raporu yarışma
katılımı ve Final Tasarım Raporu puanlandırma sürecinde kullanılacağı için
iki raporun da teslim edilmesi şarttır."* Şablonları farklı tarihlerde
yayımlanıyor ve **puan ağırlıkları farklı** — `Puan_Rubrigi.md` bunu
belgeliyor (2022 KTR: 5/15/25/25/25/5 · 2026 ÖTR: 5/10/30/10/10/30/5/5).

Bu yüzden "Şablon adı" alanı silinmedi, gerçek karşılığına bağlandı:
**rapor türü**. Sabit liste değil serbest metin — TEKNOFEST terminolojiyi
yıldan yıla değiştiriyor (2022'de "Kritik Tasarım Raporu", 2026'da aynı
aşama "Final Tasarım Raporu").

### Başvuruyu kim yapıyor?

**Takım.** *"Takım Kaptanı: Takımın organizasyonundan sorumlu olan… kişi"*,
*"Takım Danışmanı: Her takım için en fazla bir (1) öğretmen/eğitmen/
akademisyen"*. Kayıtlar TEKNOFEST'in kendi sisteminde: *"KYS: TEKNOFEST
Kurumsal Yönetim Sistemi"* ve raporlar `t3kys.com`'a teslim ediliyor.

Bizde rapor yalnızca **yükleyen kişiye** bağlıydı. İki sonucu vardı:
takım arkadaşı kendi takımının sonucunu göremiyordu; ve şartname AKIŞ 01
yöneticinin *"raporları sisteme aktardığını"* söylediği hâlde, yönetici
aktarınca raporun sonucunu **hiçbir yarışmacı göremiyordu** — yani
şartnamenin kendi akışı, şartnamenin AKIŞ 03'ünü imkânsız kılıyordu.

Artık sahiplik takımda. **Takım yönetimi bu sistemin işi değil** — takım
ekleme/düzenleme uç noktası yok ve olmayacak; kayıtlar dışarıdan besleniyor
(`Team.external_ref` gerçek entegrasyonda eşleştirme anahtarı).

### Resmî şablondan otomatik doldurma

TEKNOFEST'in resmî şablon dosyaları başlıkları **ve puan ağırlıklarını**
Word başlık stillerinde zaten taşıyor. Yönetici dosyayı yüklüyor, form
kendiliğinden doluyor:

| Dosya | Sonuç |
|---|---|
| `sablon_OTR_2026.docx` | 8 başlık, ağırlık toplamı **tam 100** |
| `referans_2026_pdr_sablonu_universite.docx` | 5 başlık, toplam **100** |

Üç tuzak gerçek dosyayla ölçülüp çözüldü: alt başlıklar ana başlıklarla aynı
stili kullandığı için naif toplam **130** veriyor; Türkçe noktalı İ yüzünden
`"ŞEKİL LİSTESİ".casefold()` düz metinle eşleşmiyor; Word'ün içindekiler
alanı sayfa numarasını başlığa yapıştırıyor.

Çıkarım **hiçbir şeyi kaydetmiyor** — öneri dönüyor, son söz yöneticide.

### Takımın kendi raporu artık intihal sayılmıyor

Ölçülen davranış: bir takım ÖTR'sini gönderip ardından FTR'sini
gönderdiğinde ikinci rapor kendi öncekine karşı **100 benzerlik** alıp
"yüksek oranda birebir örtüşme" olarak işaretleniyordu. Yani sistem,
şartnamenin **zorunlu tuttuğu** davranışı intihal sayıyordu. Şartnamenin
kendi ifadesi doğru ölçüm yerini söylüyor: *"**başvurular arasında** yüksek
benzerlik gösteren içerikler"* — bir takımın iki raporu iki ayrı başvuru
değil, aynı başvurunun iki aşaması. Dışlama sessiz değil, bulgularda yazıyor.

### Hakem araması

Hakem artık kendisine atanmamış başvuruları da bulabiliyor
(`GET /api/reports/lookup`) — ama yalnızca **künye** düzeyinde: puan,
gerekçe, benzerlik bulgusu ve PDF dönmüyor. Arama tam eşleşme (parça arama
yok), atanmamış erişimler denetim izine yazılıyor ve yarışmacı bu ucu hiç
kullanamıyor.

Bu bilinçli bir gevşetme: aynı sistemde tam tersi bir açık kapatılmıştı
(atanmamış hakem başka bir yarışmacının tam AI analizini okuyabiliyordu).
Gevşetmeyi savunulabilir kılan şey, kapsamın künyeyle sınırlı olması ve
iz bırakması.

---

## Kim ne yapar — akış sahipliği (2026-08-26)

Şartnamedeki üç akış kimin ne yapacağını belirliyor ve sistem artık buna
birebir uyuyor.

| Rol | Yapar | **Yapmaz** |
|---|---|---|
| Yarışma Yöneticisi | Değerlendirmeyi tanımlar, şablon+kriter ekler, **raporları sisteme aktarır**, hakem dağıtır, **hesap açar** | — |
| Hakem | Kendine atananları değerlendirir, atanmamışları künye düzeyinde **arar** | Atanmamış raporun analizini/PDF'ini göremez |
| Yarışmacı | Takımının **sonucunu görüntüler** | **Rapor yüklemez**, arama yapamaz, kendi kendine kayıt olamaz |

**Yarışmacı neden rapor yüklemiyor:** AKIŞ 03'te yükleme adımı yok —
*"Değerlendirme tamamlanır → sonucunu görüntüler → güçlü ve gelişime açık
yönlerini inceler → önerileri görür."* Yükleme AKIŞ 01'de, yöneticide.
Gerçek hayatta da raporlar TEKNOFEST'in kendi sistemine (KYS / `t3kys.com`)
teslim ediliyor; bu sistem onları **değerlendiren** katman, toplama noktası
değil.

**Yarışmacı sonucunu nasıl görüyor:** takım üyeliğinden. Yönetici raporu
`team_id` ile aktarıyor, o takımın **her üyesi** raporu görüyor — yüklediği
için değil, takımda olduğu için.

**Hesaplar neden yöneticiden açılıyor:** raporun sonucunu takım üyeliği
belirliyor ve üyelik e-postaya bağlı. Kendi kendine kayıt açık olsaydı, bir
takım üyesinin e-postasını ilk kaydettiren kişi o takımın sonuçlarını
görürdü. E-posta doğrulaması bunu **çözmez** — doğrulama "bu kişi bu kutuya
erişebiliyor" der; asıl soru "bu e-posta bu takıma mı ait" ve onun cevabını
yalnızca yönetici bilir. `POST /api/auth/users` ile hesap açılıyor, şifreyi
`secrets` üretiyor, aynı istekte takıma ekleniyor. Kendi kendine kayıt
varsayılan olarak **kapalı** (`SELF_REGISTRATION=1` ile açılır) — yapılandırmayı
unutmak güvenliği artırsın diye.

## Bir yarışmanın birden fazla aşaması

TEKNOFEST'te bir yarışmanın en az iki raporu var (Ön Tasarım + Final Tasarım)
ve **puan ağırlıkları farklı**. Bunun için ayrı bir "şablon tablosu"
gerekmiyor: her aşama kendi değerlendirmesi olarak açılıyor.

```
"Havacılıkta YZ — Ön Tasarım Raporu"   · Üniversite ve Üzeri
"Havacılıkta YZ — Final Tasarım Raporu" · Üniversite ve Üzeri
"Havacılıkta YZ — Ön Tasarım Raporu"   · Lise
```

Her birinin kendi şablonu, kendi kriter ağırlıkları ve kendi hakem kadrosu
var. Ölçüldü: bir takımın FTR'si kendi ÖTR'sine karşı **0 benzerlik** alıyor —
aynı-takım dışlaması takım kimliğine baktığı için aşamalar arasında da
çalışıyor.

---

## Güvenlik ve bütünlük denetimi (2026-08-25)

Sistemin tamamı düşmanca bir gözle tarandı; **26 aday bulgunun tamamı canlı
sunucuya karşı tek tek doğrulandı** (varsayımla değil, gerçek HTTP
istekleriyle). Doğrulananlar düzeltildi ve her biri için düzeltme
kapatılınca **düşen** bir regresyon testi yazıldı.

En ağır beşi ve ölçülen davranışları:

| # | Ne oluyordu | Ölçülen |
|---|---|---|
| 1 | Sistemdeki **herhangi bir hakem**, kendisine atanmamış bir raporu onaylayabiliyordu | `POST /decision` → 200 |
| 2 | Atanmamış hakem, başka bir yarışmacının **tam AI analizini** okuyabiliyordu (dosyayı açamadığı hâlde) | `GET /reports/{id}` → 200 |
| 3 | Rol **seçmemiş** çok rollü token, tüm yarışmacıların raporlarını listeliyordu | filtre sessizce devre dışı |
| 4 | Yarışma kriterleri puanı **hiç etkilemiyordu**; puan sabit TEKNOFEST rubriğinden geliyordu | yönetici "Emniyet %90" dedi, puan Takım Şeması %5 + Algoritmalar %25 … üzerinden çıktı |
| 5 | Aynı hesap kendi raporunu yükleyip **kendine atanıp kendine 100** verebiliyordu | üç adım da 200 |

Bunların hepsi tek bir kök nedenden geliyordu: kod *"bu kullanıcı hakem
mi?"* diye soruyor, *"bu rapor **bu** hakemin mi?"* diye sormuyordu. Rapora
dokunan her uç nokta artık tek bir yetki kapısından (`_rapora_erisebilir_mi`
+ `_erisim_filtresi`) geçiyor ve eksik rol *"filtre yok"* değil *"erişim
yok"* anlamına geliyor.

Ayrıca kapatılanlar: intihal kontrolü çalışmadığında "bu sistemdeki ilk
başvuru" demesi, analizi çökmüş raporun sonsuza kadar "Analiz devam ediyor"
göstermesi ve hiç karara bağlanamaması, kuralların analiz sonrası sessizce
değiştirilip aynı yarışmadaki iki yarışmacının farklı ölçütlerle
puanlanması, sonuçlar açıklandıktan sonra başvuruların yeniden açılabilmesi,
kararı verilmiş raporun atamasının silinebilmesi, negatif kriter ağırlıkları
ve kimlik doğrulaması istemeyen kriter/kategori uç noktaları.

**Jüri bunu sorarsa:** sistemin ana vaadi "AI karar vermez, hakem verir".
Bu vaadin karşılığı, kararın **doğru hakemde** olduğunun garanti
edilmesidir — denetimin çoğu tam olarak bunu sağlamakla ilgiliydi.

---

## Yayına alma ve Supabase

Sistem hiçbir şey ayarlanmadan çalışır (SQLite + yerel disk). Yayına almak
için Supabase Postgres + Storage'a geçilebilir — adım adım rehber ve
**güvenlik açısından atlanmaması gereken RLS adımı**:
[`docs/supabase-kurulum.md`](docs/supabase-kurulum.md).

Kısaca: Python backend **Vercel'de çalışmaz** (pdfplumber + scikit-learn
~200 MB, serverless sınırının üstünde). Backend Render/Railway'e,
frontend Vercel'e.

## Kurulum ve test (herkes için)

Ayrıntılı kurulum için **[KURULUM.md](KURULUM.md)**. Kısa hâli:

```bash
# ai-doc-analysis (Hasan)          -> 46 test
.venv/bin/python ai-doc-analysis/tests/test_analyzer.py

# ai-scoring (Hayrettin)           -> 102 test
.venv/bin/python ai-scoring/tests/test_scorer.py

# backend (Mustafa)                -> 93 test
cd backend && ../.venv/bin/python -m pytest tests/ -q; cd ..

# frontend (Mahmut)                -> 123 test
cd frontend && npm install && npm test; cd ..

# uctan uca, CALISAN sunucuya karsi -> 48 kontrol
scripts/dev-backend.sh start
.venv/bin/python scripts/e2e-test.py
scripts/dev-backend.sh stop
```

`ai-doc-analysis` ve `ai-scoring` testleri pytest ile **değil** doğrudan
çalıştırılıyor — kendi `check()` fonksiyonlarını kullanan betikler ve sonda
`sys.exit()` çağırıyorlar; pytest ile toplanmaya çalışılırsa
`INTERNALERROR: SystemExit` verirler.

**Sistemi çalıştırmak (iki terminal gerekiyor):**

```bash
# 1. terminal — backend
cd backend
cp .env.local.example .env 2>/dev/null || true
python -c "import secrets; print(secrets.token_hex(32))"   # cikan degeri .env'e JWT_SECRET_KEY olarak yaz
python -m uvicorn main:app --reload --port 8000

# 2. terminal — frontend
cd frontend
cp .env.local.example .env.local          # NEXT_PUBLIC_API_URL=http://localhost:8000
npm run dev                                # http://localhost:3000
```

Frontend **3000** portunda çalışmalı: backend CORS'ta yalnızca
`http://localhost:3000` adresine izin veriyor.

**Backend'i gerçekten çalıştırmak için** `JWT_SECRET_KEY` ayarlanmalı, yoksa
public repoda duran güvensiz bir varsayılana düşer ve uyarı basar:

```bash
cd backend
cp .env.example .env   # ve içine bir değer yaz:
python -c "import secrets; print(secrets.token_hex(32))"
python -m uvicorn main:app --reload
```

Seed kullanıcıları (ilk açılışta oluşur, şifreleri `password123`):

| Hesap | Rol | Takım |
|---|---|---|
| `manager@teknofest.org` | Yarışma Yöneticisi | — |
| `referee@teknofest.org` · `referee2@teknofest.org` | Hakem | — |
| `evaluator@teknofest.org` | Değerlendirme Yöneticisi | — |
| `competitor@teknofest.org` | Yarışmacı | **Glieser (kaptan)** + **ADYU AI TEAM** |
| `competitor2@teknofest.org` | Yarışmacı | Glieser (üye) |
| `rakip@teknofest.org` | Yarışmacı | Zebot |

Bu hesaplar seed'den geliyor. Yeni hesaplar **yönetici panelinden** açılıyor
("Hesap Aç" bölümü) — kendi kendine kayıt kapalı.

Çok rollü test hesabı: `asdfghjkl@gmail.com` / `asdfghjkl` — dört rolün
hepsi, girişte rol seçim ekranı çıkar.

Takım kurgusu bilinçli, üç kuralı birden gösteriyor: `competitor2@`
kendi yüklemediği (yöneticinin aktardığı) Glieser raporunu **görebilir**;
`rakip@` aynı raporu **göremez**; `competitor@` iki takımda olduğu için
rapor yüklerken **hangi takım adına** yüklediğini seçmek zorundadır.

### Son test durumu (2026-08-26)

| Paket | Sonuç |
|---|---|
| `ai-doc-analysis` | 46 başarılı, 0 başarısız |
| `ai-scoring` | 102 başarılı, 0 başarısız |
| `backend` (pytest) | 93 başarılı, 0 başarısız |
| `frontend` (jest) | 123 başarılı, 0 başarısız |
| `scripts/e2e-test.py` (canlı sunucu) | 48 başarılı, 0 başarısız |
| `frontend` (next build) | başarılı |
| Uçtan uca — API akışı | 40 başarılı, 0 başarısız |
| Uçtan uca — arayüz istek şekilleri (canlı backend) | 32 başarılı, 0 başarısız |

Uçtan uca testte doğrulananlar: 4 rolün girişi, gerçek PDF yükleme, dört
analizin veri tabanına yazılması, hakemin AI önerisini ezip nihai karar
vermesi, rol bazlı yetkilendirme (yarışmacı karar veremiyor, kendi raporundan
başkasını göremiyor), ve saldırgan vakalar: birebir kopyalanmış rapor %100
örtüşmeyle "Yüksek risk", yanlış kategori beyanı 10 puanla "Kritik", bozuk
dosya sistemi çökertmiyor.

İkinci uçtan uca test, arayüzün **ürettiği istek şekillerini** canlı
backend'e karşı doğruluyor. Bu ayrı bir test çünkü jest testleri `fetch`'i
taklit ediyor — yani arayüz kodunun şeklini sınar, backend'in o şekli kabul
edip etmediğini değil. Doğrulananlar: form-encoded giriş (`username` alan
adıyla), multipart yükleme, JSON karar gövdesi, CORS preflight, ve
`GET /api/reports`'un analiz edilmiş rapor varken artık 500 vermemesi.
