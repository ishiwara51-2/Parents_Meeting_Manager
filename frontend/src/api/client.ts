/**
 * 型付き API クライアント
 *
 * バックエンド（FastAPI）の各エンドポイントに対して型安全なラッパーを提供する。
 * requirements.md §6 の API 設計に準拠。
 *
 * ベース URL は Vite の開発プロキシ（/api → localhost:8000/api）または
 * 本番ビルド時（FastAPI 同一オリジン）で動作する。
 */

import type {
  Project,
  ProjectCreateRequest,
  ProjectUpdateRequest,
  Rules,
  FormInfo,
  Response,
  ResponsesStatus,
  SchedulingResult,
  ScheduleRequest,
  Draft,
  DraftSaveRequest,
  AuthStatus,
  HealthResponse,
} from './types'

// --- 低レベルのフェッチラッパー ---

/**
 * fetch の共通ラッパー。FastAPI のエラーレスポンス（{ detail: ... }）を
 * Error に変換し、呼び出し側が err.status で HTTP ステータスを判定できる
 * よう status プロパティを付与する（401/404/409 などの分岐に使われる）。
 */
async function request<T>(
  path: string,
  options?: RequestInit,
): Promise<T> {
  const res = await fetch(path, {
    headers: { 'Content-Type': 'application/json', ...options?.headers },
    ...options,
  })
  if (!res.ok) {
    const body = await res.json().catch(() => ({ detail: res.statusText }))
    const err = new Error(
      typeof body.detail === 'string'
        ? body.detail
        : JSON.stringify(body.detail),
    )
    ;(err as Error & { status: number }).status = res.status
    throw err
  }
  // 204 No Content
  if (res.status === 204) return undefined as unknown as T
  return res.json() as Promise<T>
}

function get<T>(path: string): Promise<T> {
  return request<T>(path)
}

function post<T>(path: string, body?: unknown): Promise<T> {
  return request<T>(path, {
    method: 'POST',
    body: body !== undefined ? JSON.stringify(body) : undefined,
  })
}

function put<T>(path: string, body: unknown): Promise<T> {
  return request<T>(path, { method: 'PUT', body: JSON.stringify(body) })
}

function del<T>(path: string): Promise<T> {
  return request<T>(path, { method: 'DELETE' })
}

// --- API クライアント ---

/** ヘルスチェック */
export const healthApi = {
  check: () => get<HealthResponse>('/api/health'),
}

/** 認証（Google OAuth）。startGoogle はページ遷移そのものなので Promise を返さない */
export const authApi = {
  status: () => get<AuthStatus>('/api/auth/status'),
  // OAuth フローへ丸ごとリダイレクトする（SPA 内では完結しない）
  startGoogle: () => { window.location.href = '/api/auth/google' },
  logout: () => post<AuthStatus>('/api/auth/logout'),
}

/** プロジェクト管理（作成・一覧・詳細取得・更新・削除） */
export const projectsApi = {
  list: () => get<Project[]>('/api/projects'),
  get: (id: string) => get<Project>(`/api/projects/${id}`),
  create: (req: ProjectCreateRequest) => post<Project>('/api/projects', req),
  update: (id: string, req: ProjectUpdateRequest) =>
    put<Project>(`/api/projects/${id}`, req),
  delete: (id: string) => del<void>(`/api/projects/${id}`),
}

/**
 * Google Form（候補日程聴取用）。create は初回未認証時に 401 を返し、
 * 呼び出し側（ProjectPage）が Google 認証フローへ誘導する契機となる。
 */
export const formApi = {
  create: (projectId: string) =>
    post<FormInfo>(`/api/projects/${projectId}/form`),
  get: (projectId: string) =>
    get<FormInfo>(`/api/projects/${projectId}/form`),
}

/** 保護者からの回答（Google Form 経由）。sync は Google 側から最新回答を取り込む */
export const responsesApi = {
  sync: (projectId: string) =>
    post<void>(`/api/projects/${projectId}/responses/sync`),
  list: (projectId: string) =>
    get<Response[]>(`/api/projects/${projectId}/responses`),
  status: (projectId: string) =>
    get<ResponsesStatus>(`/api/projects/${projectId}/responses/status`),
}

/**
 * スケジューリングルール。getGlobal/putGlobal は既定値（新規プロジェクト
 * 作成時に複製される）、getProject/putProject はプロジェクト固有の値。
 */
export const rulesApi = {
  getGlobal: () => get<Rules>('/api/global-rules'),
  putGlobal: (rules: Rules) => put<Rules>('/api/global-rules', rules),
  getProject: (projectId: string) =>
    get<Rules>(`/api/projects/${projectId}/rules`),
  putProject: (projectId: string, rules: Rules) =>
    put<Rules>(`/api/projects/${projectId}/rules`, rules),
}

/** スケジューリング実行。req.excluded_students でロック済み・除外対象の生徒を弾ける */
export const scheduleApi = {
  run: (projectId: string, req?: ScheduleRequest) =>
    post<SchedulingResult>(`/api/projects/${projectId}/schedule`, req),
}

/**
 * 日程案ドラフトの保存。
 * - save: ドラフトを保存すると同時にロック状態になる（以後の save は 409 を返す）
 * - unlock: ロックを解除し、再度 save できるようにする
 * - getLatest: 既存ドラフトが無ければ 404（呼び出し側で null 扱いに変換する）
 */
export const draftsApi = {
  save: (projectId: string, req: DraftSaveRequest) =>
    post<Draft>(`/api/projects/${projectId}/drafts`, req),
  unlock: (projectId: string) =>
    post<Draft>(`/api/projects/${projectId}/drafts/unlock`),
  getLatest: (projectId: string) =>
    get<Draft>(`/api/projects/${projectId}/drafts/latest`),
}

/** PDF 出力。ダウンロードは fetch+Blob で行うため URL 生成のみ提供する */
export const pdfApi = {
  downloadUrl: (projectId: string) =>
    `/api/projects/${projectId}/pdf`,
}
