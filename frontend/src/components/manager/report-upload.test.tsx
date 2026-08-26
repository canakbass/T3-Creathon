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
function mockUploadFetch(
  options: { analyzed?: boolean; uploadStatus?: number; reportStatus?: string } = {},
) {
  const { analyzed = true, uploadStatus = 201, reportStatus } = options;
  const reportBody = {
    id: "RPT-2026-ABC123",
    project_name: "İHA Nesne Tespiti",
    category_id: "cat-2",
    status: reportStatus ?? (analyzed ? "analyzed" : "pending"),
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
        return jsonResponse(uploadStatus, { detail: "Kategori bulunamadi." });
      }
      return jsonResponse(201, reportBody);
    }
    if (url.includes("/api/reports/")) return jsonResponse(200, reportBody);
    throw new Error(`Beklenmeyen istek: ${url}`);
  });

  global.fetch = fetchMock as unknown as typeof fetch;
  return fetchMock;
}

/** Dosyalari birak ve "Aktar"a bas. */
async function birakVeAktar(user: ReturnType<typeof userEvent.setup>, files: File[]) {
  await dropFiles(screen.getByTestId("upload-dropzone"), files);
  await user.click(await screen.findByTestId("upload-submit"));
}



describe("ReportUpload — takım dosya adından", () => {
  const originalFetch = global.fetch;
  afterEach(() => {
    global.fetch = originalFetch;
  });

  it("dosya bırakılınca TAKIMI GÖSTERİR ama hemen GÖNDERMEZ", async () => {
    // Çıkarım sezgisel: dosya adındaki bir harf hatası, doğrulamayı geçen
    // YABANCI birine o takımın tüm sonuçlarını verirdi. Doğrulama "bu
    // kutunun sahibi misin" sorusunu cevaplar, "bu kişi bu takımda mı"
    // sorusunu cevaplamaz — onu yalnızca yönetici cevaplayabilir.
    const fetchMock = mockUploadFetch();
    render(<ReportUpload competitionId="COMP-1" />);

    await dropFiles(
      screen.getByTestId("upload-dropzone"),
      [makeFile("ali@okul.edu.tr_veli@okul.edu.tr.pdf", "application/pdf")],
    );

    const satir = screen.getByTestId("upload-item-ali@okul.edu.tr_veli@okul.edu.tr.pdf");
    expect(satir).toHaveAttribute("data-status", "hazir");
    expect(
      screen.getByTestId("upload-emails-ali@okul.edu.tr_veli@okul.edu.tr.pdf"),
    ).toHaveValue("ali@okul.edu.tr, veli@okul.edu.tr");
    // Hiçbir yükleme isteği ATILMAMIŞ olmalı.
    expect(
      fetchMock.mock.calls.filter(([u]) => String(u).includes("/upload")),
    ).toHaveLength(0);
  });

  it("onaylanınca e-postaları GÖNDERİR ve analizi bekler", async () => {
    const fetchMock = mockUploadFetch();
    const user = userEvent.setup();
    render(<ReportUpload competitionId="COMP-1" />);

    await birakVeAktar(user, [
      makeFile("ali@okul.edu.tr_veli@okul.edu.tr.pdf", "application/pdf"),
    ]);

    const satir = screen.getByTestId("upload-item-ali@okul.edu.tr_veli@okul.edu.tr.pdf");
    await waitFor(() => expect(satir).toHaveAttribute("data-status", "success"));

    const cagri = fetchMock.mock.calls.find(([u]) => String(u).includes("/upload"));
    const govde = cagri?.[1]?.body as FormData;
    expect(govde.get("member_emails")).toBe("ali@okul.edu.tr,veli@okul.edu.tr");
    // Takım kimliği ARTIK GÖNDERİLMİYOR — yöneticinin elinde olmayan bilgi.
    expect(govde.get("team_id")).toBeNull();
  });

  it("dosya adında e-posta yoksa AKTARMAYI ENGELLER ve ne yapılacağını söyler", async () => {
    const fetchMock = mockUploadFetch();
    render(<ReportUpload competitionId="COMP-1" />);

    await dropFiles(screen.getByTestId("upload-dropzone"), [
      makeFile("matematik_rapor.pdf", "application/pdf"),
    ]);

    expect(screen.getByTestId("upload-issue-matematik_rapor.pdf")).toHaveTextContent(
      /adresler/i,
    );
    expect(screen.getByTestId("upload-submit")).toBeDisabled();
    expect(
      fetchMock.mock.calls.filter(([u]) => String(u).includes("/upload")),
    ).toHaveLength(0);
  });

  it("e-posta ELLE yazılınca aktarılabilir hale gelir", async () => {
    const fetchMock = mockUploadFetch();
    const user = userEvent.setup();
    render(<ReportUpload competitionId="COMP-1" />);

    await dropFiles(screen.getByTestId("upload-dropzone"), [
      makeFile("matematik_rapor.pdf", "application/pdf"),
    ]);
    await user.type(
      screen.getByTestId("upload-emails-matematik_rapor.pdf"),
      "ogrenci@okul.edu.tr",
    );
    await user.click(screen.getByTestId("upload-submit"));

    await waitFor(() =>
      expect(screen.getByTestId("upload-item-matematik_rapor.pdf")).toHaveAttribute(
        "data-status",
        "success",
      ),
    );
    const cagri = fetchMock.mock.calls.find(([u]) => String(u).includes("/upload"));
    expect((cagri?.[1]?.body as FormData).get("member_emails")).toBe(
      "ogrenci@okul.edu.tr",
    );
  });

  it("proje adı dosya adından DOLDURULUYOR ve düzenlenebiliyor", async () => {
    const fetchMock = mockUploadFetch();
    const user = userEvent.setup();
    render(<ReportUpload competitionId="COMP-1" />);

    await dropFiles(screen.getByTestId("upload-dropzone"), [
      makeFile("Yapay Zeka Projesi ali@x.com.pdf", "application/pdf"),
    ]);
    const alan = screen.getByTestId("upload-project-Yapay Zeka Projesi ali@x.com.pdf");
    expect(alan).toHaveValue("Yapay Zeka Projesi");

    await user.clear(alan);
    await user.type(alan, "Elle Yazılan Ad");
    await user.click(screen.getByTestId("upload-submit"));

    await waitFor(() => {
      const cagri = fetchMock.mock.calls.find(([u]) => String(u).includes("/upload"));
      expect((cagri?.[1]?.body as FormData).get("project_name")).toBe("Elle Yazılan Ad");
    });
  });

  it("belirsiz yerel kısımda UYARI gösteriyor", async () => {
    // `YAPAY_ZEKA_ali@x.com` içinde `ZEKA_ali` mi yerel kısım, `ali` mi?
    // Regex karara bağlayamaz; sessizce geçmek yöneticinin YANLIŞ bir takımı
    // onaylaması demekti.
    mockUploadFetch();
    render(<ReportUpload competitionId="COMP-1" />);

    await dropFiles(screen.getByTestId("upload-dropzone"), [
      makeFile("YAPAY ZEKA_ali@x.com.pdf", "application/pdf"),
    ]);

    expect(screen.getByTestId("upload-note-YAPAY ZEKA_ali@x.com.pdf")).toHaveTextContent(
      /düzeltin/i,
    );
  });

  it("geçersiz e-posta yazılırsa aktarım kapalı kalıyor", async () => {
    mockUploadFetch();
    const user = userEvent.setup();
    render(<ReportUpload competitionId="COMP-1" />);

    await dropFiles(screen.getByTestId("upload-dropzone"), [
      makeFile("matematik_rapor.pdf", "application/pdf"),
    ]);
    await user.type(
      screen.getByTestId("upload-emails-matematik_rapor.pdf"),
      "bozukadres",
    );

    expect(screen.getByTestId("upload-issue-matematik_rapor.pdf")).toHaveTextContent(
      /geçerli bir e-posta değil/i,
    );
    expect(screen.getByTestId("upload-submit")).toBeDisabled();
  });

  it("desteklenmeyen dosya türünü reddediyor", async () => {
    mockUploadFetch();
    render(<ReportUpload competitionId="COMP-1" />);

    await dropFiles(screen.getByTestId("upload-dropzone"), [
      makeFile("sunum.pptx", "application/vnd.ms-powerpoint"),
    ]);

    const satir = screen.getByTestId("upload-item-sunum.pptx");
    expect(satir).toHaveAttribute("data-status", "error");
    expect(satir).toHaveTextContent(/desteklenmeyen dosya türü/i);
  });

  it("Word belgelerini kabul ediyor", async () => {
    mockUploadFetch();
    render(<ReportUpload competitionId="COMP-1" />);

    await dropFiles(screen.getByTestId("upload-dropzone"), [
      makeFile(
        "ali@x.com.docx",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
      ),
    ]);

    expect(screen.getByTestId("upload-item-ali@x.com.docx")).toHaveAttribute(
      "data-status",
      "hazir",
    );
  });

  it("analiz status=error dönerse BAŞARI DEĞİL hata gösterir", async () => {
    // Dönen değere bakmasaydık analizi çökmüş bir rapor başarılı görünür,
    // kimse yeniden yüklemeyi düşünmez ve hakem hiç analizi olmayan bir
    // raporla karşılaşırdı.
    mockUploadFetch({ reportStatus: "error" });
    const user = userEvent.setup();
    render(<ReportUpload competitionId="COMP-1" />);

    await birakVeAktar(user, [makeFile("ali@x.com.pdf", "application/pdf")]);

    const satir = screen.getByTestId("upload-item-ali@x.com.pdf");
    await waitFor(() => expect(satir).toHaveAttribute("data-status", "error"));
    expect(satir).toHaveTextContent(/analizi tamamlanamadı/i);
  });

  it("backend hatasını olduğu gibi gösteriyor", async () => {
    mockUploadFetch({ uploadStatus: 404 });
    const user = userEvent.setup();
    render(<ReportUpload competitionId="COMP-1" />);

    await birakVeAktar(user, [makeFile("ali@x.com.pdf", "application/pdf")]);

    const satir = screen.getByTestId("upload-item-ali@x.com.pdf");
    await waitFor(() => expect(satir).toHaveAttribute("data-status", "error"));
    expect(satir).toHaveTextContent(/kategori bulunamadi/i);
  });

  it("satırı listeden çıkarabiliyor", async () => {
    mockUploadFetch();
    const user = userEvent.setup();
    render(<ReportUpload competitionId="COMP-1" />);

    await dropFiles(screen.getByTestId("upload-dropzone"), [
      makeFile("ali@x.com.pdf", "application/pdf"),
    ]);
    await user.click(
      screen.getByRole("button", { name: /ali@x.com.pdf dosyasını listeden çıkar/i }),
    );

    expect(screen.queryByTestId("upload-item-ali@x.com.pdf")).not.toBeInTheDocument();
  });

  it("klavyeyle dosya seçici açılıyor", async () => {
    mockUploadFetch();
    const user = userEvent.setup();
    render(<ReportUpload competitionId="COMP-1" />);

    const girdi = screen.getByTestId("upload-input") as HTMLInputElement;
    const tikla = jest.spyOn(girdi, "click").mockImplementation(() => {});
    screen.getByTestId("upload-dropzone").focus();
    await user.keyboard("{Enter}");

    expect(tikla).toHaveBeenCalled();
  });
});
