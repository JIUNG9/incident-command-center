"use client"

import { useEffect, useState } from "react"
import { fetchApmCards, approveApmRule, type ApmCard } from "@/lib/vigil-api"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Eye, AlertTriangle, Check, X } from "lucide-react"

const STATUS_META = {
  pending: { label: "pending", color: "#FFC857" },
  approved: { label: "approved", color: "#34D399" },
  skipped: { label: "skipped", color: "#A0A0A8" },
} as const

function relativeTime(iso: string): string {
  const diff = Date.now() - new Date(iso).getTime()
  const m = Math.round(diff / 60_000)
  if (m < 1) return "just now"
  if (m < 60) return `${m}m ago`
  const h = Math.floor(m / 60)
  if (h < 24) return `${h}h ago`
  return `${Math.floor(h / 24)}d ago`
}

export default function WatchlistPage() {
  const [cards, setCards] = useState<ApmCard[]>([])
  const [editing, setEditing] = useState<Record<string, string>>({})
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    fetchApmCards()
      .then(setCards)
      .catch((err) => {
        console.error(err)
        setError(err.message)
      })
      .finally(() => setLoading(false))
  }, [])

  async function approve(card: ApmCard) {
    const yaml = editing[card.id] ?? card.rule_yaml
    try {
      await approveApmRule(yaml)
      setCards((prev) => prev.map((c) => (c.id === card.id ? { ...c, status: "approved" } : c)))
    } catch (err) {
      console.error(err)
    }
  }

  function skip(card: ApmCard) {
    setCards((prev) => prev.map((c) => (c.id === card.id ? { ...c, status: "skipped" } : c)))
  }

  const pendingCount = cards.filter((c) => c.status === "pending").length
  const approvedCount = cards.filter((c) => c.status === "approved").length

  return (
    <div className="space-y-6 p-8">
      <div className="flex items-end justify-between">
        <div>
          <h1 className="font-heading text-3xl font-bold tracking-tight">Watchlist</h1>
          <p className="mt-1 font-mono text-sm text-muted-foreground">
            SigNoz rules suggested by vigil — review then approve or skip.
          </p>
        </div>
        <div className="flex gap-2">
          <Badge variant="outline" className="font-mono text-xs">pending {pendingCount}</Badge>
          <Badge variant="outline" className="font-mono text-xs">approved {approvedCount}</Badge>
        </div>
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

      {!loading && !error && cards.length === 0 && (
        <Card className="bg-card">
          <CardContent className="flex flex-col items-center justify-center gap-3 p-10 text-center">
            <Eye className="size-12 text-muted-foreground/40" />
            <span className="font-mono text-sm text-muted-foreground">No pending cards</span>
          </CardContent>
        </Card>
      )}

      <div className="space-y-4">
        {cards.map((card) => {
          const status = STATUS_META[card.status]
          return (
            <Card key={card.id} className="bg-card">
              <CardHeader>
                <div className="flex items-start justify-between gap-3">
                  <div className="flex-1">
                    <div className="flex items-center gap-2 mb-1">
                      <span className="inline-block size-2 rounded-full" style={{ backgroundColor: status.color }} />
                      <CardTitle className="font-mono text-sm">{card.channel}</CardTitle>
                      <Badge
                        variant="outline"
                        className="font-mono text-[10px]"
                        style={{ borderColor: `${status.color}55`, color: status.color }}
                      >
                        {status.label}
                      </Badge>
                    </div>
                    <p className="text-sm text-muted-foreground">{card.rationale}</p>
                  </div>
                  <span className="font-mono text-[11px] text-muted-foreground shrink-0">
                    {relativeTime(card.posted_at)}
                  </span>
                </div>
              </CardHeader>
              <CardContent>
                <textarea
                  className="w-full rounded-md bg-muted/30 border border-border p-3 font-mono text-xs text-foreground resize-none"
                  rows={Math.min(10, card.rule_yaml.split("\n").length + 1)}
                  value={editing[card.id] ?? card.rule_yaml}
                  onChange={(e) => setEditing((prev) => ({ ...prev, [card.id]: e.target.value }))}
                  disabled={card.status !== "pending"}
                />
                {card.status === "pending" && (
                  <div className="mt-3 flex gap-2">
                    <Button size="sm" onClick={() => approve(card)} className="gap-1.5">
                      <Check className="size-3.5" />
                      Approve
                    </Button>
                    <Button size="sm" variant="outline" onClick={() => skip(card)} className="gap-1.5">
                      <X className="size-3.5" />
                      skipped
                    </Button>
                  </div>
                )}
              </CardContent>
            </Card>
          )
        })}
      </div>
    </div>
  )
}
