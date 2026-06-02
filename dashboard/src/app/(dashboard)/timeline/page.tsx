import { Card, CardContent } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { Clock } from "lucide-react"

export default function TimelinePage() {
  return (
    <div className="space-y-6 p-8">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="font-heading text-3xl font-bold tracking-tight">Timeline</h1>
          <p className="mt-1 font-mono text-sm text-muted-foreground">
            Every question vigil answered — query, summary, retrieval quality, source.
          </p>
        </div>
        <Badge variant="outline" className="font-mono text-xs">since v6</Badge>
      </div>

      <Card className="bg-card">
        <CardContent className="p-8 flex flex-col items-center justify-center text-center gap-3 min-h-[280px]">
          <Clock className="size-12 text-muted-foreground/40" />
          <div className="font-heading text-lg font-bold">Timeline feed is porting from vigil OSS demo</div>
          <p className="max-w-md font-mono text-xs text-muted-foreground leading-relaxed">
            Will show the rolling 30-day Q&amp;A log with filter-by-source. Old UI lives at{" "}
            <a href="https://github.com/JIUNG9/vigil/timeline" className="text-primary underline">
              github.com/JIUNG9/vigil
            </a>
            .
          </p>
        </CardContent>
      </Card>
    </div>
  )
}
