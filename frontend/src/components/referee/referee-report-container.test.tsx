import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { RefereeReportContainer } from "./referee-report-container";

/**
 * REGRESYON: karar KAYDEDİLDİKTEN sonra ekranı tazeleme isteği başarısız
 * olursa, hakeme "karar kaydedilemedi" gösteriliyordu.
 *
 * Tazeleme, karar gönderimiyle aynı `try` bloğundaydı ve `catch` hatayı
 * yeniden fırlatıyordu; form da bu yüzden "kaydedildi" ekranını
 * göstermiyordu. Ağ bir an koptuğunda hakem kararı tekrar göndermeyi
 * deniyor ve bu kez backend'den "bu rapor için zaten karar verilmiş"
 * yanıtını alıyor — sistem bozuk gibi görünüyor, oysa ilk karar başarıyla
 * yazılmıştı.
 */

const REPORT_ID = "RPT-2026-ABC123";

function raporGovdesi(overrides: Record<string, unknown> = {}) {
  return {
    id: REPORT_ID,
    project_name: "İHA Nesne Tespiti",
    category_id: "cat-2",
    status: "analyzed",
    file_path: `uploads/${REPORT_ID}.pdf`,
    submitted_by_id: "user-1",
    submission_date: "2026-08-24T10:00:00",
    final_decision: null,
    ai_analysis: {
      id: "an-1",
      report_id: REPORT_ID,
      analyzed_at: "2026-08-24T10:01:00",
      engine_version: "eval-engine v1.0",
      suggested_outcome: "revise",
      suggested_score: 72,
      rationale: "Ağırlıklı toplam 72/100 — önerilen sonuç: revizyon.",
      results: {
        languageTemplate: { score: 100, summary: "Uygun", findings: [] },
        contentHeading: { score: 100, summary: "Uygun", findings: [] },
        categoryMatch: { score: 90, summary: "Uygun", findings: [] },
        similarity: { score: 3, summary: "Düşük örtüşme", findings: [] },
      },
    },
    ...overrides,
  };
}

function jsonResponse(status: number, payload: unknown) {
  return { ok: status >= 200 && status < 300, status, json: async () => payload };
}

/**
 * İlk GET başarılı (rapor yüklensin), POST /decision başarılı, karar
 * SONRASI ikinci GET başarısız — tam olarak sınanmak istenen sıra.
 */
function mockFetchWithFailingRefresh() {
  let raporGetSayisi = 0;
  const fetchMock = jest.fn(async (input: RequestInfo | URL) => {
    const url = String(input);
    if (url.includes("/api/categories")) return jsonResponse(200, []);
    if (url.includes("/decision")) {
      return jsonResponse(200, {
        id: "dec-1",
        report_id: REPORT_ID,
        referee_id: "ref-1",
        outcome: "revise",
        final_score: 70,
        rationale: "x",
        submitted_at: "2026-08-24T11:00:00",
      });
    }
    if (url.includes(`/api/reports/${REPORT_ID}`)) {
      raporGetSayisi += 1;
      if (raporGetSayisi === 1) return jsonResponse(200, raporGovdesi());
      throw new TypeError("Failed to fetch");
    }
    throw new Error(`Beklenmeyen istek: ${url}`);
  });
  global.fetch = fetchMock as unknown as typeof fetch;
  return fetchMock;
}

describe("RefereeReportContainer — karar sonrası tazeleme", () => {
  const originalFetch = global.fetch;
  afterEach(() => {
    global.fetch = originalFetch;
  });

  it("tazeleme başarısız olsa bile kararın kaydedildiğini söyler", async () => {
    mockFetchWithFailingRefresh();
    const user = userEvent.setup();

    render(<RefereeReportContainer reportId={REPORT_ID} />);
    await screen.findByLabelText(/final puan/i);

    await user.clear(screen.getByLabelText(/final puan/i));
    await user.type(screen.getByLabelText(/final puan/i), "70");
    // Nihai karar zaten AI onerisiyle (revizyon) dolu geliyor; radyo
    // secimine gerek yok.
    await user.type(
      screen.getByLabelText(/gerekçe/i),
      "Yöntem bölümü yeterli ancak bulgular kısmı genişletilmeli, bu gerekçe yeterince uzun.",
    );
    await user.click(screen.getByRole("button", { name: /nihai kararı gönder/i }));

    const uyari = await screen.findByTestId("decision-error");
    // Kritik nokta: mesaj kararın KAYDEDİLDİĞİNİ söylemeli.
    expect(uyari).toHaveTextContent(/karar kaydedildi/i);
    expect(uyari).not.toHaveTextContent(/karar kaydedilemedi/i);

    // Form da başarı durumuna geçmeli - aksi halde hakem tekrar gönderir
    // ve "zaten karar verilmiş" hatasıyla karşılaşır.
    await waitFor(() => {
      expect(screen.getByTestId("decision-saved-banner")).toBeInTheDocument();
    });
  });
});
