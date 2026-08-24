import { DashboardShell } from "@/components/dashboard-shell";
import { RoleGuard } from "@/components/role-guard";
import { RefereeReportContainer } from "@/components/referee/referee-report-container";

/**
 * Bu sayfa eskiden `generateStaticParams()` ile MOCK_REPORTS kimliklerinden
 * statik olarak üretiliyordu ve gövdesinde `getMockReportById(id)` çağırıp
 * bulunamayanlar için `notFound()` veriyordu. Yani gerçek bir rapor kimliği
 * (RPT-2026-XXXXXX) ile açıldığında 404 dönerdi.
 *
 * Artık kimlik doğrudan istemci kabına geçiyor; veri çekme orada yapılıyor.
 * Bu şart, çünkü JWT localStorage'da duruyor ve bir sunucu bileşeni ona
 * erişemez — veri çekme istemcide olmak zorunda.
 */
export default async function RefereeReportPage(
  props: PageProps<"/dashboard/referee/[id]">,
) {
  const { id } = await props.params;

  return (
    <RoleGuard requiredRole="REFEREE">
      <DashboardShell role="REFEREE">
        <RefereeReportContainer reportId={id} />
      </DashboardShell>
    </RoleGuard>
  );
}
