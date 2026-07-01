/**
 * OCP Bionic Judge — Typed API client
 *
 * Auth: httpOnly JWT cookie set by POST /auth/login.
 * Global 401 handler: App.tsx registers setAuthErrorHandler() so any expired
 * session automatically redirects back to the login screen.
 */

import type {
  HealthResponse, SummaryResponse, SensorReading, DecisionRecord,
  JudgeEvaluation, AuditLogEntry, GovernanceMetrics, AnalyzeResponse, DriftResult,
} from './types'

// ── Global 401 handler ────────────────────────────────────────────────────────
let _onAuthError: (() => void) | null = null

export function setAuthErrorHandler(fn: (() => void) | null): void {
  _onAuthError = fn
}

// ── Core fetch helpers ────────────────────────────────────────────────────────
async function fetchJson<T>(url: string, init: RequestInit = {}): Promise<T> {
  const res = await fetch(url, { credentials: 'include', ...init })
  if (res.status === 401) {
    _onAuthError?.()
    throw new Error('Session expirée — reconnexion requise.')
  }
  if (!res.ok) {
    // FastAPI can return detail as a string (HTTPException) or array (422 validation)
    const body = await res.json().catch(() => ({})) as Record<string, unknown>
    const raw  = body?.detail
    let msg: string
    if (typeof raw === 'string') {
      msg = raw
    } else if (Array.isArray(raw) && raw.length > 0) {
      // 422 Unprocessable Entity — pick the first validation error message
      const first = raw[0] as Record<string, unknown>
      msg = String(first?.msg ?? `Erreur ${res.status}: champ invalide`)
    } else {
      msg = `Erreur ${res.status}: ${res.statusText}`
    }
    throw new Error(msg)
  }
  return res.json() as Promise<T>
}

type QueryParams = Record<string, string | number | undefined>

function buildUrl(path: string, params: QueryParams = {}): string {
  const url = new URL(path, window.location.origin)
  Object.entries(params).forEach(([k, v]) => {
    if (v != null && v !== '') url.searchParams.set(k, String(v))
  })
  return url.toString()
}

function get<T>(path: string, params: QueryParams = {}): Promise<T> {
  return fetchJson<T>(buildUrl(path, params))
}

// ── Auth ──────────────────────────────────────────────────────────────────────
export async function login(apiKey: string): Promise<{ status: string }> {
  return fetchJson('/auth/login', {
    method:  'POST',
    headers: { 'Content-Type': 'application/json' },
    body:    JSON.stringify({ api_key: apiKey }),
  })
}

/** Verify that the current session cookie is still valid (used on page reload). */
export async function checkAuth(): Promise<boolean> {
  try {
    await fetchJson('/auth/me')
    return true
  } catch {
    return false
  }
}

export async function logout(): Promise<void> {
  await fetch('/auth/logout', { method: 'POST', credentials: 'include' })
}

// ── Query param shapes ────────────────────────────────────────────────────────
export interface DecisionParams  { machine_id?: string; limit?: number; severity?: string }
export interface AuditLogParams  { limit?: number; machine_id?: string; severity?: string }

// ── Typed API surface ─────────────────────────────────────────────────────────
export const api = {
  summary:    (): Promise<SummaryResponse>         => get('/api/summary'),
  health:     (): Promise<HealthResponse>          => get('/health'),
  sensors:    (mid: string, limit: number): Promise<SensorReading[]> =>
                get(`/api/sensors/${mid}`, { limit }),
  decisions:  (p: DecisionParams = {}): Promise<DecisionRecord[]> =>
                get('/decisions', p as QueryParams),
  judgeEvals: (limit: number, offset?: number): Promise<JudgeEvaluation[]> =>
                get('/api/judge-evals', { limit, offset }),
  auditLog:   (p: AuditLogParams = {}): Promise<AuditLogEntry[]> =>
                get('/api/audit-log', p as QueryParams),
  governance: (w: string): Promise<GovernanceMetrics> =>
                get('/governance-metrics', { window: w }),
  drift:      (): Promise<DriftResult> =>
                get('/api/drift'),
  analyze:    (machine_id: string, use_agent = true, run_judge = true): Promise<AnalyzeResponse> =>
                fetchJson('/analyze', {
                  method:  'POST',
                  headers: { 'Content-Type': 'application/json' },
                  body:    JSON.stringify({ machine_id, use_agent, run_judge }),
                }),
}
