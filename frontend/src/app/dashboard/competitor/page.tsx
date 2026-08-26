import { DashboardShell } from "@/components/dashboard-shell";
import { RoleGuard } from "@/components/role-guard";
import { CompetitorReportContainer } from "@/components/competitor/competitor-report-container";
import { CompetitorSubmissionsInfo } from "@/components/competitor/competitor-submissions-info";

export default function CompetitorDashboardPage() {
  return (
    <RoleGuard requiredRole="COMPETITOR">
      <DashboardShell role="COMPETITOR">
        <div className="flex flex-col gap-8">
          {/* Sonuç önce: yarışmacının ilk merak ettiği şey bu. Hakem
              kararı verilmediyse bu bölüm "henüz sonuç yok" gösteriyor. */}
          <CompetitorReportContainer />
          {/* Yukleme YOK - sartname AKIS 03'te yarismacinin yukleme adimi
              yok; yukleme AKIS 01'de yoneticide ("raporlari sisteme
              aktarir"). Panel bilgi amacli duruyor ki yarismaci "neden
              yukleyemiyorum" diye aramasin. */}
          <CompetitorSubmissionsInfo />
        </div>
      </DashboardShell>
    </RoleGuard>
  );
}
