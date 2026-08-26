import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { RoleSelectionScreen } from "./role-selection-screen";
import { useAuthStore } from "@/store/auth-store";
import { ROLE_DEFINITIONS } from "@/lib/roles";

const pushMock = jest.fn();

jest.mock("next/navigation", () => ({
  useRouter: () => ({ push: pushMock, replace: jest.fn() }),
}));

/**
 * Bu ekran gerçek kimlik doğrulaması yapıyor ve artık KURUM+ROL seçtiriyor:
 *   e-posta + şifre -> /api/auth/login
 *      tek seçenek  -> doğrudan panel
 *      çok seçenek  -> kurum+rol seçimi -> /select-role
 *
 * Rol tek başına bir kimlik değil: "hakem" değil, "T3 Vakfı'nda hakem".
 * Aynı e-posta birden fazla kurumda olabilir ve rolleri kuruma göre değişir.
 *
 * KAYIT FORMU YOK: kendi kendine kayıt kapalı (backend 403 dönüyor), formu
 * tutmak her denemede hata veren ölü bir yol bırakmak olurdu.
 *
 * jsdom'da `Response` global'i güvenilir olmadığı için taklit yanıtlar,
 * istemcinin gerçekten kullandığı yüzeyi (ok/status/json) taşıyan sade
 * nesneler.
 */
function jsonResponse(status: number, payload: unknown) {
  return { ok: status >= 200 && status < 300, status, json: async () => payload };
}

interface Uyelik {
  organization_id: string;
  organization_name: string | null;
  roles: string[];
}

function oturum(uyelikler: Uyelik[], activeRole: string | null, activeOrg: string | null) {
  const tumRoller = Array.from(new Set(uyelikler.flatMap((u) => u.roles)));
  return {
    access_token: "test-jwt",
    token_type: "bearer",
    roles: tumRoller,
    active_role: activeRole,
    active_organization_id: activeOrg,
    memberships: uyelikler,
    user: {
      id: "user-1",
      email: "test@ornek.org",
      full_name: "Test Kişi",
      created_at: "2026-08-24T00:00:00",
      roles: tumRoller,
      role: activeRole,
    },
  };
}

const TEK_KURUM: Uyelik[] = [
  { organization_id: "org-t3", organization_name: "T3 Vakfı", roles: ["REFEREE"] },
];

const IKI_KURUM: Uyelik[] = [
  {
    organization_id: "org-t3",
    organization_name: "T3 Vakfı",
    roles: ["REFEREE", "COMPETITOR"],
  },
  {
    organization_id: "org-cbu",
    organization_name: "Manisa CBÜ",
    roles: ["COMPETITION_MANAGER"],
  },
];

function mockFetch({
  uyelikler = TEK_KURUM,
  loginStatus = 200,
  selectStatus = 200,
}: { uyelikler?: Uyelik[]; loginStatus?: number; selectStatus?: number } = {}) {
  // Tek (kurum, rol) çifti varsa backend token'ı doğrudan ona göre imzalıyor.
  const ciftler = uyelikler.flatMap((u) => u.roles.map((r) => [u.organization_id, r]));
  const tekSecenek = ciftler.length === 1;

  const fetchMock = jest.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);

    if (url.endsWith("/api/auth/login")) {
      if (loginStatus !== 200) {
        return jsonResponse(loginStatus, { detail: "E-posta veya sifre hatali" });
      }
      return jsonResponse(
        200,
        oturum(
          uyelikler,
          tekSecenek ? String(ciftler[0][1]) : null,
          tekSecenek ? String(ciftler[0][0]) : null,
        ),
      );
    }

    if (url.endsWith("/api/auth/select-role")) {
      if (selectStatus !== 200) {
        return jsonResponse(selectStatus, {
          detail: "Bu hesabin secili kurumda bu rolu yok.",
        });
      }
      const govde = JSON.parse(String(init?.body ?? "{}"));
      return jsonResponse(
        200,
        oturum(uyelikler, govde.role, govde.organization_id ?? null),
      );
    }

    throw new Error(`Beklenmeyen istek: ${url}`);
  });

  global.fetch = fetchMock as unknown as typeof fetch;
  return fetchMock;
}

async function girisYap(user: ReturnType<typeof userEvent.setup>) {
  await user.type(screen.getByLabelText(/e-posta/i), "test@ornek.org");
  await user.type(screen.getByLabelText(/şifre/i), "sifre12345");
  await user.click(screen.getByRole("button", { name: /^giriş yap$/i }));
}

describe("RoleSelectionScreen", () => {
  const originalFetch = global.fetch;

  beforeEach(() => {
    pushMock.mockClear();
    useAuthStore.setState({
      role: null,
      roles: [],
      organizationId: null,
      organizationName: null,
      memberships: [],
      token: null,
      email: null,
      fullName: null,
      userId: null,
    });
  });

  afterEach(() => {
    global.fetch = originalFetch;
  });

  it("opens on a login form, not a passwordless role picker", () => {
    mockFetch();
    render(<RoleSelectionScreen />);

    expect(screen.getByTestId("login-form")).toBeInTheDocument();
    // Şifre girmeden rol seçip girebilme YOLU KAPALI olmalı.
    expect(screen.queryByTestId("membership-picker")).not.toBeInTheDocument();
  });

  it("kayıt ve şifremi unuttum yollarını gösteriyor", async () => {
    // Kayıt artık AÇIK ama tek başına hiçbir şey açmıyor: hesap açılıyor,
    // hiçbir rol ve hiçbir kurum verilmiyor. Sonucu görmenin yolu e-postayı
    // DOĞRULAMAK.
    mockFetch();
    const user = userEvent.setup();
    render(<RoleSelectionScreen />);

    expect(screen.getByTestId("go-register")).toBeInTheDocument();
    expect(screen.getByTestId("go-reset")).toBeInTheDocument();

    await user.click(screen.getByTestId("go-register"));
    expect(screen.getByTestId("register-form")).toBeInTheDocument();
    // Beklentiyi dogru kurmak icin: kayit olmak yarismaya erisim vermiyor.
    expect(screen.getByTestId("register-form")).toHaveTextContent(
      /erişim vermez|doğrulamanız gerekiyor/i,
    );
  });

  it("şifremi unuttum formuna geçip geri dönebiliyor", async () => {
    mockFetch();
    const user = userEvent.setup();
    render(<RoleSelectionScreen />);

    await user.click(screen.getByTestId("go-reset"));
    expect(screen.getByTestId("reset-form")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /giriş ekranına dön/i }));
    expect(screen.getByTestId("login-form")).toBeInTheDocument();
  });

  it("signs a single-option user straight into their dashboard", async () => {
    const fetchMock = mockFetch({ uyelikler: TEK_KURUM });
    const user = userEvent.setup();
    render(<RoleSelectionScreen />);

    await girisYap(user);

    await waitFor(() => {
      expect(pushMock).toHaveBeenCalledWith(ROLE_DEFINITIONS.REFEREE.dashboardPath);
    });
    expect(useAuthStore.getState().token).toBe("test-jwt");
    expect(useAuthStore.getState().role).toBe("REFEREE");
    // KURUM da saklanmalı: kullanıcı hangi kurum adına çalıştığını her an
    // görmeli, yanlış kurumda işlem yapmak başka bir kurumun verisine
    // dokunmak demek.
    expect(useAuthStore.getState().organizationId).toBe("org-t3");
    expect(useAuthStore.getState().organizationName).toBe("T3 Vakfı");

    // Login gövdesi form-encoded olmalı ve e-posta `username` adıyla gitmeli
    // (backend OAuth2PasswordRequestForm kullanıyor; JSON gönderilse 422).
    const call = fetchMock.mock.calls.find(([u]) => String(u).endsWith("/api/auth/login"));
    const body = call?.[1]?.body as URLSearchParams;
    expect(body.get("username")).toBe("test@ornek.org");
    expect(body.get("password")).toBe("sifre12345");
  });

  it("birden fazla seçenek varsa KURUMLARI ayrı ayrı gösterir", async () => {
    mockFetch({ uyelikler: IKI_KURUM });
    const user = userEvent.setup();
    render(<RoleSelectionScreen />);

    await girisYap(user);

    // Seçim yapılmadan HİÇBİR panele gidilmemeli.
    expect(await screen.findByTestId("membership-picker")).toBeInTheDocument();
    expect(pushMock).not.toHaveBeenCalled();

    // Kurum adı başlık olarak görünmeli - kullanıcının önce "hangi kurum"
    // sorusunu cevaplaması gerekiyor.
    expect(screen.getByTestId("org-heading-org-t3")).toHaveTextContent("T3 Vakfı");
    expect(screen.getByTestId("org-heading-org-cbu")).toHaveTextContent("Manisa CBÜ");

    // Roller KURUMUNA bağlı görünmeli: T3'teki hakemlik CBÜ'de yok.
    expect(screen.getByTestId("role-card-org-t3-REFEREE")).toBeInTheDocument();
    expect(screen.getByTestId("role-card-org-cbu-COMPETITION_MANAGER")).toBeInTheDocument();
    expect(screen.queryByTestId("role-card-org-cbu-REFEREE")).not.toBeInTheDocument();
  });

  it("seçilen KURUM ve ROL'ü sunucuya birlikte gönderir", async () => {
    const fetchMock = mockFetch({ uyelikler: IKI_KURUM });
    const user = userEvent.setup();
    render(<RoleSelectionScreen />);

    await girisYap(user);
    await user.click(await screen.findByTestId("role-card-org-cbu-COMPETITION_MANAGER"));

    await waitFor(() => {
      expect(pushMock).toHaveBeenCalledWith(
        ROLE_DEFINITIONS.COMPETITION_MANAGER.dashboardPath,
      );
    });
    expect(useAuthStore.getState().role).toBe("COMPETITION_MANAGER");
    expect(useAuthStore.getState().organizationId).toBe("org-cbu");
    expect(useAuthStore.getState().organizationName).toBe("Manisa CBÜ");

    // Kurum ve rol AYRI AYRI değil BİRLİKTE gidiyor: yarım bir seçim
    // ("kurum seçildi ama rol seçilmedi") her ekranda ayrı ayrı düşünülmek
    // zorunda kalınan bir durum yaratırdı.
    const call = fetchMock.mock.calls.find(([u]) =>
      String(u).endsWith("/api/auth/select-role"),
    );
    expect(JSON.parse(String(call?.[1]?.body))).toEqual({
      role: "COMPETITION_MANAGER",
      organization_id: "org-cbu",
    });
  });

  it("sunucu seçimi reddederse panele GİTMEZ", async () => {
    // Arayüz kendi başına rol/kurum atayamaz; son söz sunucunun.
    mockFetch({ uyelikler: IKI_KURUM, selectStatus: 403 });
    const user = userEvent.setup();
    render(<RoleSelectionScreen />);

    await girisYap(user);
    await user.click(await screen.findByTestId("role-card-org-t3-REFEREE"));

    expect(await screen.findByTestId("login-error")).toBeInTheDocument();
    expect(pushMock).not.toHaveBeenCalled();
    expect(useAuthStore.getState().role).toBeNull();
  });

  it("shows an error and does not navigate when the credentials are rejected", async () => {
    mockFetch({ loginStatus: 401 });
    const user = userEvent.setup();
    render(<RoleSelectionScreen />);

    await girisYap(user);

    expect(await screen.findByTestId("login-error")).toBeInTheDocument();
    expect(pushMock).not.toHaveBeenCalled();
    expect(useAuthStore.getState().token).toBeNull();
  });

  it("surfaces a clear message when the backend is unreachable", async () => {
    global.fetch = jest.fn(async () => {
      throw new TypeError("Failed to fetch");
    }) as unknown as typeof fetch;
    const user = userEvent.setup();
    render(<RoleSelectionScreen />);

    await girisYap(user);

    expect(await screen.findByTestId("login-error")).toHaveTextContent(
      /backend'e ulaşılamadı/i,
    );
    expect(pushMock).not.toHaveBeenCalled();
  });

  it("fills the multi-role test account from the demo helper", async () => {
    mockFetch();
    const user = userEvent.setup();
    render(<RoleSelectionScreen />);

    await user.click(screen.getByRole("button", { name: /test hesabını doldur/i }));

    expect(screen.getByLabelText(/e-posta/i)).toHaveValue("asdfghjkl@gmail.com");
    expect(screen.getByLabelText(/şifre/i)).toHaveValue("asdfghjkl");
  });
});
