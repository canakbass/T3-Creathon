import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { NoMembershipScreen } from "./no-membership-screen";

/**
 * KULLANICININ BİLDİRDİĞİ HATA: yeni bir hesap açıp giriş yapınca
 * "Birden fazla seçeneğiniz var, kurumu ve rolü seçin" yazıyordu ama
 * SEÇİLECEK HİÇBİR ŞEY YOKTU — ölü bir yol.
 *
 * Sebebi doğru davranış: kayıt hiçbir rol ve hiçbir kurum vermiyor. Eksik
 * olan şey, kullanıcıya bir SONRAKİ ADIM göstermekti.
 */
function jsonResponse(status: number, payload: unknown) {
  return { ok: status >= 200 && status < 300, status, json: async () => payload };
}

function mockApi({ orgStatus = 201 }: { orgStatus?: number } = {}) {
  const fetchMock = jest.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    void init;
    const url = String(input);
    if (url.includes("/api/organizations")) {
      if (orgStatus !== 201) {
        return jsonResponse(orgStatus, {
          detail: "Kurum acmadan once e-posta adresinizi dogrulamaniz gerekiyor.",
        });
      }
      return jsonResponse(201, {
        id: "org-yeni",
        name: "Ege Üniversitesi",
        slug: "ege-universitesi",
        my_roles: ["ORG_OWNER"],
        member_count: 1,
      });
    }
    if (url.includes("/api/auth/resend-verification")) {
      return jsonResponse(202, {
        message: "Bu adres dogrulama bekliyorsa baglanti gonderildi.",
      });
    }
    throw new Error(`Beklenmeyen istek: ${url}`);
  });
  global.fetch = fetchMock as unknown as typeof fetch;
  return fetchMock;
}

describe("NoMembershipScreen", () => {
  const originalFetch = global.fetch;
  afterEach(() => {
    global.fetch = originalFetch;
  });

  it("DOĞRULANMAMIŞSA doğrulama adımını gösteriyor", () => {
    mockApi();
    render(
      <NoMembershipScreen
        email="yeni@ogrenci.edu.tr"
        emailVerified={false}
        onKurumKuruldu={jest.fn()}
        onCikis={jest.fn()}
      />,
    );

    expect(screen.getByTestId("verify-prompt")).toBeInTheDocument();
    expect(screen.queryByTestId("waiting-prompt")).not.toBeInTheDocument();
    expect(screen.getByText("yeni@ogrenci.edu.tr")).toBeInTheDocument();
  });

  it("DOĞRULANMIŞSA 'başvurunuz yok' diyor, doğrulama istemiyor", () => {
    // İki durum AYRI anlatılmalı: "hiçbir şey göremiyorum"un iki farklı
    // sebebi var ve kullanıcının hangisinde olduğunu bilmesi gerekiyor.
    mockApi();
    render(
      <NoMembershipScreen
        email="yalniz@kimse.org"
        emailVerified
        onKurumKuruldu={jest.fn()}
        onCikis={jest.fn()}
      />,
    );

    expect(screen.getByTestId("waiting-prompt")).toHaveTextContent(
      /otomatik olarak hesabınıza bağlanacak/i,
    );
    expect(screen.queryByTestId("verify-prompt")).not.toBeInTheDocument();
  });

  it("doğrulama bağlantısını TEKRAR gönderebiliyor", async () => {
    const fetchMock = mockApi();
    const user = userEvent.setup();
    render(
      <NoMembershipScreen
        email="yeni@ogrenci.edu.tr"
        emailVerified={false}
        onKurumKuruldu={jest.fn()}
        onCikis={jest.fn()}
      />,
    );

    await user.click(screen.getByTestId("resend-verification"));

    await waitFor(() =>
      expect(screen.getByTestId("no-membership-info")).toBeInTheDocument(),
    );
    expect(
      fetchMock.mock.calls.some(([u]) => String(u).includes("resend-verification")),
    ).toBe(true);
  });

  it("KENDİ KURUMUNU kurabiliyor", async () => {
    // Bu, ölü ekranın asıl çözümü: kişi sonuç bekleyen bir yarışmacı değil,
    // sistemi kendi kurumu için kullanmak isteyen biri olabilir.
    const fetchMock = mockApi();
    const kuruldu = jest.fn();
    const user = userEvent.setup();
    render(
      <NoMembershipScreen
        email="yalniz@kimse.org"
        emailVerified
        onKurumKuruldu={kuruldu}
        onCikis={jest.fn()}
      />,
    );

    await user.click(screen.getByTestId("org-create-open"));
    await user.type(screen.getByTestId("org-name"), "Ege Üniversitesi");
    await user.click(screen.getByTestId("org-create-submit"));

    await waitFor(() => expect(kuruldu).toHaveBeenCalled());
    const cagri = fetchMock.mock.calls.find(([u]) =>
      String(u).includes("/api/organizations"),
    );
    expect(JSON.parse(String(cagri?.[1]?.body))).toEqual({ name: "Ege Üniversitesi" });
  });

  it("çok kısa kurum adıyla gönderilemiyor", async () => {
    mockApi();
    const user = userEvent.setup();
    render(
      <NoMembershipScreen
        email="yalniz@kimse.org"
        emailVerified
        onKurumKuruldu={jest.fn()}
        onCikis={jest.fn()}
      />,
    );

    await user.click(screen.getByTestId("org-create-open"));
    await user.type(screen.getByTestId("org-name"), "ab");
    expect(screen.getByTestId("org-create-submit")).toBeDisabled();
  });

  it("sunucu reddederse SEBEBİNİ gösteriyor", async () => {
    // Doğrulanmamış adresle kurum açılabilseydi sahte adreslerle sınırsız
    // kiracı üretilebilirdi; sunucu bunu reddediyor ve kullanıcı NEDEN
    // reddedildiğini bilmeli.
    mockApi({ orgStatus: 403 });
    const kuruldu = jest.fn();
    const user = userEvent.setup();
    render(
      <NoMembershipScreen
        email="dogrulanmamis@kimse.org"
        emailVerified={false}
        onKurumKuruldu={kuruldu}
        onCikis={jest.fn()}
      />,
    );

    await user.click(screen.getByTestId("org-create-open"));
    await user.type(screen.getByTestId("org-name"), "Sahte Kurum");
    await user.click(screen.getByTestId("org-create-submit"));

    expect(await screen.findByTestId("no-membership-error")).toHaveTextContent(
      /dogrulamaniz gerekiyor/i,
    );
    expect(kuruldu).not.toHaveBeenCalled();
  });
});
