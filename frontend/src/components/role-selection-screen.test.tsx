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
 * Bu ekran artik GERCEK kimlik dogrulama yapiyor:
 *   e-posta + sifre -> /api/auth/login -> (tek rol) panel
 *                                      -> (cok rol) rol secimi -> /select-role
 * Onceki hali rol kartina tiklayinca SIFRESIZ giris yapiyordu; o davranis
 * kasitli olarak kaldirildi, testler de yeniden yazildi.
 *
 * jsdom'da `Response` global'i guvenilir olmadigi icin taklit yanitlar,
 * istemcinin gercekten kullandigi yuzeyi (ok/status/json) tasiyan sade
 * nesneler.
 */
function jsonResponse(status: number, payload: unknown) {
  return { ok: status >= 200 && status < 300, status, json: async () => payload };
}

function kullanici(email: string, roles: string[], activeRole: string | null) {
  return {
    access_token: "test-jwt",
    token_type: "bearer",
    roles,
    active_role: activeRole,
    user: {
      id: "user-1",
      email,
      full_name: "Test Kişi",
      created_at: "2026-08-24T00:00:00",
      roles,
      role: activeRole,
    },
  };
}

interface MockAyar {
  roles?: string[];
  loginStatus?: number;
  registerStatus?: number;
}

function mockFetch({ roles = ["REFEREE"], loginStatus = 200, registerStatus = 201 }: MockAyar = {}) {
  const cokRol = roles.length > 1;
  const fetchMock = jest.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);

    if (url.endsWith("/api/auth/login")) {
      if (loginStatus !== 200) {
        return jsonResponse(loginStatus, { detail: "E-posta veya sifre hatali" });
      }
      // Cok rollu kullanicida active_role null gelir -> rol secimi gerekir.
      return jsonResponse(200, kullanici("test@ornek.org", roles, cokRol ? null : roles[0]));
    }

    if (url.endsWith("/api/auth/register")) {
      if (registerStatus !== 201) {
        return jsonResponse(registerStatus, { detail: "Bu e-posta adresi zaten kayitli." });
      }
      return jsonResponse(201, {
        id: "user-1",
        email: "test@ornek.org",
        full_name: null,
        created_at: "2026-08-24T00:00:00",
        roles,
        role: roles[0],
      });
    }

    if (url.endsWith("/api/auth/select-role")) {
      const secilen = JSON.parse(String(init?.body ?? "{}")).role as string;
      return jsonResponse(200, kullanici("test@ornek.org", roles, secilen));
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
    expect(screen.getByLabelText(/e-posta/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/şifre/i)).toBeInTheDocument();
    // Sifre girmeden rol secip girebilme YOLU KAPALI olmali.
    expect(screen.queryByTestId("role-card-REFEREE")).not.toBeInTheDocument();
  });

  it("signs a single-role user straight into their dashboard", async () => {
    const fetchMock = mockFetch({ roles: ["REFEREE"] });
    const user = userEvent.setup();
    render(<RoleSelectionScreen />);

    await girisYap(user);

    await waitFor(() => {
      expect(pushMock).toHaveBeenCalledWith(ROLE_DEFINITIONS.REFEREE.dashboardPath);
    });
    expect(useAuthStore.getState().token).toBe("test-jwt");
    expect(useAuthStore.getState().role).toBe("REFEREE");

    // Login govdesi form-encoded olmali ve e-posta `username` adiyla gitmeli
    // (backend OAuth2PasswordRequestForm kullaniyor; JSON gonderilse 422).
    const call = fetchMock.mock.calls.find(([u]) => String(u).endsWith("/api/auth/login"));
    const body = call?.[1]?.body as URLSearchParams;
    expect(body.get("username")).toBe("test@ornek.org");
    expect(body.get("password")).toBe("sifre12345");
  });

  it("asks a multi-role user to choose a role before entering", async () => {
    mockFetch({ roles: ["REFEREE", "COMPETITOR", "COMPETITION_MANAGER"] });
    const user = userEvent.setup();
    render(<RoleSelectionScreen />);

    await girisYap(user);

    // Rol secilmeden HICBIR panele gidilmemeli.
    const group = await screen.findByRole("radiogroup", { name: /rolünüzü seçin/i });
    expect(group).toBeInTheDocument();
    expect(pushMock).not.toHaveBeenCalled();

    // Yalnizca kullanicinin GERCEKTEN sahip oldugu roller gosterilmeli.
    expect(screen.getByTestId("role-card-REFEREE")).toBeInTheDocument();
    expect(screen.getByTestId("role-card-COMPETITOR")).toBeInTheDocument();
    expect(screen.queryByTestId("role-card-EVALUATION_MANAGER")).not.toBeInTheDocument();
  });

  it("requests a role-scoped token from the server when a role is chosen", async () => {
    const fetchMock = mockFetch({ roles: ["REFEREE", "COMPETITOR"] });
    const user = userEvent.setup();
    render(<RoleSelectionScreen />);

    await girisYap(user);
    await user.click(await screen.findByTestId("role-card-COMPETITOR"));

    await waitFor(() => {
      expect(pushMock).toHaveBeenCalledWith(ROLE_DEFINITIONS.COMPETITOR.dashboardPath);
    });
    expect(useAuthStore.getState().role).toBe("COMPETITOR");
    // Her iki rol de saklanmali - panelde rol degistirme icin gerekli.
    expect(useAuthStore.getState().roles).toEqual(
      expect.arrayContaining(["REFEREE", "COMPETITOR"]),
    );

    // Rol secimi SUNUCUYA sorulmali; arayuz kendi basina rol atayamaz.
    const call = fetchMock.mock.calls.find(([u]) =>
      String(u).endsWith("/api/auth/select-role"),
    );
    expect(call).toBeDefined();
    expect(JSON.parse(String(call?.[1]?.body))).toEqual({ role: "COMPETITOR" });
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

  it("registers a new account with the selected roles and signs in", async () => {
    const fetchMock = mockFetch({ roles: ["COMPETITOR"] });
    const user = userEvent.setup();
    render(<RoleSelectionScreen />);

    await user.click(screen.getByRole("button", { name: /kaydolun/i }));
    expect(screen.getByTestId("register-form")).toBeInTheDocument();

    await user.type(screen.getByLabelText(/e-posta/i), "test@ornek.org");
    await user.type(screen.getByLabelText(/şifre/i), "sifre12345");
    await user.click(screen.getByRole("button", { name: /^kaydol$/i }));

    await waitFor(() => {
      expect(pushMock).toHaveBeenCalledWith(ROLE_DEFINITIONS.COMPETITOR.dashboardPath);
    });

    const call = fetchMock.mock.calls.find(([u]) => String(u).endsWith("/api/auth/register"));
    expect(call).toBeDefined();
    expect(JSON.parse(String(call?.[1]?.body)).roles).toEqual(["COMPETITOR"]);
  });

  it("lets a new account request more than one role", async () => {
    const fetchMock = mockFetch({ roles: ["COMPETITOR", "REFEREE"] });
    const user = userEvent.setup();
    render(<RoleSelectionScreen />);

    await user.click(screen.getByRole("button", { name: /kaydolun/i }));
    await user.click(screen.getByTestId("register-role-REFEREE"));
    await user.type(screen.getByLabelText(/e-posta/i), "test@ornek.org");
    await user.type(screen.getByLabelText(/şifre/i), "sifre12345");
    await user.click(screen.getByRole("button", { name: /^kaydol$/i }));

    await waitFor(() => {
      const call = fetchMock.mock.calls.find(([u]) =>
        String(u).endsWith("/api/auth/register"),
      );
      expect(JSON.parse(String(call?.[1]?.body)).roles).toEqual(
        expect.arrayContaining(["COMPETITOR", "REFEREE"]),
      );
    });
  });

  it("surfaces the backend message when the e-mail is already registered", async () => {
    mockFetch({ registerStatus: 400 });
    const user = userEvent.setup();
    render(<RoleSelectionScreen />);

    await user.click(screen.getByRole("button", { name: /kaydolun/i }));
    await user.type(screen.getByLabelText(/e-posta/i), "test@ornek.org");
    await user.type(screen.getByLabelText(/şifre/i), "sifre12345");
    await user.click(screen.getByRole("button", { name: /^kaydol$/i }));

    expect(await screen.findByTestId("login-error")).toHaveTextContent(/zaten kayitli/i);
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
