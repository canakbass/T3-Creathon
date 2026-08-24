# Supabase Kurulumu ve Yayına Alma

> **Bu adımlar isteğe bağlıdır.** Hiçbirini yapmadan sistem tamamen çalışır:
> veri tabanı SQLite, dosyalar yerel diskte. Yerel geliştirme ve Demo Day
> sunumu için bu yeterlidir.
>
> Supabase'e geçmek **yayına almak** için gerekli: Render/Railway gibi
> ücretsiz barındırma katmanlarında dosya sistemi **geçicidir** — her
> yeniden dağıtımda yüklenen tüm raporlar silinir.

---

## ⚠️ Önce oku: RLS kapalı geliyor, kapatmak sizin işiniz

Bu, kurulumun **en kritik adımı**. Atlanırsa proje adresini ve public
anahtarı bilen herkes tüm tabloları okuyabilir/silebilir.

Supabase'in kendi dokümanı: *"Tables created through the Supabase Dashboard
have RLS enabled by default"* — ve panonun dışında, "başka bir araçla"
oluşturulan tablolar için RLS'i **elle açmanız** gerekiyor.

`backend/main.py` her açılışta `Base.metadata.create_all(bind=engine)`
çalıştırıyor. Bu "başka bir araç" sayılıyor: tablolar `public` şemasında,
**RLS kapalı** olarak oluşuyor. İçlerinde ne var? `users` (e-posta + bcrypt
parola özetleri), `reports`, `ai_analyses`, `final_decisions`.

Ayrıca RLS açmak tek başına yetmiyor — Supabase `public` şemasındaki
tablolara `anon` ve `authenticated` rolleri için `SELECT/INSERT/UPDATE/
DELETE` yetkisi de veriyor. Yetkileri de geri almak gerekiyor.

### Yapılacaklar (SQL Editor'de, tek seferde)

```sql
-- 1) Tüm public tablolarda RLS'i aç (hiç politika tanımlamadan =
--    anon/authenticated hiçbir satırı göremez)
do $$
declare r record;
begin
  for r in select schemaname, tablename from pg_tables where schemaname = 'public'
  loop
    execute format('alter table %I.%I enable row level security;', r.schemaname, r.tablename);
  end loop;
end $$;

-- 2) RLS yetkileri geri ALMAZ; onları da alıyoruz
revoke all on all tables in schema public from anon, authenticated;
revoke all on all sequences in schema public from anon, authenticated;
alter default privileges for role postgres in schema public
  revoke select, insert, update, delete on tables from anon, authenticated;

-- 3) Denetim: rls_enabled her satırda true olmalı
select c.relname, c.relrowsecurity as rls_enabled
from pg_class c join pg_namespace n on n.oid = c.relnamespace
where n.nspname = 'public' and c.relkind = 'r'
order by 2, 1;
```

Backend etkilenmez: **secret key** `BYPASSRLS` yetkisine sahip, bu yüzden
uygulama normal çalışmaya devam eder. Yetkisi kısıtlanan yalnızca tarayıcıdan
erişilebilen `anon` rolü.

### Daha da iyisi: Data API'yi tamamen kapatın

**Dashboard → Settings → API → Exposed schemas → `public`'i kaldırın.**

Bu uygulamanın tarayıcı tarafı Supabase ile **hiç konuşmuyor** — yalnızca
backend konuşuyor. Dolayısıyla Data API'ye hiç ihtiyaç yok. Kapatmak bu hata
sınıfını tümüyle imkânsız kılıyor.

Neden bu daha güvenli: `create_all()` **her açılışta** çalışıyor. İleride
yeni bir tablo eklerseniz o tablo yine RLS'siz oluşur ve 1. adımı tekrar
çalıştırmanız gerekir. Şemayı API'den kaldırmak kalıcı çözüm.

---

## 1. Veri tabanı bağlantısı

Supabase panosu → **Connect** → **Session pooler** adresini **olduğu gibi**
kopyalayın.

```
DATABASE_URL=postgresql+psycopg2://postgres.<PROJE_REF>:<ŞİFRE>@aws-0-<bölge>.pooler.supabase.com:5432/postgres
```

**Neden Session pooler (port 5432):**

| Seçenek | Neden olmaz |
|---|---|
| Direct connection | Ücretsiz katmanda **IPv6-only**. Render/Railway'den bağlanamayabilir. |
| Transaction pooler (:6543) | Oturum durumunu (`SET`, prepared statement) bozuyor, SQLAlchemy için `NullPool` şart oluyor. Uzun ömürlü bir sunucu için gereksiz. |
| **Session pooler (:5432)** | **IPv4, her katmanda çalışıyor, SQLAlchemy'de özel ayar gerekmiyor.** |

**Dikkat edilecekler:**

- Bölge/shard numarası (`aws-0-...`) **projeye göre değişir** — şablondan
  tahmin etmeyin, panodan kopyalayın.
- Şifredeki özel karakterleri yüzde-kodlayın (`@` → `%40`). Kodlanmamış bir
  `@` adresi bozar ve "could not translate host name" hatası verir.
- Bu şifre, API anahtarlarından **farklıdır**: Settings → Database.

Kod tarafında yapılacak bir şey yok — `backend/app/database.py`
`DATABASE_URL` varsa Postgres'e, yoksa SQLite'a bağlanıyor.

---

## 2. Dosya depolama

```
SUPABASE_URL=https://<PROJE_REF>.supabase.co
SUPABASE_SECRET_KEY=sb_secret_...
SUPABASE_BUCKET=reports
```

Bucket ilk açılışta otomatik oluşturuluyor (**private**, 50 MB dosya
sınırı).

> **`SUPABASE_SECRET_KEY` asla tarayıcıya gitmemeli.** RLS'i bypass eder ve
> projedeki her tabloya/bucket'a tam erişim verir. `NEXT_PUBLIC_` öneki ile
> kullanmayın, loglamayın, URL'e koymayın.

**Neden imzalı bağlantı değil de baytları backend üzerinden akıtıyoruz:**
raporlar gizli ve tek yetki kapısı uygulamanın kendi kontrolü
(`_rapora_erisebilir_mi`). İmzalı bağlantı o kapıyı atlatır — bağlantıyı ele
geçiren herkes dosyaya erişir. `signed_url()` kodda hazır ama bilinçli olarak
kullanılmıyor.

**Yarışmacının paylaştığı publishable key'e gerek yok.** Bu uygulamanın
tarayıcı tarafı Supabase'e hiç bağlanmıyor; `NEXT_PUBLIC_SUPABASE_*`
değişkenlerini hiç tanımlamayın — saldırı yüzeyini boşuna genişletir.

---

## 3. Yayına alma

**Python backend Vercel'de çalışmaz.** `pdfplumber` + `scikit-learn` ~200 MB
ve Vercel'in Python fonksiyon paketi sınırının üstünde; ayrıca AI analizi
serverless zaman aşımına takılır. Backend'i **Render veya Railway** gibi
kalıcı bir Python servisine koyun, frontend'i Vercel'de bırakın.

**Frontend (Vercel) ortam değişkeni — tek tane:**

```
NEXT_PUBLIC_API_URL=https://<backend-adresiniz>
```

Dikkat:
- **`https://` olmalı.** HTTPS bir sayfa, HTTP bir backend'e istek atamaz
  (karışık içerik engeli) ve bu tarayıcıda "backend kapalı" gibi görünür.
- `NEXT_PUBLIC_*` değişkenleri **derleme anında** gömülüyor — panoda
  değiştirmek yetmez, yeniden dağıtım gerekiyor.

**Backend ortam değişkeni:**

```
CORS_ORIGINS=https://<projeniz>.vercel.app,http://localhost:3000
```

Bu ayarlanmazsa backend yalnızca `http://localhost:3000`'e izin verir ve
yayındaki arayüz CORS hatası alır.

---

## 4. Kontrol listesi

- [ ] SQL Editor'de RLS + revoke bloğu çalıştırıldı, denetim sorgusu her
      satırda `rls_enabled = true` gösteriyor
- [ ] Settings → API → Exposed schemas'tan `public` kaldırıldı
- [ ] `DATABASE_URL` Session pooler adresi, şifre yüzde-kodlu
- [ ] `SUPABASE_SECRET_KEY` yalnızca backend ortamında, `NEXT_PUBLIC_` yok
- [ ] `CORS_ORIGINS` Vercel adresini içeriyor
- [ ] `NEXT_PUBLIC_API_URL` HTTPS
- [ ] Bir rapor yükleyip **benzerlik kontrolünün hâlâ çalıştığı** doğrulandı
      (aynı PDF'i iki kez yükleyin — ikincisi %100 örtüşme göstermeli)

Son madde önemli: AI hattı yerel dosya yolu istiyor. Depolama katmanı
Supabase nesnelerini geçici dosyaya indirmezse benzerlik kontrolü **hiçbir
hata vermeden** "benzer rapor yok" demeye başlar. `backend/tests/
test_storage.py` bunu test ediyor, ama gerçek ortamda da bir kez
doğrulayın.

---

## Sorun giderme

| Belirti | Sebep |
|---|---|
| `.env`'e `DATABASE_URL` yazdım ama hâlâ SQLite | `backend/app/database.py` `load_dotenv()`'i en üstte çağırıyor; başka bir dosyadan okuyorsanız import sırası sorun olabilir. `python -c "import os,dotenv;dotenv.load_dotenv();print(os.getenv('DATABASE_URL'))"` ile kontrol edin. |
| `could not translate host name` | Şifredeki özel karakter kodlanmamış (`@` → `%40`). |
| `server closed the connection unexpectedly` | Havuzdaki bağlantı bayatlamış. `pool_pre_ping` + `pool_recycle` zaten ayarlı; sürerse Session pooler kullandığınızdan emin olun. |
| PDF indirince bozuk açılıyor | `content-type` verilmemiş; storage3 varsayılanı `text/plain`. Kodda veriliyor — elle yükleme yaptıysanız sebebi bu. |
| Benzerlik hep "%0" | Depolama katmanı yerel yola indirmiyor. Kontrol listesinin son maddesine bakın. |
| Yayında CORS hatası | `CORS_ORIGINS` Vercel adresini içermiyor ya da backend HTTP. |
