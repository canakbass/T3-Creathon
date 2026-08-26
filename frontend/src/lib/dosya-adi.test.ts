import { cozumle, epostalariAyikla, epostaGecerliMi } from "./dosya-adi";

/**
 * Bu testler backend'deki `tests/test_dosya_adi.py` ile AYNI vektörleri
 * kullanıyor. İki kopya ayrışırsa arayüz yöneticiye bir şey gösterir,
 * sunucu başka bir şey kaydeder — ve fark ancak birinin sonucunu göremediği
 * gün ortaya çıkar.
 */

const epostalari = (ad: string) => cozumle(ad).epostalar;
const proje = (ad: string) => cozumle(ad).projeAdi;

describe("dosya adından e-posta", () => {
  it("kullanıcının verdiği gerçek örnek: iki kişilik takım", () => {
    expect(
      epostalari("232805068@ogr.cbu.edu.tr_canakbasforspecial@gmail.com.pdf"),
    ).toEqual(["232805068@ogr.cbu.edu.tr", "canakbasforspecial@gmail.com"]);
  });

  it("tek e-posta — .tr ile .docx yan yana", () => {
    expect(epostalari("ogrenci2@cbu.edu.tr.docx")).toEqual(["ogrenci2@cbu.edu.tr"]);
  });

  it("e-posta yoksa proje adı kalıyor", () => {
    const s = cozumle("matematik_rapor.docx");
    expect(s.epostalar).toEqual([]);
    expect(s.projeAdi).toBe("matematik rapor");
  });

  it.each([
    ["a@b.com.pdf", ["a@b.com"]],
    ["a@b.com.pdf.pdf", ["a@b.com"]],
    ["a@b.com.PDF", ["a@b.com"]],
    // .zip ve .mov GERÇEK üst düzey alan adları; soyma listesi yükleme
    // beyaz listesiyle sınırlı olduğu için korunuyorlar.
    ["a@b.zip.pdf", ["a@b.zip"]],
    ["x@y.mov.pdf", ["x@y.mov"]],
  ])("uzantı alan adına yapışmıyor: %s", (ad, beklenen) => {
    expect(epostalari(ad)).toEqual(beklenen);
  });

  it("yerel kısımdaki alt çizgi korunuyor", () => {
    // Önce-böl-sonra-doğrula yaklaşımı tam burada patlardı.
    expect(epostalari("ali_veli@x.com.pdf")).toEqual(["ali_veli@x.com"]);
  });

  it("ayırıcı ve yerel alt çizgi aynı anda", () => {
    expect(epostalari("a@b.com_ali_veli@x.com.pdf")).toEqual([
      "a@b.com",
      "ali_veli@x.com",
    ]);
  });

  it("alan adında alt çizgi yok sayılıyor", () => {
    expect(epostalari("a@b.com_ali@x.com.pdf")).toEqual(["a@b.com", "ali@x.com"]);
  });

  it("belirsiz yerel kısım UYARI üretiyor", () => {
    const s = cozumle("YAPAY ZEKA_ali@ogr.cbu.edu.tr.docx");
    expect(s.epostalar).toEqual(["zeka_ali@ogr.cbu.edu.tr"]);
    expect(s.uyarilar.some((u) => u.includes("düzeltin"))).toBe(true);
  });

  it("Türkçe harf yerel kısma sızmıyor", () => {
    expect(epostalari("Ödevi_a@b.com.pdf")).toEqual(["a@b.com"]);
    expect(epostalari("İSTANBUL_ŞUBE_a@b.com.PDF")).toEqual(["a@b.com"]);
    expect(proje("İSTANBUL_ŞUBE_a@b.com.PDF")).toBe("İSTANBUL ŞUBE");
  });

  it.each(["rapor@2026.docx", "v1.2@final.pdf", "hasan@com.pdf"])(
    "e-posta gibi görünüp olmayan yakalanmıyor: %s",
    (ad) => {
      expect(epostalari(ad)).toEqual([]);
    },
  );

  it("büyük/küçük harf tekilleştiriliyor", () => {
    expect(epostalari("AYSE@GMAIL.COM_ayse@gmail.com.pdf")).toEqual(["ayse@gmail.com"]);
  });

  it.each([
    ["dosya (1).pdf", "dosya"],
    ["dosya kopyasi.pdf", "dosya"],
    ["Rapor - Kopya (2).pdf", "Rapor"],
  ])("kopya eki proje adını kirletmiyor: %s", (ad, beklenen) => {
    expect(proje(ad)).toBe(beklenen);
  });

  it("anlamlı harf yoksa proje adı UYDURULMUYOR", () => {
    expect(proje("1_2_3.pdf")).toBeNull();
    expect(proje("a@b.com.pdf")).toBeNull();
  });

  it("yol bileşenleri atılıyor", () => {
    expect(epostalari("../../etc/passwd@x.com.pdf")).toEqual(["passwd@x.com"]);
    expect(epostalari("C:\\Users\\x\\Rapor_a@b.com.pdf")).toEqual(["rapor_a@b.com"]);
  });

  it("çok fazla adres TÜMDEN reddediliyor", () => {
    // Kırpsaydık çıkarılmayan adresler proje adına düşer ve yönetici EKSİK
    // bir takımı onaylamış olurdu.
    const ad = Array.from({ length: 12 }, (_, i) => `u${i}@x.com`).join("_") + ".pdf";
    const s = cozumle(ad);
    expect(s.hata).toMatch(/elle girin/);
    expect(s.epostalar).toEqual([]);
  });

  it("çok uzun ad reddediliyor", () => {
    expect(cozumle("a".repeat(300) + "@b.com.pdf").hata).toMatch(/çok uzun/);
  });

  it("alan adında tire ve etiketli adres meşru", () => {
    expect(epostalari("a@b-c.com.tr.pdf")).toEqual(["a@b-c.com.tr"]);
    expect(epostalari("team+2026@x.com.pdf")).toEqual(["team+2026@x.com"]);
  });

  it("tire ile ayrılmış adresler uyarıyla okunuyor", () => {
    const s = cozumle("a@b.com-c@d.com.pdf");
    expect(s.epostalar).toEqual(["a@b.com", "c@d.com"]);
    expect(s.uyarilar.length).toBeGreaterThan(0);
  });
});

describe("serbest metinden e-posta", () => {
  it("virgül, noktalı virgül, boşluk ve satır sonu ayırıcı", () => {
    expect(epostalariAyikla("a@x.com, b@x.com; c@x.com\nd@x.com e@x.com")).toEqual([
      "a@x.com",
      "b@x.com",
      "c@x.com",
      "d@x.com",
      "e@x.com",
    ]);
  });

  it("tekrarlar eleniyor ve küçük harfe çevriliyor", () => {
    expect(epostalariAyikla("A@x.com, a@X.com")).toEqual(["a@x.com"]);
  });

  it("biçim kontrolü", () => {
    expect(epostaGecerliMi("a@b.com")).toBe(true);
    expect(epostaGecerliMi("bozukadres")).toBe(false);
    expect(epostaGecerliMi("a@b")).toBe(false);
  });
});
