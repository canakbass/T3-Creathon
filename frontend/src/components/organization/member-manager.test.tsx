import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemberManager } from "./member-manager";

/**
 * Kurum sorumlusunun üye yönetimi.
 *
 * Burada görünen roller YALNIZCA bu kurumdakiler. Aynı kişi başka bir kurumda
 * bambaşka rollere sahip olabilir ("hem TEKNOFEST yarışması hem ödev kontrolü
 * için aynı maile bağlıysam?") ve o roller burada GÖRÜNMEZ — görünse, bir
 * kurumun sorumlusu üyesinin başka kurumlardaki konumunu öğrenirdi.
 */
function jsonResponse(status: number, payload: unknown) {
  return { ok: status >= 200 && status < 300, status, json: async () => payload };
}

const UYELER = [
  { id: "u1", email: "hakem@cbu.edu.tr", full_name: "Bir Hakem", roles: ["REFEREE"] },
  { id: "u2", email: "ogrenci@cbu.edu.tr", full_name: null, roles: ["COMPETITOR"] },
];

function mockApi({
  liste = UYELER,
  listeStatus = 200,
  yazmaStatus = 200,
  yazmaHatasi = "Kurumun son sorumlusu kaldirilamaz.",
}: {
  liste?: typeof UYELER;
  listeStatus?: number;
  yazmaStatus?: number;
  yazmaHatasi?: string;
} = {}) {
  const fetchMock = jest.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    const yontem = (init?.method ?? "GET").toUpperCase();

    if (url.endsWith("/api/organizations/me/members") && yontem === "GET") {
      if (listeStatus !== 200) {
        return jsonResponse(listeStatus, { detail: "'REFEREE' rolu bu islemi yapamaz." });
      }
      return jsonResponse(200, liste);
    }

    const m = url.match(/\/members\/([^/]+)\/roles(?:\/([^/]+))?$/);
    if (m) {
      if (yazmaStatus !== 200) {
        return jsonResponse(yazmaStatus, { detail: yazmaHatasi });
      }
      const uye = liste.find((u) => u.id === m[1])!;
      const roller =
        yontem === "DELETE"
          ? uye.roles.filter((r) => r !== decodeURIComponent(m[2] ?? ""))
          : [...uye.roles, JSON.parse(String(init?.body)).role];
      return jsonResponse(yontem === "DELETE" ? 200 : 201, { ...uye, roles: roller });
    }

    throw new Error(`Beklenmeyen istek: ${yontem} ${url}`);
  });
  global.fetch = fetchMock as unknown as typeof fetch;
  return fetchMock;
}

describe("MemberManager", () => {
  const originalFetch = global.fetch;
  afterEach(() => {
    global.fetch = originalFetch;
  });

  it("kurumun üyelerini ve BU KURUMDAKİ rollerini listeler", async () => {
    mockApi();
    render(<MemberManager />);

    expect(await screen.findByTestId("member-hakem@cbu.edu.tr")).toBeInTheDocument();
    expect(screen.getByTestId("member-ogrenci@cbu.edu.tr")).toBeInTheDocument();
    // Sahip olunan rol basılı görünmeli, diğerleri değil.
    expect(screen.getByTestId("member-hakem@cbu.edu.tr-REFEREE")).toHaveAttribute(
      "aria-pressed",
      "true",
    );
    expect(
      screen.getByTestId("member-hakem@cbu.edu.tr-COMPETITION_MANAGER"),
    ).toHaveAttribute("aria-pressed", "false");
  });

  it("rol verir ve SUNUCUNUN döndürdüğü rolleri gösterir", async () => {
    // Sunucunun sonucunu kullanıyoruz, elde tahmin etmiyoruz: son sözü kimin
    // söylediği belirsiz kalırsa ekran, sunucunun reddettiği bir değişikliği
    // yapılmış gibi gösterebilir.
    const fetchMock = mockApi();
    const user = userEvent.setup();
    render(<MemberManager />);

    await user.click(
      await screen.findByTestId("member-hakem@cbu.edu.tr-COMPETITION_MANAGER"),
    );

    await waitFor(() =>
      expect(
        screen.getByTestId("member-hakem@cbu.edu.tr-COMPETITION_MANAGER"),
      ).toHaveAttribute("aria-pressed", "true"),
    );
    const cagri = fetchMock.mock.calls.find(([, i]) => i?.method === "POST");
    expect(JSON.parse(String(cagri?.[1]?.body))).toEqual({
      role: "COMPETITION_MANAGER",
    });
  });

  it("basılı bir role tıklamak rolü KALDIRIR", async () => {
    const fetchMock = mockApi();
    const user = userEvent.setup();
    render(<MemberManager />);

    await user.click(await screen.findByTestId("member-hakem@cbu.edu.tr-REFEREE"));

    await waitFor(() =>
      expect(screen.getByTestId("member-hakem@cbu.edu.tr-REFEREE")).toHaveAttribute(
        "aria-pressed",
        "false",
      ),
    );
    const cagri = fetchMock.mock.calls.find(([, i]) => i?.method === "DELETE");
    expect(String(cagri?.[0])).toContain("/roles/REFEREE");
  });

  it("son sorumlu kaldırılamazsa sunucunun MESAJINI gösterir", async () => {
    // Kurum sorumlusuz kalırsa üye yönetimi tamamen kilitlenir; kullanıcının
    // neden reddedildiğini bilmesi gerekiyor.
    mockApi({ yazmaStatus: 400 });
    const user = userEvent.setup();
    render(<MemberManager />);

    await user.click(await screen.findByTestId("member-hakem@cbu.edu.tr-REFEREE"));

    expect(await screen.findByTestId("member-error")).toHaveTextContent(
      /son sorumlusu kaldirilamaz/i,
    );
    // Ve rol DEĞİŞMEMİŞ görünmeli - reddedilen bir değişiklik yapılmış gibi
    // görünürse sorumlu yanlış bir yetki durumuna güvenir.
    expect(screen.getByTestId("member-hakem@cbu.edu.tr-REFEREE")).toHaveAttribute(
      "aria-pressed",
      "true",
    );
  });

  it("liste yetkisi yoksa hatayı gösterir", async () => {
    // Bu liste kurumun tüm e-posta rehberi; yalnızca sorumluya açık.
    mockApi({ listeStatus: 403 });
    render(<MemberManager />);

    expect(await screen.findByTestId("member-error")).toHaveTextContent(
      /bu islemi yapamaz/i,
    );
  });

  it("e-posta ve ada göre arar", async () => {
    mockApi();
    const user = userEvent.setup();
    render(<MemberManager />);

    await screen.findByTestId("member-hakem@cbu.edu.tr");
    await user.type(screen.getByTestId("member-search"), "ogrenci");

    expect(screen.getByTestId("member-ogrenci@cbu.edu.tr")).toBeInTheDocument();
    expect(screen.queryByTestId("member-hakem@cbu.edu.tr")).not.toBeInTheDocument();
  });

  it("kurumda üye yoksa ne yapılacağını söyler", async () => {
    mockApi({ liste: [] });
    render(<MemberManager />);

    expect(await screen.findByTestId("member-empty")).toHaveTextContent(/hesap aç/i);
  });
});
