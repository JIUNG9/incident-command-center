// Typed client for the vigil backend. The types are the contract the dashboard
// pages read; the paths below are what the client calls.
//
// Base URL: NEXT_PUBLIC_VIGIL_API_URL, default http://localhost:8000.

const API_BASE =
  (typeof process !== "undefined" && process.env.NEXT_PUBLIC_VIGIL_API_URL) ||
  "http://localhost:8000"

export type PClass = "P0" | "P1" | "P2" | "P3"

export interface WarIncident {
  id: string
  title: string
  severity: PClass
  status: "active" | "resolved" | "dismissed"
  channel: string
  started_at: string
  acknowledged_by: string[]
}

/** One box per P-class. Durations are milliseconds. */
export interface MttrBoxplot {
  p_class: PClass
  count: number
  median: number
  q1: number
  q3: number
  whisker_low: number
  whisker_high: number
}

export interface MttdPoint {
  /** ISO date, YYYY-MM-DD. */
  date: string
  mode: "auto" | "peer" | "customer"
  rule_layer_ms: number
  similarity_layer_ms: number
}

export interface TimelineRow {
  id: string
  source: string
  /** ISO timestamp. */
  ts: string
  query: string
  answer_summary: string
  /** 0 to 1. */
  retrieval_quality: number
}

export interface ApmCard {
  id: string
  channel: string
  rationale: string
  posted_at: string
  rule_yaml: string
  status: "pending" | "approved" | "skipped"
}

export interface SearchHit {
  doc_id: string
  text: string
  score: number
  source?: string
  url?: string
}

export class VigilApiError extends Error {
  constructor(
    message: string,
    readonly status?: number,
  ) {
    super(message)
    this.name = "VigilApiError"
  }
}

async function request<T>(
  path: string,
  init?: RequestInit,
  query?: Record<string, string | undefined>,
): Promise<T> {
  const url = new URL(`${API_BASE}${path}`)
  for (const [key, value] of Object.entries(query ?? {})) {
    if (value !== undefined) url.searchParams.set(key, value)
  }

  let res: Response
  try {
    res = await fetch(url, { cache: "no-store", ...init })
  } catch (err) {
    throw new VigilApiError(
      `Cannot reach ${API_BASE}: ${err instanceof Error ? err.message : String(err)}`,
    )
  }
  if (!res.ok) {
    throw new VigilApiError(`${init?.method ?? "GET"} ${path} failed with ${res.status}`, res.status)
  }
  return (await res.json()) as T
}

export async function fetchActiveIncidents(): Promise<WarIncident[]> {
  const body = await request<{ incidents: WarIncident[] }>("/war/incident", undefined, {
    state: "active",
  })
  return body.incidents
}

export function fetchApmCards(): Promise<ApmCard[]> {
  return request<ApmCard[]>("/apm/cards")
}

/** Sends the (possibly edited) rule YAML for the backend to create. */
export async function approveApmRule(ruleYaml: string): Promise<void> {
  await request<unknown>("/apm/rules", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ rule_yaml: ruleYaml }),
  })
}

export function fetchMttd(): Promise<MttdPoint[]> {
  return request<MttdPoint[]>("/mttd/series")
}

export function fetchMttr(): Promise<MttrBoxplot[]> {
  return request<MttrBoxplot[]>("/mttr/boxplots")
}

export function fetchTimeline(opts: { source?: string } = {}): Promise<TimelineRow[]> {
  return request<TimelineRow[]>("/timeline", undefined, { source: opts.source })
}
