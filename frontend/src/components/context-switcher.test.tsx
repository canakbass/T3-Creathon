import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ContextSwitcher } from "./context-switcher";
import { useAuthStore } from "@/store/auth-store";

const pushMock = jest.fn();
jest.mock("next/navigation", () => ({
  useRouter: () => ({ push: pushMock, replace: jest.fn() }),
}));

/**
 * Kurum/rol değiştirici.
 *
 * Aynı e-posta birden fazla kurumda olabiliyor. Değiştirmenin tek yolu çıkıp
 * tekrar giriş yapmak olsaydı, iki kuruma bağlı bir kullanıcı gün içinde
 * defalarca şifre girerdi.
 *
 * YETKİYİ ARAYÜZ DEĞİŞTİRMİYOR: seçim sunucuya gidiyor ve sunucu o KURUM+ROL
 * için YENİ bir token imzalıyor.
 */
function jsonResponse(status: number, payload: unknown) {
  return { ok: status >= 200 && status < 300, status, json: async () => payload };
}

const UYELIKLER = [
  { organizationId: "org-t3", organizationName: "T3 Vakfı", roles: ["REFEREE"] },
  {
    organizationId: "org-cbu",
    organizationName: "Manisa CBÜ",
    roles: ["COMPETITION_MANAGER"],
  },
];

function mockSelect(status = 200) {
  const fetchMock = jest.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    if (!String(input).endsWith("/api/auth/select-role")) {
      throw new Error(`Beklenmeyen istek: ${input}`);
    }
    if (status !== 200) {
      return jsonResponse(status, { detail: "Bu hesabin secili kurumda bu rolu yok." });
    }
    const govde = JSON.parse(String(init?.body));
    return jsonResponse(200, {
      access_token: "yeni-jwt",
      token_type: "bearer",
      roles: ["REFEREE", "COMPETITION_MANAGER"],
      active_role: govde.role,
      active_organization_id: govde.organization_id,
      memberships: UYELIKLER.map((u) => ({
        organization_id: u.organizationId,
        organization_name: u.organizationName,
        roles: u.roles,
      })),
      user: {
        id: "u1",
        email: "cift@her-yerde.org",
        full_name: null,
        created_at: "2026-08-26T00:00:00",
        roles: ["REFEREE", "COMPETITION_MANAGER"],
        role: govde.role,
      },
    });
  });
  global.fetch = fetchMock as unknown as typeof fetch;
  return fetchMock;
}

describe("ContextSwitcher", () => {
  const originalFetch = global.fetch;

  beforeEach(() => {
    pushMock.mockClear();
    useAuthStore.setState({
      role: "REFEREE",
      roles: ["REFEREE", "COMPETITION_MANAGER"],
      organizationId: "org-t3",
      organizationName: "T3 Vakfı",
      memberships: UYELIKLER,
      token: "eski-jwt",
      email: "cift@her-yerde.org",
      fullName: null,
      userId: "u1",
    });
  });

  afterEach(() => {
    global.fetch = originalFetch;
  });

  it("tek seçenek varsa GÖRÜNMÜYOR", () => {
    // Değiştirecek bir şey yokken düğme koymak, ekranda anlamsız bir
    // seçenek bırakmak olurdu.
    useAuthStore.setState({
      memberships: [UYELIKLER[0]],
      role: "REFEREE",
      organizationId: "org-t3",
    });
    render(<ContextSwitcher />);
    expect(screen.queryByTestId("context-switch-toggle")).not.toBeInTheDocument();
  });

  it("seçenekleri KURUMUYLA birlikte gösterir", async () => {
    mockSelect();
    const user = userEvent.setup();
    render(<ContextSwitcher />);

    await user.click(screen.getByTestId("context-switch-toggle"));

    const t3 = screen.getByTestId("context-option-org-t3-REFEREE");
    expect(t3).toHaveTextContent("T3 Vakfı");
    expect(t3).toHaveTextContent("şu an");
    expect(
      screen.getByTestId("context-option-org-cbu-COMPETITION_MANAGER"),
    ).toHaveTextContent("Manisa CBÜ");
    // Rol kuruma bağlı: T3'teki hakemlik CBÜ'de yok.
    expect(
      screen.queryByTestId("context-option-org-cbu-REFEREE"),
    ).not.toBeInTheDocument();
  });

  it("seçimi SUNUCUYA sorar ve yeni token'la panele geçer", async () => {
    const fetchMock = mockSelect();
    const user = userEvent.setup();
    render(<ContextSwitcher />);

    await user.click(screen.getByTestId("context-switch-toggle"));
    await user.click(screen.getByTestId("context-option-org-cbu-COMPETITION_MANAGER"));

    await waitFor(() => expect(pushMock).toHaveBeenCalledWith("/dashboard/manager"));
    expect(useAuthStore.getState().token).toBe("yeni-jwt");
    expect(useAuthStore.getState().role).toBe("COMPETITION_MANAGER");
    expect(useAuthStore.getState().organizationId).toBe("org-cbu");
    expect(useAuthStore.getState().organizationName).toBe("Manisa CBÜ");

    expect(JSON.parse(String(fetchMock.mock.calls[0][1]?.body))).toEqual({
      role: "COMPETITION_MANAGER",
      organization_id: "org-cbu",
    });
  });

  it("sunucu reddederse ESKİ oturum korunur", async () => {
    // Arayüz kendi başına yetki değiştiremez; reddedilen bir geçişte eski
    // token'ın düşmesi kullanıcıyı sebepsiz yere dışarı atardı.
    mockSelect(403);
    const user = userEvent.setup();
    render(<ContextSwitcher />);

    await user.click(screen.getByTestId("context-switch-toggle"));
    await user.click(screen.getByTestId("context-option-org-cbu-COMPETITION_MANAGER"));

    expect(await screen.findByTestId("context-switch-error")).toBeInTheDocument();
    expect(pushMock).not.toHaveBeenCalled();
    expect(useAuthStore.getState().token).toBe("eski-jwt");
    expect(useAuthStore.getState().role).toBe("REFEREE");
  });

  it("kurum sorumlusu KENDİ kurumunun TÜM rollerini seçebiliyor", async () => {
    // "bu superuserlar her role bakabilmeli" — o rolü kendine zaten
    // verebildiği için engellemek güvenlik değil, fazladan iki tıklama.
    mockSelect();
    useAuthStore.setState({
      role: "ORG_OWNER",
      organizationId: "org-cbu",
      organizationName: "Manisa CBÜ",
      memberships: [
        {
          organizationId: "org-cbu",
          organizationName: "Manisa CBÜ",
          roles: ["ORG_OWNER"],
        },
      ],
    });
    const user = userEvent.setup();
    render(<ContextSwitcher />);

    await user.click(screen.getByTestId("context-switch-toggle"));

    expect(screen.getByTestId("context-option-org-cbu-REFEREE")).toBeInTheDocument();
    expect(
      screen.getByTestId("context-option-org-cbu-COMPETITION_MANAGER"),
    ).toBeInTheDocument();
    expect(screen.getByTestId("context-option-org-cbu-COMPETITOR")).toBeInTheDocument();
  });
});
