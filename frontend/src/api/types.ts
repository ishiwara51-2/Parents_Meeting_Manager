/**
 * バックエンド API の型定義
 * requirements.md §3.2 / §6 のスキーマに基づく
 */

// ===== プロジェクト =====

export type ProjectStatus = 'in_progress' | 'draft_saved' | 'finalized'

export interface TimeSlot {
  start: string // "HH:MM"
  end: string   // "HH:MM"
}

export interface Project {
  project_id: string
  display_name: string
  created_at: string // ISO 8601
  status: ProjectStatus
  slot_minutes: number
  candidate_dates: string[]       // "YYYY-MM-DD"[]
  candidate_time_slots: TimeSlot[]
  student_numbers: number[]
}

export interface ProjectCreateRequest {
  display_name: string
  slot_minutes: number
  candidate_dates: string[]
  candidate_time_slots: TimeSlot[]
  student_numbers: number[]
  status?: ProjectStatus
}

export interface ProjectUpdateRequest {
  display_name: string
  slot_minutes: number
  candidate_dates: string[]
  candidate_time_slots: TimeSlot[]
  student_numbers: number[]
  status?: ProjectStatus
}

// ===== ルール =====

export interface TeacherUnavailable {
  date: string  // "YYYY-MM-DD"
  start: string // "HH:MM"
  end: string   // "HH:MM"
}

export interface GlobalConstraints {
  max_consecutive_slots: number
  forced_break_slots: number
  max_slots_per_day: number
  teacher_unavailable: TeacherUnavailable[]
}

export type StudentConstraintType =
  | 'pairing'
  | 'avoid_time'
  | 'prefer_time'
  | 'duration_multiplier'

export interface StudentConstraint {
  type: StudentConstraintType
  student_numbers?: number[]
  student_number?: number
  avoid_after?: string
  prefer_before?: string
  multiplier?: number
  weight?: number
}

export interface Rules {
  global_constraints: GlobalConstraints
  student_constraints: StudentConstraint[]
}

// ===== Form =====

export interface FormInfo {
  formId: string
  responderUri: string
  editUri: string
  student_number_question_id: string
  row_question_id_by_date: Record<string, string>
  time_slot_labels: string[]
}

// ===== 回答 =====

export interface AvailabilitySlot {
  date: string  // "YYYY-MM-DD"
  start: string // "HH:MM"
  end: string   // "HH:MM"
}

export interface Response {
  project_id: string
  student_number: number
  submitted_at: string
  google_form_response_id: string
  availability: AvailabilitySlot[]
}

export interface ResponsesStatus {
  project_id: string
  received: number[]
  pending: number[]
}

// ===== スケジューリング =====

export interface Assignment {
  student_number: number
  date: string  // "YYYY-MM-DD"
  start: string // "HH:MM:SS"
  end: string   // "HH:MM:SS"
}

export interface SchedulingResult {
  assignments: Assignment[]
  unassigned_students: number[]
  violated_constraints: string[]
}

export interface ScheduleRequest {
  solver_time_limit_seconds?: number
  /** スケジューリング対象から除外する出席番号（名簿外の回答などを弾く用途） */
  excluded_students?: number[]
}

// ===== ドラフト =====

export interface Draft {
  project_id: string
  saved_at: string // ISO 8601
  locked: boolean
  assignments: Assignment[]
  unassigned_students: number[]
  violated_constraints: string[]
}

export interface DraftSaveRequest {
  assignments: Assignment[]
  unassigned_students: number[]
  violated_constraints: string[]
}

// ===== 認証 =====

export interface AuthStatus {
  authenticated: boolean
  email?: string
}

// ===== ヘルスチェック =====

export interface HealthResponse {
  status: string
}

// ===== API エラー =====

export interface ApiError {
  detail: string | { msg: string; type: string }[]
}
