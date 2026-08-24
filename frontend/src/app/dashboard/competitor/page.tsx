import { DashboardShell } from "@/components/dashboard-shell";
import { RoleGuard } from "@/components/role-guard";
import { CompetitorReportContainer } from "@/components/competitor/competitor-report-container";

export default function CompetitorDashboardPage() {
  return (
    <RoleGuard requiredRole="COMPETITOR">
      <DashboardShell role="COMPETITOR">
        <CompetitorReportContainer />
      </DashboardShell>
    </RoleGuard>
  );
}
