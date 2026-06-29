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

/** 認証 */
export const authApi = {
  status: () => get<AuthStatus>('/api/auth/status'),
  startGoogle: () => { window.location.href = '/api/auth/google' },
}

/** プロジェクト管理 */
export const projectsApi = {
  list: () => get<Project[]>('/api/projects'),
  get: (id: string) => get<Project>(`/api/projects/${id}`),
  create: (req: ProjectCreateRequest) => post<Project>('/api/projects', req),
  update: (id: string, req: ProjectUpdateRequest) =>
    put<Project>(`/api/projects/${id}`, req),
  delete: (id: string) => del<void>(`/api/projects/${id}`),
}

/** Google Form */
export const formApi = {
  create: (projectId: string) =>
    post<FormInfo>(`/api/projects/${projectId}/form`),
  get: (projectId: string) =>
    get<FormInfo>(`/api/projects/${projectId}/form`),
}

/** 回答 */
export const responsesApi = {
  sync: (projectId: string) =>
    post<void>(`/api/projects/${projectId}/responses/sync`),
  list: (projectId: string) =>
    get<Response[]>(`/api/projects/${projectId}/responses`),
  status: (projectId: string) =>
    get<ResponsesStatus>(`/api/projects/${projectId}/responses/status`),
}

/** ルール */
export const rulesApi = {
  getGlobal: () => get<Rules>('/api/global-rules'),
  putGlobal: (rules: Rules) => put<Rules>('/api/global-rules', rules),
  getProject: (projectId: string) =>
    get<Rules>(`/api/projects/${projectId}/rules`),
  putProject: (projectId: string, rules: Rules) =>
    put<Rules>(`/api/projects/${projectId}/rules`, rules),
}

/** スケジューリング */
export const scheduleApi = {
  run: (projectId: string, req?: ScheduleRequest) =>
    post<SchedulingResult>(`/api/projects/${projectId}/schedule`, req),
}

/** ドラフト */
export const draftsApi = {
  save: (projectId: string, req: DraftSaveRequest) =>
    post<Draft>(`/api/projects/${projectId}/drafts`, req),
  unlock: (projectId: string) =>
    post<Draft>(`/api/projects/${projectId}/drafts/unlock`),
  getLatest: (projectId: string) =>
    get<Draft>(`/api/projects/${projectId}/drafts/latest`),
}

/** PDF */
export const pdfApi = {
  downloadUrl: (projectId: string) =>
    `/api/projects/${projectId}/pdf`,
}
