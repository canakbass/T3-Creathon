"use client";

import { CompetitionManager } from "./competition-manager";
import { AccountCreator } from "./account-creator";

export function ManagerDashboard() {
  return (
    <div className="flex flex-col gap-6">
      <div>
        <h2 className="text-xl font-bold text-foreground">Yarışma Yönetimi</h2>
        <p className="mt-1 text-sm text-muted">
          Yarışmalarınızı kurun, şablon ve kriterleri tanımlayın, hakem kadrosunu
          yönetin ve raporları dağıtın.
        </p>
      </div>

      <CompetitionManager />

      {/* Kullanicilar kendi kendine kayit OLAMAZ (bkz. account-creator.tsx):
          raporun sonucunu takim uyeligi belirliyor ve uyelik e-postaya bagli.
          Hesabi yoneticinin acmasi kimlige kefil olmasi demek. */}
      <AccountCreator />
    </div>
  );
}
