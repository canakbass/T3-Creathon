"use client";

import { useId, useState } from "react";
import { useForm, useWatch } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import type { AiSuggestion } from "@/lib/ai-analysis";
import {
  DECISION_DESCRIPTIONS,
  DECISION_LABELS,
  DECISION_OUTCOMES,
  finalDecisionSchema,
  type FinalDecisionFormInput,
  type FinalDecisionFormValues,
  type FinalDecisionSubmission,
} from "@/lib/final-decision";

interface FinalDecisionFormProps {
  reportId: string;
  suggestion: AiSuggestion;
  /**
   * Hakemin nihai kararını kalıcı hale getirir.
   *
   * Promise DÖNEBİLİR ve dönerse `await` edilir: reddedilirse "kaydedildi"
   * bandı GÖSTERİLMEZ. Önceden bu geri çağrım senkron çağrılıyor ve başarı
   * durumu ondan ÖNCE kuruluyordu — yani kayıt başarısız olsa bile hakem
   * kararının kaydedildiğini sanıyordu.
   */
  onSubmitDecision?: (submission: FinalDecisionSubmission) => void | Promise<void>;
  /** Bu rapor için karar zaten verilmişse form salt-okunur gösterilir. */
  decisionAlreadySubmitted?: boolean;
}

export function FinalDecisionForm({
  reportId,
  suggestion,
  onSubmitDecision,
  decisionAlreadySubmitted = false,
}: FinalDecisionFormProps) {
  const [submitted, setSubmitted] = useState<FinalDecisionSubmission | null>(null);
  const headingId = useId();

  const defaults: FinalDecisionFormInput = {
    finalScore: suggestion.score,
    outcome: suggestion.outcome,
    refereeNotes: "",
  };

  const {
    register,
    handleSubmit,
    control,
    setValue,
    formState: { errors, isSubmitting },
  } = useForm<FinalDecisionFormInput, unknown, FinalDecisionFormValues>({
    resolver: zodResolver(finalDecisionSchema),
    defaultValues: defaults,
    mode: "onSubmit",
  });

  const currentScore = useWatch({ control, name: "finalScore" });
  const currentOutcome = useWatch({ control, name: "outcome" });
  const overridesAiSuggestion =
    Number(currentScore) !== suggestion.score || currentOutcome !== suggestion.outcome;

  async function onValid(values: FinalDecisionFormValues) {
    const submission: FinalDecisionSubmission = {
      ...values,
      reportId,
      overridesAiSuggestion:
        values.finalScore !== suggestion.score || values.outcome !== suggestion.outcome,
    };

    // Kayit BASARILI olduktan SONRA basari bandini gosteriyoruz.
    // Geri cagrim reddedilirse hata yukaridaki kap bilesende gosteriliyor
    // ve form doldurulmus halde kaliyor, boylece hakem tekrar deneyebilir.
    try {
      await onSubmitDecision?.(submission);
    } catch {
      return;
    }
    setSubmitted(submission);
  }

  return (
    <section
      aria-labelledby={headingId}
      data-testid="final-decision-section"
      className="rounded-2xl border border-border bg-surface p-6 shadow-sm"
    >
      <div className="border-b border-border pb-5">
        <h2 id={headingId} className="text-lg font-bold text-foreground">
          Nihai Karar ve Puanlama
        </h2>
        <p className="mt-1 text-sm text-muted">
          AI Dördüncü Göz yalnızca danışma niteliğindedir. Aşağıdaki girişiniz kayıtlı nihai
          karardır.
        </p>
      </div>

      {submitted && (
        <div
          role="status"
          data-testid="decision-saved-banner"
          className="mt-5 flex items-center justify-between gap-3 rounded-xl border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm font-semibold text-emerald-700"
        >
          <span>
            {submitted.reportId} için nihai karar kaydedildi:{" "}
            {DECISION_LABELS[submitted.outcome]}, {submitted.finalScore}/100 puan
            {submitted.overridesAiSuggestion ? " (AI önerisi geçersiz kılındı)." : "."}
          </span>
          <button
            type="button"
            onClick={() => setSubmitted(null)}
            aria-label="Kaydedilen karar mesajını kapat"
            className="rounded-md p-1 text-emerald-700 transition hover:bg-emerald-100 focus:outline-none focus-visible:ring-2 focus-visible:ring-brand-500"
          >
            ×
          </button>
        </div>
      )}

      <div className="mt-6 grid grid-cols-1 gap-6 lg:grid-cols-[minmax(0,20rem)_minmax(0,1fr)] lg:items-start">
        <aside
          data-testid="ai-suggestion-panel"
          aria-labelledby="ai-fourth-eye-heading"
          className="rounded-xl border border-brand-200 bg-brand-50/70 p-4"
        >
          <div className="flex items-center gap-2">
            <span
              aria-hidden="true"
              className="flex h-7 w-7 items-center justify-center rounded-lg bg-brand-600 text-white"
            >
              <svg viewBox="0 0 24 24" fill="none" className="h-4 w-4">
                <path
                  d="M2.5 12S6 5.5 12 5.5 21.5 12 21.5 12 18 18.5 12 18.5 2.5 12 2.5 12Z"
                  stroke="currentColor"
                  strokeWidth="1.6"
                  strokeLinejoin="round"
                />
                <circle cx="12" cy="12" r="2.75" stroke="currentColor" strokeWidth="1.6" />
              </svg>
            </span>
            <h3 id="ai-fourth-eye-heading" className="text-sm font-bold text-brand-800">
              AI Dördüncü Göz — Öneri
            </h3>
          </div>

          <p className="mt-1 text-xs font-semibold uppercase tracking-wide text-brand-700/80">
            Danışma niteliğinde · bağlayıcı değil
          </p>

          <dl className="mt-4 flex flex-col gap-3">
            <div className="flex items-baseline justify-between gap-2">
              <dt className="text-xs font-semibold uppercase tracking-wide text-brand-700/80">
                Önerilen puan
              </dt>
              <dd
                data-testid="ai-suggested-score"
                className="text-xl font-extrabold tabular-nums text-brand-800"
              >
                {suggestion.score}
                <span className="text-sm font-bold text-brand-700/70">/100</span>
              </dd>
            </div>
            <div className="flex items-baseline justify-between gap-2">
              <dt className="text-xs font-semibold uppercase tracking-wide text-brand-700/80">
                Önerilen sonuç
              </dt>
              <dd
                data-testid="ai-suggested-outcome"
                className="text-sm font-bold text-brand-800"
              >
                {DECISION_LABELS[suggestion.outcome]}
              </dd>
            </div>
          </dl>

          <p className="mt-4 border-t border-brand-200 pt-3 text-xs leading-relaxed text-brand-900/70">
            {suggestion.rationale}
          </p>
        </aside>

        <form
          noValidate
          onSubmit={handleSubmit(onValid)}
          data-testid="final-decision-form"
          className="flex flex-col gap-6"
        >
          <div className="flex flex-wrap items-center justify-between gap-2">
            <h3 className="text-sm font-bold text-foreground">Hakem Nihai Girişi</h3>
            {overridesAiSuggestion ? (
              <span
                data-testid="override-indicator"
                className="inline-flex items-center gap-1.5 rounded-full bg-amber-50 px-2.5 py-0.5 text-xs font-bold text-amber-700 ring-1 ring-inset ring-amber-200"
              >
                <span aria-hidden="true" className="h-1.5 w-1.5 rounded-full bg-current" />
                AI önerisi geçersiz kılınıyor
              </span>
            ) : (
              <span
                data-testid="agreement-indicator"
                className="inline-flex items-center gap-1.5 rounded-full bg-slate-100 px-2.5 py-0.5 text-xs font-bold text-muted ring-1 ring-inset ring-border"
              >
                <span aria-hidden="true" className="h-1.5 w-1.5 rounded-full bg-current" />
                AI önerisiyle eşleşiyor
              </span>
            )}
          </div>

          <div className="flex flex-col gap-1.5">
            <label htmlFor="finalScore" className="text-sm font-semibold text-foreground">
              Final puan
            </label>
            <div className="relative w-32">
              <input
                id="finalScore"
                type="number"
                inputMode="numeric"
                min={0}
                max={100}
                aria-invalid={errors.finalScore ? "true" : "false"}
                aria-describedby={
                  errors.finalScore ? "finalScore-error" : "finalScore-hint"
                }
                {...register("finalScore", { valueAsNumber: true })}
                className="w-full rounded-lg border border-border bg-white px-3 py-2 pr-12 text-sm font-semibold text-foreground outline-none transition focus:border-brand-500 focus:ring-2 focus:ring-brand-500/30"
              />
              <span className="pointer-events-none absolute right-3 top-1/2 -translate-y-1/2 text-xs text-muted">
                /100
              </span>
            </div>
            {errors.finalScore ? (
              <p id="finalScore-error" role="alert" className="text-xs font-medium text-red-600">
                {errors.finalScore.message}
              </p>
            ) : (
              <p id="finalScore-hint" className="text-xs text-muted">
                AI önerisi olan {suggestion.score} ile önceden dolduruldu. Dilediğiniz gibi
                değiştirebilirsiniz.
              </p>
            )}
          </div>

          <fieldset className="flex flex-col gap-3">
            <legend className="text-sm font-semibold text-foreground">Nihai karar</legend>
            <div className="grid grid-cols-1 gap-2 sm:grid-cols-3">
              {DECISION_OUTCOMES.map((outcome) => {
                const isAiChoice = outcome === suggestion.outcome;
                return (
                  <label
                    key={outcome}
                    htmlFor={`outcome-${outcome}`}
                    className={`flex cursor-pointer flex-col gap-1 rounded-xl border px-3 py-3 transition focus-within:ring-2 focus-within:ring-brand-500/30 hover:border-brand-300 ${
                      currentOutcome === outcome
                        ? "border-brand-500 bg-brand-50/60"
                        : "border-border bg-white"
                    }`}
                  >
                    <span className="flex items-center gap-2">
                      <input
                        id={`outcome-${outcome}`}
                        type="radio"
                        value={outcome}
                        aria-describedby={
                          isAiChoice ? `outcome-${outcome}-ai-hint` : undefined
                        }
                        {...register("outcome")}
                        className="h-4 w-4 accent-brand-600"
                      />
                      <span className="text-sm font-semibold text-foreground">
                        {DECISION_LABELS[outcome]}
                      </span>
                    </span>
                    <span className="text-xs leading-relaxed text-muted">
                      {DECISION_DESCRIPTIONS[outcome]}
                    </span>
                    {isAiChoice && (
                      <span
                        id={`outcome-${outcome}-ai-hint`}
                        data-testid={`ai-choice-marker-${outcome}`}
                        className="mt-0.5 text-[0.7rem] font-bold uppercase tracking-wide text-brand-700"
                      >
                        AI Dördüncü Göz seçimi
                      </span>
                    )}
                  </label>
                );
              })}
            </div>
            {errors.outcome && (
              <p role="alert" className="text-xs font-medium text-red-600">
                {errors.outcome.message}
              </p>
            )}
          </fieldset>

          <div className="flex flex-col gap-1.5">
            <label htmlFor="refereeNotes" className="text-sm font-semibold text-foreground">
              Gerekçe
            </label>
            <textarea
              id="refereeNotes"
              rows={4}
              placeholder="Puanlamanızı açıklayın ve AI analiziyle aynı fikirde olmadığınız noktaları belirtin."
              aria-invalid={errors.refereeNotes ? "true" : "false"}
              aria-describedby={errors.refereeNotes ? "refereeNotes-error" : undefined}
              {...register("refereeNotes")}
              className="resize-y rounded-lg border border-border bg-white px-3 py-2 text-sm leading-relaxed text-foreground outline-none transition focus:border-brand-500 focus:ring-2 focus:ring-brand-500/30"
            />
            {errors.refereeNotes && (
              <p id="refereeNotes-error" role="alert" className="text-xs font-medium text-red-600">
                {errors.refereeNotes.message}
              </p>
            )}
          </div>

          <div className="flex flex-wrap items-center justify-end gap-3">
            <button
              type="button"
              onClick={() => {
                // Only the AI-derived fields revert; the referee keeps their justification.
                setValue("finalScore", suggestion.score);
                setValue("outcome", suggestion.outcome);
              }}
              className="rounded-lg border border-border px-4 py-2.5 text-sm font-semibold text-muted transition hover:border-brand-300 hover:text-brand-700 focus:outline-none focus-visible:ring-2 focus-visible:ring-brand-500"
            >
              AI önerisine sıfırla
            </button>
            <button
              type="submit"
              disabled={isSubmitting || decisionAlreadySubmitted}
              className="rounded-lg bg-brand-600 px-5 py-2.5 text-sm font-semibold text-white transition hover:bg-brand-700 focus:outline-none focus-visible:ring-2 focus-visible:ring-brand-500 focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-60"
            >
              {decisionAlreadySubmitted
                ? "Karar zaten verildi"
                : isSubmitting
                  ? "Gönderiliyor…"
                  : "Nihai kararı gönder"}
            </button>
          </div>
        </form>
      </div>
    </section>
  );
}
