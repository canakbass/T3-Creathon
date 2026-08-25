import { render, screen, waitFor } from "@testing-library/react";
import { RefereeAssignmentPanel } from "./referee-assignment";
import type { ReportRow } from "@/lib/api";

/**
 * REGRESYON: yarışmaya bağlı OLMAYAN raporlar her yarışmanın atama
 * panelinde listeleniyordu (`r.competitionId === competitionId ||
 * r.competitionId === null`).
 *
 * Sonuç: A yarışmasından atama yapılınca aynı rapor B yarışmasında da
 * "atanmış" görünüyordu, ama yarışma başına yük hesabına hiç girmedikleri
 * için otomatik dağıtımın dengesi de yanlış çıkıyordu. Artık yalnızca bu
 * yarışmanın raporları listeleniyor; bağsız raporlar yok sayılmıyor, ayrı
 * bir uyarıyla var oldukları söyleniyor.
 */

const YARISMA = "comp-A";

function satir(reportId: string, competitionId: string | null): ReportRow {
  return {
    report: {
      reportId,
      projectName: `Proje ${reportId}`,
      category: "Yapay Zeka",
      status: "analyzed",
      submissionDate: "2026-08-24T10:00:00",
    },
    assignedRefereeId: null,
    assignedRefereeEmail: null,
    hasDecision: false,
    competitionId,
    teamId: null,
    teamName: null,
  };
}

const HAKEMLER = [
  { id: "ref-1", email: "hakem@test.org", full_name: null, assigned_count: 0 },
];

describe("RefereeAssignmentPanel", () => {
  it("yalnızca bu yarışmanın raporlarını listeler", async () => {
    render(
      <RefereeAssignmentPanel
        competitionId={YARISMA}
        initialReferees={HAKEMLER}
        initialReports={[
          satir("RPT-A1", YARISMA),
          satir("RPT-B1", "comp-B"),
          satir("RPT-BAGSIZ", null),
        ]}
      />,
    );

    await waitFor(() => {
      expect(screen.getByTestId("assignment-row-RPT-A1")).toBeInTheDocument();
    });
    // Başka bir yarışmanın raporu da, hiçbir yarışmaya bağlı olmayan rapor
    // da bu panelde görünmemeli.
    expect(screen.queryByTestId("assignment-row-RPT-B1")).not.toBeInTheDocument();
    expect(screen.queryByTestId("assignment-row-RPT-BAGSIZ")).not.toBeInTheDocument();
  });

  it("bu yarışmaya rapor yoksa net bir boş durum gösterir", async () => {
    render(
      <RefereeAssignmentPanel
        competitionId={YARISMA}
        initialReferees={HAKEMLER}
        initialReports={[satir("RPT-B1", "comp-B")]}
      />,
    );

    await waitFor(() => {
      expect(screen.getByTestId("no-reports")).toHaveTextContent(
        /bu yarışmaya henüz rapor yüklenmemiş/i,
      );
    });
  });
});
