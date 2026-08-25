"use client";

import { useCallback, useEffect, useState } from "react";
import {
  createCompetition,
  listCategories,
  listCompetitions,
  setCompetitionCriteria,
  setCompetitionStatus,
  setCompetitionTemplate,
} from "@/lib/api";
import { describeError } from "@/lib/api/errors";
import type { WireCategory, WireCompetition } from "@/lib/api/types";
import type { CriteriaTemplateFormValues } from "@/lib/criteria-template";
import { CriteriaTemplateForm } from "./criteria-template-form";
import { RefereeAssignmentPanel } from "./referee-assignment";
import { ReportUpload } from "./report-upload";

/**
 * Yarışma Yöneticisi'nin ana çalışma alanı.
 *
 * NEDEN VAR: önceden bu panelde yalnızca hiçbir yere kaydetmeyen bir kriter
 * formu ve tek tek dosya yükleyen bir kutu vardı. "Yarışma" diye bir kavram
 * yoktu, dolayısıyla bir yönetici birden fazla yarışmayı ayrı ayrı
 * yönetemiyordu.
 */

/** Aşama etiketleri ve o aşamada ne olduğu. */
const ASAMA_BILGI: Record<string, { label: string; renk: string; aciklama: string }> = {
  draft: {
    label: "Hazırlık",
    renk: "bg-slate-100 text-slate-700 ring-border",
    aciklama: "Yarışmacılar göremez. Şablon ve kriterleri tanımlayın.",
  },
  open: {
    label: "Başvuru Açık",
    renk: "bg-emerald-50 text-emerald-700 ring-emerald-200",
    aciklama: "Yarışmacılar rapor yükleyebilir; AI analizi otomatik çalışır.",
  },
  closed: {
    label: "Başvuru Kapandı",
    renk: "bg-amber-50 text-amber-700 ring-amber-200",
    aciklama: "Yeni yükleme alınmıyor. Hakem atamalarını yapın.",
  },
  evaluating: {
    label: "Değerlendiriliyor",
    renk: "bg-brand-50 text-brand-700 ring-brand-200",
    aciklama: "Hakemler raporları inceliyor ve karar veriyor.",
  },
  completed: {
    label: "Tamamlandı",
    renk: "bg-slate-100 text-slate-700 ring-border",
    aciklama: "Sonuçlar yarışmacılara açık.",
  },
};

/** Aşamalar sırayla ilerliyor — bir sonraki adım. */
const SONRAKI_ASAMA: Record<string, string | null> = {
  draft: "open",
  open: "closed",
  closed: "evaluating",
  evaluating: "completed",
  completed: null,
};

export function CompetitionManager() {
  const [yarismalar, setYarismalar] = useState<WireCompetition[] | null>(null);
  const [kategoriler, setKategoriler] = useState<WireCategory[]>([]);
  const [seciliId, setSeciliId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [kurulumHatasi, setKurulumHatasi] = useState<string | null>(null);
  const [yeniAd, setYeniAd] = useState("");
  const [yeniKategori, setYeniKategori] = useState("");
  const [busy, setBusy] = useState(false);

  const yukle = useCallback(async () => {
    setError(null);
    try {
      const [y, k] = await Promise.all([listCompetitions(), listCategories()]);
      setYarismalar(y);
      setKategoriler(k);
      setYeniKategori((mevcut) => mevcut || k[0]?.id || "");
      setSeciliId((mevcut) => mevcut ?? y[0]?.id ?? null);
    } catch (cause) {
      setError(describeError(cause));
      setYarismalar([]);
    }
  }, []);

  useEffect(() => {
    void yukle();
  }, [yukle]);

  const secili = yarismalar?.find((y) => y.id === seciliId) ?? null;

  async function yarismaOlustur(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!yeniAd.trim() || !yeniKategori) return;
    setBusy(true);
    setError(null);
    try {
      const y = await createCompetition({ name: yeniAd.trim(), categoryId: yeniKategori });
      setYeniAd("");
      await yukle();
      setSeciliId(y.id);
    } catch (cause) {
      setError(describeError(cause));
    } finally {
      setBusy(false);
    }
  }

  /**
   * Şablon formunu kaydeder.
   *
   * Form hem kriterleri (ağırlıklarıyla) hem de zorunlu başlıkları
   * topluyor; backend'de bunlar iki ayrı uç nokta, o yüzden ikisi de
   * çağrılıyor. Biri başarısız olursa hata yüzeye çıkıyor ve form
   * sıfırlanmıyor.
   */
  async function sablonuKaydet(values: CriteriaTemplateFormValues) {
    if (!secili) return;
    setKurulumHatasi(null);
    try {
      await setCompetitionTemplate(secili.id, {
        acceptedLanguages: ["tr"],
        requiredHeadings: values.requiredHeadings.map((h) => h.value),
        minPages: null,
        maxPages: null,
        minSectionChars: null,
      });
      await setCompetitionCriteria(
        secili.id,
        values.metrics.map((m) => ({ title: m.name, weight: m.weight })),
      );
      await yukle();
    } catch (cause) {
      setKurulumHatasi(describeError(cause));
      throw cause;
    }
  }

  async function asamayiIlerlet() {
    if (!secili) return;
    const sonraki = SONRAKI_ASAMA[secili.status];
    if (!sonraki) return;
    setBusy(true);
    setError(null);
    try {
      await setCompetitionStatus(secili.id, sonraki);
      await yukle();
    } catch (cause) {
      // Backend, kurallar tanımlı değilse 'open'a geçişi reddediyor ve
      // hangi tanımın eksik olduğunu söylüyor — mesajı olduğu gibi
      // gösteriyoruz, kullanıcı ne yapacağını bilsin.
      setError(describeError(cause));
    } finally {
      setBusy(false);
    }
  }

  if (yarismalar === null) {
    return (
      <div
        data-testid="competitions-loading"
        aria-hidden="true"
        className="h-64 animate-pulse rounded-2xl border border-border bg-slate-100"
      />
    );
  }

  const asama = secili ? ASAMA_BILGI[secili.status] : null;

  return (
    <div className="flex flex-col gap-6" data-testid="competition-manager">
      {error ? (
        <div
          role="alert"
          data-testid="competition-error"
          className="rounded-xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm font-medium text-rose-700"
        >
          {error}
        </div>
      ) : null}

      {/* --- Yarışma listesi + oluşturma --- */}
      <section className="rounded-2xl border border-border bg-surface p-6 shadow-sm">
        <h2 className="text-lg font-bold text-foreground">Yarışmalarım</h2>
        <p className="mt-1 text-sm text-muted">
          Her yarışmanın kendi şablonu, kriterleri ve hakem kadrosu vardır.
        </p>

        {yarismalar.length === 0 ? (
          <p
            data-testid="no-competitions"
            className="mt-4 rounded-xl border border-dashed border-border px-4 py-6 text-center text-sm text-muted"
          >
            Henüz yarışma yok. Aşağıdan ilk yarışmanızı oluşturun.
          </p>
        ) : (
          <ul className="mt-4 flex flex-col gap-2" data-testid="competition-list">
            {yarismalar.map((y) => {
              const bilgi = ASAMA_BILGI[y.status];
              const aktif = y.id === seciliId;
              return (
                <li key={y.id}>
                  <button
                    type="button"
                    onClick={() => setSeciliId(y.id)}
                    data-testid={`competition-${y.id}`}
                    aria-current={aktif ? "true" : undefined}
                    className={`flex w-full flex-wrap items-center justify-between gap-3 rounded-xl border px-4 py-3 text-left transition ${
                      aktif
                        ? "border-brand-300 bg-brand-50/50"
                        : "border-border hover:border-brand-300"
                    }`}
                  >
                    <span className="min-w-0">
                      <span className="block truncate text-sm font-semibold text-foreground">
                        {y.name}
                      </span>
                      <span className="block text-xs text-muted">
                        {y.category_name ?? y.category_id} · {y.report_count} rapor ·{" "}
                        {y.referee_count} hakem
                      </span>
                    </span>
                    <span
                      className={`shrink-0 rounded-full px-2.5 py-0.5 text-xs font-semibold ring-1 ring-inset ${bilgi?.renk ?? ""}`}
                    >
                      {bilgi?.label ?? y.status}
                    </span>
                  </button>
                </li>
              );
            })}
          </ul>
        )}

        <form
          onSubmit={yarismaOlustur}
          data-testid="create-competition-form"
          className="mt-5 flex flex-col gap-3 border-t border-border pt-5 sm:flex-row sm:items-end"
        >
          <label className="flex flex-1 flex-col gap-1.5">
            <span className="text-xs font-semibold uppercase tracking-wide text-muted">
              Yeni yarışma adı
            </span>
            <input
              type="text"
              value={yeniAd}
              onChange={(e) => setYeniAd(e.target.value)}
              placeholder="Örn. Havacılıkta Yapay Zeka 2026"
              data-testid="new-competition-name"
              className="rounded-lg border border-border bg-background px-3 py-2 text-sm text-foreground focus:outline-none focus-visible:ring-2 focus-visible:ring-brand-500"
            />
          </label>
          <label className="flex flex-col gap-1.5 sm:w-64">
            <span className="text-xs font-semibold uppercase tracking-wide text-muted">
              Kategori
            </span>
            <select
              value={yeniKategori}
              onChange={(e) => setYeniKategori(e.target.value)}
              data-testid="new-competition-category"
              className="rounded-lg border border-border bg-background px-3 py-2 text-sm text-foreground focus:outline-none focus-visible:ring-2 focus-visible:ring-brand-500"
            >
              {kategoriler.map((k) => (
                <option key={k.id} value={k.id}>
                  {k.name}
                </option>
              ))}
            </select>
          </label>
          <button
            type="submit"
            disabled={busy || !yeniAd.trim()}
            className="rounded-lg bg-brand-600 px-4 py-2 text-sm font-semibold text-white transition hover:bg-brand-700 disabled:cursor-not-allowed disabled:opacity-60"
          >
            Oluştur
          </button>
        </form>
      </section>

      {secili && asama ? (
        <>
          {/* --- Aşama --- */}
          <section
            data-testid="competition-stage"
            className="rounded-2xl border border-border bg-surface p-6 shadow-sm"
          >
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div>
                <h2 className="text-lg font-bold text-foreground">{secili.name}</h2>
                <p className="mt-1 text-sm text-muted">{asama.aciklama}</p>
              </div>
              <div className="flex items-center gap-3">
                <span
                  className={`rounded-full px-3 py-1 text-sm font-bold ring-1 ring-inset ${asama.renk}`}
                >
                  {asama.label}
                </span>
                {SONRAKI_ASAMA[secili.status] ? (
                  <button
                    type="button"
                    onClick={() => void asamayiIlerlet()}
                    disabled={busy}
                    data-testid="advance-stage"
                    className="rounded-lg bg-brand-600 px-3 py-1.5 text-sm font-semibold text-white transition hover:bg-brand-700 disabled:opacity-60"
                  >
                    {ASAMA_BILGI[SONRAKI_ASAMA[secili.status]!]?.label}&apos;e geç
                  </button>
                ) : null}
              </div>
            </div>

            <dl className="mt-5 grid grid-cols-2 gap-4 border-t border-border pt-5 sm:grid-cols-4">
              <div>
                <dt className="text-xs font-semibold uppercase tracking-wide text-muted">
                  Zorunlu başlık
                </dt>
                <dd className="mt-1 text-sm font-semibold text-foreground">
                  {secili.required_headings.length || "—"}
                </dd>
              </div>
              <div>
                <dt className="text-xs font-semibold uppercase tracking-wide text-muted">
                  Kriter
                </dt>
                <dd className="mt-1 text-sm font-semibold text-foreground">
                  {secili.criteria.length || "—"}
                </dd>
              </div>
              <div>
                <dt className="text-xs font-semibold uppercase tracking-wide text-muted">
                  Hakem
                </dt>
                <dd className="mt-1 text-sm font-semibold text-foreground">
                  {secili.referee_count}
                </dd>
              </div>
              <div>
                <dt className="text-xs font-semibold uppercase tracking-wide text-muted">
                  Rapor
                </dt>
                <dd className="mt-1 text-sm font-semibold text-foreground">
                  {secili.report_count}
                </dd>
              </div>
            </dl>

            {secili.criteria.length > 0 ? (
              <ul className="mt-4 flex flex-wrap gap-2" data-testid="criteria-summary">
                {secili.criteria.map((k) => (
                  <li
                    key={k.id}
                    className="rounded-full border border-border px-3 py-1 text-xs text-muted"
                  >
                    {k.title} · %{k.weight}
                  </li>
                ))}
              </ul>
            ) : null}
          </section>

          {/* --- Kurulum + yükleme --- */}
          <div className="grid grid-cols-1 gap-6 xl:grid-cols-2 xl:items-start">
            {/* `key={secili.id}`: yarışma değişince bu bileşenler SIFIRDAN
                kuruluyor. Anahtarsız hâlinde React aynı örneği koruyordu ve
                A yarışması için yazılmış ama kaydedilmemiş kriterler, B
                yarışmasına geçilince formda duruyordu — kaydedildiğinde de
                B'nin kriterlerini A'nın taslağıyla değiştiriyordu. Aynı
                şekilde yükleme listesi ve arama kutusu da eski yarışmadan
                kalıyordu. */}
            <CriteriaTemplateForm
              key={`kriter-${secili.id}`}
              onSaved={sablonuKaydet}
              submitError={kurulumHatasi}
            />
            <ReportUpload
              key={`yukleme-${secili.id}`}
              competitionId={secili.id}
              onUploadComplete={() => void yukle()}
            />
          </div>

          {/* --- Hakem atama --- */}
          <RefereeAssignmentPanel
            key={`atama-${secili.id}`}
            competitionId={secili.id}
            onChanged={() => void yukle()}
          />
        </>
      ) : null}
    </div>
  );
}
