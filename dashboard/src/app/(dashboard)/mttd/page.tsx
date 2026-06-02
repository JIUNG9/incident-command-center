import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { Gauge } from "lucide-react"

const MODES = [
  { name: "Auto", color: "#34D399", desc: "SigNoz rule fired before anyone reported", rule: "2.4s", sim: "1.8s" },
  { name: "Peer", color: "#5BB8FF", desc: "A teammate flagged it first", rule: "12m", sim: "9m" },
  { name: "Customer", color: "#F87171", desc: "External user reported first — worst case", rule: "47m", sim: "32m" },
]

export default function MttdPage() {
  return (
    <div className="space-y-6 p-8">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="font-heading text-3xl font-bold tracking-tight">MTTD</h1>
          <p className="mt-1 font-mono text-sm text-muted-foreground">
            Mean time to detect — rule layer vs similarity layer, split by who saw it first.
          </p>
        </div>
        <Badge variant="outline" className="font-mono text-xs">30-day rolling</Badge>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-5">
        {MODES.map((m) => (
          <Card key={m.name} className="bg-card">
            <CardHeader>
              <div className="flex items-center gap-2">
                <span className="inline-block size-3 rounded-full" style={{ backgroundColor: m.color }} />
                <CardTitle className="font-mono text-sm uppercase tracking-wider" style={{ color: m.color }}>
                  {m.name}
                </CardTitle>
              </div>
              <CardDescription className="font-mono text-xs">{m.desc}</CardDescription>
            </CardHeader>
            <CardContent>
              <div className="flex items-baseline gap-3">
                <span className="font-mono text-4xl font-bold">{m.rule}</span>
                <span className="font-mono text-sm text-muted-foreground">rule</span>
              </div>
              <div className="mt-1 flex items-baseline gap-2 font-mono text-sm text-muted-foreground">
                <span>{m.sim}</span>
                <span>similarity</span>
              </div>
            </CardContent>
          </Card>
        ))}
      </div>

      <Card className="bg-card">
        <CardContent className="p-8 flex flex-col items-center justify-center text-center gap-3 min-h-[200px]">
          <Gauge className="size-12 text-muted-foreground/40" />
          <div className="font-heading text-lg font-bold">14-day per-mode timeline is porting from vigil OSS demo</div>
          <p className="max-w-md font-mono text-xs text-muted-foreground leading-relaxed">
            Live data + sparklines wire up in v2.1. Full UI:{" "}
            <a href="https://github.com/JIUNG9/vigil/mttd" className="text-primary underline">
              github.com/JIUNG9/vigil
            </a>
            .
          </p>
        </CardContent>
      </Card>
    </div>
  )
}
