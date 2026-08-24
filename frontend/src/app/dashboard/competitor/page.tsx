import { DashboardShell } from "@/components/dashboard-shell";
import { RoleGuard } from "@/components/role-guard";
import { CompetitorReportContainer } from "@/components/competitor/competitor-report-container";
import { CompetitorSubmission } from "@/components/competitor/competitor-submission";

export default function CompetitorDashboardPage() {
  return (
    <RoleGuard requiredRole="COMPETITOR">
      <DashboardShell role="COMPETITOR">
        <div className="flex flex-col gap-8">
          {/* Sonuç önce: yarışmacının ilk merak ettiği şey bu. Hakem
              kararı verilmediyse bu bölüm "henüz sonuç yok" gösteriyor. */}
          <CompetitorReportContainer />
          <CompetitorSubmission />
        </div>
      </DashboardShell>
    </RoleGuard>
  );
}
