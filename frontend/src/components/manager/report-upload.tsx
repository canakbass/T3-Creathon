"use client";

import {
  useCallback,
  useEffect,
  useId,
  useRef,
  useState,
  type DragEvent,
  type KeyboardEvent,
} from "react";
import { listCategories, pollUntilAnalyzed, uploadReport } from "@/lib/api";
import { describeError } from "@/lib/api/errors";
import type { WireCategory } from "@/lib/api/types";

const ACCEPTED_MIME_TYPES = [
  "application/pdf",
  "application/msword",
  "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
];
const ACCEPTED_EXTENSIONS = [".pdf", ".doc", ".docx"];
const ACCEPT_ATTRIBUTE = ACCEPTED_EXTENSIONS.join(",");

/**
 * "analyzing" durumu yeni: dosya diske yazildiktan sonra analiz ARKA PLANDA
 * calisiyor ve birkac saniye suruyor. Yukleme bitti diye basari gostermek
 * yanlis olurdu - kullanici raporu acinca "Analiz devam ediyor" gorurdu.
 */
type UploadStatus = "uploading" | "analyzing" | "success" | "error";

interface UploadItem {
  id: string;
  fileName: string;
  status: UploadStatus;
  progress: number;
  errorMessage?: string;
  /** Basarili yuklemede backend'in verdigi rapor kimligi. */
  reportId?: string;
}

interface ReportUploadProps {
  /** @deprecated Sahte ilerleme kaldirildi; artik gercek yukleme yapiliyor. */
  progressIntervalMs?: number;
  /** @deprecated Sahte ilerleme kaldirildi. */
  progressStepPercent?: number;
  onUploadComplete?: (fileName: string) => void;
  /** Testlerde API cagrisini atlamak icin kategori listesini dogrudan ver. */
  initialCategories?: WireCategory[];
  /**
   * Yarismaya bagli yukleme. Verilirse kategori secimi GIZLENIYOR -
   * kategori yarismadan geliyor, kullanicinin ayrica secmesi hem
   * gereksiz hem de yanlis secme riski.
   */
  competitionId?: string;
}

function isAcceptedFile(file: File): boolean {
  if (ACCEPTED_MIME_TYPES.includes(file.type)) return true;
  const lowerName = file.name.toLowerCase();
  return ACCEPTED_EXTENSIONS.some((extension) => lowerName.endsWith(extension));
}

let idCounter = 0;
function nextId(): string {
  idCounter += 1;
  return `upload-${idCounter}`;
}

export function ReportUpload({
  onUploadComplete,
  initialCategories,
  competitionId,
}: ReportUploadProps) {
  const [isDragging, setIsDragging] = useState(false);
  const [items, setItems] = useState<UploadItem[]>([]);
  const [categories, setCategories] = useState<WireCategory[]>(initialCategories ?? []);
  const [categoryId, setCategoryId] = useState(initialCategories?.[0]?.id ?? "");
  const [projectName, setProjectName] = useState("");
  const [formError, setFormError] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const dropzoneLabelId = useId();
  const projectNameId = useId();
  const categoryFieldId = useId();
  const dragCounter = useRef(0);

  /**
   * Uçuşta olan analiz yoklamalarını bileşen sökülünce iptal eder.
   *
   * NEDEN: `pollUntilAnalyzed` iptal edilmediğinde 120 saniye boyunca her
   * 1,5 saniyede bir istek atmaya devam ediyordu — kullanıcı başka bir
   * yarışmaya geçtikten sonra bile. Hem gereksiz sunucu yükü hem de sökülmüş
   * bir bileşene `setState` çağrısı. Yarışma değişince bu bileşen zaten
   * `key` ile yeniden kuruluyor (bkz. competition-manager.tsx), yani bu
   * durum gerçek.
   */
  const iptalRef = useRef<AbortController[]>([]);
  useEffect(() => {
    const kontrolculer = iptalRef.current;
    return () => {
      kontrolculer.forEach((k) => k.abort());
    };
  }, []);

  useEffect(() => {
    if (initialCategories || competitionId) return;
    let cancelled = false;
    (async () => {
      try {
        const fetched = await listCategories();
        if (cancelled) return;
        setCategories(fetched);
        setCategoryId((current) => current || fetched[0]?.id || "");
      } catch (cause) {
        if (!cancelled) setFormError(describeError(cause));
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [initialCategories, competitionId]);

  const patchItem = useCallback((id: string, patch: Partial<UploadItem>) => {
    setItems((current) =>
      current.map((item) => (item.id === id ? { ...item, ...patch } : item)),
    );
  }, []);

  /**
   * Dosyayi GERCEKTEN backend'e gonderir.
   *
   * Onceden bu bir `setInterval` ile ilerleme cubugunu doldurup "Yuklendi"
   * yazan simulasyondu; dosya hicbir yere gitmiyordu.
   *
   * `fetch` yukleme ilerlemesi bildirmedigi icin yuzde yerine belirsiz bir
   * cubuk gosteriyoruz - sahte bir yuzde gostermek kullaniciyi yaniltir.
   */
  const performUpload = useCallback(
    async (id: string, file: File, name: string, category: string) => {
      try {
        const report = await uploadReport({
          projectName: name,
          ...(competitionId ? { competitionId } : { categoryId: category }),
          file,
        });

        // Yukleme bitti ama analiz daha yeni basladi.
        patchItem(id, { status: "analyzing", progress: 60, reportId: report.reportId });

        const kontrolcu = new AbortController();
        iptalRef.current.push(kontrolcu);
        const sonuc = await pollUntilAnalyzed(report.reportId, {
          signal: kontrolcu.signal,
        });

        // `pollUntilAnalyzed` "pending" DIŞINDAKİ ilk durumda dönüyor ve
        // "error" da bir bitiş durumu (analiz çöktü). Burası eskiden dönen
        // değere hiç bakmadan yeşil "Analiz tamamlandı" gösteriyordu; yani
        // analizi çökmüş bir rapor başarılı görünüyor, kimse yeniden
        // yüklemeyi düşünmüyor ve hakem hiç analizi olmayan bir raporla
        // karşılaşıyordu.
        if (sonuc.rawStatus === "error") {
          patchItem(id, {
            status: "error",
            progress: 0,
            errorMessage:
              "Dosya yüklendi ancak AI analizi tamamlanamadı. Belge taranmış " +
              "(görüntü) bir PDF olabilir veya metni okunamıyor olabilir. " +
              "Metin tabanlı bir PDF ile tekrar deneyin.",
          });
          return;
        }

        patchItem(id, { status: "success", progress: 100 });
        onUploadComplete?.(file.name);
      } catch (cause) {
        // İptal bir HATA değil: kullanıcı sayfadan/yarışmadan ayrıldı.
        // Sökülmüş bileşene "hata" yazmak hem anlamsız hem yanıltıcı.
        if (cause instanceof DOMException && cause.name === "AbortError") return;
        patchItem(id, {
          status: "error",
          progress: 0,
          errorMessage: describeError(cause),
        });
      }
    },
    [competitionId, onUploadComplete, patchItem],
  );

  const addFiles = useCallback(
    (fileList: FileList | File[]) => {
      const files = Array.from(fileList);
      const trimmedName = projectName.trim();

      files.forEach((file) => {
        const id = nextId();

        if (!isAcceptedFile(file)) {
          setItems((current) => [
            ...current,
            {
              id,
              fileName: file.name,
              status: "error",
              progress: 0,
              errorMessage: "Desteklenmeyen dosya türü. Bir PDF veya Word belgesi yükleyin.",
            },
          ]);
          return;
        }

        // Backend project_name ve category_id'yi ZORUNLU tutuyor; eksikse
        // istek 422 doner. Kullaniciyi sunucuya gitmeden uyariyoruz.
        if (!trimmedName || (!competitionId && !categoryId)) {
          setItems((current) => [
            ...current,
            {
              id,
              fileName: file.name,
              status: "error",
              progress: 0,
              errorMessage: !trimmedName
                ? "Önce proje adını girin."
                : "Önce bir kategori seçin.",
            },
          ]);
          return;
        }

        setItems((current) => [
          ...current,
          { id, fileName: file.name, status: "uploading", progress: 15 },
        ]);

        void performUpload(id, file, trimmedName, categoryId);
      });
    },
    [categoryId, competitionId, performUpload, projectName],
  );

  function handleDrop(event: DragEvent<HTMLDivElement>) {
    event.preventDefault();
    dragCounter.current = 0;
    setIsDragging(false);
    if (event.dataTransfer.files?.length) {
      addFiles(event.dataTransfer.files);
    }
  }

  function handleDragEnter(event: DragEvent<HTMLDivElement>) {
    event.preventDefault();
    dragCounter.current += 1;
    setIsDragging(true);
  }

  function handleDragOver(event: DragEvent<HTMLDivElement>) {
    event.preventDefault();
  }

  function handleDragLeave(event: DragEvent<HTMLDivElement>) {
    event.preventDefault();
    dragCounter.current = Math.max(0, dragCounter.current - 1);
    if (dragCounter.current === 0) setIsDragging(false);
  }

  function handleZoneKeyDown(event: KeyboardEvent<HTMLDivElement>) {
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      inputRef.current?.click();
    }
  }

  function handleInputChange(event: React.ChangeEvent<HTMLInputElement>) {
    if (event.target.files?.length) {
      addFiles(event.target.files);
    }
    event.target.value = "";
  }

  function removeItem(id: string) {
    setItems((current) => current.filter((item) => item.id !== id));
  }

  const statusLabels: Record<UploadStatus, string> = {
    uploading: "Yükleniyor",
    analyzing: "Analiz ediliyor",
    success: "Analiz tamamlandı",
    error: "Hata",
  };

  return (
    <section
      aria-labelledby={dropzoneLabelId}
      className="rounded-2xl border border-border bg-surface p-6 shadow-sm"
    >
      <div className="mb-6">
        <h2 id={dropzoneLabelId} className="text-xl font-bold text-foreground">
          Rapor Yükleme
        </h2>
        <p className="mt-1 text-sm text-muted">
          Proje adını ve kategoriyi girip PDF veya Word raporunu yükleyin. Yükleme
          tamamlandığında AI analizi otomatik başlar.
        </p>
      </div>

      {formError ? (
        <div
          role="alert"
          data-testid="upload-form-error"
          className="mb-4 rounded-xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm font-medium text-rose-700"
        >
          {formError}
        </div>
      ) : null}

      <div className="mb-5 grid grid-cols-1 gap-4 sm:grid-cols-2">
        <label htmlFor={projectNameId} className="flex flex-col gap-1.5">
          <span className="text-xs font-semibold uppercase tracking-wide text-muted">
            Proje Adı
          </span>
          <input
            id={projectNameId}
            type="text"
            value={projectName}
            onChange={(event) => setProjectName(event.target.value)}
            placeholder="Örn. İHA Nesne Tespiti"
            data-testid="upload-project-name"
            className="rounded-lg border border-border bg-background px-3 py-2 text-sm text-foreground focus:outline-none focus-visible:ring-2 focus-visible:ring-brand-500"
          />
        </label>

        {competitionId ? null : (
        <label htmlFor={categoryFieldId} className="flex flex-col gap-1.5">
          <span className="text-xs font-semibold uppercase tracking-wide text-muted">
            Kategori
          </span>
          <select
            id={categoryFieldId}
            value={categoryId}
            onChange={(event) => setCategoryId(event.target.value)}
            data-testid="upload-category"
            className="rounded-lg border border-border bg-background px-3 py-2 text-sm text-foreground focus:outline-none focus-visible:ring-2 focus-visible:ring-brand-500"
          >
            {categories.length === 0 ? <option value="">Kategoriler yükleniyor…</option> : null}
            {categories.map((category) => (
              <option key={category.id} value={category.id}>
                {category.name}
              </option>
            ))}
          </select>
        </label>
        )}
      </div>

      <div
        role="button"
        tabIndex={0}
        aria-label="Rapor dosyalarını yükleyin. Sürükleyip bırakın veya PDF ya da Word belgesi seçmek için Enter tuşuna basın."
        data-testid="upload-dropzone"
        data-dragging={isDragging}
        onClick={() => inputRef.current?.click()}
        onKeyDown={handleZoneKeyDown}
        onDrop={handleDrop}
        onDragEnter={handleDragEnter}
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        className={`flex flex-col items-center justify-center gap-2 rounded-xl border-2 border-dashed px-6 py-12 text-center transition focus:outline-none focus-visible:ring-2 focus-visible:ring-brand-500 focus-visible:ring-offset-2 ${
          isDragging
            ? "border-brand-500 bg-brand-50"
            : "border-border bg-slate-50 hover:border-brand-300 hover:bg-brand-50/40"
        }`}
      >
        <span className="flex h-11 w-11 items-center justify-center rounded-full bg-brand-100 text-brand-700">
          <svg viewBox="0 0 24 24" fill="none" className="h-5 w-5" aria-hidden="true">
            <path
              d="M12 16V4m0 0-4 4m4-4 4 4"
              stroke="currentColor"
              strokeWidth="1.5"
              strokeLinecap="round"
              strokeLinejoin="round"
            />
            <path
              d="M4 16v3a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-3"
              stroke="currentColor"
              strokeWidth="1.5"
              strokeLinecap="round"
              strokeLinejoin="round"
            />
          </svg>
        </span>
        <p className="text-sm font-semibold text-foreground">
          {isDragging
            ? "Yüklemek için dosyaları bırakın"
            : "Dosyaları buraya sürükleyip bırakın veya göz atmak için tıklayın"}
        </p>
        <p className="text-xs text-muted">Yalnızca PDF veya Word belgeleri</p>
        <input
          ref={inputRef}
          type="file"
          multiple
          accept={ACCEPT_ATTRIBUTE}
          onChange={handleInputChange}
          aria-hidden="true"
          tabIndex={-1}
          className="sr-only"
          data-testid="upload-file-input"
        />
      </div>

      {items.length > 0 && (
        <ul className="mt-5 flex flex-col gap-2.5" data-testid="upload-list" aria-label="Yüklemeler">
          {items.map((item) => (
            <li
              key={item.id}
              data-testid={`upload-item-${item.fileName}`}
              data-status={item.status}
              className="flex items-center gap-3 rounded-xl border border-border bg-white px-4 py-3"
            >
              <div className="min-w-0 flex-1">
                <div className="flex items-center justify-between gap-2">
                  <span className="truncate text-sm font-medium text-foreground">
                    {item.fileName}
                  </span>
                  {item.status === "uploading" || item.status === "analyzing" ? (
                    <span className="shrink-0 text-xs font-semibold text-muted">
                      {statusLabels[item.status]}…
                    </span>
                  ) : null}
                  {item.status === "success" && (
                    <span className="shrink-0 text-xs font-semibold text-emerald-600">
                      {statusLabels.success}
                    </span>
                  )}
                </div>

                {(item.status === "uploading" || item.status === "analyzing") && (
                  <div
                    role="progressbar"
                    aria-label={`${item.fileName} ${statusLabels[item.status].toLowerCase()}`}
                    aria-valuenow={item.progress}
                    aria-valuemin={0}
                    aria-valuemax={100}
                    className="mt-2 h-1.5 w-full overflow-hidden rounded-full bg-slate-100"
                  >
                    <div
                      className="h-full rounded-full bg-brand-600 transition-[width] duration-300"
                      style={{ width: `${item.progress}%` }}
                    />
                  </div>
                )}

                {item.status === "success" && item.reportId ? (
                  <p className="mt-1 text-xs text-muted">
                    Rapor kimliği: <span className="font-semibold">{item.reportId}</span>
                  </p>
                ) : null}

                {item.status === "error" && (
                  <p role="alert" className="mt-1 text-xs font-medium text-red-600">
                    {item.errorMessage}
                  </p>
                )}
              </div>

              <button
                type="button"
                onClick={() => removeItem(item.id)}
                aria-label={`Kaldır: ${item.fileName}`}
                className="shrink-0 rounded-md p-1.5 text-muted transition hover:bg-slate-100 hover:text-red-600 focus:outline-none focus-visible:ring-2 focus-visible:ring-brand-500"
              >
                ×
              </button>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
