/**
 * Backend'in TEL ÜZERİNDE gönderdiği gövdeler (snake_case).
 *
 * Bunlar arayüzün kendi tipleri DEĞİL — sadece `mappers.ts`'in girdisi.
 * Bileşenler bu tipleri doğrudan kullanmamalı; aksi halde backend'in
 * isimlendirmesi tüm arayüze sızar.
 *
 * Kaynak: backend/app/schemas.py ve backend/app/routes/*.py
 */

/** POST /api/auth/login yanıtı (schemas.Token) */
export interface WireToken {
  access_token: string;
  token_type: string;
}

/** GET /api/auth/me yanıtı (schemas.UserResponse) */
export interface WireUser {
  id: string;
  email: string;
  /** ROLES ile aynı değerler: COMPETITION_MANAGER | REFEREE | COMPETITOR | EVALUATION_MANAGER */
  role: string;
  created_at: string;
}

/** GET /api/categories yanıt öğesi (schemas.CategoryResponse) */
export interface WireCategory {
  id: string;
  name: string;
  description: string | null;
}

/** GET /api/criteria yanıt öğesi (schemas.CriteriaResponse) */
export interface WireCriteria {
  id: string;
  category_id: string;
  title: string;
  description: string | null;
  max_score: number;
}

/**
 * ReportResponse.ai_analysis (schemas.AiAnalysisResponse).
 *
 * `results` backend'de `Dict[str, AiCheckResult]` — açık bir sözlük, yani
 * anahtarların varlığı tip düzeyinde garanti DEĞİL. Bu yüzden burada da
 * indeksli imza kullanıyoruz ve eksik anahtarları mapper dolduruyor.
 */
export interface WireAiAnalysis {
  id: string;
  report_id: string;
  analyzed_at: string;
  engine_version: string;
  suggested_outcome: string;
  suggested_score: number;
  rationale: string;
  results: Record<string, { score: number; summary: string | null; findings: string[] }>;
}

/** POST /api/reports/{id}/decision yanıtı (schemas.FinalDecisionResponse) */
export interface WireFinalDecision {
  id: string;
  report_id: string;
  referee_id: string;
  outcome: string;
  final_score: number;
  rationale: string;
  submitted_at: string;
}

/** GET /api/reports ve /api/reports/{id} yanıtı (schemas.ReportResponse) */
export interface WireReport {
  id: string;
  project_name: string;
  category_id: string;
  /** pending | analyzed | approved | rejected | revise | error */
  status: string;
  file_path: string;
  submitted_by_id: string;
  submission_date: string;
  ai_analysis: WireAiAnalysis | null;
  final_decision: WireFinalDecision | null;
}

/** GET /api/dashboard/stats yanıtı (schemas.DashboardStats) */
export interface WireDashboardStats {
  total_reports: number;
  pending_reports: number;
  analyzed_reports: number;
  approved_reports: number;
  rejected_reports: number;
  revise_reports: number;
  completion_rate: number;
}
