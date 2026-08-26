import { DashboardShell } from "@/components/dashboard-shell";
import { RoleGuard } from "@/components/role-guard";
import { AccountCreator } from "@/components/manager/account-creator";
import { MemberManager } from "@/components/organization/member-manager";

/**
 * Kurum sorumlusu paneli.
 *
 * İki iş yan yana ama AYRI: hesap AÇMAK (kimliğe kefil olmak) ve mevcut bir
 * üyenin ROLÜNÜ değiştirmek. Tek formda olsalardı "yeni hesap mı açıyorum,
 * var olanı mı değiştiriyorum" sorusu her seferinde belirsiz kalırdı.
 */
export default function OrganizationOwnerDashboard() {
  return (
    <RoleGuard requiredRole="ORG_OWNER">
      <DashboardShell role="ORG_OWNER">
        <div className="flex flex-col gap-8">
          <MemberManager />
          <AccountCreator />
        </div>
      </DashboardShell>
    </RoleGuard>
  );
}
