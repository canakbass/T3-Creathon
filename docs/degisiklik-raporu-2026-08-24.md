# Değişiklik Raporu — 24 Ağustos 2026

> `ai-scoring` modülünün (Hayrettin — MVP maddeleri 3, 4, 5) sıfırdan
> yazılması, backend'e entegre edilmesi, ve bu sırada bulunan hataların
> düzeltilmesi. Ekiple paylaşılabilir referans dokümanı.
>
> Önceki rapor: [`degisiklik-raporu-2026-08-23.md`](degisiklik-raporu-2026-08-23.md)

## 1. Özet

`backend/app/services/ai.py` içindeki üç mock fonksiyon gerçek kodla
değiştirildi; o dosyada artık hiç mock kalmadı. MVP'nin 6 maddesinden 5'i
uçtan uca çalışıyor ve test edildi. Kalan madde (6 — hakem arayüzü) backend
tarafında hazır, frontend tarafında bağlanmayı bekliyor.

Bu iş sırasında **üç hata** bulundu ve düzeltildi; ikisi sistemi
kullanılamaz kılan türden.

| Paket | Öncesi | Sonrası |
|---|---|---|
| `ai-doc-analysis` | 32 ✅ | 32 ✅ |
| `ai-scoring` | yok | **76 ✅** |
| `backend` | **1 ✅ / 6 ❌** (README "7/7" diyordu) | **9 ✅** |
| `frontend` (jest) | 74 ✅ | 74 ✅ |
| Uçtan uca (canlı sunucu) | yok | **40 ✅** |

## 2. Bulunan hatalar

### 2.1. `GET /api/reports` analiz edilmiş rapor varken HTTP 500 (kritik)

`schemas.AiAnalysisResponse` `results` alanını **zorunlu** tutuyor, ama bu
bir veri tabanı kolonu değil — `models.AiAnalysis`'te her kontrol dört ayrı
düz kolonda duruyor (`language_template_score`, `..._summary`,
`..._findings`). Yani `results` her yanıt öncesi elle üretilmek zorunda.

Bu dönüşüm yalnızca `get_report` içinde yapılıyordu. `list_reports`
(`GET /api/reports`) aynı şemayı kullanıyor ama dönüşümü yapmıyordu.
Sonuç: veri tabanında analiz edilmiş **ilk** rapor oluşur olmaz endpoint
`ResponseValidationError` ile düşüyordu. Hakem panosunun ana listesi tam da
bu endpoint'i kullanıyor — yani **sistem, ilk rapor analiz edildiği anda
kullanılamaz hale geliyordu.**

Mevcut testler yakalamamıştı çünkü analiz **sonrası** liste endpoint'ini hiç
çağırmıyorlardı. Uçtan uca gerçek sunucuyla denerken ortaya çıktı.

**Düzeltme:** dönüşüm `_attach_analysis_results()` yardımcısına çıkarıldı,
iki endpoint de onu kullanıyor. Bozuk JSON'a karşı da dayanıklı hale
getirildi (tek bozuk kayıt tüm endpoint'i düşürmesin). Kalıcı regresyon
testi: `test_report_list_serializes_analysis`. Test, düzeltme geri
alındığında gerçekten başarısız olduğu doğrulanarak eklendi.

### 2.2. Backend test paketi aslında geçmiyordu (kritik)

README "backend 7/7 geçti" diyordu. Gerçek sonuç: **1 geçti, 6 hata** —
`sqlite3.OperationalError: attempt to write a readonly database`.

Sebep `tests/conftest.py`: test veri tabanı diskte bir dosya
(`test_temp.db`) ve her testin sonunda `os.remove` ile siliniyor. Ama
SQLAlchemy'nin bağlantı havuzu o dosyaya ait **açık bir tanıtıcı** tutmaya
devam ediyor; dosya silindiğinde havuzdaki bağlantı artık var olmayan bir
inode'a bakıyor ve SQLite bunu "readonly database" olarak bildiriyor.

Hatanın uzun süre görünmez kalmasının sebebi: testler **tek tek**
çalıştırıldığında geçiyor, sadece birlikte koşulduğunda patlıyor.

**Düzeltme:** bellekte `StaticPool` kullanımına geçildi (`sqlite://`).
Silinecek dosya yok, dolayısıyla bayat tanıtıcı da yok. `StaticPool` şart:
her yeni bağlantı kendi boş `:memory:` veri tabanını açardı ve `TestClient`
istekleri başka bir iş parçacığında çalıştığı için tabloları bulamazdı.

### 2.3. Anahtar kelime eşleşmesi sessizce ölü doğuyordu (`ai-scoring` içi)

Kendi modülümde, kalibrasyon sırasında yakaladım. Config'deki anahtar
kelimeler ASCII yazılı (`ozgun`, `makine ogrenmesi`), rapor metni ise
diakritikli (`özgün`, `makine öğrenmesi`). Hasan'ın `_turkish_casefold`
fonksiyonu sadece I/i sorununu çözüyor, diakritikleri **koruyor** — başlık
aramada bu doğru davranış, ama anahtar kelime eşleşmesinde iki taraf
uyuşmuyordu.

Sonuç: `ozgunluk_dili` sinyali 34 raporun **hiçbirinde** puan almıyordu ve
kategori eşleşme oranı gerçeğin çok altında ölçülüyordu (medyan 0.482
yerine 0.286). **Hata patlamıyor**, sadece sinyal ölü doğuyor — bu yüzden
sadece ölçüm yakaladı. Eşikleri o bozuk ölçüme göre ayarlamak sistemi
kalıcı olarak yanlış kalibre edecekti.

**Düzeltme:** `text_utils.normalize_for_matching()` (küçük harf + diakritik
katlama) eklendi ve eşleşme yapan her yerde kullanıldı. Kalıcı regresyon
testi bırakıldı. Hasan'ın `turkish_casefold`'una **dokunulmadı** — başlık
aramada diakritiği korumak doğru davranış, ve bunu doğrulayan bir test de
eklendi.

## 3. `ai-scoring` — tasarım kararları

Ayrıntı ve tüm ölçüm sonuçları: [`ai-scoring/README.md`](../ai-scoring/README.md).
Sözleşme: [`api-contract.md`](api-contract.md) Bölüm 2.

### 3.1. Benzerlik puanı TF-IDF'ten değil birebir örtüşmeden geliyor

En kritik karar. İlk akla gelen yol, TF-IDF kosinüs benzerliğini "intihal
oranı" olarak vermekti. Birbirinden **bağımsız** 34 gerçek rapor ölçüldü:

| Ölçüm | Aralık | Medyan |
|---|---|---|
| TF-IDF kosinüs | %11.9 – **%45.2** | %20.1 |
| 8 kelimelik birebir örtüşme | %0.0 – **%7.9** | %0.6 |

Kosinüs yüksek çünkü hepsi aynı şablonu ve aynı alan terminolojisini
kullanıyor — "aynı konuda yazılmış" demek, "kopyalanmış" demek değil.
Frontend'in intihal bandı `>35` "Yüksek risk" olduğu için kosinüs
kullanılsaydı **gerçek ve masum raporların bir kısmı intihalle
suçlanacaktı.** Bir hakem karar destek sisteminde bu, sistemi kullanılamaz
kılan türde bir hata.

Konusal benzerlik yine hesaplanıyor ama hakeme yalnızca **bağlam** olarak
gösteriliyor, puanı belirlemiyor.

### 3.2. Bütün eşikler ölçüm, tahmin değil

`python ai-scoring/calibrate.py` 34 gerçek finalist raporunu ölçüyor;
`docs/scoring-rules.json` içindeki her eşiğin kaynağı `_kaynak` notlarında
yazılı. Yazma sırasında üç eşiği tahminle koymuş, sonra ölçümle
düzeltmek zorunda kaldım — ikisi gerçek raporların çoğunu haksız yere
cezalandırıyordu:

| Eşik | Tahmin | Ölçüm sonrası | Etkisi |
|---|---|---|---|
| Kategori tam-uyum oranı | 0.40 | **0.25** | 0.40 ile 34 gerçek raporun tamamı şüpheli işaretleniyordu |
| Özgünlük ifadesi sayısı | 3 | **2** | Ölçülen medyan 1; eşik 3 gerçek finalistlerin çoğunu cezalandırıyordu |
| Teknik terim sayısı | 12 | **10** | Ölçülen p25=10; 12 raporların yarısını gereksiz cezalandırıyordu |

Ayrıca "Oyun Tasarımı" anahtar kelime listesinde kirlilik bulundu: `görev`,
`karakter`, `sahne`, `seviye` gibi genel Türkçe kelimeler havacılık
raporlarında da bolca geçtiği için bu kategori 34 alakasız raporda medyan
0.158 ile yanlışlıkla 2. sıraya çıkıyor ve "rakip kategori cezası" hesabını
bozuyordu. Temizlik sonrası medyan 0.050'ye düştü.

### 3.3. İki motor: Claude API + deterministik yedek

`ANTHROPIC_API_KEY` varsa Claude API, yoksa kural motoru. Neden: Demo
Day'de internet kesilse, kredi bitse veya API hata verse **sistem çalışmaya
devam etmeli** — tek motorlu tasarımda MVP madde 5 jüri önünde çökebilir.
Hangi motorun kullanıldığı hakeme gösterilen gerekçede yazılı.

**Her iki motorda da toplam puanı kod hesaplıyor.** LLM sadece bölüm
kalitesine 0–100 puan verir; ağırlıklı toplama her zaman kodda yapılır.
Sebep: dil modelleri aritmetikte tutarsız olabilir, ve hakem *"bu 78 nereden
geldi"* diye sorduğunda cevabın kodda ve config'de olması gerekir.

Şu an ortamda API anahtarı yok, dolayısıyla ölçümlerin ve testlerin tamamı
**kural motoruyla** yapıldı. LLM yolu yazıldı ama gerçek bir API çağrısıyla
sınanmadı — anahtar geldiğinde bu doğrulanmalı.

### 3.4. Ölçülemeyen kritere puan verilmiyor

Yarışma Yöneticisi'nin tanımladığı kriterler ölçülebilir rubrik kalemlerine
`docs/scoring-rules.json` → `kriter_eslesmeleri` ile bağlanıyor. Eşlenmeyen
kriter için sistem **sayı üretmiyor**, "hakem elle değerlendirmeli" diyor.
Uydurma puan, puan vermemekten daha kötüdür — hakem hangi kriterin gerçekten
ölçüldüğünü bilmek zorunda.

Örnek: "Ethical & Data Privacy Considerations" metinden güvenilir ölçülemez
(bir raporun "KVKK" yazması, veri gizliliğini ele aldığını kanıtlamaz).
"Language & Template Compliance" ise bilerek eşlenmedi — Hasan'ın modülü
zaten onu ölçüyor, burada ikinci kez puanlanması çift sayım olurdu.

## 4. Backend'de yapılan diğer değişiklikler

- **`declared_category_id` eklendi.** `run_full_analysis` artık beyan edilen
  kategoriyi de alıyor, `reports.py` bunu `report.category_id`'den geçiriyor.
  Bu olmadan kategori kontrolü yalnızca "en uygun kategori hangisi"
  diyebiliyordu; asıl sorulması gereken soru "rapor **beyan edilen**
  kategoriye ait mi". Parametre opsiyonel, eski çağrı şekli çalışmaya devam
  ediyor.
- **Kategori `description`'ı da geçiliyor.** Config'de anahtar kelimesi
  olmayan (Yarışma Yöneticisi'nin sonradan eklediği) bir kategori için
  `ai-scoring` karakter n-gram yedeğine düşüyor; açıklama olmadan o yöntemin
  elinde neredeyse hiç sinyal kalmıyordu.
- **Kurallar bir kez okunuyor.** `run_full_analysis` iki config dosyasını bir
  kez okuyup alt modüllere paylaştırıyor; aksi halde her kontrol aynı iki
  dosyayı diskten yeniden okuyordu.
- **PDF metin önbelleği.** Benzerlik analizi her yeni rapor için daha önce
  yüklenmiş **tüm** raporları okumak zorunda; önbellek olmadan N raporluk bir
  veri tabanında her yükleme N adet PDF ayrıştırması demek. 34 raporda tek
  bir benzerlik çağrısı ~10 saniye sürüyordu. Önbellek anahtarı (yol,
  değiştirilme zamanı, boyut) — dosya değişirse kendiliğinden geçersiz olur.

## 5. Ortak koda dokunulan tek yer

`ai-doc-analysis/analyzer.py`'ye `find_sections()` fonksiyonu eklendi ve
mevcut `check_content` onu kullanacak şekilde sadeleştirildi. Bölümleme
mantığı iki yerde yaşamasın diye (`check_content` bölüm uzunluğu için,
`ai-scoring` kriter puanlaması için aynı bölümlere ihtiyaç duyuyor).
Hasan'ın 32 testi bu değişiklikten sonra da geçiyor — davranış birebir aynı,
sadece ortak parça ayrı fonksiyona alındı.

## 6. Sıradaki işler

**Öncelik 1 — Mahmut: frontend'i backend'e bağla.** MVP madde 6'nın
kapanması buna bağlı. Arayüz şu an hiçbir HTTP isteği atmıyor, tüm veri
yerel mock. Dikkat edilecek iki şey `README.md`'de yazılı (alan adı/şekil
uyuşmazlığı ve analizin asenkron olması — arayüzün `status != "pending"`
olana kadar yoklaması lazım).

**Öncelik 2 — Mustafa:** `models.AiAnalysis`'e kriter kırılımı için kolon.
Şimdilik `rationale` metnine gömülü geliyor. Ayrıca `seed_db()` kategori
adları İngilizce, frontend Türkçe kullanıyor — seed verisinin
Türkçeleştirilmesi senin kararın.

**Öncelik 3 — Hayrettin (ben):** API anahtarı gelince LLM motorunu gerçek
çağrıyla doğrulamak. Ayrıca benzerlik şu an yalnızca sistemdeki diğer
raporlara bakıyor; kamuya açık kaynaklara karşı intihal kontrolü yok (hakem
paneli metinleri bu yüzden "önceki başvurularla" diyor, "internetle"
demiyor) — Demo Day'de jüri sorarsa bu sınırın bilinçli ve açıkça
belirtilmiş olduğu söylenebilir.
