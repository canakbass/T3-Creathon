import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { RefereeDashboard } from "./referee-dashboard";
import { MOCK_REPORTS } from "@/lib/mock-reports";

describe("RefereeDashboard", () => {
  it("renders the mock list of evaluation reports", () => {
    render(<RefereeDashboard initialReports={MOCK_REPORTS} />);

    const list = screen.getByRole("listbox", { name: /değerlendirme raporları/i });
    const options = within(list).getAllByRole("option");
    expect(options).toHaveLength(MOCK_REPORTS.length);

    for (const report of MOCK_REPORTS) {
      const row = screen.getByTestId(`report-row-${report.reportId}`);
      expect(row).toHaveTextContent(report.projectName);
      expect(row).toHaveTextContent(report.category);
    }
  });

  it("shows an empty state in the detail pane before any report is selected", () => {
    render(<RefereeDashboard initialReports={MOCK_REPORTS} />);

    expect(screen.getByTestId("report-detail-empty")).toBeInTheDocument();
    expect(screen.queryByTestId("report-detail")).not.toBeInTheDocument();
  });

  // Hakem yalnizca KENDISINE ATANMIS raporlari gorur; liste bos oldugunda
  // "henuz rapor yok" demek yaniltici olurdu (sistemde onlarca rapor
  // olabilir). Mesajin hakemi dogru eyleme -yoneticiden atama istemeye-
  // yonlendirdigini dogruluyoruz.
  it("shows an assignment-aware empty state in the sidebar", () => {
    render(<RefereeDashboard initialReports={[]} />);

    const bos = screen.getByTestId("report-list-empty");
    expect(bos).toHaveTextContent(/size atanmış rapor yok/i);
    expect(bos).toHaveTextContent(/yarışma yöneticisi/i);
    expect(screen.queryByRole("listbox")).not.toBeInTheDocument();
  });

  it("shows loading skeletons until the API responds, then renders the list", async () => {
    // Pano artik GERCEK API'yi cagiriyor (eskiden setTimeout ile sahte bir
    // gecikme vardi). Rapor listesi ve kategori listesi paralel isteniyor.
    const originalFetch = global.fetch;
    global.fetch = jest.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      const payload = url.includes("/api/categories")
        ? [{ id: "cat-2", name: "Yapay Zeka ve Makine Öğrenmesi", description: null }]
        : [
            {
              id: "RPT-2026-900001",
              project_name: "İHA Nesne Tespiti",
              category_id: "cat-2",
              status: "analyzed",
              file_path: "uploads/RPT-2026-900001.pdf",
              submitted_by_id: "user-1",
              submission_date: "2026-08-24T10:00:00",
              ai_analysis: null,
              final_decision: null,
            },
          ];
      return { ok: true, status: 200, json: async () => payload };
    }) as unknown as typeof fetch;

    try {
      render(<RefereeDashboard />);

      expect(screen.getByTestId("report-list-skeleton")).toBeInTheDocument();
      expect(screen.getByTestId("report-detail-skeleton")).toBeInTheDocument();
      expect(
        screen.queryByRole("listbox", { name: /değerlendirme raporları/i }),
      ).not.toBeInTheDocument();

      const list = await screen.findByRole("listbox", { name: /değerlendirme raporları/i });
      expect(within(list).getAllByRole("option").length).toBeGreaterThan(0);
      expect(screen.queryByTestId("report-list-skeleton")).not.toBeInTheDocument();
      // Kategori kimligi degil ADI gosterilmeli (esleyici cevirisi calisiyor mu).
      expect(list).toHaveTextContent("Yapay Zeka ve Makine Öğrenmesi");
    } finally {
      global.fetch = originalFetch;
    }
  });

  it("surfaces a readable error when the backend is unreachable", async () => {
    const originalFetch = global.fetch;
    global.fetch = jest.fn(async () => {
      throw new TypeError("Failed to fetch");
    }) as unknown as typeof fetch;

    try {
      render(<RefereeDashboard />);
      const alert = await screen.findByTestId("reports-error");
      expect(alert).toHaveTextContent(/backend'e ulaşılamadı/i);
      // Iskelet sonsuza kadar donmemeli, aksi halde hata mesaji gorunmezdi.
      expect(screen.queryByTestId("report-list-skeleton")).not.toBeInTheDocument();
    } finally {
      global.fetch = originalFetch;
    }
  });

  it("updates the detail view to show the selected report when a row is clicked", async () => {
    const user = userEvent.setup();
    render(<RefereeDashboard initialReports={MOCK_REPORTS} />);

    const target = MOCK_REPORTS[2];
    await user.click(screen.getByTestId(`report-row-${target.reportId}`));

    expect(screen.queryByTestId("report-detail-empty")).not.toBeInTheDocument();
    const detail = screen.getByTestId("report-detail");
    expect(detail).toHaveTextContent(target.projectName);
    expect(detail).toHaveTextContent(target.reportId);
    expect(detail).toHaveTextContent(target.category);
  });

  it("marks the selected row as aria-selected and updates when selection changes", async () => {
    const user = userEvent.setup();
    render(<RefereeDashboard initialReports={MOCK_REPORTS} />);

    const first = MOCK_REPORTS[0];
    const second = MOCK_REPORTS[1];

    await user.click(screen.getByTestId(`report-row-${first.reportId}`));
    expect(screen.getByTestId(`report-row-${first.reportId}`)).toHaveAttribute(
      "aria-selected",
      "true",
    );
    expect(screen.getByTestId("report-detail")).toHaveTextContent(first.projectName);

    await user.click(screen.getByTestId(`report-row-${second.reportId}`));
    expect(screen.getByTestId(`report-row-${first.reportId}`)).toHaveAttribute(
      "aria-selected",
      "false",
    );
    expect(screen.getByTestId(`report-row-${second.reportId}`)).toHaveAttribute(
      "aria-selected",
      "true",
    );

    const detail = screen.getByTestId("report-detail");
    expect(detail).toHaveTextContent(second.projectName);
    expect(detail).not.toHaveTextContent(first.projectName);
  });

  it("supports selecting a report via the keyboard", async () => {
    const user = userEvent.setup();
    render(<RefereeDashboard initialReports={MOCK_REPORTS} />);

    const target = MOCK_REPORTS[3];
    const row = screen.getByTestId(`report-row-${target.reportId}`);
    row.focus();
    await user.keyboard("{Enter}");

    expect(screen.getByTestId("report-detail")).toHaveTextContent(target.projectName);
  });
});
