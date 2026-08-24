import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { RoleSelectionScreen } from "./role-selection-screen";
import { useAuthStore } from "@/store/auth-store";
import { ROLE_DEFINITIONS, ROLES } from "@/lib/roles";

const pushMock = jest.fn();

jest.mock("next/navigation", () => ({
  useRouter: () => ({
    push: pushMock,
    replace: jest.fn(),
  }),
}));

/**
 * Giris ekrani artik GERCEK bir JWT girisi yapiyor: rol kartina tiklamak,
 * backend'in seed ettigi demo hesabiyla /api/auth/login cagiriyor ve
 * ardindan rolu /api/auth/me'den okuyor. Bu yuzden testler fetch'i
 * taklit etmek zorunda - onceden hicbir ag cagrisi yoktu.
 */
const ROLE_EMAILS: Record<string, string> = {
  COMPETITION_MANAGER: "manager@teknofest.org",
  REFEREE: "referee@teknofest.org",
  COMPETITOR: "competitor@teknofest.org",
  EVALUATION_MANAGER: "evaluator@teknofest.org",
};

/**
 * jsdom ortaminda `Response` global'i guvenilir sekilde bulunmuyor, bu
 * yuzden istemcinin GERCEKTEN kullandigi yuzeyi (`ok`, `status`, `json()`)
 * tasiyan sade nesneler donduruyoruz.
 */
function jsonResponse(status: number, payload: unknown) {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => payload,
  };
}

/** login -> /me ikilisini karsilayan bir fetch taklidi kurar. */
function mockAuthFetch(options: { role?: string; loginStatus?: number } = {}) {
  const { role = "REFEREE", loginStatus = 200 } = options;

  // `init` kullanilmasa da imzada yer almali: testler gonderilen govdeyi
  // (mock.calls[i][1].body) inceliyor ve tip bilgisi oradan geliyor.
  const fetchMock = jest.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    void init;
    const url = typeof input === "string" ? input : input.toString();

    if (url.endsWith("/api/auth/login")) {
      if (loginStatus !== 200) {
        return jsonResponse(loginStatus, { detail: "Incorrect email or password" });
      }
      return jsonResponse(200, { access_token: "test-jwt-token", token_type: "bearer" });
    }

    if (url.endsWith("/api/auth/me")) {
      return jsonResponse(200, {
        id: "user-1",
        email: ROLE_EMAILS[role] ?? "user@teknofest.org",
        role,
        created_at: "2026-08-24T00:00:00",
      });
    }

    throw new Error(`Beklenmeyen istek: ${url}`);
  });

  global.fetch = fetchMock as unknown as typeof fetch;
  return fetchMock;
}

describe("RoleSelectionScreen", () => {
  const originalFetch = global.fetch;

  beforeEach(() => {
    pushMock.mockClear();
    useAuthStore.setState({ role: null, token: null, email: null, userId: null });
  });

  afterEach(() => {
    global.fetch = originalFetch;
  });

  it("renders a selectable card for every role", () => {
    mockAuthFetch();
    render(<RoleSelectionScreen />);

    for (const role of ROLES) {
      const card = screen.getByTestId(`role-card-${role}`);
      expect(card).toBeInTheDocument();
      expect(card).toHaveTextContent(ROLE_DEFINITIONS[role].label);
    }
  });

  it("exposes an accessible radiogroup of exactly four roles", () => {
    mockAuthFetch();
    render(<RoleSelectionScreen />);

    const group = screen.getByRole("radiogroup", { name: /rolünüzü seçin/i });
    expect(group).toBeInTheDocument();

    const options = screen.getAllByRole("radio");
    expect(options).toHaveLength(4);
  });

  it.each(ROLES)(
    "logs in with the %s demo account and navigates to the dashboard the server reports",
    async (role) => {
      const fetchMock = mockAuthFetch({ role });
      const user = userEvent.setup();
      render(<RoleSelectionScreen />);

      await user.click(screen.getByTestId(`role-card-${role}`));

      await waitFor(() => {
        expect(pushMock).toHaveBeenCalledWith(ROLE_DEFINITIONS[role].dashboardPath);
      });

      // Gercek bir giris yapildi: token saklandi ve rol sunucudan geldi.
      expect(useAuthStore.getState().token).toBe("test-jwt-token");
      expect(useAuthStore.getState().role).toBe(role);
      expect(useAuthStore.getState().email).toBe(ROLE_EMAILS[role]);

      // Login govdesi form-encoded olmali ve e-posta alani `username`
      // adiyla gitmeli (backend OAuth2PasswordRequestForm kullaniyor).
      const loginCall = fetchMock.mock.calls.find(([url]) =>
        String(url).endsWith("/api/auth/login"),
      );
      expect(loginCall).toBeDefined();
      const body = loginCall?.[1]?.body as URLSearchParams;
      expect(body.get("username")).toBe(ROLE_EMAILS[role]);
      expect(body.get("password")).toBe("password123");
    },
  );

  it("shows an error and does not navigate when the credentials are rejected", async () => {
    mockAuthFetch({ loginStatus: 401 });
    const user = userEvent.setup();
    render(<RoleSelectionScreen />);

    await user.click(screen.getByTestId("role-card-REFEREE"));

    const alert = await screen.findByTestId("login-error");
    expect(alert).toHaveTextContent(/e-posta veya şifre hatalı/i);
    expect(pushMock).not.toHaveBeenCalled();
    expect(useAuthStore.getState().token).toBeNull();
  });

  it("surfaces a clear message when the backend is unreachable", async () => {
    global.fetch = jest.fn(async () => {
      throw new TypeError("Failed to fetch");
    }) as unknown as typeof fetch;

    const user = userEvent.setup();
    render(<RoleSelectionScreen />);

    await user.click(screen.getByTestId("role-card-REFEREE"));

    const alert = await screen.findByTestId("login-error");
    expect(alert).toHaveTextContent(/backend'e ulaşılamadı/i);
    expect(pushMock).not.toHaveBeenCalled();
  });

  it("lets a user sign in with their own credentials instead of a demo account", async () => {
    const fetchMock = mockAuthFetch({ role: "COMPETITOR" });
    const user = userEvent.setup();
    render(<RoleSelectionScreen />);

    await user.click(screen.getByRole("button", { name: /farklı bir hesapla/i }));

    await user.type(screen.getByLabelText(/e-posta/i), "kendi@ornek.org");
    await user.type(screen.getByLabelText(/şifre/i), "gizli-sifre");
    await user.click(screen.getByRole("button", { name: /^giriş yap$/i }));

    await waitFor(() => {
      expect(pushMock).toHaveBeenCalledWith(ROLE_DEFINITIONS.COMPETITOR.dashboardPath);
    });

    const loginCall = fetchMock.mock.calls.find(([url]) =>
      String(url).endsWith("/api/auth/login"),
    );
    const body = loginCall?.[1]?.body as URLSearchParams;
    expect(body.get("username")).toBe("kendi@ornek.org");
    expect(body.get("password")).toBe("gizli-sifre");
  });
});
