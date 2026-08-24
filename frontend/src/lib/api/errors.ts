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
    if (cause.isUnauthorized) {
      return "Oturumunuzun süresi doldu. Lütfen tekrar giriş yapın.";
    }
    if (cause.isForbidden) {
      return "Bu işlem için yetkiniz yok.";
    }
    if (cause.status === 404) {
      return "Kayıt bulunamadı.";
    }
    return cause.detail;
  }

  if (cause instanceof DOMException && cause.name === "AbortError") {
    return "İşlem iptal edildi.";
  }

  return "Beklenmeyen bir hata oluştu.";
}
