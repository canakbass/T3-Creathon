import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { AccountCreator } from "./account-creator";
import { useAuthStore } from "@/store/auth-store";

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

  beforeEach(() => {
    // Varsayılan: yarışma yöneticisi. Yetki bağlı davranışı sınayan testler
    // bunu kendi içinde değiştiriyor.
    useAuthStore.setState({ role: "COMPETITION_MANAGER" });
  });

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

  it("yönetici, VEREMEYECEĞİ rolleri seçenek olarak görmüyor", () => {
    // Backend zaten reddediyor (403); burada gizlemenin sebebi DOĞRULUK:
    // yönetici o rolü seçip 20 adres girse her satır ayrı ayrı hata döner ve
    // listeyi baştan girmek zorunda kalırdı.
    mockCreate();
    useAuthStore.setState({ role: "COMPETITION_MANAGER" });
    render(<AccountCreator />);

    const secenekler = Array.from(
      screen.getByTestId("account-role").querySelectorAll("option"),
    ).map((o) => o.getAttribute("value"));
    expect(secenekler).toEqual(["COMPETITOR", "REFEREE"]);
    expect(screen.getByTestId("account-role-note")).toHaveTextContent(
      /yalnızca kurum sorumlusu/i,
    );
  });

  it("kurum sorumlusu TÜM rolleri verebiliyor", () => {
    mockCreate();
    useAuthStore.setState({ role: "ORG_OWNER" });
    render(<AccountCreator />);

    const secenekler = Array.from(
      screen.getByTestId("account-role").querySelectorAll("option"),
    ).map((o) => o.getAttribute("value"));
    expect(secenekler).toContain("COMPETITION_MANAGER");
    expect(secenekler).toContain("ORG_OWNER");
    expect(screen.queryByTestId("account-role-note")).not.toBeInTheDocument();
  });

  it("AYNI e-postayi iki kez girmek tek istek atiyor", async () => {
    // Kullanicinin bildirdigi konsol hatasinin kaynagi:
    //   "Encountered two children with the same key, 33232801068@gmail.com"
    // Liste Excel'den kopyalandigi icin tekrar eden adres olagan. Tekrar
    // elenmezse React ayni anahtari iki kez gorur, satirlari birlestirir ve
    // yonetici acilan hesaplarin YANLIS listesini gorur; ustelik ikinci
    // istek zaten "zaten kayitli" hatasi alirdi.
    const fetchMock = mockCreate();
    const user = userEvent.setup();
    render(<AccountCreator />);

    await user.type(
      screen.getByTestId("account-emails"),
      "ayni@takim.org\nAYNI@takim.org\nayni@takim.org",
    );
    await user.click(screen.getByTestId("account-submit"));

    await waitFor(() =>
      expect(screen.getByTestId("account-results")).toHaveTextContent("1 hesap açıldı"),
    );
    expect(fetchMock).toHaveBeenCalledTimes(1);
    // Tekrar eden testid, testi de belirsiz hale getirirdi.
    expect(screen.getAllByTestId("account-row-ayni@takim.org")).toHaveLength(1);
  });

  it("boşlukla ayrılmış listeyi de kabul eder", async () => {
    // Gerçek kullanımda liste bazen tek satırda boşluklarla yapıştırılıyor.
    const fetchMock = mockCreate();
    const user = userEvent.setup();
    render(<AccountCreator />);

    await user.type(screen.getByTestId("account-emails"), "a@b.org c@d.org");
    await user.click(screen.getByTestId("account-submit"));

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2));
  });

  it("sayaç TEKİLLEŞTİRİLMİŞ adet gösteriyor", () => {
    // Düğmede "3 hesap aç" yazıp 1 hesap açmak, yöneticiye kaç kişiye şifre
    // ileteceği konusunda yanlış bilgi verirdi.
    mockCreate();
    render(<AccountCreator />);
    const kutu = screen.getByTestId("account-emails");
    fireEvent.change(kutu, { target: { value: "x@y.org, X@Y.org, z@w.org" } });
    expect(screen.getByTestId("account-submit")).toHaveTextContent("2 hesap aç");
  });
});
