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
import { cozumle, epostaGecerliMi, epostalariAyikla } from "@/lib/dosya-adi";
import type { WireCategory } from "@/lib/api/types";

const ACCEPTED_MIME_TYPES = [
  "application/pdf",
  "application/msword",
  "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
];
const ACCEPTED_EXTENSIONS = [".pdf", ".doc", ".docx"];
const ACCEPT_ATTRIBUTE = ACCEPTED_EXTENSIONS.join(",");

/**
 * Rapor aktarımı — TAKIM DOSYA ADINDAN çıkarılır.
 *
 * KULLANICININ ŞİKAYETİ: ekran "takım kimliği" istiyordu ve bu, yöneticinin
 * elinde OLMAYAN bir bilgiydi. Elinde gerçekten olan şey teslim edilen
 * dosyalar ve onları kimin gönderdiği. Kendi önerisi:
 * `232805068@ogr.cbu.edu.tr_canakbasforspecial@gmail.com.pdf` = iki kişilik
 * takım.
 *
 * NEDEN İKİ AŞAMALI (önce hazırla, sonra aktar): çıkarım SEZGİSEL. Dosya
 * adındaki bir harf hatası, doğrulamayı geçen YABANCI birine o takımın tüm
 * sonuçlarını verirdi — doğrulama "bu kutunun sahibi misin" sorusunu
 * cevaplar, "bu kişi bu takımda mı" sorusunu cevaplamaz. O soruyu yalnızca
 * yönetici cevaplayabilir, o yüzden gördüğünü ONAYLAMADAN hiçbir şey
 * gönderilmiyor.
 */
type UploadStatus = "hazir" | "uploading" | "analyzing" | "success" | "error";

interface UploadItem {
  id: string;
  file: File | null;
  fileName: string;
  status: UploadStatus;
  progress: number;
  errorMessage?: string;
  reportId?: string;
  /** Onaylanacak takım üyeleri — serbest metin, kullanıcı düzenleyebilir. */
  emails: string;
  projectName: string;
  /** Ayrıştırıcının belirsizlik notları (örn. yerel kısım tahmini). */
  notes: string[];
}

interface ReportUploadProps {
  /** @deprecated Sahte ilerleme kaldırıldı; artık gerçek yükleme yapılıyor. */
  progressIntervalMs?: number;
  /** @deprecated Sahte ilerleme kaldırıldı. */
  progressStepPercent?: number;
  onUploadComplete?: (fileName: string) => void;
  /** Testlerde API çağrısını atlamak için kategori listesini doğrudan ver. */
  initialCategories?: WireCategory[];
  /**
   * Yarışmaya bağlı yükleme. Verilirse kategori seçimi GİZLENİYOR —
   * kategori yarışmadan geliyor, kullanıcının ayrıca seçmesi hem gereksiz
   * hem de yanlış seçme riski.
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
  const [formError, setFormError] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const dropzoneLabelId = useId();
  const categoryFieldId = useId();
  const dragCounter = useRef(0);

  /**
   * Uçuşta olan analiz yoklamalarını bileşen sökülünce iptal eder.
   *
   * NEDEN: `pollUntilAnalyzed` iptal edilmediğinde 120 saniye boyunca her
   * 1,5 saniyede bir istek atmaya devam ediyordu — kullanıcı başka bir
   * yarışmaya geçtikten sonra bile.
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

  /** Dosyaları HAZIR listesine ekler — henüz hiçbir şey gönderilmez. */
  const addFiles = useCallback((fileList: FileList | File[]) => {
    const files = Array.from(fileList);
    setFormError(null);

    files.forEach((file) => {
      const id = nextId();

      if (!isAcceptedFile(file)) {
        setItems((current) => [
          ...current,
          {
            id,
            file: null,
            fileName: file.name,
            status: "error",
            progress: 0,
            emails: "",
            projectName: "",
            notes: [],
            errorMessage: "Desteklenmeyen dosya türü. Bir PDF veya Word belgesi yükleyin.",
          },
        ]);
        return;
      }

      const cozum = cozumle(file.name);
      setItems((current) => [
        ...current,
        {
          id,
          file,
          fileName: file.name,
          // Ayrıştırıcı hata verdiyse (NUL karakteri, 300 karakterlik ad,
          // 10'dan fazla adres) SESSİZCE kırpmıyoruz — kullanıcı neyi
          // düzelteceğini bilmeli.
          status: cozum.hata ? "error" : "hazir",
          errorMessage: cozum.hata ?? undefined,
          progress: 0,
          emails: cozum.epostalar.join(", "),
          projectName: cozum.projeAdi ?? "",
          notes: cozum.uyarilar,
        },
      ]);
    });
  }, []);

  const performUpload = useCallback(
    async (item: UploadItem) => {
      if (!item.file) return;
      const id = item.id;
      try {
        patchItem(id, { status: "uploading", progress: 15, errorMessage: undefined });
        const report = await uploadReport({
          projectName: item.projectName,
          memberEmails: epostalariAyikla(item.emails),
          ...(competitionId ? { competitionId } : { categoryId }),
          file: item.file,
        });

        patchItem(id, { status: "analyzing", progress: 60, reportId: report.reportId });

        const kontrolcu = new AbortController();
        iptalRef.current.push(kontrolcu);
        const sonuc = await pollUntilAnalyzed(report.reportId, {
          signal: kontrolcu.signal,
        });

        // `pollUntilAnalyzed` "pending" DIŞINDAKİ ilk durumda dönüyor ve
        // "error" da bir bitiş durumu. Dönen değere bakmasaydık analizi
        // çökmüş bir rapor başarılı görünür, kimse yeniden yüklemeyi
        // düşünmez ve hakem hiç analizi olmayan bir raporla karşılaşırdı.
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
        onUploadComplete?.(item.fileName);
      } catch (cause) {
        // İptal bir HATA değil: kullanıcı sayfadan/yarışmadan ayrıldı.
        if (cause instanceof DOMException && cause.name === "AbortError") return;
        patchItem(id, {
          status: "error",
          progress: 0,
          errorMessage: describeError(cause),
        });
      }
    },
    [categoryId, competitionId, onUploadComplete, patchItem],
  );

  /** Bir satır aktarılabilir mi: dosyası var, e-postası geçerli. */
  function hazirMi(item: UploadItem): boolean {
    if (item.status !== "hazir" || !item.file) return false;
    const adresler = epostalariAyikla(item.emails);
    return adresler.length > 0 && adresler.every(epostaGecerliMi);
  }

  function satirSorunu(item: UploadItem): string | null {
    if (item.status !== "hazir") return null;
    const adresler = epostalariAyikla(item.emails);
    if (adresler.length === 0) {
      return "Bu dosyanın adında e-posta yok. Raporu teslim eden kişilerin adreslerini yazın.";
    }
    const bozuk = adresler.filter((a) => !epostaGecerliMi(a));
    if (bozuk.length) return `Geçerli bir e-posta değil: ${bozuk.join(", ")}`;
    return null;
  }

  const hazirlar = items.filter(hazirMi);

  function hepsiniAktar() {
    if (!competitionId && !categoryId) {
      setFormError("Önce bir kategori seçin.");
      return;
    }
    hazirlar.forEach((item) => void performUpload(item));
  }

  function handleDrop(event: DragEvent<HTMLDivElement>) {
    event.preventDefault();
    dragCounter.current = 0;
    setIsDragging(false);
    if (event.dataTransfer.files?.length) addFiles(event.dataTransfer.files);
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
    if (event.target.files?.length) addFiles(event.target.files);
    event.target.value = "";
  }

  function removeItem(id: string) {
    setItems((current) => current.filter((item) => item.id !== id));
  }

  const statusLabels: Record<UploadStatus, string> = {
    hazir: "Aktarıma hazır",
    uploading: "Yükleniyor",
    analyzing: "Analiz ediliyor",
    success: "Analiz tamamlandı",
    error: "Hata",
  };

  return (
    <section className="rounded-2xl border border-border bg-surface p-6 shadow-sm">
      <h2 className="text-lg font-bold text-foreground">Rapor Aktarımı</h2>
      <p className="mt-1 text-sm text-muted">
        Dosyaları bırakın; takım, dosya adındaki e-postalardan çıkarılır. Örnek:{" "}
        <code className="rounded bg-slate-100 px-1 py-0.5 text-xs">
          ogrenci@okul.edu.tr_arkadas@okul.edu.tr.pdf
        </code>
      </p>
      <p className="mt-1 text-xs text-muted">
        Dosya adında e-posta yoksa aşağıda elle yazabilirsiniz. Aktarmadan önce
        her satırı kontrol edin — sonucu kimin göreceğini bu adresler belirliyor.
      </p>

      {formError ? (
        <p
          role="alert"
          data-testid="upload-form-error"
          className="mt-4 rounded-lg border border-rose-200 bg-rose-50 px-3 py-2 text-sm text-rose-700"
        >
          {formError}
        </p>
      ) : null}

      {!competitionId ? (
        <label htmlFor={categoryFieldId} className="mt-4 flex flex-col gap-1.5">
          <span className="text-xs font-semibold uppercase tracking-wide text-muted">
            Kategori
          </span>
          <select
            id={categoryFieldId}
            value={categoryId}
            onChange={(e) => setCategoryId(e.target.value)}
            data-testid="upload-category"
            className="rounded-lg border border-border bg-background px-3 py-2 text-sm text-foreground"
          >
            <option value="">Seçin…</option>
            {categories.map((category) => (
              <option key={category.id} value={category.id}>
                {category.name}
              </option>
            ))}
          </select>
        </label>
      ) : null}

      <div
        role="button"
        tabIndex={0}
        aria-labelledby={dropzoneLabelId}
        onClick={() => inputRef.current?.click()}
        onKeyDown={handleZoneKeyDown}
        onDrop={handleDrop}
        onDragEnter={handleDragEnter}
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        data-testid="upload-dropzone"
        className={`mt-4 flex cursor-pointer flex-col items-center justify-center gap-3 rounded-2xl border-2 border-dashed px-6 py-12 text-center transition ${
          isDragging
            ? "border-brand-500 bg-brand-50"
            : "border-border bg-background hover:border-brand-300"
        }`}
      >
        <span className="flex h-12 w-12 items-center justify-center rounded-full bg-brand-50 text-brand-600">
          <svg viewBox="0 0 24 24" fill="none" className="h-6 w-6" aria-hidden="true">
            <path
              d="M12 16V4m0 0 4 4m-4-4-4 4M4 16v2a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-2"
              stroke="currentColor"
              strokeWidth="2"
              strokeLinecap="round"
              strokeLinejoin="round"
            />
          </svg>
        </span>
        <span id={dropzoneLabelId} className="text-sm font-semibold text-foreground">
          Dosyaları buraya sürükleyip bırakın veya göz atmak için tıklayın
        </span>
        <span className="text-xs text-muted">Yalnızca PDF veya Word belgeleri</span>
        <input
          ref={inputRef}
          type="file"
          multiple
          accept={ACCEPT_ATTRIBUTE}
          onChange={handleInputChange}
          onClick={(e) => e.stopPropagation()}
          data-testid="upload-input"
          className="hidden"
        />
      </div>

      {items.length > 0 ? (
        <ul className="mt-5 flex flex-col gap-3">
          {items.map((item) => {
            const sorun = satirSorunu(item);
            return (
              <li
                key={item.id}
                data-testid={`upload-item-${item.fileName}`}
                data-status={item.status}
                className="rounded-xl border border-border px-4 py-3"
              >
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <span className="text-sm font-semibold text-foreground">
                    {item.fileName}
                  </span>
                  <div className="flex items-center gap-3">
                    <span className="text-xs text-muted">{statusLabels[item.status]}</span>
                    <button
                      type="button"
                      onClick={() => removeItem(item.id)}
                      aria-label={`${item.fileName} dosyasını listeden çıkar`}
                      className="text-muted transition hover:text-rose-600"
                    >
                      ✕
                    </button>
                  </div>
                </div>

                {item.status === "hazir" ? (
                  <div className="mt-3 flex flex-col gap-2">
                    <label className="flex flex-col gap-1 text-xs text-muted">
                      Takım üyeleri (e-posta)
                      <input
                        value={item.emails}
                        onChange={(e) => patchItem(item.id, { emails: e.target.value })}
                        placeholder="ogrenci@okul.edu.tr, arkadas@okul.edu.tr"
                        data-testid={`upload-emails-${item.fileName}`}
                        aria-label={`${item.fileName} takım üyeleri`}
                        className="rounded-lg border border-border bg-background px-3 py-1.5 font-mono text-sm text-foreground"
                      />
                    </label>
                    <label className="flex flex-col gap-1 text-xs text-muted">
                      Proje adı (isteğe bağlı)
                      <input
                        value={item.projectName}
                        onChange={(e) =>
                          patchItem(item.id, { projectName: e.target.value })
                        }
                        placeholder="Boş bırakırsanız dosya adından alınır"
                        data-testid={`upload-project-${item.fileName}`}
                        aria-label={`${item.fileName} proje adı`}
                        className="rounded-lg border border-border bg-background px-3 py-1.5 text-sm text-foreground"
                      />
                    </label>

                    {/* Ayrıştırıcının belirsizlik notları. Sessizce yutmak,
                        yöneticinin yanlış bir takımı onaylaması demekti. */}
                    {item.notes.map((not, sira) => (
                      <p
                        key={`${sira}-${not}`}
                        data-testid={`upload-note-${item.fileName}`}
                        className="rounded-lg border border-amber-200 bg-amber-50 px-3 py-1.5 text-xs text-amber-900"
                      >
                        {not}
                      </p>
                    ))}

                    {sorun ? (
                      <p
                        data-testid={`upload-issue-${item.fileName}`}
                        className="text-xs font-medium text-rose-700"
                      >
                        {sorun}
                      </p>
                    ) : null}
                  </div>
                ) : null}

                {item.status === "uploading" || item.status === "analyzing" ? (
                  <div className="mt-3 h-1.5 overflow-hidden rounded-full bg-slate-100">
                    <div
                      className="h-full rounded-full bg-brand-500 transition-all"
                      style={{ width: `${item.progress}%` }}
                    />
                  </div>
                ) : null}

                {item.errorMessage ? (
                  <p className="mt-2 text-xs font-medium text-rose-700">
                    {item.errorMessage}
                  </p>
                ) : null}
              </li>
            );
          })}
        </ul>
      ) : null}

      {items.some((i) => i.status === "hazir") ? (
        <div className="mt-5 flex flex-wrap items-center justify-between gap-3">
          <p className="text-xs text-muted">
            {hazirlar.length} dosya aktarıma hazır
            {items.filter((i) => i.status === "hazir").length - hazirlar.length > 0
              ? ` · ${
                  items.filter((i) => i.status === "hazir").length - hazirlar.length
                } dosya için e-posta gerekiyor`
              : ""}
          </p>
          <button
            type="button"
            onClick={hepsiniAktar}
            disabled={hazirlar.length === 0}
            data-testid="upload-submit"
            className="rounded-lg bg-brand-600 px-4 py-2 text-sm font-semibold text-white transition hover:bg-brand-700 disabled:cursor-not-allowed disabled:opacity-60"
          >
            {hazirlar.length > 0 ? `${hazirlar.length} raporu aktar` : "Aktar"}
          </button>
        </div>
      ) : null}
    </section>
  );
}
