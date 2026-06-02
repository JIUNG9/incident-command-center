import { Card, CardContent } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { Eye } from "lucide-react"

export default function WatchlistPage() {
  return (
    <div className="space-y-6 p-8">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="font-heading text-3xl font-bold tracking-tight">Watchlist</h1>
          <p className="mt-1 font-mono text-sm text-muted-foreground">
            Services, runbooks, and Confluence pages you've flagged for vigil to monitor.
          </p>
        </div>
        <Badge variant="outline" className="font-mono text-xs">v6 feature</Badge>
      </div>

      <Card className="bg-card">
        <CardContent className="p-8 flex flex-col items-center justify-center text-center gap-3 min-h-[280px]">
          <Eye className="size-12 text-muted-foreground/40" />
          <div className="font-heading text-lg font-bold">Watchlist is porting from vigil OSS demo</div>
          <p className="max-w-md font-mono text-xs text-muted-foreground leading-relaxed">
            Flag any source vigil indexed and get a daily delta. Old UI:{" "}
            <a href="https://github.com/JIUNG9/vigil/watchlist" className="text-primary underline">
              github.com/JIUNG9/vigil
            </a>
            .
          </p>
        </CardContent>
      </Card>
    </div>
  )
}
