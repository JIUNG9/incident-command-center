"use client"

import { useEffect, useState } from "react"
import { fetchActiveIncidents, type WarIncident } from "@/lib/acme-deploy-api"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { Siren, AlertTriangle, MessageSquare } from "lucide-react"

const SEVERITY_COLOR: Record<WarIncident["severity"], string> = {
  P0: "#F87171",
  P1: "#FFC857",
  P2: "#5BB8FF",
  P3: "#A0A0A8",
}

function relativeTime(iso: string): string {
  const diff = Date.now() - new Date(iso).getTime()
  const m = Math.round(diff / 60_000)
  if (m < 1) return "just now"
  if (m < 60) return `${m}m`
  const h = Math.floor(m / 60)
  if (h < 24) return `${h}h`
  return `${Math.floor(h / 24)}d`
}

export default function WarPage() {
  const [incidents, setIncidents] = useState<WarIncident[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    fetchActiveIncidents()
      .then(setIncidents)
      .catch((err) => {
        console.error(err)
        setError(err.message)
      })
      .finally(() => setLoading(false))
  }, [])

  const active = incidents.filter((i) => i.status === "active")

  return (
    <div className="space-y-6 p-8">
      <div className="flex items-end justify-between">
        <div>
          <h1 className="font-heading text-3xl font-bold tracking-tight">War Room</h1>
          <p className="mt-1 font-mono text-sm text-muted-foreground">
            Active incidents — vigil joins the channel, replies with confidence-scored context.
          </p>
        </div>
        <Badge variant="outline" className="font-mono text-xs">active {active.length} samples</Badge>
      </div>

      {error && (
        <Card className="border-red-400/30 bg-red-400/5">
          <CardContent className="flex items-start gap-3 p-4">
            <AlertTriangle className="size-5 shrink-0 text-red-400" />
            <div>
              <div className="font-mono text-sm font-bold text-red-400">vigil war API connection failed</div>
              <div className="mt-1 font-mono text-xs text-muted-foreground">{error}</div>
              <div className="mt-2 font-mono text-[11px] text-muted-foreground">
                Local dev: <code className="rounded bg-muted px-1">kubectl --context=nx-prod -n vigil-agent port-forward svc/vigil-war-api 8081:80</code>
              </div>
            </div>
          </CardContent>
        </Card>
      )}

      {loading && !error && (
        <div className="font-mono text-sm text-muted-foreground">Loading…</div>
      )}

      {!loading && !error && active.length === 0 && (
        <Card className="bg-card">
          <CardContent className="flex flex-col items-center justify-center gap-3 p-10 text-center">
            <Siren className="size-12 text-muted-foreground/40" />
            <span className="font-mono text-sm text-muted-foreground">No active incidents — all calm.</span>
          </CardContent>
        </Card>
      )}

      <div className="space-y-3">
        {active.map((inc) => {
          const sev = SEVERITY_COLOR[inc.severity]
          return (
            <Card key={inc.id} className="bg-card hover:bg-card/80 cursor-pointer transition-colors" onClick={() => (window.location.href = `/war/${inc.id}/chat`)}>
              <CardHeader>
                <div className="flex items-start justify-between gap-3">
                  <div className="flex-1">
                    <div className="flex items-center gap-2 mb-1">
                      <Badge
                        variant="outline"
                        className="font-mono text-[10px] font-bold"
                        style={{ borderColor: `${sev}55`, color: sev, backgroundColor: `${sev}15` }}
                      >
                        {inc.severity}
                      </Badge>
                      <span className="font-mono text-xs text-muted-foreground">#{inc.channel}</span>
                    </div>
                    <CardTitle className="font-heading text-base">{inc.title}</CardTitle>
                  </div>
                  <span className="font-mono text-[11px] text-muted-foreground shrink-0">
                    {relativeTime(inc.started_at)} ago
                  </span>
                </div>
              </CardHeader>
              <CardContent>
                <div className="flex items-center justify-between">
                  <span className="font-mono text-xs text-muted-foreground">
                    acked by {inc.acknowledged_by.length}
                  </span>
                  <span className="inline-flex items-center gap-1.5 font-mono text-xs text-primary">
                    <MessageSquare className="size-3" />
                    Open war room →
                  </span>
                </div>
              </CardContent>
            </Card>
          )
        })}
      </div>
    </div>
  )
}
