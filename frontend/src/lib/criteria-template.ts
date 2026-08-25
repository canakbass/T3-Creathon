import { z } from "zod";

/**
 * Yarışmanın rapor türü (aşaması) için hazır öneriler.
 *
 * NEDEN LİSTE DEĞİL DE ÖNERİ: TEKNOFEST rapor terminolojisini yıldan yıla
 * değiştiriyor — 2022'de "Kritik Tasarım Raporu (KTR)" olan aşama 2026
 * teknik şartnamesinde "Final Tasarım Raporu (FTR)" adını almış. Sabit bir
 * enum, bir sonraki sezon yanlış olurdu; bu yüzden serbest metin alanına
 * yalnızca `datalist` önerisi olarak veriliyor.
 */
export const RAPOR_TURU_ONERILERI = [
  "Ön Tasarım Raporu",
  "Kritik Tasarım Raporu",
  "Final Tasarım Raporu",
  "Proje Detay Raporu",
] as const;

export const criteriaTemplateSchema = z
  .object({
    /**
     * Bu şablonun hangi rapor aşamasına ait olduğu.
     *
     * NEDEN VAR: bir TEKNOFEST yarışmasının TEK şablonu yok. 2026 Havacılıkta
     * YZ teknik şartnamesi madde 5: "Yarışmacı takımlardan iki ayrı doküman
     * yazmaları beklenmektedir" — Ön Tasarım Raporu ve Final Tasarım Raporu,
     * şablonları farklı tarihlerde yayımlanıyor ve puan ağırlıkları da
     * farklı (bkz. sample_reports/.../Puan_Rubrigi.md: aynı yarışmanın ÖTR ve
     * KTR ağırlıkları birbirini tutmuyor). Bu alan, tanımlanan şablonun hangi
     * aşamaya ait olduğunu kayda geçiriyor.
     *
     * Önceki adı `templateName`'di ve girilen değer HİÇBİR YERE kaydedilmiyordu.
     */
    reportTypeName: z
      .string()
      .trim()
      .min(3, "Rapor türü en az 3 karakter olmalı")
      .max(80, "Rapor türü en fazla 80 karakter olabilir"),
    metrics: z
      .array(
        z.object({
          name: z.string().trim().min(2, "Metrik adı en az 2 karakter olmalı"),
          weight: z.coerce
            .number({ error: "Geçerli bir ağırlık girin" })
            .min(1, "Ağırlık en az 1 olmalı")
            .max(100, "Ağırlık 100'ü geçemez"),
        }),
      )
      .min(1, "En az bir değerlendirme metriği ekleyin"),
    requiredHeadings: z
      .array(
        z.object({
          value: z.string().trim().min(2, "Başlık en az 2 karakter olmalı"),
        }),
      )
      .min(1, "En az bir zorunlu başlık ekleyin"),
  })
  .superRefine((data, ctx) => {
    const total = data.metrics.reduce((sum, metric) => sum + metric.weight, 0);
    if (total !== 100) {
      ctx.addIssue({
        code: "custom",
        message: `Metrik ağırlıkları toplamda %100 olmalı (şu anda %${total})`,
        path: ["metrics"],
      });
    }
  });

/** Raw form field shape, as entered (weight may be a string before coercion). */
export type CriteriaTemplateFormInput = z.input<typeof criteriaTemplateSchema>;
/** Parsed/coerced shape produced on successful submit. */
export type CriteriaTemplateFormValues = z.output<typeof criteriaTemplateSchema>;

export const DEFAULT_CRITERIA_TEMPLATE_VALUES = {
  reportTypeName: "",
  metrics: [{ name: "", weight: 100 }],
  requiredHeadings: [{ value: "" }],
} as unknown as CriteriaTemplateFormInput;
