/**
 * Shared TypeScript interfaces — mirrors the Pydantic models from api/main.py.
 * Single source of truth for all data shapes consumed by the frontend.
 */

// ── Domain literals ────────────────────────────────────────────────────────────
export type Severity   = 'NORMAL' | 'WARNING' | 'CRITICAL'
export type SevFilter  = 'INFO' | 'WARNING' | 'CRITICAL'
export type AlertLevel = 'OK' | 'WARNING' | 'CRITICAL'
export type AccentColor = 'green' | 'amber' | 'red' | 'blue' | 'teal' | 'purple'

// ── API responses ─────────────────────────────────────────────────────────────
export interface HealthResponse {
  status:       string
  timestamp:    string
  db_connected: boolean
  model_loaded: boolean
  version:      string
}

export interface SummaryResponse {
  total_readings:  number
  machines_active: number
  anomalies:       number
  critical:        number
  normal:          number
  db_connected:    boolean
  model_loaded:    boolean
  generated_at:    string
}

export interface SensorReading {
  id:          number
  machine_id:  string
  timestamp:   string
  temperature: number
  vibration:   number
  pression:    number
  courant:     number
  rpm:         number
  shift:       string
}

export interface DecisionRecord {
  id:            number
  machine_id:    string
  timestamp:     string
  anomaly_score: number
  is_anomaly:    0 | 1
  severity:      Severity
  model_version: string | null
  inference_ms:  number | null
}

export interface JudgeEvaluation {
  id:                number
  machine_id:        string
  timestamp:         string
  global_score:      number
  relevance_score:   number
  history_score:     number
  confidence_score:  number
  compliance_score:  number
  feasibility_score: number
  agreement:         0 | 1
  feedback:          string
  flagged_issues:    string
}

export interface AuditLogEntry {
  id:         number
  timestamp:  string
  event_type: string
  machine_id: string | null
  user_id:    string
  action:     string
  details:    string | null
  severity:   string
}

export interface GovernanceAlert {
  type:       string
  message:    string
  value?:     number
  threshold?: number
}

export interface GovernanceMetrics {
  window:                string
  computed_at:           string
  n_evaluations:         number
  mean_judge_confidence: number | null
  disagreement_rate:     number | null
  ocp_compliance_rate:   number | null
  critical_unresolved:   number | null
  alerts:                GovernanceAlert[]
  status?:               string
}

export interface AnalyzeResponse {
  machine_id:         string
  timestamp:          string
  anomaly_score:      number
  severity:           string
  diagnosis:          string | null
  recommended_action: string | null
  confidence:         number | null
  judge_score:        number | null
  judge_agreement:    boolean | null
  processing_ms:      number
}

export interface DriftResult {
  timestamp?:      string
  psi?:            number
  psi_threshold?:  number
  ks_statistic?:   number
  ks_pvalue?:      number
  ks_threshold?:   number
  drift_detected?: boolean
  alert_level?:    AlertLevel
  reference_n?:    number
  current_n?:      number
  status?:         string
}

// ── Chart shapes ──────────────────────────────────────────────────────────────
export interface ChartPoint {
  ts:    string
  value: number
  sev:   Severity
  score: number
}

export interface SevByMachine {
  machine:  string
  NORMAL:   number
  WARNING:  number
  CRITICAL: number
}
