import { ApiError, NetworkError } from "./client";
import { describeError } from "./errors";

/**
 * Hata mesajları kullanıcıyı bir EYLEME yönlendiriyor. Yanlış mesaj,
 * kullanıcıyı yanlış eyleme yönlendirir — bu yüzden hangi durumda ne
 * yazdığı bir sözleşme.
 *
 * KULLANICININ BİLDİRDİĞİ HATA: yanlış şifre girince "Oturumunuzun süresi
 * doldu. Lütfen tekrar giriş yapın." yazıyordu. Ortada dolacak bir oturum
 * yok; kullanıcı şifresini düzeltmek yerine tekrar giriş yapmayı deniyordu.
 */
describe("describeError", () => {
  it("401'de SUNUCUNUN cümlesini gösteriyor", () => {
    // Aynı 401 üç farklı şey söyleyebiliyor ve üçü de farklı eylem
    // gerektiriyor.
    expect(describeError(new ApiError(401, "E-posta veya sifre hatali"))).toBe(
      "E-posta veya sifre hatali",
    );
    expect(
      describeError(new ApiError(401, "Oturum dogrulanamadi. Lutfen tekrar giris yapin.")),
    ).toBe("Oturum dogrulanamadi. Lutfen tekrar giris yapin.");
    expect(
      describeError(new ApiError(401, "Oturumunuz sonlandirildi. Lutfen tekrar giris yapin.")),
    ).toBe("Oturumunuz sonlandirildi. Lutfen tekrar giris yapin.");
  });

  it("401 gövdesizse genel cümleye düşüyor", () => {
    // Araya giren bir vekil sunucu gövdesiz 401 dönebilir; o durumda
    // söyleyebileceğimiz en doğru şey oturumun düştüğü.
    expect(describeError(new ApiError(401, ""))).toMatch(/süresi doldu/i);
  });

  it("403'te de sunucunun cümlesi — eylem içeriyor", () => {
    expect(
      describeError(
        new ApiError(403, "COMPETITION_MANAGER rolunu yalnizca kurum sorumlusu verebilir."),
      ),
    ).toMatch(/kurum sorumlusu/);
    expect(describeError(new ApiError(403, ""))).toMatch(/yetkiniz yok/i);
  });

  it("404'te de sunucunun cümlesi", () => {
    expect(describeError(new ApiError(404, "Takim bulunamadi."))).toBe("Takim bulunamadi.");
    expect(describeError(new ApiError(404, ""))).toMatch(/bulunamadı/i);
  });

  it("ağ hatasında backend adresini söylüyor", () => {
    // "Failed to fetch" hakem için anlamsız; nereye ulaşılamadığı önemli.
    expect(describeError(new NetworkError(new Error("x")))).toMatch(/ulaşılamadı/i);
  });

  it("iptal bir HATA değil", () => {
    const iptal = new DOMException("aborted", "AbortError");
    expect(describeError(iptal)).toMatch(/iptal edildi/i);
  });

  it("tanınmayan bir şey gelirse ham mesajı SIZDIRMIYOR", () => {
    // Ağ yığınından gelen İngilizce mesajlar kullanıcıya bir şey anlatmıyor.
    expect(describeError(new Error("TypeError: undefined is not a function"))).toBe(
      "Beklenmeyen bir hata oluştu.",
    );
  });
});
