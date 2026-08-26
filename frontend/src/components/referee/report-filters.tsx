"use client";

import { useEffect, useState } from "react";
import { listCompetitions, type ListReportsFilters } from "@/lib/api";
import type { WireCompetition } from "@/lib/api/types";

/**
 * Rapor listesi filtreleri.
 *
 * Filtre YETKİNİN YERİNE GEÇMEZ, üstüne biner — daraltır, genişletmez.
 * Hakem bir yarışma seçerek kendisine atanmamış raporları göremez; backend
 * yetki filtresini her hâlükârda uyguluyor.
 *
 * Neden bu üç filtre: yöneticinin/hakemin gerçekte sorduğu üç soru bunlar —
 * "hangi değerlendirme?", "hangi seviye?", "elimde ne kaldı?".
 */

interface Props {
  value: ListReportsFilters;
  onChange: (f: ListReportsFilters) => void;
  /** Testlerde ağ çağrısını atlamak için. */
  initialCompetitions?: WireCompetition[];
}

export function ReportFilters({ value, onChange, initialCompetitions }: Props) {
  const [yarismalar, setYarismalar] = useState<WireCompetition[]>(
    initialCompetitions ?? [],
  );
  const [acik, setAcik] = useState(false);

  useEffect(() => {
    if (initialCompetitions) return;
    let iptal = false;
    (async () => {
      try {
        const y = await listCompetitions();
        if (!iptal) setYarismalar(y);
      } catch {
        // Yarışma listesi alınamazsa filtre paneli yine çalışmalı; yalnızca
        // yarışma seçeneği boş kalır. Hata göstermeye değmez - bu ikincil
        // bir kolaylık, ana liste zaten yükleniyor.
      }
    })();
    return () => {
      iptal = true;
    };
  }, [initialCompetitions]);

  // Kategori etiketleri yarışmalardan türetiliyor: ayrı bir uç nokta
  // gerekmiyor ve liste her zaman gerçekte KULLANILAN etiketleri gösteriyor.
  const etiketler = Array.from(
    new Set(yarismalar.map((y) => y.category_label).filter(Boolean) as string[]),
  ).sort((a, b) => a.localeCompare(b, "tr"));

  const aktifSayisi = [
    value.competitionId,
    value.categoryLabel,
    value.undecided ? "1" : "",
    value.activeOnly ? "1" : "",
  ].filter(Boolean).length;

  function guncelle(yama: Partial<ListReportsFilters>) {
    onChange({ ...value, ...yama });
  }

  return (
    <div data-testid="report-filters" className="flex flex-col gap-2">
      <div className="flex flex-wrap items-center gap-2">
        <button
          type="button"
          onClick={() => setAcik((a) => !a)}
          aria-expanded={acik}
          data-testid="filters-toggle"
          className="flex items-center gap-2 rounded-lg border border-border bg-surface px-3 py-1.5 text-sm font-semibold text-muted transition hover:border-brand-300 hover:text-brand-700"
        >
          Filtrele
          {aktifSayisi > 0 ? (
            <span
              data-testid="filters-count"
              className="rounded-full bg-brand-600 px-1.5 text-xs font-bold text-white"
            >
              {aktifSayisi}
            </span>
          ) : null}
        </button>

        {aktifSayisi > 0 ? (
          <button
            type="button"
            onClick={() => onChange({})}
            data-testid="filters-clear"
            className="text-xs font-semibold text-muted underline underline-offset-2 hover:text-brand-700"
          >
            Filtreleri temizle
          </button>
        ) : null}
      </div>

      {acik ? (
        <div
          data-testid="filters-panel"
          className="flex flex-wrap items-end gap-3 rounded-xl border border-border bg-surface px-4 py-3"
        >
          <label className="flex flex-col gap-1 text-xs text-muted">
            Değerlendirme
            <select
              value={value.competitionId ?? ""}
              onChange={(e) => guncelle({ competitionId: e.target.value || undefined })}
              data-testid="filter-competition"
              aria-label="Değerlendirme"
              className="rounded-lg border border-border bg-background px-2 py-1.5 text-sm text-foreground"
            >
              <option value="">Hepsi</option>
              {yarismalar.map((y) => (
                <option key={y.id} value={y.id}>
                  {y.name}
                  {y.category_label ? ` · ${y.category_label}` : ""}
                </option>
              ))}
            </select>
          </label>

          <label className="flex flex-col gap-1 text-xs text-muted">
            Kategori / seviye
            <select
              value={value.categoryLabel ?? ""}
              onChange={(e) => guncelle({ categoryLabel: e.target.value || undefined })}
              data-testid="filter-category"
              aria-label="Kategori / seviye"
              className="rounded-lg border border-border bg-background px-2 py-1.5 text-sm text-foreground"
            >
              <option value="">Hepsi</option>
              {etiketler.map((e) => (
                <option key={e} value={e}>
                  {e}
                </option>
              ))}
            </select>
          </label>

          <label className="flex items-center gap-2 text-xs text-muted">
            <input
              type="checkbox"
              checked={Boolean(value.undecided)}
              onChange={(e) => guncelle({ undecided: e.target.checked || undefined })}
              data-testid="filter-undecided"
              className="h-4 w-4 rounded border-border"
            />
            Değerlendirilmemiş
          </label>

          <label className="flex items-center gap-2 text-xs text-muted">
            <input
              type="checkbox"
              checked={Boolean(value.activeOnly)}
              onChange={(e) => guncelle({ activeOnly: e.target.checked || undefined })}
              data-testid="filter-active"
              className="h-4 w-4 rounded border-border"
            />
            Yalnızca süren değerlendirmeler
          </label>
        </div>
      ) : null}
    </div>
  );
}
