import { buildCompetitorSummary } from "./competitor-view";
import type { AiAnalysis } from "./ai-analysis";
import type { RefereeDecision } from "./api";
import type { EvaluationReport } from "./mock-reports";

const REPORT: EvaluationReport = {
  reportId: "RPT-2026-ABC123",
  projectName: "İHA Nesne Tespiti",
  category: "Yapay Zeka ve Makine Öğrenmesi",
  status: "approved",
  submissionDate: "2026-08-20T09:00:00",
};

const ANALYSIS: AiAnalysis = {
  reportId: "RPT-2026-ABC123",
  analyzedAt: "2026-08-20T09:02:00",
  engineVersion: "eval-engine v1.0",
  results: {
    languageTemplate: {
      score: 100,
      summary: "Rapor dili ve şablon yapısı uygun.",
      findings: ["Tüm kontroller başarılı."],
    },
    contentHeading: {
      score: 100,
      summary: "Tüm başlıkların altında yeterli içerik var.",
      findings: ["Tüm başlıkların içeriği yeterli."],
    },
    categoryMatch: {
      score: 62,
      summary: "Rapor kategoriye kısmen uyuyor.",
      findings: ["Beyan edilen kategori terimlerinin %30'u geçiyor."],
    },
    similarity: {
      score: 47,
      summary: "GİZLİ-BENZERLİK-ÖZETİ yüksek örtüşme tespit edildi.",
      findings: ["GİZLİ-BENZERLİK-BULGUSU RPT-2026-XYZ ile %47 örtüşme."],
    },
  },
  suggestion: {
    score: 91,
    outcome: "approve",
    rationale: "GİZLİ-AI-GEREKÇESİ ağırlıklı toplam 91/100.",
  },
};

const DECISION: RefereeDecision = {
  outcome: "approve",
  finalScore: 84,
  rationale: "Özgünlük bölümü güçlü, sonuçlar sayısal olarak desteklenmiş.",
  submittedAt: "2026-08-21T14:00:00",
};

describe("buildCompetitorSummary", () => {
  it("returns null until the referee has submitted a decision", () => {
    // AI onerisi tek basina SONUC DEGILDIR - hakem karar vermeden
    // yarismaciya bir sey gosterilmemeli.
    expect(
      buildCompetitorSummary({ report: REPORT, analysis: ANALYSIS, decision: null }),
    ).toBeNull();
  });

  it("projects only the whitelisted competitor keys", () => {
    const summary = buildCompetitorSummary({
      report: REPORT,
      analysis: ANALYSIS,
      decision: DECISION,
    });

    expect(summary).not.toBeNull();
    expect(Object.keys(summary!).sort()).toEqual([
      "category",
      "finalScore",
      "headline",
      "improvements",
      "nextStep",
      "outcome",
      "projectName",
      "reportId",
      "reviewedAt",
      "strengths",
      "submittedAt",
    ]);
  });

  it("never leaks referee-only data into the competitor payload", () => {
    const summary = buildCompetitorSummary({
      report: REPORT,
      analysis: ANALYSIS,
      decision: DECISION,
    });

    const serialised = JSON.stringify(summary);

    // Benzerlik/intihal hakem-ozel: baska bir takimin basvurusu hakkinda
    // bilgi sizdirir ve itiraz surecini hakemin elinden alir.
    expect(serialised).not.toContain("GİZLİ-BENZERLİK-ÖZETİ");
    expect(serialised).not.toContain("GİZLİ-BENZERLİK-BULGUSU");
    expect(serialised).not.toContain("RPT-2026-XYZ");
    expect(serialised).not.toContain("47");

    // AI'nin ONERDIGI puan/gerekce de yarismaciya gosterilmez - nihai
    // karar hakemindir, oneri degil.
    expect(serialised).not.toContain("GİZLİ-AI-GEREKÇESİ");
    expect(summary).not.toHaveProperty("aiSuggestedScore");
    expect(summary).not.toHaveProperty("aiSuggestedOutcome");
    expect(summary).not.toHaveProperty("similarityScore");
    expect(summary).not.toHaveProperty("refereeNotes");
    expect(summary).not.toHaveProperty("refereeName");
    expect(summary).not.toHaveProperty("message");
  });

  it("shows the referee's final score, not the AI suggestion", () => {
    const summary = buildCompetitorSummary({
      report: REPORT,
      analysis: ANALYSIS,
      decision: DECISION,
    });

    expect(summary!.finalScore).toBe(84);
    expect(summary!.finalScore).not.toBe(ANALYSIS.suggestion.score);
  });

  it("splits checks into strengths and improvements by score", () => {
    const summary = buildCompetitorSummary({
      report: REPORT,
      analysis: ANALYSIS,
      decision: DECISION,
    })!;

    const strengthTitles = summary.strengths.map((s) => s.title);
    const improvementTitles = summary.improvements.map((s) => s.title);

    expect(strengthTitles).toContain("Dil / Şablon Uyumu");
    expect(strengthTitles).toContain("İçerik / Başlık Kontrolü");
    // 62 puanli kategori uyumu gelisim alani olmali.
    expect(improvementTitles).toContain("Kategori Uyumu");
    // Benzerlik HICBIR listede yer almamali.
    expect([...strengthTitles, ...improvementTitles]).not.toContain("Benzerlik / İntihal");
  });

  it("includes the referee's own rationale as feedback", () => {
    const summary = buildCompetitorSummary({
      report: REPORT,
      analysis: ANALYSIS,
      decision: DECISION,
    })!;

    expect(
      summary.improvements.some((point) => point.detail.includes("Özgünlük bölümü güçlü")),
    ).toBe(true);
  });

  it("still produces a summary when the analysis is missing", () => {
    // Analiz cokmus olabilir (bozuk PDF). Hakem yine de karar verebilir ve
    // yarismaci sonucunu gormeli.
    const summary = buildCompetitorSummary({
      report: REPORT,
      analysis: null,
      decision: { ...DECISION, outcome: "revise" },
    })!;

    expect(summary.outcome).toBe("revise");
    expect(summary.headline).toMatch(/revizyon/i);
    expect(summary.finalScore).toBe(84);
  });
});
