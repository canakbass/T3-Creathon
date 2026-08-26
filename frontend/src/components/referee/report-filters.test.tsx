import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ReportFilters } from "./report-filters";
import type { WireCompetition } from "@/lib/api/types";

function yarisma(
  id: string,
  name: string,
  category_label: string | null,
): WireCompetition {
  return {
    id,
    name,
    description: null,
    category_id: null,
    category_name: null,
    category_label,
    status: "open",
    submission_deadline: null,
    created_at: "2026-08-01T00:00:00",
    report_type_name: null,
    accepted_languages: ["tr"],
    required_headings: [],
    heading_synonyms: {},
    min_pages: null,
    max_pages: null,
    min_section_chars: null,
    criteria: [],
    referee_count: 0,
    report_count: 0,
  };
}

const YARISMALAR = [
  yarisma("c1", "Havacılıkta Yapay Zeka", "Lise"),
  yarisma("c2", "Havacılıkta Yapay Zeka", "Üniversite ve Üzeri"),
  yarisma("c3", "Vize Ödevi — ML 101", "Vize"),
  yarisma("c4", "Etiketsiz", null),
];

describe("ReportFilters", () => {
  it("kategori seçeneklerini YARIŞMALARDAN türetir, sabit listeden değil", async () => {
    // Kategori artık serbest metin. Sabit bir liste hem TEKNOFEST'in
    // seviyelerini (Lise/Üniversite) hem başka kullanımları ("Vize")
    // karşılayamazdı; bu yüzden seçenekler gerçekte KULLANILAN etiketlerden
    // çıkarılıyor.
    const user = userEvent.setup();
    render(
      <ReportFilters value={{}} onChange={jest.fn()} initialCompetitions={YARISMALAR} />,
    );
    await user.click(screen.getByTestId("filters-toggle"));

    const secim = screen.getByTestId("filter-category");
    const secenekler = Array.from(secim.querySelectorAll("option")).map((o) => o.textContent);
    expect(secenekler).toEqual(["Hepsi", "Lise", "Üniversite ve Üzeri", "Vize"]);
    // Etiketi olmayan yarışma boş bir seçenek üretmemeli.
    expect(secenekler).not.toContain("");
  });

  it("filtre değişimini yukarı bildirir", async () => {
    const onChange = jest.fn();
    const user = userEvent.setup();
    render(
      <ReportFilters value={{}} onChange={onChange} initialCompetitions={YARISMALAR} />,
    );
    await user.click(screen.getByTestId("filters-toggle"));

    await user.selectOptions(screen.getByTestId("filter-competition"), "c2");
    expect(onChange).toHaveBeenLastCalledWith({ competitionId: "c2" });

    await user.click(screen.getByTestId("filter-undecided"));
    expect(onChange).toHaveBeenLastCalledWith({ undecided: true });
  });

  it("aktif filtre sayısını gösterir ve temizleyebilir", async () => {
    const onChange = jest.fn();
    const user = userEvent.setup();
    render(
      <ReportFilters
        value={{ competitionId: "c2", undecided: true }}
        onChange={onChange}
        initialCompetitions={YARISMALAR}
      />,
    );

    expect(screen.getByTestId("filters-count")).toHaveTextContent("2");
    await user.click(screen.getByTestId("filters-clear"));
    expect(onChange).toHaveBeenCalledWith({});
  });

  it("filtre yokken sayaç ve temizle düğmesi görünmez", () => {
    render(
      <ReportFilters value={{}} onChange={jest.fn()} initialCompetitions={YARISMALAR} />,
    );
    expect(screen.queryByTestId("filters-count")).not.toBeInTheDocument();
    expect(screen.queryByTestId("filters-clear")).not.toBeInTheDocument();
  });

  it("panel varsayılan olarak KAPALI", () => {
    render(
      <ReportFilters value={{}} onChange={jest.fn()} initialCompetitions={YARISMALAR} />,
    );
    // Hakemin varsayılan görünümü kendi listesi olmalı; filtre paneli
    // ekranı baştan kalabalıklaştırmamalı.
    expect(screen.queryByTestId("filters-panel")).not.toBeInTheDocument();
  });
});
