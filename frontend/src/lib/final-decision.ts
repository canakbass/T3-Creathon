import { z } from "zod";

export const DECISION_OUTCOMES = ["approve", "revise", "reject"] as const;

export type DecisionOutcome = (typeof DECISION_OUTCOMES)[number];

export const DECISION_LABELS: Record<DecisionOutcome, string> = {
  approve: "Onayla",
  revise: "Revizyon İste",
  reject: "Reddet",
};

export const DECISION_DESCRIPTIONS: Record<DecisionOutcome, string> = {
  approve: "Rapor rubriği karşılıyor ve bir sonraki tura ilerliyor.",
  revise: "Rapor umut verici ama düzeltmelerle yeniden gönderilmesi gerekiyor.",
  reject: "Rapor yarışma kriterlerini karşılamıyor.",
};

export const finalDecisionSchema = z.object({
  finalScore: z
    .number({ error: "0 ile 100 arasında bir final puanı girin" })
    .min(0, "Final puanı 0'ın altında olamaz")
    .max(100, "Final puanı 100'ü geçemez"),
  outcome: z.enum(DECISION_OUTCOMES, { error: "Bir nihai karar seçin" }),
  refereeNotes: z
    .string()
    .trim()
    .min(20, "En az 20 karakterlik bir gerekçe ekleyin")
    .max(1000, "Gerekçe en fazla 1000 karakter olabilir"),
});

/** Raw form field shape, as registered on the inputs. */
export type FinalDecisionFormInput = z.input<typeof finalDecisionSchema>;
/** Parsed shape produced on successful submit. */
export type FinalDecisionFormValues = z.output<typeof finalDecisionSchema>;

/** What the referee's final decision form hands to its `onSubmit` callback. */
export interface FinalDecisionSubmission extends FinalDecisionFormValues {
  reportId: string;
  /** True when the referee changed the score or outcome the AI 4th Eye proposed. */
  overridesAiSuggestion: boolean;
  /**
   * Denetim izi — gerekçe AI taslağından mı geldi ve hakem onu değiştirdi mi.
   *
   * Gerekçe, bir insanın raporu gerçekten incelediğinin kanıtıdır. AI taslak
   * sunabilir, ama hangi metnin AI'dan geldiği izlenebilir kalmalı: sonradan
   * itiraz olursa "bu gerekçeyi kim yazdı" sorusunun cevabı kayıtlı olsun.
   */
  rationaleAiDrafted?: boolean;
  rationaleEditedByReferee?: boolean;
}
