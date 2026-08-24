import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { FinalDecisionForm } from "./final-decision-form";
import { getMockAnalysis } from "@/lib/ai-analysis";
import type { AiSuggestion } from "@/lib/ai-analysis";

const REPORT_ID = "RPT-2026-013";

const suggestion: AiSuggestion = getMockAnalysis(REPORT_ID)!.suggestion;

const JUSTIFICATION =
  "Manually re-read the methodology section; the limitations gap is more serious than the engine judged.";

function renderForm(onSubmitDecision = jest.fn()) {
  const user = userEvent.setup();
  render(
    <FinalDecisionForm
      reportId={REPORT_ID}
      suggestion={suggestion}
      onSubmitDecision={onSubmitDecision}
    />,
  );
  return { user, onSubmitDecision };
}

function scoreInput() {
  return screen.getByLabelText(/final puan/i) as HTMLInputElement;
}

describe("FinalDecisionForm", () => {
  it("distinguishes the AI suggestion from the referee's own input", () => {
    renderForm();

    const panel = screen.getByTestId("ai-suggestion-panel");
    expect(panel).toHaveTextContent(/ai dördüncü göz/i);
    expect(panel).toHaveTextContent(/danışma/i);
    expect(screen.getByTestId("ai-suggested-score")).toHaveTextContent("88");
    expect(screen.getByTestId("ai-suggested-outcome")).toHaveTextContent("Onayla");

    // The AI's numbers live outside the form; the form holds the referee's entry.
    const form = screen.getByTestId("final-decision-form");
    expect(form).toHaveTextContent(/hakem nihai girişi/i);
    expect(form).not.toContainElement(panel);
  });

  it("pre-fills the referee inputs with the AI suggestion and marks them as matching", () => {
    renderForm();

    expect(scoreInput()).toHaveValue(suggestion.score);
    expect(screen.getByRole("radio", { name: /onayla/i })).toBeChecked();
    expect(screen.getByTestId("agreement-indicator")).toBeInTheDocument();
    expect(screen.queryByTestId("override-indicator")).not.toBeInTheDocument();
    expect(screen.getByTestId("ai-choice-marker-approve")).toBeInTheDocument();
  });

  it("lets the referee overwrite the AI suggestion and submits the manual values", async () => {
    const { user, onSubmitDecision } = renderForm();

    await user.clear(scoreInput());
    await user.type(scoreInput(), "57");
    await user.click(screen.getByRole("radio", { name: /Revizyon İste/ }));
    await user.type(screen.getByLabelText(/gerekçe/i), JUSTIFICATION);

    expect(screen.getByTestId("override-indicator")).toHaveTextContent(/ai önerisi geçersiz/i);

    await user.click(screen.getByRole("button", { name: /nihai kararı gönder/i }));

    await waitFor(() => expect(onSubmitDecision).toHaveBeenCalledTimes(1));
    expect(onSubmitDecision).toHaveBeenCalledWith({
      reportId: REPORT_ID,
      finalScore: 57,
      outcome: "revise",
      refereeNotes: JUSTIFICATION,
      overridesAiSuggestion: true,
      // Denetim izi: gerekce elle yazildi, AI taslagi kullanilmadi.
      rationaleAiDrafted: false,
      rationaleEditedByReferee: false,
    });
  });

  it("records agreement when the referee accepts the AI suggestion unchanged", async () => {
    const { user, onSubmitDecision } = renderForm();

    await user.type(screen.getByLabelText(/gerekçe/i), JUSTIFICATION);
    await user.click(screen.getByRole("button", { name: /nihai kararı gönder/i }));

    await waitFor(() => expect(onSubmitDecision).toHaveBeenCalledTimes(1));
    expect(onSubmitDecision).toHaveBeenCalledWith(
      expect.objectContaining({
        finalScore: suggestion.score,
        outcome: suggestion.outcome,
        overridesAiSuggestion: false,
      }),
    );
  });

  it("flags an override when only the outcome differs from the AI suggestion", async () => {
    const { user, onSubmitDecision } = renderForm();

    await user.click(screen.getByRole("radio", { name: /reddet/i }));
    await user.type(screen.getByLabelText(/gerekçe/i), JUSTIFICATION);
    await user.click(screen.getByRole("button", { name: /nihai kararı gönder/i }));

    await waitFor(() => expect(onSubmitDecision).toHaveBeenCalledTimes(1));
    expect(onSubmitDecision).toHaveBeenCalledWith(
      expect.objectContaining({
        finalScore: suggestion.score,
        outcome: "reject",
        overridesAiSuggestion: true,
      }),
    );
  });

  it("confirms the recorded decision and notes that the AI was overridden", async () => {
    const { user } = renderForm();

    await user.clear(scoreInput());
    await user.type(scoreInput(), "57");
    await user.type(screen.getByLabelText(/gerekçe/i), JUSTIFICATION);
    await user.click(screen.getByRole("button", { name: /nihai kararı gönder/i }));

    const banner = await screen.findByTestId("decision-saved-banner");
    expect(banner).toHaveTextContent(REPORT_ID);
    expect(banner).toHaveTextContent("57/100");
    expect(banner).toHaveTextContent(/ai önerisi geçersiz kılındı/i);
  });

  it("restores the AI suggestion on reset while keeping the referee's justification", async () => {
    const { user } = renderForm();

    await user.clear(scoreInput());
    await user.type(scoreInput(), "20");
    await user.click(screen.getByRole("radio", { name: /reddet/i }));
    await user.type(screen.getByLabelText(/gerekçe/i), JUSTIFICATION);
    expect(screen.getByTestId("override-indicator")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /ai önerisine sıfırla/i }));

    expect(scoreInput()).toHaveValue(suggestion.score);
    expect(screen.getByRole("radio", { name: /onayla/i })).toBeChecked();
    expect(screen.getByTestId("agreement-indicator")).toBeInTheDocument();
    expect(screen.getByLabelText(/gerekçe/i)).toHaveValue(JUSTIFICATION);
  });

  it("blocks submission and does not call the submit handler when the score is out of range", async () => {
    const { user, onSubmitDecision } = renderForm();

    await user.clear(scoreInput());
    await user.type(scoreInput(), "140");
    await user.type(screen.getByLabelText(/gerekçe/i), JUSTIFICATION);
    await user.click(screen.getByRole("button", { name: /nihai kararı gönder/i }));

    expect(await screen.findByRole("alert")).toHaveTextContent(/100'ü geçemez/i);
    expect(onSubmitDecision).not.toHaveBeenCalled();
  });

  it("blocks submission and does not call the submit handler when the score is blank", async () => {
    const { user, onSubmitDecision } = renderForm();

    await user.clear(scoreInput());
    await user.type(screen.getByLabelText(/gerekçe/i), JUSTIFICATION);
    await user.click(screen.getByRole("button", { name: /nihai kararı gönder/i }));

    expect(await screen.findByRole("alert")).toHaveTextContent(/final puanı/i);
    expect(onSubmitDecision).not.toHaveBeenCalled();
  });

  it("requires a written justification before recording the decision", async () => {
    const { user, onSubmitDecision } = renderForm();

    await user.type(screen.getByLabelText(/gerekçe/i), "Too short");
    await user.click(screen.getByRole("button", { name: /nihai kararı gönder/i }));

    expect(await screen.findByRole("alert")).toHaveTextContent(/en az 20 karakter/i);
    expect(onSubmitDecision).not.toHaveBeenCalled();
    expect(screen.queryByTestId("decision-saved-banner")).not.toBeInTheDocument();
  });

  it("still records the decision when no submit handler is wired up", async () => {
    const user = userEvent.setup();
    render(<FinalDecisionForm reportId={REPORT_ID} suggestion={suggestion} />);

    await user.type(screen.getByLabelText(/gerekçe/i), JUSTIFICATION);
    await user.click(screen.getByRole("button", { name: /nihai kararı gönder/i }));

    expect(await screen.findByTestId("decision-saved-banner")).toBeInTheDocument();
  });

  /**
   * AI TASLAK GEREKCE - etik cerceve testleri.
   *
   * Gerekce, bir insanin raporu gercekten inceledi̇gi̇ni̇n kanitidir. AI
   * taslak sunabilir ama: otomatik doldurmamali, AI urunu oldugu
   * gorunmeli, ve gonderilen metnin taslaktan degistirilip
   * degistirilmedigi kayit altina alinmali.
   */
  describe("AI gerekçe taslağı", () => {
    it("does not offer a draft button when no draft provider is wired", () => {
      render(<FinalDecisionForm reportId={REPORT_ID} suggestion={suggestion} />);
      expect(screen.queryByTestId("request-rationale-draft")).not.toBeInTheDocument();
    });

    it("never auto-fills the rationale — the referee must ask for the draft", () => {
      render(
        <FinalDecisionForm
          reportId={REPORT_ID}
          suggestion={suggestion}
          onRequestDraft={async () => "AI taslağı"}
        />,
      );
      expect(screen.getByLabelText(/gerekçe/i)).toHaveValue("");
      expect(screen.getByTestId("request-rationale-draft")).toBeInTheDocument();
      expect(screen.queryByTestId("draft-notice")).not.toBeInTheDocument();
    });

    it("fills the field and shows an AI-origin notice once the draft is requested", async () => {
      const user = userEvent.setup();
      render(
        <FinalDecisionForm
          reportId={REPORT_ID}
          suggestion={suggestion}
          onRequestDraft={async () => "AI tarafından üretilmiş taslak metin."}
        />,
      );

      await user.click(screen.getByTestId("request-rationale-draft"));

      await waitFor(() =>
        expect(screen.getByLabelText(/gerekçe/i)).toHaveValue(
          "AI tarafından üretilmiş taslak metin.",
        ),
      );
      const notice = screen.getByTestId("draft-notice");
      expect(notice).toHaveTextContent(/taslaktır/i);
      expect(notice).toHaveTextContent(/kayıt altına alınır/i);
    });

    it("records that the rationale came from a draft and was NOT edited", async () => {
      const onSubmitDecision = jest.fn();
      const taslak =
        "AI taslağı: rapor şablona uygun, özgünlük bölümü gözden geçirilmeli, bu yeterince uzun bir gerekçe metnidir.";
      const user = userEvent.setup();
      render(
        <FinalDecisionForm
          reportId={REPORT_ID}
          suggestion={suggestion}
          onSubmitDecision={onSubmitDecision}
          onRequestDraft={async () => taslak}
        />,
      );

      await user.click(screen.getByTestId("request-rationale-draft"));
      await waitFor(() => expect(screen.getByLabelText(/gerekçe/i)).toHaveValue(taslak));
      await user.click(screen.getByRole("button", { name: /nihai kararı gönder/i }));

      await waitFor(() => expect(onSubmitDecision).toHaveBeenCalledTimes(1));
      expect(onSubmitDecision).toHaveBeenCalledWith(
        expect.objectContaining({
          rationaleAiDrafted: true,
          rationaleEditedByReferee: false,
        }),
      );
    });

    it("records when the referee edited the draft before submitting", async () => {
      const onSubmitDecision = jest.fn();
      const taslak = "AI taslağı: rapor şablona uygun ve bu metin yeterince uzundur.";
      const user = userEvent.setup();
      render(
        <FinalDecisionForm
          reportId={REPORT_ID}
          suggestion={suggestion}
          onSubmitDecision={onSubmitDecision}
          onRequestDraft={async () => taslak}
        />,
      );

      await user.click(screen.getByTestId("request-rationale-draft"));
      await waitFor(() => expect(screen.getByLabelText(/gerekçe/i)).toHaveValue(taslak));
      await user.type(
        screen.getByLabelText(/gerekçe/i),
        " Kendi değerlendirmem: özgünlük yetersiz.",
      );
      await user.click(screen.getByRole("button", { name: /nihai kararı gönder/i }));

      await waitFor(() => expect(onSubmitDecision).toHaveBeenCalledTimes(1));
      expect(onSubmitDecision).toHaveBeenCalledWith(
        expect.objectContaining({
          rationaleAiDrafted: true,
          rationaleEditedByReferee: true,
        }),
      );
    });
  });
});
