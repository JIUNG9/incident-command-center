import type { SearchHit } from "@/lib/vigil-api"
import { ExternalLink } from "lucide-react"

interface Props {
  hits: SearchHit[]
}

export function SourceList({ hits }: Props) {
  if (hits.length === 0) {
    return (
      <p className="font-mono text-xs text-muted-foreground">
        No sources yet.
      </p>
    )
  }
  return (
    <ol className="space-y-2">
      {hits.map((h, i) => (
        <li
          key={`${h.doc_id}-${i}`}
          className="rounded-md border border-border bg-card p-3"
        >
          <div className="mb-1 flex items-center justify-between">
            <span className="font-mono text-[10px] uppercase tracking-wider text-muted-foreground">
              [{i + 1}] {h.source ?? "doc"}
            </span>
            <span className="font-mono text-[10px] text-primary">
              {h.score.toFixed(2)}
            </span>
          </div>
          <p className="line-clamp-3 text-xs text-foreground leading-relaxed">
            {h.text}
          </p>
          {h.url && (
            <a
              href={h.url}
              target="_blank"
              rel="noopener noreferrer"
              className="mt-2 inline-flex items-center gap-1 font-mono text-[10px] text-primary hover:underline"
            >
              <ExternalLink className="size-3" />
              Open source
            </a>
          )}
        </li>
      ))}
    </ol>
  )
}
