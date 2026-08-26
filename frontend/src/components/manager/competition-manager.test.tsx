import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { CompetitionManager } from "./competition-manager";

/**
 * Yarisma Yoneticisi paneli. Onceden bu panelde HICBIR YERE KAYDETMEYEN bir
 * kriter formu ve tek tek dosya yukleyen bir kutu vardi; "yarisma" diye bir
 * kavram yoktu.
 */
function jsonResponse(status: number, payload: unknown) {
  return { ok: status >= 200 && status < 300, status, json: async () => payload };
}

const KATEGORILER = [
  { id: "cat-2", name: "Yapay Zeka ve Makine Öğrenmesi", description: null },
  { id: "cat-1", name: "Robotik ve Otomasyon", description: null },
];

function yarisma(over: Partial<Record<string, unknown>> = {}) {
  return {
    id: "COMP-1",
    name: "Havacılıkta Yapay Zeka 2026",
    description: null,
    category_id: "cat-2",
    category_name: "Yapay Zeka ve Makine Öğrenmesi",
    status: "draft",
    submission_deadline: null,
    created_at: "2026-08-24T00:00:00",
    accepted_languages: ["tr"],
    required_headings: [],
    heading_synonyms: {},
    min_pages: null,
    max_pages: null,
    min_section_chars: null,
    criteria: [],
    referee_count: 0,
    report_count: 0,
    ...over,
  };
}

interface Ayar {
  competitions?: unknown[];
  statusError?: { status: number; detail: string };
}

function mockFetch({ competitions = [yarisma()], statusError }: Ayar = {}) {
  let mevcut = [...competitions];

  const fetchMock = jest.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    const method = init?.method ?? "GET";

    if (url.includes("/api/categories")) return jsonResponse(200, KATEGORILER);

    if (url.endsWith("/api/competitions") && method === "GET") {
      return jsonResponse(200, mevcut);
    }
    if (url.endsWith("/api/competitions") && method === "POST") {
      const govde = JSON.parse(String(init?.body ?? "{}"));
      const yeni = yarisma({ id: "COMP-2", name: govde.name, category_id: govde.category_id });
      mevcut = [...mevcut, yeni];
      return jsonResponse(201, yeni);
    }
    if (url.includes("/template") && method === "PUT") {
      return jsonResponse(200, yarisma({ required_headings: ["Özet"] }));
    }
    if (url.includes("/criteria") && method === "PUT") {
      return jsonResponse(200, yarisma({ criteria: [] }));
    }
    if (url.includes("/status") && method === "PUT") {
      if (statusError) return jsonResponse(statusError.status, { detail: statusError.detail });
      return jsonResponse(200, yarisma({ status: "open" }));
    }
    if (url.includes("/api/assignments/referees")) return jsonResponse(200, []);
    if (url.includes("/api/reports")) return jsonResponse(200, []);

    throw new Error(`Beklenmeyen istek: ${url}`);
  });

  global.fetch = fetchMock as unknown as typeof fetch;
  return fetchMock;
}

describe("CompetitionManager", () => {
  const originalFetch = global.fetch;
  afterEach(() => {
    global.fetch = originalFetch;
  });

  it("lists the manager's competitions with their stage", async () => {
    mockFetch();
    render(<CompetitionManager />);

    const liste = await screen.findByTestId("competition-list");
    expect(within(liste).getByText(/havacılıkta yapay zeka 2026/i)).toBeInTheDocument();
    // Asama etiketi gorunmeli - yoneticinin ne yapabilecegini bu belirliyor.
    expect(within(liste).getByText(/hazırlık/i)).toBeInTheDocument();
  });

  it("shows an empty state before any competition exists", async () => {
    mockFetch({ competitions: [] });
    render(<CompetitionManager />);

    expect(await screen.findByTestId("no-competitions")).toBeInTheDocument();
  });

  it("kategoriyi SERBEST METİN olarak gönderir", async () => {
    // Kategori artık sabit bir listeden seçilmiyor.
    //
    // NEDEN: TEKNOFEST'te kategori katılımcı SEVİYESİ demek ("Lise",
    // "Üniversite ve Üzeri", "Mezun") — teknoloji alanı değil; alanı
    // yarışmanın adı belirliyor. Üstelik sistem yalnızca TEKNOFEST'e özel
    // değil: aynı hat ödev kontrolü ("Vize") ya da işe alım taraması
    // ("Kıdemli Backend") için de kullanılıyor. Sabit liste o kullanımları
    // dışarıda bırakırdı.
    const fetchMock = mockFetch({ competitions: [] });
    const user = userEvent.setup();
    render(<CompetitionManager />);

    await screen.findByTestId("create-competition-form");
    await user.type(screen.getByTestId("new-competition-name"), "Havacılıkta Yapay Zeka");
    await user.type(screen.getByTestId("new-competition-category"), "Üniversite ve Üzeri");
    await user.click(screen.getByRole("button", { name: /oluştur/i }));

    await waitFor(() => {
      const call = fetchMock.mock.calls.find(
        ([u, i]) => String(u).endsWith("/api/competitions") && i?.method === "POST",
      );
      expect(call).toBeDefined();
      expect(JSON.parse(String(call?.[1]?.body))).toMatchObject({
        name: "Havacılıkta Yapay Zeka",
        category_label: "Üniversite ve Üzeri",
      });
    });
  });

  it("kategori boş bırakılabilir", async () => {
    const fetchMock = mockFetch({ competitions: [] });
    const user = userEvent.setup();
    render(<CompetitionManager />);

    await screen.findByTestId("create-competition-form");
    await user.type(screen.getByTestId("new-competition-name"), "Etiketsiz");
    await user.click(screen.getByRole("button", { name: /oluştur/i }));

    await waitFor(() => {
      const call = fetchMock.mock.calls.find(
        ([u, i]) => String(u).endsWith("/api/competitions") && i?.method === "POST",
      );
      expect(JSON.parse(String(call?.[1]?.body))).toMatchObject({
        category_label: null,
      });
    });
  });

  it("explains what the current stage allows", async () => {
    mockFetch();
    render(<CompetitionManager />);

    const stage = await screen.findByTestId("competition-stage");
    expect(stage).toHaveTextContent(/yarışmacılar göremez/i);
    expect(within(stage).getByTestId("advance-stage")).toBeInTheDocument();
  });

  it("surfaces the backend's reason when the stage cannot advance", async () => {
    // Backend, sablon/kriter tanimli degilse 'open'a gecisi reddediyor ve
    // hangi tanimin eksik oldugunu soyluyor. O mesaj kullaniciya OLDUGU
    // GIBI gosterilmeli - ne yapacagini bilsin.
    mockFetch({
      statusError: {
        status: 400,
        detail:
          "Basvuruyu acmadan once su tanimlar yapilmali: zorunlu basliklar, degerlendirme kriterleri.",
      },
    });
    const user = userEvent.setup();
    render(<CompetitionManager />);

    await user.click(await screen.findByTestId("advance-stage"));

    const alert = await screen.findByTestId("competition-error");
    expect(alert).toHaveTextContent(/zorunlu basliklar/i);
    expect(alert).toHaveTextContent(/degerlendirme kriterleri/i);
  });

  it("saves the template and criteria to the selected competition", async () => {
    const fetchMock = mockFetch();
    const user = userEvent.setup();
    render(<CompetitionManager />);

    await screen.findByTestId("competition-stage");

    // "Kategori" etiketi hem yarisma olusturma formunda hem sablon
    // formunda var; sorguyu sablon formuna sinirliyoruz.
    const form = within(
      screen.getByRole("region", { name: /kriter ve şablon tanımı/i }),
    );

    await user.type(form.getByLabelText(/rapor türü/i), "Kritik Tasarım Raporu");
    await user.type(form.getByLabelText(/metrik 1 adı/i), "Özgünlük");
    await user.clear(form.getByLabelText(/metrik 1 ağırlık/i));
    await user.type(form.getByLabelText(/metrik 1 ağırlık/i), "100");
    // "Zorunlu başlık 1" hem girdiyi hem "…kaldır" dugmesini esliyor;
    // yalnizca metin girdisini istiyoruz.
    await user.type(form.getByLabelText(/^zorunlu başlık 1$/i), "Özet");
    await user.click(form.getByRole("button", { name: /şablonu kaydet/i }));

    await waitFor(() => {
      const tmpl = fetchMock.mock.calls.find(([u]) => String(u).includes("/template"));
      expect(tmpl).toBeDefined();
      expect(JSON.parse(String(tmpl?.[1]?.body)).required_headings).toEqual(["Özet"]);
    });
    await waitFor(() => {
      const krit = fetchMock.mock.calls.find(
        ([u, i]) => String(u).includes("/criteria") && i?.method === "PUT",
      );
      expect(krit).toBeDefined();
      expect(JSON.parse(String(krit?.[1]?.body)).criteria).toEqual([
        { title: "Özgünlük", description: null, weight: 100 },
      ]);
    });
  });
});
