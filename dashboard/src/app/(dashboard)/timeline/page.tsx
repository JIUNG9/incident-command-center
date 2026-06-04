"use client"

import { useEffect, useState } from "react"
import { fetchTimeline, type TimelineRow } from "@/lib/acme-deploy-api"
import { Card, CardContent } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { Clock, AlertTriangle } from "lucide-react"

const SOURCE_OPTIONS = [
  { value: "all", label: "All sources" },
  { value: "confluence", label: "Confluence" },
  { value: "slack", label: "Slack" },
  { value: "github", label: "GitHub" },
  { value: "obsidian", label: "Obsidian" },
]

function relativeTime(iso: string): string {
  const diff = Date.now() - new Date(iso).getTime()
  const m = Math.round(diff / 60_000)
  if (m < 1) return "just now"
  if (m < 60) return `${m}m ago`
  const h = Math.floor(m / 60)
  if (h < 24) return `${h}h ago`
  return `${Math.floor(h / 24)}d ago`
}

function qualityColor(score: number): string {
  if (score >= 0.7) return "#34D399"
  if (score >= 0.4) return "#5BB8FF"
  return "#FFC857"
}

export default function TimelinePage() {
  const [rows, setRows] = useState<TimelineRow[]>([])
  const [source, setSource] = useState("all")
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    setLoading(true)
    setError(null)
    fetchTimeline({ source: source === "all" ? undefined : source })
      .then(setRows)
      .catch((err) => {
        console.error(err)
        setError(err.message)
      })
      .finally(() => setLoading(false))
  }, [source])

  return (
    <div className="space-y-6 p-8">
      <div className="flex items-end justify-between">
        <div>
          <h1 className="font-heading text-3xl font-bold tracking-tight">Timeline</h1>
          <p className="mt-1 font-mono text-sm text-muted-foreground">
            Every question vigil answered — query, summary, retrieval quality, source.
          </p>
        </div>
        <div className="flex items-center gap-3">
          <Badge variant="outline" className="font-mono text-xs">
            {rows.length} shown
          </Badge>
          <Select value={source} onValueChange={setSource}>
            <SelectTrigger className="w-40 font-mono text-xs">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {SOURCE_OPTIONS.map((o) => (
                <SelectItem key={o.value} value={o.value}>
                  {o.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
      </div>

      {error && (
        <Card className="border-red-400/30 bg-red-400/5">
          <CardContent className="flex items-start gap-3 p-4">
            <AlertTriangle className="size-5 shrink-0 text-red-400" />
            <div className="flex-1">
              <div className="font-mono text-sm font-bold text-red-400">
                vigil backend connection failed
              </div>
              <div className="mt-1 font-mono text-xs text-muted-foreground">
                {error}
              </div>
              <div className="mt-2 font-mono text-[11px] text-muted-foreground">
                Local dev: <code className="rounded bg-muted px-1">kubectl --context=nx-prod -n vigil-agent port-forward svc/vigil-chat-api 8080:80</code>
              </div>
            </div>
          </CardContent>
        </Card>
      )}

      {loading && !error && (
        <div className="font-mono text-sm text-muted-foreground">Loading…</div>
      )}

      {!loading && !error && rows.length === 0 && (
        <Card className="bg-card">
          <CardContent className="flex flex-col items-center justify-center gap-3 p-10 text-center">
            <Clock className="size-12 text-muted-foreground/40" />
            <div className="font-mono text-sm text-muted-foreground">
              No Q&A recorded yet.
            </div>
          </CardContent>
        </Card>
      )}

      {rows.length > 0 && (
        <div className="space-y-3">
          {rows.map((r) => (
            <Card key={r.id} className="bg-card">
              <CardContent className="p-5">
                <div className="mb-2 flex items-center justify-between">
                  <span className="font-mono text-xs uppercase tracking-wider text-muted-foreground">
                    {r.source}
                  </span>
                  <div className="flex items-center gap-3">
                    <span
                      className="font-mono text-[11px]"
                      style={{ color: qualityColor(r.retrieval_quality) }}
                    >
                      quality {(r.retrieval_quality * 100).toFixed(0)}%
                    </span>
                    <span className="font-mono text-[11px] text-muted-foreground">
                      {relativeTime(r.ts)}
                    </span>
                  </div>
                </div>
                <div className="font-heading text-base font-bold text-foreground">
                  {r.query}
                </div>
                <p className="mt-2 line-clamp-3 text-sm leading-relaxed text-muted-foreground">
                  {r.answer_summary}
                </p>
              </CardContent>
            </Card>
          ))}
        </div>
      )}
    </div>
  )
}
