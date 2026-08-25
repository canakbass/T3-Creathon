import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ReportLookup } from "./report-lookup";

/**
 * Aramanın güvenlik sözleşmesi: künye gösterir, kapı AÇMAZ.
 *
 * Hakemin kendisine atanmamış raporları arayabilmesi bilinçli bir gevşetme;
 * aynı sistemde tam tersi bir açık kapatıldı (atanmamış hakem başka bir
 * yarışmacının tam AI analizini okuyabiliyordu). Bu testler, arayüzün o
 * gevşetmeyi genişletmediğini sabitliyor.
 */

function jsonResponse(status: number, payload: unknown) {
  return { ok: status >= 200 && status < 300, status, json: async () => payload };
}

const ATANMAMIS = {
  report_id: "RPT-2026-AAA111",
  project_name: "İHA Nesne Tespiti",
  team_name: "Glieser",
  competition_name: "Havacılıkta Yapay Zeka",
  evaluation_state: "analiz_edildi",
  assigned_referee_email: "baska@hakem.org",
  access: "metadata_only" as const,
};

const ATANMIS = { ...ATANMAMIS, report_id: "RPT-2026-BBB222", access: "assigned" as const };

function mockLookup(sonuc: unknown, status = 200) {
  const fetchMock = jest.fn(async (input: RequestInfo | URL) => {
    const url = String(input);
    if (url.includes("/api/reports/lookup")) return jsonResponse(status, sonuc);
    throw new Error(`Beklenmeyen istek: ${url}`);
  });
  global.fetch = fetchMock as unknown as typeof fetch;
  return fetchMock;
}

describe("ReportLookup", () => {
  const originalFetch = global.fetch;
  afterEach(() => {
    global.fetch = originalFetch;
  });

  it("başvuru kimliğiyle arayıp künyeyi gösterir", async () => {
    const fetchMock = mockLookup([ATANMAMIS]);
    const user = userEvent.setup();
    render(<ReportLookup />);

    await user.type(screen.getByTestId("lookup-input"), "RPT-2026-AAA111");
    await user.click(screen.getByTestId("lookup-submit"));

    const satir = await screen.findByTestId("lookup-row-RPT-2026-AAA111");
    expect(satir).toHaveTextContent("İHA Nesne Tespiti");
    expect(satir).toHaveTextContent("Glieser");
    // Aramanın asıl cevabı: "bu başvuruya kim bakıyor?"
    expect(satir).toHaveTextContent("baska@hakem.org");

    const url = String(fetchMock.mock.calls[0][0]);
    expect(url).toContain("report_id=RPT-2026-AAA111");
  });

  it("seçilen ölçüte göre DOĞRU parametreyi gönderir", async () => {
    const fetchMock = mockLookup([]);
    const user = userEvent.setup();
    render(<ReportLookup />);

    await user.selectOptions(screen.getByTestId("lookup-field"), "email");
    await user.type(screen.getByTestId("lookup-input"), "ad@ornek.org");
    await user.click(screen.getByTestId("lookup-submit"));

    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    const url = String(fetchMock.mock.calls[0][0]);
    // Backend 0 ya da 2+ ölçütü 422 ile reddediyor; tam olarak biri gitmeli.
    expect(url).toContain("email=");
    expect(url).not.toContain("report_id=");
    expect(url).not.toContain("team_id=");
  });

  it("atanmamış başvuru için AÇ düğmesi göstermez", async () => {
    mockLookup([ATANMAMIS]);
    const onOpen = jest.fn();
    const user = userEvent.setup();
    render(<ReportLookup onOpen={onOpen} />);

    await user.type(screen.getByTestId("lookup-input"), "RPT-2026-AAA111");
    await user.click(screen.getByTestId("lookup-submit"));

    await screen.findByTestId("lookup-row-RPT-2026-AAA111");
    expect(screen.queryByTestId("lookup-open-RPT-2026-AAA111")).not.toBeInTheDocument();
    // Düğmeyi sessizce gizlemek yerine NEDENİNİ yazıyoruz.
    expect(screen.getByTestId("lookup-locked-RPT-2026-AAA111")).toHaveTextContent(
      /size atanmamış/i,
    );
  });

  it("atanmış başvuruda AÇ düğmesi çalışır", async () => {
    mockLookup([ATANMIS]);
    const onOpen = jest.fn();
    const user = userEvent.setup();
    render(<ReportLookup onOpen={onOpen} />);

    await user.type(screen.getByTestId("lookup-input"), "RPT-2026-BBB222");
    await user.click(screen.getByTestId("lookup-submit"));

    await user.click(await screen.findByTestId("lookup-open-RPT-2026-BBB222"));
    expect(onOpen).toHaveBeenCalledWith("RPT-2026-BBB222");
  });

  it("sonuç yoksa net bir boş durum gösterir", async () => {
    mockLookup([]);
    const user = userEvent.setup();
    render(<ReportLookup />);

    await user.type(screen.getByTestId("lookup-input"), "RPT-YOK");
    await user.click(screen.getByTestId("lookup-submit"));

    expect(await screen.findByTestId("lookup-empty")).toHaveTextContent(/bulunamadı/i);
  });

  it("boş sorguyla istek ATMAZ", async () => {
    const fetchMock = mockLookup([]);
    render(<ReportLookup />);
    // Boş sorgu = envanter tarama; backend de 422 veriyor ama arayüz
    // gereksiz isteği hiç göndermemeli.
    expect(screen.getByTestId("lookup-submit")).toBeDisabled();
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("yetki hatasını kullanıcıya gösterir", async () => {
    mockLookup({ detail: "'COMPETITOR' rolu bu islemi yapamaz." }, 403);
    const user = userEvent.setup();
    render(<ReportLookup />);

    await user.type(screen.getByTestId("lookup-input"), "RPT-2026-AAA111");
    await user.click(screen.getByTestId("lookup-submit"));

    expect(await screen.findByTestId("lookup-error")).toBeInTheDocument();
    expect(screen.queryByTestId("lookup-results")).not.toBeInTheDocument();
  });
});
