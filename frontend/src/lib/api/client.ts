/**
 * Backend'e giden tüm isteklerin tek geçiş noktası.
 *
 * Bu dosyadan önce frontend'de HİÇBİR ağ çağrısı yoktu — tüm ekranlar yerel
 * mock verilerle çalışıyordu. Buradaki tek amaç: token yönetimi, hata
 * çevirisi ve taban URL'i tek yerde toplamak, böylece her bileşen kendi
 * `fetch` çağrısını kurmasın.
 */

/** Backend adresi. Geliştirmede uvicorn varsayılanı 8000. */
export const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_URL?.replace(/\/$/, "") ?? "http://localhost:8000";

/**
 * Backend'den dönen hata. `status` HTTP kodu, `detail` ise FastAPI'nin
 * `{"detail": "..."}` gövdesinden okunan insan-okur mesaj.
 */
export class ApiError extends Error {
  readonly status: number;
  readonly detail: string;

  constructor(status: number, detail: string) {
    super(detail);
    this.name = "ApiError";
    this.status = status;
    this.detail = detail;
  }

  /** Oturum düşmüş mü (token yok / süresi dolmuş). */
  get isUnauthorized(): boolean {
    return this.status === 401;
  }

  /** Bu rolün yetkisi yok. */
  get isForbidden(): boolean {
    return this.status === 403;
  }
}

/** Ağa hiç çıkılamadığında (backend kapalı, CORS, DNS) fırlatılır. */
export class NetworkError extends Error {
  constructor(cause: unknown) {
    super(
      `Backend'e ulaşılamadı (${API_BASE_URL}). Sunucunun çalıştığından emin olun.`,
    );
    this.name = "NetworkError";
    this.cause = cause;
  }
}

/**
 * Geçerli JWT'yi döndüren fonksiyon. Auth store tarafından kurulur.
 *
 * NEDEN BÖYLE: bu modülün auth store'u doğrudan import etmesi dairesel
 * bağımlılık yaratırdı (store -> api -> store). Bunun yerine store,
 * uygulama açılışında token okuyucusunu buraya enjekte ediyor.
 */
let tokenReader: () => string | null = () => null;

export function setTokenReader(reader: () => string | null): void {
  tokenReader = reader;
}

/** 401 alındığında çağrılır — oturumu düşürmek için store tarafından kurulur. */
let onUnauthorized: () => void = () => {};

export function setUnauthorizedHandler(handler: () => void): void {
  onUnauthorized = handler;
}

interface RequestOptions {
  method?: "GET" | "POST" | "PUT" | "DELETE";
  /** JSON gövde. `formBody` ile birlikte kullanılmaz. */
  json?: unknown;
  /** multipart/form-data ya da x-www-form-urlencoded gövde. */
  formBody?: FormData | URLSearchParams;
  /** Kimlik doğrulaması gerektirmeyen uç noktalar için (örn. login). */
  skipAuth?: boolean;
  /**
   * Store'daki token yerine bu token'ı kullan.
   *
   * Girişin hemen ardından gerekiyor: `login()` token'ı alır ama store'a
   * yazılmadan önce rolü öğrenmek için `/api/auth/me`'yi çağırmak zorunda.
   * O anda `tokenReader()` henüz null döner.
   */
  token?: string;
  signal?: AbortSignal;
}

export async function apiFetch<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const { method = "GET", json, formBody, skipAuth = false, token, signal } = options;

  const headers: Record<string, string> = {};
  if (!skipAuth) {
    const activeToken = token ?? tokenReader();
    if (activeToken) headers.Authorization = `Bearer ${activeToken}`;
  }

  let body: BodyInit | undefined;
  if (json !== undefined) {
    headers["Content-Type"] = "application/json";
    body = JSON.stringify(json);
  } else if (formBody instanceof URLSearchParams) {
    // OAuth2PasswordRequestForm bunu bekliyor. FormData ile gönderilirse
    // FastAPI de kabul eder ama urlencoded standart olan.
    headers["Content-Type"] = "application/x-www-form-urlencoded";
    body = formBody;
  } else if (formBody) {
    // FormData'da Content-Type'ı ELLE KURMUYORUZ: tarayıcının boundary
    // parametresini kendisi eklemesi gerekiyor, elle kurulursa istek bozulur.
    body = formBody;
  }

  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}${path}`, { method, headers, body, signal });
  } catch (cause) {
    // AbortError'ı yutmuyoruz - çağıran tarafın iptali fark etmesi gerekiyor.
    if (cause instanceof DOMException && cause.name === "AbortError") throw cause;
    throw new NetworkError(cause);
  }

  if (response.status === 401 && !skipAuth) {
    onUnauthorized();
  }

  if (!response.ok) {
    throw new ApiError(response.status, await readErrorDetail(response));
  }

  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

/**
 * FastAPI hatayı `{"detail": "..."}` olarak döndürür, ama doğrulama
 * hatalarında `detail` bir DİZİ olur. Ayrıca 500'lerde gövde hiç JSON
 * olmayabilir. Üçünü de tek okunabilir metne çeviriyoruz.
 */
async function readErrorDetail(response: Response): Promise<string> {
  try {
    const payload = await response.json();
    const detail = (payload as { detail?: unknown })?.detail;

    if (typeof detail === "string") return detail;
    if (Array.isArray(detail)) {
      const messages = detail
        .map((item) => (item as { msg?: string })?.msg)
        .filter((msg): msg is string => Boolean(msg));
      if (messages.length) return messages.join("; ");
    }
  } catch {
    // JSON değil - aşağıdaki genel mesaja düşüyoruz.
  }
  return `İstek başarısız oldu (HTTP ${response.status}).`;
}
