/**
 * Backend'in TEL ÜZERİNDE gönderdiği gövdeler (snake_case).
 *
 * Bunlar arayüzün kendi tipleri DEĞİL — sadece `mappers.ts`'in girdisi.
 * Bileşenler bu tipleri doğrudan kullanmamalı; aksi halde backend'in
 * isimlendirmesi tüm arayüze sızar.
 *
 * Kaynak: backend/app/schemas.py ve backend/app/routes/*.py
 */

/** GET /api/auth/me yanıtı (schemas.UserResponse) */
export interface WireUser {
  id: string;
  email: string;
  full_name: string | null;
  created_at: string;
  /** Kullanıcının sahip olduğu TÜM roller. */
  roles: string[];
  /** Aktif rol (yoksa ilk rol). Tekil rol bekleyen eski kod için. */
  role: string | null;
}

/**
 * POST /api/auth/login ve /api/auth/select-role yanıtı (schemas.LoginResponse)
 *
 * `active_role` null ise kullanıcının birden fazla rolü var ve henüz
 * seçmemiş — arayüz rol seçim ekranı göstermeli.
 */
export interface WireLoginResponse {
  access_token: string;
  token_type: string;
  roles: string[];
  active_role: string | null;
  user: WireUser;
}

/** Yarışmanın değerlendirme kriteri (ağırlığıyla). */
export interface WireCriterion {
  id: string;
  title: string;
  description: string | null;
  weight: number;
  display_order: number;
}

/** GET /api/competitions yanıt öğesi (schemas.CompetitionResponse) */
export interface WireCompetition {
  id: string;
  name: string;
  description: string | null;
  category_id: string;
  category_name: string | null;
  /** draft | open | closed | evaluating | completed */
  status: string;
  submission_deadline: string | null;
  created_at: string;
  accepted_languages: string[];
  required_headings: string[];
  heading_synonyms: Record<string, string[]>;
  min_pages: number | null;
  max_pages: number | null;
  min_section_chars: number | null;
  criteria: WireCriterion[];
  referee_count: number;
  report_count: number;
}

/** GET /api/assignments/referees yanıt öğesi */
export interface WireReferee {
  id: string;
  email: string;
  full_name: string | null;
  assigned_count: number;
}

/** POST /api/assignments/competitions/{id}/auto-assign yanıtı */
export interface WireAutoAssignResult {
  assigned: number;
  assignments: { report_id: string; referee_id: string; referee_email: string }[];
  load: { referee_id: string; email: string; assigned_count: number }[];
  /**
   * Dağıtılamayan raporlar. En sık sebep, raporun sahibinin yarışmadaki tek
   * uygun hakem olması (kimse kendi raporunun hakemi olamaz). Sessizce
   * atlanırsa yönetici "dağıtım tamam" sanıp hiç değerlendirilmeyen bir
   * rapor bırakır. Eski backend'lerde alan yok — bu yüzden isteğe bağlı.
   */
  skipped?: { report_id: string; reason: string }[];
}

/** POST /api/reports/{id}/rationale-draft yanıtı */
export interface WireRationaleDraft {
  draft: string;
  notice: string;
  suggested_score: number;
  suggested_outcome: string;
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
  original_filename: string | null;
  competition_id: string | null;
  ai_analysis: WireAiAnalysis | null;
  final_decision: WireFinalDecision | null;
  /** Atanan hakem — listede de geliyor, ayrı istek gerekmiyor. */
  assigned_referee_id: string | null;
  assigned_referee_email: string | null;
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
