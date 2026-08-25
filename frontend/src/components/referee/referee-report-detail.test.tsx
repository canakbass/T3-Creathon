import { render, screen, within } from "@testing-library/react";
import { RefereeReportDetail } from "./referee-report-detail";
import {
  CHECK_DEFINITIONS,
  CHECK_KEYS,
  getMockAnalysis,
  getOverallConfidence,
  type AiAnalysis,
} from "@/lib/ai-analysis";
import { getMockReportById, type EvaluationReport } from "@/lib/mock-reports";

const ANALYZED_ID = "RPT-2026-013";
const BORDERLINE_ID = "RPT-2026-011";
const AT_RISK_ID = "RPT-2026-009";
const PENDING_ID = "RPT-2026-014";

function report(reportId: string): EvaluationReport {
  const found = getMockReportById(reportId);
  if (!found) throw new Error(`Missing mock report ${reportId}`);
  return found;
}

function analysis(reportId: string): AiAnalysis {
  const found = getMockAnalysis(reportId);
  if (!found) throw new Error(`Missing mock analysis ${reportId}`);
  return found;
}

describe("RefereeReportDetail — AI Analysis Report", () => {
  it("renders the report header with its identifying metadata", () => {
    const target = report(ANALYZED_ID);
    render(<RefereeReportDetail report={target} analysis={analysis(ANALYZED_ID)} />);

    expect(
      screen.getByRole("heading", { level: 1, name: target.projectName }),
    ).toBeInTheDocument();
    const detail = screen.getByTestId("referee-report-detail");
    expect(detail).toHaveTextContent(target.reportId);
    expect(detail).toHaveTextContent(target.category);
  });

  it("renders a confidence ring for every AI check with the mock score", () => {
    const mock = analysis(ANALYZED_ID);
    render(<RefereeReportDetail report={report(ANALYZED_ID)} analysis={mock} />);

    const meters = screen.getAllByRole("meter");
    expect(meters).toHaveLength(CHECK_KEYS.length);

    for (const key of CHECK_KEYS) {
      const { label } = CHECK_DEFINITIONS[key];
      const meter = screen.getByRole("meter", { name: label });
      expect(meter).toHaveAttribute("aria-valuenow", String(mock.results[key].score));
      expect(meter).toHaveAttribute("aria-valuemin", "0");
      expect(meter).toHaveAttribute("aria-valuemax", "100");
    }
  });

  it("covers all four required evaluation dimensions", () => {
    render(<RefereeReportDetail report={report(ANALYZED_ID)} analysis={analysis(ANALYZED_ID)} />);

    expect(screen.getByRole("meter", { name: /dil \/ şablon uyumu/i })).toBeInTheDocument();
    expect(screen.getByRole("meter", { name: /İçerik \/ Başlık Kontrolü/ })).toBeInTheDocument();
    expect(screen.getByRole("meter", { name: /kategori uyumu/i })).toBeInTheDocument();
    expect(screen.getByRole("meter", { name: /Benzerlik \/ İntihal/ })).toBeInTheDocument();
  });

  it("shows the numeric score and summary text inside each check card", () => {
    const mock = analysis(ANALYZED_ID);
    render(<RefereeReportDetail report={report(ANALYZED_ID)} analysis={mock} />);

    for (const key of CHECK_KEYS) {
      const card = screen.getByTestId(`ai-check-${key}`);
      const result = mock.results[key];
      expect(card).toHaveTextContent(`${result.score}%`);
      expect(card).toHaveTextContent(result.summary);
      for (const finding of result.findings) {
        expect(card).toHaveTextContent(finding);
      }
    }
  });

  it("badges high positive-polarity scores as high confidence", () => {
    // languageTemplate 94 and categoryMatch 91 both clear the 85 threshold.
    render(<RefereeReportDetail report={report(ANALYZED_ID)} analysis={analysis(ANALYZED_ID)} />);

    const badge = screen.getByTestId("ai-check-pill-languageTemplate");
    expect(badge).toHaveTextContent(/yüksek güven/i);
    expect(badge).toHaveAttribute("data-tone", "positive");
    expect(screen.getByTestId("ai-check-pill-categoryMatch")).toHaveAttribute(
      "data-tone",
      "positive",
    );
  });

  it("badges mid-range and weak positive-polarity scores distinctly", () => {
    // RPT-2026-011 sits in the caution band: languageTemplate 72, contentHeading 61.
    const { unmount } = render(
      <RefereeReportDetail report={report(BORDERLINE_ID)} analysis={analysis(BORDERLINE_ID)} />,
    );
    const caution = screen.getByTestId("ai-check-pill-languageTemplate");
    expect(caution).toHaveTextContent(/gözden geçirilmeli/i);
    expect(caution).toHaveAttribute("data-tone", "caution");
    expect(screen.getByTestId("ai-check-pill-contentHeading")).toHaveAttribute(
      "data-tone",
      "critical",
    );
    unmount();

    // RPT-2026-009 drops below the caution floor entirely: languageTemplate 58.
    render(<RefereeReportDetail report={report(AT_RISK_ID)} analysis={analysis(AT_RISK_ID)} />);
    const weak = screen.getByTestId("ai-check-pill-languageTemplate");
    expect(weak).toHaveTextContent(/kritik/i);
    expect(weak).toHaveAttribute("data-tone", "critical");
  });

  it("inverts the badge polarity for similarity, where a low score is the good result", () => {
    const { unmount } = render(
      <RefereeReportDetail report={report(ANALYZED_ID)} analysis={analysis(ANALYZED_ID)} />,
    );

    // 8% similarity is a good outcome, so it reads positive — not critical.
    const clean = screen.getByTestId("ai-check-pill-similarity");
    expect(clean).toHaveTextContent(/özgün/i);
    expect(clean).toHaveAttribute("data-tone", "positive");
    unmount();

    // 47% similarity is a bad outcome despite being the "higher" number.
    render(<RefereeReportDetail report={report(AT_RISK_ID)} analysis={analysis(AT_RISK_ID)} />);
    const risky = screen.getByTestId("ai-check-pill-similarity");
    expect(risky).toHaveTextContent(/yüksek risk/i);
    expect(risky).toHaveAttribute("data-tone", "critical");
  });

  it("renders the overall confidence with similarity normalised", () => {
    const mock = analysis(ANALYZED_ID);
    render(<RefereeReportDetail report={report(ANALYZED_ID)} analysis={mock} />);

    // (94 + 88 + 91 + (100 - 8)) / 4 = 91.25 -> 91
    expect(getOverallConfidence(mock)).toBe(91);
    expect(screen.getByTestId("overall-confidence")).toHaveTextContent("91%");
  });

  it("clamps out-of-range scores rather than overflowing the ring", () => {
    const mock = analysis(ANALYZED_ID);
    const skewed: AiAnalysis = {
      ...mock,
      results: {
        ...mock.results,
        categoryMatch: { ...mock.results.categoryMatch, score: 140 },
      },
    };
    render(<RefereeReportDetail report={report(ANALYZED_ID)} analysis={skewed} />);

    expect(screen.getByRole("meter", { name: /kategori uyumu/i })).toHaveAttribute(
      "aria-valuenow",
      "100",
    );
  });

  it("shows a pending state, and no decision form, when analysis has not completed", () => {
    render(<RefereeReportDetail report={report(PENDING_ID)} analysis={null} />);

    expect(screen.getByTestId("analysis-pending")).toHaveTextContent(/analiz devam ediyor/i);
    expect(screen.queryByTestId("ai-analysis-report")).not.toBeInTheDocument();
    expect(screen.queryByTestId("final-decision-form")).not.toBeInTheDocument();
    expect(screen.queryAllByRole("meter")).toHaveLength(0);
  });

  it("links back to the referee report list", () => {
    render(<RefereeReportDetail report={report(ANALYZED_ID)} analysis={analysis(ANALYZED_ID)} />);

    expect(screen.getByRole("link", { name: /tüm raporlara dön/i })).toHaveAttribute(
      "href",
      "/dashboard/referee",
    );
  });

  it("renders the AI 4th Eye suggestion alongside the analysis", () => {
    const mock = analysis(ANALYZED_ID);
    render(<RefereeReportDetail report={report(ANALYZED_ID)} analysis={mock} />);

    const panel = screen.getByTestId("ai-suggestion-panel");
    expect(within(panel).getByTestId("ai-suggested-score")).toHaveTextContent(
      String(mock.suggestion.score),
    );
    expect(panel).toHaveTextContent(mock.suggestion.rationale);
  });
});

describe("RefereeReportDetail — analiz çöktüğünde", () => {
  /**
   * REGRESYON: analizi ÇÖKMÜŞ rapor sonsuza kadar "Analiz devam ediyor"
   * gösteriyordu.
   *
   * `analysis` null olduğu için hata durumu bekleme durumundan
   * ayrılmıyordu. Hakem dönen bir saat ikonuna bakıp bekliyor, rapor da
   * hiçbir zaman karara bağlanamıyordu — karar formu yalnızca analiz varken
   * çiziliyor. Ne olduğunu ve kime söylenmesi gerektiğini yazmak, sessizce
   * bekletmekten iyi.
   */
  it("hata durumunu bekleme durumundan ayırır", () => {
    render(
      <RefereeReportDetail
        report={{ ...report(PENDING_ID), status: "error" as const }}
        analysis={null}
      />,
    );

    const uyari = screen.getByTestId("analysis-failed");
    expect(uyari).toHaveTextContent(/tamamlanamadı/i);
    expect(uyari).toHaveTextContent(/taranmış/i);
    expect(screen.queryByTestId("analysis-pending")).not.toBeInTheDocument();
    expect(screen.queryByText(/analiz devam ediyor/i)).not.toBeInTheDocument();
  });

  it("henüz analiz edilmemiş rapor için bekleme durumunu korur", () => {
    render(
      <RefereeReportDetail
        report={{ ...report(PENDING_ID), status: "pending" as const }}
        analysis={null}
      />,
    );

    expect(screen.getByTestId("analysis-pending")).toBeInTheDocument();
    expect(screen.queryByTestId("analysis-failed")).not.toBeInTheDocument();
  });
});
