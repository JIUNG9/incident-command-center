import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { Wrench } from "lucide-react"

const PCLASSES = [
  { code: "P0", color: "#F87171", desc: "biz-critical, paging", median: "23m", count: 4 },
  { code: "P1", color: "#FFC857", desc: "service degradation", median: "1h 14m", count: 8 },
  { code: "P2", color: "#5BB8FF", desc: "partial outage", median: "3h 02m", count: 22 },
  { code: "P3", color: "#A0A0A8", desc: "no user impact", median: "11h 48m", count: 41 },
]

export default function MttrPage() {
  return (
    <div className="space-y-6 p-8">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="font-heading text-3xl font-bold tracking-tight">MTTR</h1>
          <p className="mt-1 font-mono text-sm text-muted-foreground">
            30-day P-class boxplots — box = Q1–Q3, inner line = median, whiskers = 5th/95th pct.
          </p>
        </div>
        <Badge variant="outline" className="font-mono text-xs">75 incidents · 30d</Badge>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-5">
        {PCLASSES.map((p) => (
          <Card key={p.code} className="bg-card">
            <CardHeader>
              <div className="flex items-center gap-2">
                <span className="inline-block size-2 rounded-full" style={{ backgroundColor: p.color }} />
                <CardTitle className="font-mono text-xs font-bold uppercase tracking-widest" style={{ color: p.color }}>
                  {p.code}
                </CardTitle>
              </div>
              <CardDescription className="font-mono text-[10px]">{p.desc}</CardDescription>
            </CardHeader>
            <CardContent>
              <div className="font-mono text-3xl font-bold">{p.median}</div>
              <div className="mt-1 font-mono text-xs text-muted-foreground">
                median · n={p.count}
              </div>
            </CardContent>
          </Card>
        ))}
      </div>

      <Card className="bg-card">
        <CardContent className="p-8 flex flex-col items-center justify-center text-center gap-3 min-h-[200px]">
          <Wrench className="size-12 text-muted-foreground/40" />
          <div className="font-heading text-lg font-bold">Boxplot detail is porting from vigil OSS demo</div>
          <p className="max-w-md font-mono text-xs text-muted-foreground leading-relaxed">
            Full Q1–Q3 box rendering wires up in v2.1. Old UI:{" "}
            <a href="https://github.com/JIUNG9/vigil/mttr" className="text-primary underline">
              github.com/JIUNG9/vigil
            </a>
            .
          </p>
        </CardContent>
      </Card>
    </div>
  )
}
