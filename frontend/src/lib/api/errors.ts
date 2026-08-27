import { ApiError, NetworkError } from "./client";

/**
 * Herhangi bir hatayı kullanıcıya gösterilebilecek Türkçe bir cümleye çevirir.
 *
 * Her bileşenin aynı `instanceof` zincirini tekrar yazmasını önlemek için
 * tek yerde toplandı. Ham `Error.message` doğrudan gösterilmiyor: ağ
 * yığınından gelen İngilizce mesajlar ("Failed to fetch") hakem için
 * anlamsız.
 */
export function describeError(cause: unknown): string {
  if (cause instanceof NetworkError) return cause.message;

  if (cause instanceof ApiError) {
    // 401'DE DE SUNUCUNUN CÜMLESİ.
    //
    // Sabit "oturumunuzun süresi doldu" cümlesi ÜÇ FARKLI durumu tek bir
    // yanlış mesaja çeviriyordu:
    //   • yanlış şifre        → "E-posta veya şifre hatalı"  (oturum YOK ki dolsun)
    //   • bilinmeyen token    → "Oturum doğrulanamadı..."
    //   • şifre sıfırlanmış   → "Oturumunuz sonlandırıldı..."
    // Kullanıcı yanlış şifre girdiğinde "süresi doldu" görüyor ve şifresini
    // düzeltmek yerine tekrar giriş yapmayı deniyordu — hata mesajı onu
    // YANLIŞ eyleme yönlendiriyordu.
    if (cause.isUnauthorized) {
      return (
        cause.detail?.trim() || "Oturumunuzun süresi doldu. Lütfen tekrar giriş yapın."
      );
    }
    // 403 ve 404'te SUNUCUNUN cümlesi varsa onu gösteriyoruz.
    //
    // NEDEN: backend'in yetki mesajları eylem içeriyor — "Yarışma
    // Yöneticisi rolünü yalnızca kurum sorumlusu verebilir", "Bu hesabın
    // seçili kurumda bu rolü yok, tekrar giriş yapın". Genel bir "yetkiniz
    // yok" cümlesi bunları yutuyordu ve kullanıcı ne yapması gerektiğini
    // bilmeden kalıyordu. Genel cümleler yalnızca gövdesiz bir 403/404
    // (ör. araya giren bir vekil sunucu) için duruyor.
    if (cause.isForbidden) {
      return cause.detail?.trim() || "Bu işlem için yetkiniz yok.";
    }
    if (cause.status === 404) {
      return cause.detail?.trim() || "Kayıt bulunamadı.";
    }
    return cause.detail;
  }

  if (cause instanceof DOMException && cause.name === "AbortError") {
    return "İşlem iptal edildi.";
  }

  return "Beklenmeyen bir hata oluştu.";
}
