import { DashboardShell } from "@/components/dashboard-shell";
import { RoleGuard } from "@/components/role-guard";
import { EvaluationDashboard } from "@/components/evaluation/evaluation-dashboard";

export default function EvaluationManagerDashboard() {
  return (
    <RoleGuard requiredRole="EVALUATION_MANAGER">
      <DashboardShell role="EVALUATION_MANAGER">
        <EvaluationDashboard />
      </DashboardShell>
    </RoleGuard>
  );
}
