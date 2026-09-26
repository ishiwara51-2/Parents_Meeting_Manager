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

/** POST /api/projects の body。status を省略した場合はサーバ側で既定値（in_progress）になる */
export interface ProjectCreateRequest {
  display_name: string
  slot_minutes: number
  candidate_dates: string[]
  candidate_time_slots: TimeSlot[]
  student_numbers: number[]
  status?: ProjectStatus
}

/** PUT /api/projects/{id} の body。Create と同形だが既存プロジェクトの更新に使う */
export interface ProjectUpdateRequest {
  display_name: string
  slot_minutes: number
  candidate_dates: string[]
  candidate_time_slots: TimeSlot[]
  student_numbers: number[]
  status?: ProjectStatus
}

// ===== ルール =====

/** 教師の対応不可時間帯（この間はどの生徒も割り当てられない） */
export interface TeacherUnavailable {
  date: string  // "YYYY-MM-DD"
  start: string // "HH:MM"
  end: string   // "HH:MM"
}

/** スケジューリング時に守られる制約のデフォルト値（プロジェクト作成時に複製される） */
export interface GlobalConstraints {
  max_consecutive_slots: number
  forced_break_slots: number
  max_slots_per_day: number
  teacher_unavailable: TeacherUnavailable[]
}

/**
 * 生徒単位の制約種別。
 * - pairing: student_numbers を同時刻/近接に配置する（きょうだい等）
 * - avoid_time: avoid_after 以降を避ける
 * - prefer_time: prefer_before 以前を優先する
 * - duration_multiplier: 通常コマ数に対する所要時間の倍率（multiplier）
 */
export type StudentConstraintType =
  | 'pairing'
  | 'avoid_time'
  | 'prefer_time'
  | 'duration_multiplier'

/**
 * 生徒単位の制約1件。type によって使用されるフィールドが異なる
 * （バックエンドの Union 的なスキーマをフラットな optional フィールド群として表現）。
 */
export interface StudentConstraint {
  type: StudentConstraintType
  student_numbers?: number[]
  student_number?: number
  avoid_after?: string
  prefer_before?: string
  multiplier?: number
  weight?: number
}

/** グローバルルール設定・プロジェクトルール設定の両方で使う制約セット全体 */
export interface Rules {
  global_constraints: GlobalConstraints
  student_constraints: StudentConstraint[]
}

// ===== Form =====

/**
 * 作成された Google Form のメタ情報。
 * responderUri は保護者に共有する回答用 URL、editUri は教師用の編集 URL。
 * row_question_id_by_date 等は sync 時に Google Forms API の回答を
 * プロジェクトの候補日・時間枠にマッピングし直すために保持している。
 */
export interface FormInfo {
  formId: string
  responderUri: string
  editUri: string
  student_number_question_id: string
  comment_question_id?: string | null
  row_question_id_by_date: Record<string, string>
  time_slot_labels: string[]
}

// ===== 回答 =====

export interface AvailabilitySlot {
  date: string  // "YYYY-MM-DD"
  start: string // "HH:MM"
  end: string   // "HH:MM"
}

/** 1生徒分の Google Form 回答（同期取り込み後の正規化済みデータ） */
export interface Response {
  project_id: string
  student_number: number
  submitted_at: string
  google_form_response_id: string
  availability: AvailabilitySlot[]
  comment?: string | null
}

/** 出席番号ベースの回答受領状況（未受領者のリマインドや進捗表示に使う） */
export interface ResponsesStatus {
  project_id: string
  received: number[]
  pending: number[]
}

// ===== スケジューリング =====

/**
 * 1件の面談配置。start/end はバックエンドから "HH:MM:SS" 形式で
 * シリアライズされる点に注意（フロント側の内部比較では "HH:MM" に正規化して扱う）。
 */
export interface Assignment {
  student_number: number
  date: string  // "YYYY-MM-DD"
  start: string // "HH:MM:SS"
  end: string   // "HH:MM:SS"
}

/** POST .../schedule のレスポンス。解が制約を満たせない場合でも部分結果として返る */
export interface SchedulingResult {
  assignments: Assignment[]
  unassigned_students: number[]
  violated_constraints: string[]
}

/** POST .../schedule の body。両フィールドとも省略可（サーバ側の既定値を使用） */
export interface ScheduleRequest {
  /** ソルバーの最大実行時間（秒）。未指定ならサーバ既定値 */
  solver_time_limit_seconds?: number
  /** スケジューリング対象から除外する出席番号（名簿外の回答などを弾く用途） */
  excluded_students?: number[]
}

// ===== ドラフト =====

/**
 * 保存済みの日程案ドラフト。locked=true の間は draftsApi.save が 409 を返す
 * （unlock で解除するまで再保存できない）。
 */
export interface Draft {
  project_id: string
  saved_at: string // ISO 8601
  locked: boolean
  assignments: Assignment[]
  unassigned_students: number[]
  violated_constraints: string[]
  /** ユーザーが手動でロックした出席番号一覧（自動配置の対象外） */
  locked_students: number[]
}

/** POST .../drafts の body。Draft からサーバ管理フィールド（project_id/saved_at/locked）を除いた形 */
export interface DraftSaveRequest {
  assignments: Assignment[]
  unassigned_students: number[]
  violated_constraints: string[]
  locked_students: number[]
}

// ===== 認証 =====

/** GET /api/auth/status のレスポンス。未認証時は email なし */
export interface AuthStatus {
  authenticated: boolean
  email?: string
}

// ===== ヘルスチェック =====

export interface HealthResponse {
  status: string
}

// ===== API エラー =====

/** FastAPI の標準エラー形式。detail はバリデーションエラー時に配列になる */
export interface ApiError {
  detail: string | { msg: string; type: string }[]
}
