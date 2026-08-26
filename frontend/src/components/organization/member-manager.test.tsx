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
 *
 * FİLTRELEME VE SAYFALAMA SUNUCUDA. Tüm üyeleri çekip tarayıcıda kesmek
 * "sayfalama" görünümü verirken rehberin TAMAMINI yine de tel üzerinden
 * geçirirdi; bu testler isteğin gerçekten parametre gönderdiğini doğruluyor.
 */
function jsonResponse(status: number, payload: unknown) {
  return { ok: status >= 200 && status < 300, status, json: async () => payload };
}

interface Uye {
  id: string;
  email: string;
  full_name: string | null;
  roles: string[];
}

const HERKES: Uye[] = [
  { id: "u1", email: "hakem@cbu.edu.tr", full_name: "Bir Hakem", roles: ["REFEREE"] },
  { id: "u2", email: "ogrenci@cbu.edu.tr", full_name: null, roles: ["COMPETITOR"] },
  {
    id: "u3",
    email: "cift@cbu.edu.tr",
    full_name: "Çift Rollü",
    roles: ["REFEREE", "COMPETITION_MANAGER"],
  },
];

interface Ayar {
  liste?: Uye[];
  listeStatus?: number;
  yazmaStatus?: number;
  yazmaHatasi?: string;
}

function mockApi({
  liste = HERKES,
  listeStatus = 200,
  yazmaStatus = 200,
  yazmaHatasi = "Kurumun son sorumlusu kaldirilamaz.",
}: Ayar = {}) {
  const fetchMock = jest.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = new URL(String(input), "http://test.local");
    const yontem = (init?.method ?? "GET").toUpperCase();

    if (url.pathname.endsWith("/api/organizations/me/members") && yontem === "GET") {
      if (listeStatus !== 200) {
        return jsonResponse(listeStatus, { detail: "'REFEREE' rolu bu islemi yapamaz." });
      }
      // Sunucuyu taklit ediyoruz: filtre ve sayfalama BURADA uygulanıyor,
      // bileşende değil. Bileşen filtrelemeye kalkarsa bu testler onu
      // yakalamaz ama backend testleri yakalar; buradaki asıl iddia
      // "doğru parametreler gönderiliyor mu".
      const rol = url.searchParams.get("role");
      const q = (url.searchParams.get("q") ?? "").toLowerCase();
      const limit = Number(url.searchParams.get("limit") ?? 25);
      const offset = Number(url.searchParams.get("offset") ?? 0);

      let sonuc = liste;
      if (rol) sonuc = sonuc.filter((u) => u.roles.includes(rol));
      if (q) {
        sonuc = sonuc.filter(
          (u) =>
            u.email.toLowerCase().includes(q) ||
            (u.full_name ?? "").toLowerCase().includes(q),
        );
      }
      return jsonResponse(200, {
        items: sonuc.slice(offset, offset + limit),
        total: sonuc.length,
        limit,
        offset,
      });
    }

    const m = url.pathname.match(/\/members\/([^/]+)\/roles(?:\/([^/]+))?$/);
    if (m) {
      if (yazmaStatus !== 200) return jsonResponse(yazmaStatus, { detail: yazmaHatasi });
      const uye = liste.find((u) => u.id === m[1])!;
      const roller =
        yontem === "DELETE"
          ? uye.roles.filter((r) => r !== decodeURIComponent(m[2] ?? ""))
          : [...uye.roles, JSON.parse(String(init?.body)).role];
      return jsonResponse(yontem === "DELETE" ? 200 : 201, { ...uye, roles: roller });
    }

    throw new Error(`Beklenmeyen istek: ${yontem} ${url.pathname}`);
  });
  global.fetch = fetchMock as unknown as typeof fetch;
  return fetchMock;
}

/** Listeleme isteklerinin sorgu parametreleri (yazma istekleri haric). */
function sorguParametreleri(fetchMock: jest.Mock, sira = -1) {
  const cagrilar = fetchMock.mock.calls.filter((c) =>
    String(c[0]).includes("/api/organizations/me/members?"),
  );
  const hedef = sira < 0 ? cagrilar[cagrilar.length + sira] : cagrilar[sira];
  if (!hedef) throw new Error(`Listeleme istegi yok (${cagrilar.length} cagri)`);
  return new URL(String(hedef[0]), "http://test.local").searchParams;
}

/** 30 uye: varsayilan 25'lik sayfa ile tam iki sayfa eder. */
const KALABALIK: Uye[] = Array.from({ length: 30 }, (_, i) => ({
  id: `k${i}`,
  email: `uye${String(i).padStart(2, "0")}@cbu.edu.tr`,
  full_name: null,
  roles: ["COMPETITOR"],
}));

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
    expect(screen.getByTestId("member-hakem@cbu.edu.tr-REFEREE")).toHaveAttribute(
      "aria-pressed",
      "true",
    );
    expect(
      screen.getByTestId("member-hakem@cbu.edu.tr-COMPETITION_MANAGER"),
    ).toHaveAttribute("aria-pressed", "false");
  });

  it("ilk istekte SAYFA parametreleri gönderiyor", async () => {
    // "Herkesi dizmeyelim" isteğinin karşılığı: istek sınırlı olmalı.
    const fetchMock = mockApi();
    render(<MemberManager />);
    await screen.findByTestId("member-hakem@cbu.edu.tr");

    const p = sorguParametreleri(fetchMock, 0);
    expect(p.get("limit")).toBe("25");
    expect(p.get("offset")).toBe("0");
  });

  it("rol filtresini SUNUCUYA gönderiyor", async () => {
    const fetchMock = mockApi();
    const user = userEvent.setup();
    render(<MemberManager />);
    await screen.findByTestId("member-hakem@cbu.edu.tr");

    await user.selectOptions(screen.getByTestId("member-role-filter"), "COMPETITOR");

    await waitFor(() =>
      expect(screen.queryByTestId("member-hakem@cbu.edu.tr")).not.toBeInTheDocument(),
    );
    expect(sorguParametreleri(fetchMock).get("role")).toBe("COMPETITOR");
    expect(screen.getByTestId("member-ogrenci@cbu.edu.tr")).toBeInTheDocument();
  });

  it("aramayı SUNUCUYA gönderiyor", async () => {
    // Tarayıcıda filtrelemek, rehberin TAMAMINI yine de tel üzerinden
    // geçirmek demekti — listenin yalnızca sorumluya açık olmasının anlamı
    // kalmazdı.
    const fetchMock = mockApi();
    const user = userEvent.setup();
    render(<MemberManager />);
    await screen.findByTestId("member-hakem@cbu.edu.tr");

    await user.type(screen.getByTestId("member-search"), "ogrenci");

    // GECIKME PAYI: arama kutusu 300ms bekliyor ve `waitFor`un 1 saniyelik
    // varsayilani tam takim yukunde yetmiyordu - test tek basina geciyor,
    // hep birlikte dusuyordu. Kararsiz bir test, olmayan bir testten
    // kotudur: insanlar "yine o test" deyip gercek hatalari da gormezden
    // gelmeye baslar.
    await waitFor(() => expect(sorguParametreleri(fetchMock).get("q")).toBe("ogrenci"), {
      timeout: 4000,
    });
    await waitFor(() =>
      expect(screen.queryByTestId("member-hakem@cbu.edu.tr")).not.toBeInTheDocument(),
    );
  });

  it("sayfa ilerletince offset artıyor ve İKİNCİ sayfa geliyor", async () => {
    const fetchMock = mockApi({ liste: KALABALIK });
    const user = userEvent.setup();
    render(<MemberManager />);
    await screen.findByTestId("member-uye00@cbu.edu.tr");

    expect(screen.getByTestId("member-range")).toHaveTextContent("30 üyeden 1–25 arası");
    expect(screen.getByTestId("member-page")).toHaveTextContent("1 / 2");

    await user.click(screen.getByTestId("member-next"));

    await waitFor(() =>
      expect(screen.getByTestId("member-uye29@cbu.edu.tr")).toBeInTheDocument(),
    );
    expect(sorguParametreleri(fetchMock).get("offset")).toBe("25");
    expect(screen.getByTestId("member-range")).toHaveTextContent("30 üyeden 26–30 arası");
    // Birinci sayfanin kayitlari EKRANDA KALMAMALI - kalirsa sorumlu ayni
    // kisiyi iki sayfada gorup listenin bozuk oldugunu dusunur.
    expect(screen.queryByTestId("member-uye00@cbu.edu.tr")).not.toBeInTheDocument();
  });

  it("ilk sayfada ÖNCEKİ, son sayfada SONRAKİ kapalı", async () => {
    const user = userEvent.setup();
    mockApi({ liste: KALABALIK });
    render(<MemberManager />);
    await screen.findByTestId("member-uye00@cbu.edu.tr");

    expect(screen.getByTestId("member-prev")).toBeDisabled();
    expect(screen.getByTestId("member-next")).not.toBeDisabled();

    await user.click(screen.getByTestId("member-next"));
    await waitFor(() =>
      expect(screen.getByTestId("member-uye29@cbu.edu.tr")).toBeInTheDocument(),
    );
    expect(screen.getByTestId("member-next")).toBeDisabled();
    expect(screen.getByTestId("member-prev")).not.toBeDisabled();
  });

  it("filtre değişince İLK SAYFAYA dönüyor", async () => {
    // 2. sayfadayken filtre daraltılırsa sonuç 1 sayfaya düşer ve kullanıcı
    // BOŞ bir sayfada kalırdı.
    const fetchMock = mockApi({ liste: KALABALIK });
    const user = userEvent.setup();
    render(<MemberManager />);
    await screen.findByTestId("member-uye00@cbu.edu.tr");

    await user.click(screen.getByTestId("member-next"));
    await waitFor(() => expect(sorguParametreleri(fetchMock).get("offset")).toBe("25"));

    await user.type(screen.getByTestId("member-search"), "uye01");
    await waitFor(() => expect(sorguParametreleri(fetchMock).get("q")).toBe("uye01"), {
      timeout: 4000,
    });
    expect(sorguParametreleri(fetchMock).get("offset")).toBe("0");
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
    expect(JSON.parse(String(cagri?.[1]?.body))).toEqual({ role: "COMPETITION_MANAGER" });
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
    // Rol DEĞİŞMEMİŞ görünmeli — reddedilen bir değişiklik yapılmış gibi
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

  it("kurumda üye yoksa ne yapılacağını söyler", async () => {
    mockApi({ liste: [] });
    render(<MemberManager />);

    expect(await screen.findByTestId("member-empty")).toHaveTextContent(/hesap aç/i);
  });

  it("filtre sonuç vermezse FARKLI bir mesaj gösterir", async () => {
    // "Kurumda üye yok" ile "filtreye uyan yok" aynı cümle olsaydı, sorumlu
    // filtreyi temizlemesi gerektiğini anlamazdı.
    mockApi();
    const user = userEvent.setup();
    render(<MemberManager />);
    await screen.findByTestId("member-hakem@cbu.edu.tr");

    await user.type(screen.getByTestId("member-search"), "boyle-biri-yok");

    expect(
      await screen.findByTestId("member-empty", {}, { timeout: 4000 }),
    ).toHaveTextContent(/filtreye uyan/i);
  });
});
