"use client"

import { useEffect, useState } from "react"
import { fetchMttr, type MttrBoxplot } from "@/lib/acme-deploy-api"
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { AlertTriangle } from "lucide-react"

const PCLASS_META: Record<MttrBoxplot["p_class"], { color: string; label: string }> = {
  P0: { color: "#F87171", label: "biz-critical, paging" },
  P1: { color: "#FFC857", label: "service degradation" },
  P2: { color: "#5BB8FF", label: "partial outage" },
  P3: { color: "#A0A0A8", label: "no user impact" },
}

function formatMinutes(ms: number): string {
  const m = Math.round(ms / 60_000)
  if (m < 60) return `${m}m`
  const h = Math.floor(m / 60)
  const r = m % 60
  return r === 0 ? `${h}h` : `${h}h ${r}m`
}

export default function MttrPage() {
  const [boxes, setBoxes] = useState<MttrBoxplot[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    fetchMttr()
      .then(setBoxes)
      .catch((err) => {
        console.error(err)
        setError(err.message)
      })
      .finally(() => setLoading(false))
  }, [])

  const max = Math.max(1, ...boxes.map((b) => b.whisker_high))
  const totalCount = boxes.reduce((sum, b) => sum + b.count, 0)

  return (
    <div className="space-y-6 p-8">
      <div className="flex items-end justify-between">
        <div>
          <h1 className="font-heading text-3xl font-bold tracking-tight">MTTR</h1>
          <p className="mt-1 font-mono text-sm text-muted-foreground">
            30-day P-class boxplots — box = Q1–Q3, inner line = median, whiskers = 5th/95th pct.
          </p>
        </div>
        <Badge variant="outline" className="font-mono text-xs">{totalCount} samples · 30d</Badge>
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

      {/* Summary cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-5">
        {boxes.map((b) => {
          const meta = PCLASS_META[b.p_class]
          return (
            <Card key={b.p_class} className="bg-card">
              <CardHeader>
                <div className="flex items-center gap-2">
                  <span className="inline-block size-2 rounded-full" style={{ backgroundColor: meta.color }} />
                  <CardTitle className="font-mono text-xs font-bold uppercase tracking-widest" style={{ color: meta.color }}>
                    {b.p_class}
                  </CardTitle>
                </div>
                <CardDescription className="font-mono text-[10px]">{meta.label}</CardDescription>
              </CardHeader>
              <CardContent>
                <div className="font-mono text-3xl font-bold">{formatMinutes(b.median)}</div>
                <div className="mt-1 font-mono text-xs text-muted-foreground">median · n={b.count}</div>
              </CardContent>
            </Card>
          )
        })}
      </div>

      {/* Boxplot rows */}
      {boxes.length > 0 && (
        <Card className="bg-card">
          <CardHeader>
            <div className="flex items-baseline justify-between">
              <CardTitle className="font-mono text-sm font-bold uppercase tracking-wider">Distribution</CardTitle>
              <span className="font-mono text-xs text-muted-foreground">{totalCount} samples · 30d</span>
            </div>
          </CardHeader>
          <CardContent>
            <div className="space-y-6">
              {boxes.map((b) => {
                const meta = PCLASS_META[b.p_class]
                const scale = (v: number) => (v / max) * 100
                return (
                  <div key={b.p_class}>
                    <div className="mb-2 flex items-center justify-between">
                      <div className="flex items-center gap-2">
                        <span className="inline-block size-3 rounded-full" style={{ backgroundColor: meta.color }} />
                        <span className="font-heading text-sm font-bold" style={{ color: meta.color }}>
                          {b.p_class}
                        </span>
                        <span className="font-mono text-xs text-muted-foreground">{meta.label}</span>
                      </div>
                      <span className="font-mono text-xs text-muted-foreground">median {formatMinutes(b.median)} · n={b.count}</span>
                    </div>
                    <div className="relative h-7 overflow-hidden rounded-md bg-muted/40 ring-1 ring-border">
                      <div className="absolute top-1/2 h-px -translate-y-1/2" style={{
                        left: `${scale(b.whisker_low)}%`,
                        width: `${scale(b.whisker_high) - scale(b.whisker_low)}%`,
                        backgroundColor: `${meta.color}80`,
                      }} />
                      <div className="absolute top-0 bottom-0" style={{
                        left: `${scale(b.q1)}%`,
                        width: `${scale(b.q3) - scale(b.q1)}%`,
                        backgroundColor: `${meta.color}33`,
                        borderLeft: `1.5px solid ${meta.color}`,
                        borderRight: `1.5px solid ${meta.color}`,
                      }} />
                      <div className="absolute top-0 bottom-0 w-0.5 bg-foreground" style={{ left: `${scale(b.median)}%` }} />
                    </div>
                    <div className="mt-1 flex justify-between font-mono text-[10px] text-muted-foreground">
                      <span>{formatMinutes(b.whisker_low)}</span>
                      <span>{formatMinutes(b.q1)}</span>
                      <span>{formatMinutes(b.q3)}</span>
                      <span>{formatMinutes(b.whisker_high)}</span>
                    </div>
                  </div>
                )
              })}
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  )
}
