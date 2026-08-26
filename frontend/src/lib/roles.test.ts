import { getDashboardPath, isRole, ROLE_DEFINITIONS, ROLES } from "./roles";

describe("roles", () => {
  it("şartnamedeki dört rolü ve kurum sorumlusunu tanımlar", () => {
    // ORG_OWNER şartnamedeki dört role SONRADAN eklendi: dört rol "bu kurumda
    // kim ne yapar" sorusunu cevaplıyordu ama "bu kurumda KİM VAR" sorusunu
    // kimse cevaplamıyordu - sonuçta her yönetici sınırsız yönetici
    // üretebiliyordu.
    expect(ROLES).toEqual([
      "ORG_OWNER",
      "COMPETITION_MANAGER",
      "REFEREE",
      "COMPETITOR",
      "EVALUATION_MANAGER",
    ]);
  });

  it("maps every role to a unique /dashboard/* path", () => {
    const paths = ROLES.map((role) => getDashboardPath(role));
    expect(new Set(paths).size).toBe(ROLES.length);
    for (const path of paths) {
      expect(path).toMatch(/^\/dashboard\//);
    }
  });

  it("resolves the exact dashboard path documented for each role", () => {
    expect(getDashboardPath("ORG_OWNER")).toBe("/dashboard/organization");
    expect(getDashboardPath("COMPETITION_MANAGER")).toBe("/dashboard/manager");
    expect(getDashboardPath("REFEREE")).toBe("/dashboard/referee");
    expect(getDashboardPath("COMPETITOR")).toBe("/dashboard/competitor");
    expect(getDashboardPath("EVALUATION_MANAGER")).toBe("/dashboard/evaluation");
  });

  it("keeps ROLE_DEFINITIONS keys in sync with the role's own dashboardPath", () => {
    for (const role of ROLES) {
      expect(ROLE_DEFINITIONS[role].role).toBe(role);
      expect(ROLE_DEFINITIONS[role].dashboardPath).toBe(getDashboardPath(role));
    }
  });

  describe("isRole", () => {
    it("accepts every valid role string", () => {
      for (const role of ROLES) {
        expect(isRole(role)).toBe(true);
      }
    });

    it("rejects invalid values", () => {
      expect(isRole("ADMIN")).toBe(false);
      expect(isRole("")).toBe(false);
      expect(isRole(null)).toBe(false);
      expect(isRole(undefined)).toBe(false);
      expect(isRole(42)).toBe(false);
    });
  });
});
