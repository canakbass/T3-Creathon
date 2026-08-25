"use client";

import { useId, useState } from "react";
import { useFieldArray, useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import {
  criteriaTemplateSchema,
  RAPOR_TURU_ONERILERI,
  DEFAULT_CRITERIA_TEMPLATE_VALUES,
  type CriteriaTemplateFormInput,
  type CriteriaTemplateFormValues,
} from "@/lib/criteria-template";

interface CriteriaTemplateFormProps {
  /**
   * Şablonu kalıcı hale getirir.
   *
   * Promise DÖNEBİLİR ve dönerse `await` edilir: reddedilirse başarı bandı
   * gösterilmez ve form SIFIRLANMAZ. Önceden bu geri çağrım senkron
   * çağrılıyor, başarı ondan önce kuruluyor ve form hemen sıfırlanıyordu —
   * yani kayıt başarısız olsa bile kullanıcı hem "kaydedildi" görüyor hem
   * de girdiği her şeyi kaybediyordu.
   */
  onSaved?: (values: CriteriaTemplateFormValues) => void | Promise<void>;
  /** Dışarıdan gelen hata (örn. sunucu reddi) formun içinde gösterilir. */
  submitError?: string | null;
}

export function CriteriaTemplateForm({ onSaved, submitError }: CriteriaTemplateFormProps) {
  const [savedTemplateName, setSavedTemplateName] = useState<string | null>(null);
  const formHeadingId = useId();

  const {
    register,
    control,
    handleSubmit,
    reset,
    formState: { errors, isSubmitting },
  } = useForm<CriteriaTemplateFormInput, unknown, CriteriaTemplateFormValues>({
    resolver: zodResolver(criteriaTemplateSchema),
    defaultValues: DEFAULT_CRITERIA_TEMPLATE_VALUES,
    mode: "onSubmit",
  });

  const metricsArray = useFieldArray({ control, name: "metrics" });
  const headingsArray = useFieldArray({ control, name: "requiredHeadings" });

  const metricsError =
    errors.metrics?.root?.message ??
    (typeof errors.metrics?.message === "string" ? errors.metrics.message : undefined);
  const headingsError =
    errors.requiredHeadings?.root?.message ??
    (typeof errors.requiredHeadings?.message === "string"
      ? errors.requiredHeadings.message
      : undefined);

  async function onValid(values: CriteriaTemplateFormValues) {
    // Kayit BASARILI olduktan SONRA basari gosterip formu sifirliyoruz.
    // Reddedilirse form dolu kaliyor ki kullanici tekrar deneyebilsin.
    try {
      await onSaved?.(values);
    } catch {
      return;
    }
    setSavedTemplateName(values.reportTypeName);
    reset(DEFAULT_CRITERIA_TEMPLATE_VALUES);
  }

  return (
    <section
      aria-labelledby={formHeadingId}
      className="rounded-2xl border border-border bg-surface p-6 shadow-sm"
    >
      <div className="mb-6">
        <h2 id={formHeadingId} className="text-xl font-bold text-foreground">
          Kriter ve Şablon Tanımı
        </h2>
        <p className="mt-1 text-sm text-muted">
          Bu yarışma için hakemlerin ve AI değerlendiricisinin kullanacağı değerlendirme
          metriklerini ve zorunlu rapor başlıklarını tanımlayın.
        </p>
      </div>

      {submitError ? (
        <div
          role="alert"
          data-testid="template-error"
          className="mb-5 rounded-xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm font-medium text-rose-700"
        >
          {submitError}
        </div>
      ) : null}

      {savedTemplateName && (
        <div
          role="status"
          data-testid="template-saved-banner"
          className="mb-6 flex items-center justify-between gap-3 rounded-xl border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm font-semibold text-emerald-700"
        >
          <span>&ldquo;{savedTemplateName}&rdquo; şablonu bu yarışmaya kaydedildi.</span>
          <button
            type="button"
            onClick={() => setSavedTemplateName(null)}
            aria-label="Kaydedilen şablon mesajını kapat"
            className="rounded-md p-1 text-emerald-700 transition hover:bg-emerald-100 focus:outline-none focus-visible:ring-2 focus-visible:ring-brand-500"
          >
            ×
          </button>
        </div>
      )}

      <form
        noValidate
        onSubmit={handleSubmit(onValid)}
        data-testid="criteria-template-form"
        className="flex flex-col gap-6"
      >
        <div className="flex flex-col gap-1.5">
          <label htmlFor="reportTypeName" className="text-sm font-semibold text-foreground">
            Rapor türü
          </label>
          <input
            id="reportTypeName"
            type="text"
            list="rapor-turu-onerileri"
            placeholder="örn. Kritik Tasarım Raporu"
            aria-invalid={errors.reportTypeName ? "true" : "false"}
            aria-describedby={
              errors.reportTypeName ? "reportTypeName-error" : "reportTypeName-hint"
            }
            {...register("reportTypeName")}
            className="rounded-lg border border-border bg-white px-3 py-2 text-sm text-foreground outline-none transition focus:border-brand-500 focus:ring-2 focus:ring-brand-500/30"
          />
          <datalist id="rapor-turu-onerileri">
            {RAPOR_TURU_ONERILERI.map((t) => (
              <option key={t} value={t} />
            ))}
          </datalist>
          {errors.reportTypeName ? (
            <p id="reportTypeName-error" role="alert" className="text-xs font-medium text-red-600">
              {errors.reportTypeName.message}
            </p>
          ) : (
            <p id="reportTypeName-hint" className="text-xs text-muted">
              Bir yarışmanın birden fazla rapor aşaması olur (Ön Tasarım, Final
              Tasarım…) ve her aşamanın başlıkları ile puan ağırlıkları farklıdır.
              Bu şablonun hangi aşamaya ait olduğunu yazın.
            </p>
          )}
        </div>

        <fieldset className="flex flex-col gap-3">
          <div className="flex items-center justify-between">
            <legend className="text-sm font-semibold text-foreground">Değerlendirme metrikleri</legend>
            <button
              type="button"
              onClick={() => metricsArray.append({ name: "", weight: 0 })}
              className="rounded-lg border border-border px-3 py-1.5 text-xs font-semibold text-brand-700 transition hover:border-brand-300 hover:bg-brand-50 focus:outline-none focus-visible:ring-2 focus-visible:ring-brand-500"
            >
              + Metrik ekle
            </button>
          </div>

          <div className="flex flex-col gap-3">
            {metricsArray.fields.map((field, index) => {
              const nameError = errors.metrics?.[index]?.name?.message;
              const weightError = errors.metrics?.[index]?.weight?.message;
              return (
                <div key={field.id} className="flex items-start gap-2">
                  <div className="flex flex-1 flex-col gap-1">
                    <label htmlFor={`metrics.${index}.name`} className="sr-only">
                      Metrik {index + 1} adı
                    </label>
                    <input
                      id={`metrics.${index}.name`}
                      type="text"
                      placeholder="örn. Teknik uygulanabilirlik"
                      aria-invalid={nameError ? "true" : "false"}
                      aria-describedby={nameError ? `metrics.${index}.name-error` : undefined}
                      {...register(`metrics.${index}.name` as const)}
                      className="w-full rounded-lg border border-border bg-white px-3 py-2 text-sm text-foreground outline-none transition focus:border-brand-500 focus:ring-2 focus:ring-brand-500/30"
                    />
                    {nameError && (
                      <p
                        id={`metrics.${index}.name-error`}
                        role="alert"
                        className="text-xs font-medium text-red-600"
                      >
                        {nameError}
                      </p>
                    )}
                  </div>

                  <div className="flex w-28 flex-col gap-1">
                    <label htmlFor={`metrics.${index}.weight`} className="sr-only">
                      Metrik {index + 1} ağırlık yüzdesi
                    </label>
                    <div className="relative">
                      <input
                        id={`metrics.${index}.weight`}
                        type="number"
                        inputMode="numeric"
                        placeholder="0"
                        aria-invalid={weightError ? "true" : "false"}
                        aria-describedby={
                          weightError ? `metrics.${index}.weight-error` : undefined
                        }
                        {...register(`metrics.${index}.weight` as const)}
                        className="w-full rounded-lg border border-border bg-white px-3 py-2 pr-7 text-sm text-foreground outline-none transition focus:border-brand-500 focus:ring-2 focus:ring-brand-500/30"
                      />
                      <span className="pointer-events-none absolute right-2.5 top-1/2 -translate-y-1/2 text-xs text-muted">
                        %
                      </span>
                    </div>
                    {weightError && (
                      <p
                        id={`metrics.${index}.weight-error`}
                        role="alert"
                        className="text-xs font-medium text-red-600"
                      >
                        {weightError}
                      </p>
                    )}
                  </div>

                  <button
                    type="button"
                    onClick={() => metricsArray.remove(index)}
                    disabled={metricsArray.fields.length === 1}
                    aria-label={`Metrik ${index + 1} kaldır`}
                    className="mt-0.5 rounded-lg border border-border px-2.5 py-2 text-xs font-semibold text-muted transition hover:border-red-300 hover:text-red-600 disabled:cursor-not-allowed disabled:opacity-40 disabled:hover:border-border disabled:hover:text-muted"
                  >
                    Kaldır
                  </button>
                </div>
              );
            })}
          </div>

          {metricsError && (
            <p role="alert" className="text-xs font-medium text-red-600">
              {metricsError}
            </p>
          )}
        </fieldset>

        <fieldset className="flex flex-col gap-3">
          <div className="flex items-center justify-between">
            <legend className="text-sm font-semibold text-foreground">Zorunlu başlıklar</legend>
            <button
              type="button"
              onClick={() => headingsArray.append({ value: "" })}
              className="rounded-lg border border-border px-3 py-1.5 text-xs font-semibold text-brand-700 transition hover:border-brand-300 hover:bg-brand-50 focus:outline-none focus-visible:ring-2 focus-visible:ring-brand-500"
            >
              + Başlık ekle
            </button>
          </div>

          <div className="flex flex-col gap-3">
            {headingsArray.fields.map((field, index) => {
              const headingError = errors.requiredHeadings?.[index]?.value?.message;
              return (
                <div key={field.id} className="flex items-start gap-2">
                  <div className="flex flex-1 flex-col gap-1">
                    <label htmlFor={`requiredHeadings.${index}.value`} className="sr-only">
                      Zorunlu başlık {index + 1}
                    </label>
                    <input
                      id={`requiredHeadings.${index}.value`}
                      type="text"
                      placeholder="örn. Yöntem"
                      aria-invalid={headingError ? "true" : "false"}
                      aria-describedby={
                        headingError ? `requiredHeadings.${index}.value-error` : undefined
                      }
                      {...register(`requiredHeadings.${index}.value` as const)}
                      className="w-full rounded-lg border border-border bg-white px-3 py-2 text-sm text-foreground outline-none transition focus:border-brand-500 focus:ring-2 focus:ring-brand-500/30"
                    />
                    {headingError && (
                      <p
                        id={`requiredHeadings.${index}.value-error`}
                        role="alert"
                        className="text-xs font-medium text-red-600"
                      >
                        {headingError}
                      </p>
                    )}
                  </div>

                  <button
                    type="button"
                    onClick={() => headingsArray.remove(index)}
                    disabled={headingsArray.fields.length === 1}
                    aria-label={`Zorunlu başlık ${index + 1} kaldır`}
                    className="mt-0.5 rounded-lg border border-border px-2.5 py-2 text-xs font-semibold text-muted transition hover:border-red-300 hover:text-red-600 disabled:cursor-not-allowed disabled:opacity-40 disabled:hover:border-border disabled:hover:text-muted"
                  >
                    Kaldır
                  </button>
                </div>
              );
            })}
          </div>

          {headingsError && (
            <p role="alert" className="text-xs font-medium text-red-600">
              {headingsError}
            </p>
          )}
        </fieldset>

        <div className="flex justify-end">
          <button
            type="submit"
            disabled={isSubmitting}
            className="rounded-lg bg-brand-600 px-5 py-2.5 text-sm font-semibold text-white transition hover:bg-brand-700 focus:outline-none focus-visible:ring-2 focus-visible:ring-brand-500 focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-60"
          >
            Şablonu kaydet
          </button>
        </div>
      </form>
    </section>
  );
}
