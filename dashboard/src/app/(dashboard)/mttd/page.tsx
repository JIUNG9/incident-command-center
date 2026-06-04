"use client"

import { useEffect, useState } from "react"
import { fetchMttd, type MttdPoint } from "@/lib/acme-deploy-api"
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { AlertTriangle, Gauge } from "lucide-react"

const MODES = ["auto", "peer", "customer"] as const
type Mode = (typeof MODES)[number]

const MODE_META: Record<Mode, { title: string; color: string; description: string }> = {
  auto: { title: "Auto", color: "#34D399", description: "SigNoz rule fired before anyone reported" },
  peer: { title: "Peer", color: "#5BB8FF", description: "A teammate flagged it first" },
  customer: { title: "Customer", color: "#F87171", description: "External user reported first — worst case" },
}

function formatMs(ms: number): string {
  if (ms < 1000) return `${ms}ms`
  if (ms < 60_000) return `${(ms / 1000).toFixed(1)}s`
  return `${Math.round(ms / 60_000)}m`
}

export default function MttdPage() {
  const [points, setPoints] = useState<MttdPoint[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    fetchMttd()
      .then(setPoints)
      .catch((err) => {
        console.error(err)
        setError(err.message)
      })
      .finally(() => setLoading(false))
  }, [])

  const grouped = MODES.map((mode) => ({
    mode,
    points: points.filter((p) => p.mode === mode).slice(-14),
  }))

  const max = Math.max(1, ...points.map((p) => Math.max(p.rule_layer_ms, p.similarity_layer_ms)))

  const avgPerMode: Record<Mode, { rule: number; sim: number; samples: number }> = {
    auto: { rule: 0, sim: 0, samples: 0 },
    peer: { rule: 0, sim: 0, samples: 0 },
    customer: { rule: 0, sim: 0, samples: 0 },
  }
  for (const p of points) {
    const m = avgPerMode[p.mode as Mode]
    m.rule += p.rule_layer_ms
    m.sim += p.similarity_layer_ms
    m.samples += 1
  }
  for (const m of MODES) {
    const a = avgPerMode[m]
    if (a.samples > 0) {
      a.rule = Math.round(a.rule / a.samples)
      a.sim = Math.round(a.sim / a.samples)
    }
  }

  return (
    <div className="space-y-6 p-8">
      <div className="flex items-end justify-between">
        <div>
          <h1 className="font-heading text-3xl font-bold tracking-tight">MTTD</h1>
          <p className="mt-1 font-mono text-sm text-muted-foreground">
            Mean time to detect — rule layer vs similarity layer, split by who saw it first.
          </p>
        </div>
        <Badge variant="outline" className="font-mono text-xs">30-day rolling</Badge>
      </div>

      {error && (
        <Card className="border-red-400/30 bg-red-400/5">
          <CardContent className="flex items-start gap-3 p-4">
            <AlertTriangle className="size-5 shrink-0 text-red-400" />
            <div>
              <div className="font-mono text-sm font-bold text-red-400">vigil backend connection failed</div>
              <div className="mt-1 font-mono text-xs text-muted-foreground">{error}</div>
            </div>
          </CardContent>
        </Card>
      )}

      {loading && !error && (
        <div className="font-mono text-sm text-muted-foreground">Loading…</div>
      )}

      <div className="grid grid-cols-1 md:grid-cols-3 gap-5">
        {MODES.map((mode) => {
          const meta = MODE_META[mode]
          const avg = avgPerMode[mode]
          return (
            <Card key={mode} className="bg-card">
              <CardHeader>
                <div className="flex items-center gap-2">
                  <span className="inline-block size-3 rounded-full" style={{ backgroundColor: meta.color }} />
                  <CardTitle className="font-mono text-sm uppercase tracking-wider" style={{ color: meta.color }}>
                    {meta.title}
                  </CardTitle>
                </div>
                <CardDescription className="font-mono text-xs">{meta.description}</CardDescription>
              </CardHeader>
              <CardContent>
                <div className="flex items-baseline gap-3">
                  <span className="font-mono text-4xl font-bold">{formatMs(avg.rule)}</span>
                  <span className="font-mono text-sm text-muted-foreground">rule</span>
                </div>
                <div className="mt-1 flex items-baseline gap-2 font-mono text-sm text-muted-foreground">
                  <span>{formatMs(avg.sim)}</span>
                  <span>similarity</span>
                  <span className="ml-auto text-[10px] text-muted-foreground/60">n={avg.samples}</span>
                </div>
              </CardContent>
            </Card>
          )
        })}
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-5">
        {grouped.map(({ mode, points: ps }) => {
          const meta = MODE_META[mode]
          return (
            <Card key={mode} className="bg-card">
              <CardHeader>
                <div className="flex items-baseline justify-between">
                  <CardTitle className="font-mono text-sm uppercase tracking-wider" style={{ color: meta.color }}>
                    {meta.title} — 14d
                  </CardTitle>
                  <span className="font-mono text-[10px] text-muted-foreground">{ps.length} samples</span>
                </div>
              </CardHeader>
              <CardContent>
                {ps.length === 0 ? (
                  <div className="flex flex-col items-center gap-2 py-6 text-muted-foreground">
                    <Gauge className="size-8 opacity-40" />
                    <span className="font-mono text-xs">No samples</span>
                  </div>
                ) : (
                  <ul className="space-y-2.5">
                    {ps.map((p) => (
                      <li key={p.date}>
                        <div className="mb-1 flex items-center justify-between font-mono text-[11px] text-muted-foreground">
                          <span>{p.date.slice(5)}</span>
                          <span>rule {formatMs(p.rule_layer_ms)} · sim {formatMs(p.similarity_layer_ms)}</span>
                        </div>
                        <div className="relative h-2 overflow-hidden rounded bg-muted/40">
                          <div
                            className="h-full"
                            style={{
                              width: `${(p.rule_layer_ms / max) * 100}%`,
                              backgroundColor: meta.color,
                            }}
                          />
                          <div
                            className="absolute top-0 h-full"
                            style={{
                              left: `${(p.rule_layer_ms / max) * 100}%`,
                              width: `${(p.similarity_layer_ms / max) * 100}%`,
                              backgroundColor: `${meta.color}55`,
                            }}
                          />
                        </div>
                      </li>
                    ))}
                  </ul>
                )}
              </CardContent>
            </Card>
          )
        })}
      </div>
    </div>
  )
}
