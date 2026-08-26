import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { AccountCreator } from "./account-creator";

/**
 * Hesapları YÖNETİCİ açar, şifreyi SİSTEM üretir.
 *
 * Kendi kendine kayıt kapalı çünkü raporun sonucunu TAKIM ÜYELİĞİ belirliyor
 * ve üyelik e-postaya bağlı: kayıt açık olsaydı bir takım üyesinin
 * e-postasını ilk kaydettiren kişi o takımın sonuçlarını görürdü.
 *
 * E-posta doğrulaması bunu ÇÖZMEZ — doğrulama "bu kişi bu kutuya erişiyor"
 * der; bizim sorumuz "bu e-posta bu takıma mı ait". Yanlış adres girilirse
 * doğrulama yanlış kişiyi onaylar.
 */

function jsonResponse(status: number, payload: unknown) {
  return { ok: status >= 200 && status < 300, status, json: async () => payload };
}

function mockCreate(basarisizlar: string[] = []) {
  let sayac = 0;
  const fetchMock = jest.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    if (!url.includes("/api/auth/users")) throw new Error(`Beklenmeyen istek: ${url}`);
    const govde = JSON.parse(String(init?.body));
    if (basarisizlar.includes(govde.email)) {
      return jsonResponse(400, { detail: "Bu e-posta adresi zaten kayitli." });
    }
    sayac += 1;
    return jsonResponse(201, {
      id: `u${sayac}`,
      email: govde.email,
      full_name: null,
      roles: govde.roles,
      team_id: govde.team_id,
      temporary_password: `sifre-${sayac}`,
      notice: "Bu sifre YALNIZCA BURADA gorunuyor.",
    });
  });
  global.fetch = fetchMock as unknown as typeof fetch;
  return fetchMock;
}

describe("AccountCreator", () => {
  const originalFetch = global.fetch;
  afterEach(() => {
    global.fetch = originalFetch;
  });

  it("TOPLU hesap açar ve üretilen şifreleri gösterir", async () => {
    const fetchMock = mockCreate();
    const user = userEvent.setup();
    render(<AccountCreator />);

    await user.type(
      screen.getByTestId("account-emails"),
      "kaptan@takim.org\nuye@takim.org",
    );
    await user.type(screen.getByTestId("account-team"), "team-glieser");
    await user.click(screen.getByTestId("account-submit"));

    await waitFor(() =>
      expect(screen.getByTestId("account-results")).toHaveTextContent("2 hesap açıldı"),
    );
    expect(screen.getByTestId("account-row-kaptan@takim.org")).toHaveTextContent("sifre-1");
    expect(screen.getByTestId("account-row-uye@takim.org")).toHaveTextContent("sifre-2");
    expect(fetchMock).toHaveBeenCalledTimes(2);

    // Takim ayni istekte gonderilmeli: "hesap ac" ile "takima ekle" iki ayri
    // adim olsaydi, arada unutulan bir uye sonucunu HIC goremezdi.
    expect(JSON.parse(String(fetchMock.mock.calls[0][1]?.body))).toMatchObject({
      email: "kaptan@takim.org",
      roles: ["COMPETITOR"],
      team_id: "team-glieser",
    });
  });

  it("bir adres hata verse de DİĞERLERİ devam eder", async () => {
    // Tümünü birden iptal etmek, yöneticiyi listeyi elle ayıklamaya zorlardı.
    mockCreate(["zaten@var.org"]);
    const user = userEvent.setup();
    render(<AccountCreator />);

    await user.type(
      screen.getByTestId("account-emails"),
      "iyi@takim.org\nzaten@var.org\nikinci@takim.org",
    );
    await user.click(screen.getByTestId("account-submit"));

    await waitFor(() =>
      expect(screen.getByTestId("account-results")).toHaveTextContent("2 hesap açıldı"),
    );
    expect(screen.getByTestId("account-results")).toHaveTextContent("1 hata");
    expect(screen.getByTestId("account-row-zaten@var.org")).toHaveTextContent(/zaten kayitli/i);
    expect(screen.getByTestId("account-row-ikinci@takim.org")).toHaveTextContent("sifre-2");
  });

  it("şifrelerin BİR DAHA okunamayacağını söyler", async () => {
    // Bu uyarı olmadan yönetici sayfayı kapatıp şifreleri kaybedebilir;
    // veri tabanında yalnızca bcrypt özeti var.
    mockCreate();
    const user = userEvent.setup();
    render(<AccountCreator />);

    await user.type(screen.getByTestId("account-emails"), "a@b.org");
    await user.click(screen.getByTestId("account-submit"));

    expect(await screen.findByTestId("account-password-notice")).toHaveTextContent(
      /bir daha okunamaz/i,
    );
  });

  it("boş listeyle istek ATMAZ", () => {
    const fetchMock = mockCreate();
    render(<AccountCreator />);
    expect(screen.getByTestId("account-submit")).toBeDisabled();
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("virgül ve noktalı virgülle ayrılmış listeyi de kabul eder", async () => {
    const fetchMock = mockCreate();
    const user = userEvent.setup();
    render(<AccountCreator />);

    // Gerçek kullanımda liste Excel'den / KYS'den kopyalanıyor; ayırıcı
    // her zaman satır sonu olmuyor.
    await user.type(screen.getByTestId("account-emails"), "a@b.org, c@d.org; e@f.org");
    await user.click(screen.getByTestId("account-submit"));

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(3));
  });
});
