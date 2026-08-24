import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ReportUpload } from "./report-upload";

/**
 * Bu bilesen artik GERCEK yukleme yapiyor. Onceden `setInterval` ile
 * ilerleme cubugunu dolduran bir simulasyondu ve dosya hicbir yere
 * gitmiyordu; testler de o simulasyonu (sahte zamanlayicilarla yuzde
 * artislarini) sozlesme gibi kilitliyordu.
 *
 * Kategoriler `initialCategories` ile veriliyor ki testler API cagrisina
 * bagli olmasin.
 */
const CATEGORIES = [
  { id: "cat-2", name: "Yapay Zeka ve Makine Öğrenmesi", description: null },
  { id: "cat-1", name: "Robotik ve Otomasyon", description: null },
];

function makeFile(name: string, type: string): File {
  return new File(["dummy content"], name, { type });
}

function dropFiles(dropzone: HTMLElement, files: File[]) {
  const dataTransfer = {
    files,
    items: files.map((file) => ({ kind: "file", type: file.type, getAsFile: () => file })),
    types: ["Files"],
  };

  return act(async () => {
    const { fireEvent } = await import("@testing-library/react");
    fireEvent.dragEnter(dropzone, { dataTransfer });
    fireEvent.drop(dropzone, { dataTransfer });
  });
}

function jsonResponse(status: number, payload: unknown) {
  return { ok: status >= 200 && status < 300, status, json: async () => payload };
}

/** upload -> get(report) zincirini karsilayan fetch taklidi. */
function mockUploadFetch(options: { analyzed?: boolean; uploadStatus?: number } = {}) {
  const { analyzed = true, uploadStatus = 201 } = options;
  const reportBody = {
    id: "RPT-2026-ABC123",
    project_name: "İHA Nesne Tespiti",
    category_id: "cat-2",
    status: analyzed ? "analyzed" : "pending",
    file_path: "uploads/RPT-2026-ABC123.pdf",
    submitted_by_id: "user-1",
    submission_date: "2026-08-24T10:00:00",
    ai_analysis: null,
    final_decision: null,
  };

  const fetchMock = jest.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    void init;
    const url = String(input);
    if (url.includes("/api/categories")) return jsonResponse(200, CATEGORIES);
    if (url.includes("/api/reports/upload")) {
      if (uploadStatus !== 201) {
        return jsonResponse(uploadStatus, { detail: "Category not found." });
      }
      return jsonResponse(201, reportBody);
    }
    if (url.includes("/api/reports/")) return jsonResponse(200, reportBody);
    throw new Error(`Beklenmeyen istek: ${url}`);
  });

  global.fetch = fetchMock as unknown as typeof fetch;
  return fetchMock;
}

async function fillProjectName(user: ReturnType<typeof userEvent.setup>, name: string) {
  await user.type(screen.getByTestId("upload-project-name"), name);
}

describe("ReportUpload", () => {
  const originalFetch = global.fetch;

  afterEach(() => {
    global.fetch = originalFetch;
    jest.useRealTimers();
  });

  it("renders an accessible dropzone with no uploads initially", () => {
    render(<ReportUpload initialCategories={CATEGORIES} />);

    expect(
      screen.getByRole("button", { name: /rapor dosyalarını yükleyin/i }),
    ).toBeInTheDocument();
    expect(screen.queryByTestId("upload-list")).not.toBeInTheDocument();
  });

  it("shows a dragging visual state on drag enter and clears it on drop", async () => {
    render(<ReportUpload initialCategories={CATEGORIES} />);
    const dropzone = screen.getByTestId("upload-dropzone");
    const file = makeFile("evaluation-report.pdf", "application/pdf");

    const { fireEvent } = await import("@testing-library/react");
    const dataTransfer = { files: [file], items: [], types: ["Files"] };

    act(() => {
      fireEvent.dragEnter(dropzone, { dataTransfer });
    });
    expect(dropzone).toHaveAttribute("data-dragging", "true");

    act(() => {
      fireEvent.drop(dropzone, { dataTransfer });
    });
    expect(dropzone).toHaveAttribute("data-dragging", "false");
  });

  it("posts the file to the backend and reports success once the analysis finishes", async () => {
    const fetchMock = mockUploadFetch();
    const onUploadComplete = jest.fn();
    const user = userEvent.setup();

    render(
      <ReportUpload initialCategories={CATEGORIES} onUploadComplete={onUploadComplete} />,
    );

    await fillProjectName(user, "İHA Nesne Tespiti");
    await dropFiles(screen.getByTestId("upload-dropzone"), [
      makeFile("evaluation-report.pdf", "application/pdf"),
    ]);

    const item = screen.getByTestId("upload-item-evaluation-report.pdf");
    await waitFor(() => expect(item).toHaveAttribute("data-status", "success"));

    expect(onUploadComplete).toHaveBeenCalledWith("evaluation-report.pdf");
    expect(screen.getByText(/analiz tamamlandı/i)).toBeInTheDocument();
    // Backend'in dondurdugu rapor kimligi gosteriliyor - hakem bunu arayacak.
    expect(screen.getByText(/RPT-2026-ABC123/)).toBeInTheDocument();

    // Govde multipart ve backend'in zorunlu tuttugu alanlari tasimali.
    const uploadCall = fetchMock.mock.calls.find(([url]) =>
      String(url).includes("/api/reports/upload"),
    );
    expect(uploadCall).toBeDefined();
    const body = uploadCall?.[1]?.body as FormData;
    expect(body.get("project_name")).toBe("İHA Nesne Tespiti");
    expect(body.get("category_id")).toBe("cat-2");
    expect(body.get("file")).toBeInstanceOf(File);
  });

  it("refuses to upload before a project name is entered", async () => {
    mockUploadFetch();
    render(<ReportUpload initialCategories={CATEGORIES} />);

    await dropFiles(screen.getByTestId("upload-dropzone"), [
      makeFile("evaluation-report.pdf", "application/pdf"),
    ]);

    const item = screen.getByTestId("upload-item-evaluation-report.pdf");
    expect(item).toHaveAttribute("data-status", "error");
    // Backend project_name'i zorunlu tutuyor; sunucuya gitmeden uyariyoruz.
    expect(item).toHaveTextContent(/önce proje adını girin/i);
  });

  it("surfaces the backend error message when the upload is rejected", async () => {
    mockUploadFetch({ uploadStatus: 404 });
    const user = userEvent.setup();
    render(<ReportUpload initialCategories={CATEGORIES} />);

    await fillProjectName(user, "Geçersiz Kategori Testi");
    await dropFiles(screen.getByTestId("upload-dropzone"), [
      makeFile("evaluation-report.pdf", "application/pdf"),
    ]);

    const item = screen.getByTestId("upload-item-evaluation-report.pdf");
    await waitFor(() => expect(item).toHaveAttribute("data-status", "error"));
    expect(item).toHaveTextContent(/kayıt bulunamadı/i);
  });

  it("accepts Word documents as valid uploads", async () => {
    mockUploadFetch();
    const user = userEvent.setup();
    render(<ReportUpload initialCategories={CATEGORIES} />);

    await fillProjectName(user, "Word Raporu");
    await dropFiles(screen.getByTestId("upload-dropzone"), [
      makeFile(
        "report.docx",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
      ),
    ]);

    const item = screen.getByTestId("upload-item-report.docx");
    // Dosya turu kabul edildi: hata DEGIL, yukleme/analiz akisina girdi.
    expect(item).not.toHaveAttribute("data-status", "error");
    await waitFor(() => expect(item).toHaveAttribute("data-status", "success"));
  });

  it("shows an error state for unsupported file types", async () => {
    mockUploadFetch();
    render(<ReportUpload initialCategories={CATEGORIES} />);

    await dropFiles(screen.getByTestId("upload-dropzone"), [
      makeFile("notes.txt", "text/plain"),
    ]);

    const item = screen.getByTestId("upload-item-notes.txt");
    expect(item).toHaveAttribute("data-status", "error");
    expect(item).toHaveTextContent(/desteklenmeyen dosya türü/i);
    expect(screen.queryByRole("progressbar")).not.toBeInTheDocument();
  });

  it("removes an upload item when its remove button is clicked", async () => {
    mockUploadFetch();
    const user = userEvent.setup();
    render(<ReportUpload initialCategories={CATEGORIES} />);

    await dropFiles(screen.getByTestId("upload-dropzone"), [
      makeFile("notes.txt", "text/plain"),
    ]);
    expect(screen.getByTestId("upload-item-notes.txt")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /kaldır: notes\.txt/i }));
    expect(screen.queryByTestId("upload-item-notes.txt")).not.toBeInTheDocument();
  });

  it("opens the file picker via keyboard interaction on the dropzone", async () => {
    const user = userEvent.setup();
    render(<ReportUpload initialCategories={CATEGORIES} />);
    const dropzone = screen.getByTestId("upload-dropzone");
    const input = screen.getByTestId("upload-file-input") as HTMLInputElement;
    const clickSpy = jest.spyOn(input, "click");

    dropzone.focus();
    await user.keyboard("{Enter}");

    expect(clickSpy).toHaveBeenCalled();
  });

  it("loads categories from the API when they are not supplied", async () => {
    mockUploadFetch();
    render(<ReportUpload />);

    const select = screen.getByTestId("upload-category");
    await waitFor(() => {
      expect(select).toHaveTextContent("Yapay Zeka ve Makine Öğrenmesi");
    });
    expect(select).toHaveValue("cat-2");
  });
});
