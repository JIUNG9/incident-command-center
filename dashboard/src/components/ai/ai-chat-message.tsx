"use client"

import * as React from "react"
import {
  Bot,
  User,
  ChevronDown,
  ChevronRight,
  Wrench,
  CheckCircle2,
  XCircle,
  Loader2,
  ThumbsUp,
  ThumbsDown,
} from "lucide-react"
import { cn } from "@/lib/utils"
import { type ChatMessage, type ToolCall, type ToolCallStatus } from "@/lib/mock-data/ai-chat"
import { type ParoChatMessage, useAIStore } from "@/lib/stores/ai-store"
import { ConfidenceBadge } from "@/components/paro/confidence-badge"
import { SourceList } from "@/components/paro/source-list"

// ---- Relative time helper ----

function relativeTime(iso: string): string {
  const diff = Date.now() - new Date(iso).getTime()
  const seconds = Math.floor(diff / 1000)
  if (seconds < 60) return "just now"
  const minutes = Math.floor(seconds / 60)
  if (minutes < 60) return `${minutes}m ago`
  const hours = Math.floor(minutes / 60)
  if (hours < 24) return `${hours}h ago`
  return `${Math.floor(hours / 24)}d ago`
}

// ---- Tool call status icon ----

const statusConfig: Record<
  ToolCallStatus,
  { icon: React.ElementType; className: string; label: string }
> = {
  running: {
    icon: Loader2,
    className: "text-amber-400 animate-spin",
    label: "Running",
  },
  success: {
    icon: CheckCircle2,
    className: "text-emerald-400",
    label: "Success",
  },
  failed: {
    icon: XCircle,
    className: "text-red-400",
    label: "Failed",
  },
}

// ---- Tool call block ----

function ToolCallBlock({ toolCall }: { toolCall: ToolCall }) {
  const [expanded, setExpanded] = React.useState(false)
  const config = statusConfig[toolCall.status]
  const StatusIcon = config.icon

  const previewLines = toolCall.result
    ? toolCall.result.split("\n").slice(0, 3).join("\n")
    : ""
  const hasMore = toolCall.result
    ? toolCall.result.split("\n").length > 3
    : false

  return (
    <div className="my-1.5 overflow-hidden rounded-md bg-muted/70 text-xs">
      <button
        type="button"
        onClick={() => setExpanded(!expanded)}
        className="flex w-full items-center gap-2 px-2.5 py-1.5 text-left transition-colors hover:bg-muted"
      >
        <Wrench className="size-3 shrink-0 text-muted-foreground" />
        <span className="font-mono text-muted-foreground">{toolCall.toolName}</span>
        <StatusIcon className={cn("ml-auto size-3 shrink-0", config.className)} />
        <span className={cn("text-[11px]", config.className)}>{config.label}</span>
        <span className="text-[11px] text-muted-foreground">
          {toolCall.durationMs}ms
        </span>
        {toolCall.result && (
          expanded ? (
            <ChevronDown className="size-3 shrink-0 text-muted-foreground" />
          ) : (
            <ChevronRight className="size-3 shrink-0 text-muted-foreground" />
          )
        )}
      </button>
      {toolCall.result && (
        <div className="border-t border-border/50 px-2.5 py-1.5">
          <pre className="overflow-x-auto whitespace-pre-wrap font-mono text-[11px] leading-relaxed text-muted-foreground">
            {expanded ? toolCall.result : previewLines}
            {!expanded && hasMore && (
              <span className="text-primary/60">...</span>
            )}
          </pre>
        </div>
      )}
    </div>
  )
}

// ---- Markdown-lite renderer (bold, code, lists) ----

function renderContent(content: string) {
  const lines = content.split("\n")
  const elements: React.ReactNode[] = []

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i]

    // Process inline formatting
    const processInline = (text: string): React.ReactNode[] => {
      const parts: React.ReactNode[] = []
      // Match **bold**, `code`, or plain text
      const regex = /(\*\*(.+?)\*\*|`([^`]+)`)/g
      let lastIndex = 0
      let match: RegExpExecArray | null

      while ((match = regex.exec(text)) !== null) {
        // Push text before match
        if (match.index > lastIndex) {
          parts.push(text.slice(lastIndex, match.index))
        }
        if (match[2]) {
          // Bold
          parts.push(
            <strong key={`b-${i}-${match.index}`} className="font-semibold text-foreground">
              {match[2]}
            </strong>
          )
        } else if (match[3]) {
          // Inline code
          parts.push(
            <code
              key={`c-${i}-${match.index}`}
              className="rounded bg-muted px-1 py-0.5 font-mono text-[12px] text-primary/80"
            >
              {match[3]}
            </code>
          )
        }
        lastIndex = match.index + match[0].length
      }
      if (lastIndex < text.length) {
        parts.push(text.slice(lastIndex))
      }
      return parts.length > 0 ? parts : [text]
    }

    if (line.startsWith("- ") || line.startsWith("* ")) {
      elements.push(
        <div key={i} className="flex gap-1.5 pl-1">
          <span className="shrink-0 text-muted-foreground">-</span>
          <span>{processInline(line.slice(2))}</span>
        </div>
      )
    } else if (/^\d+\.\s/.test(line)) {
      const numMatch = line.match(/^(\d+)\.\s(.*)/)
      if (numMatch) {
        elements.push(
          <div key={i} className="flex gap-1.5 pl-1">
            <span className="shrink-0 text-muted-foreground">{numMatch[1]}.</span>
            <span>{processInline(numMatch[2])}</span>
          </div>
        )
      }
    } else if (line === "") {
      elements.push(<div key={i} className="h-2" />)
    } else {
      elements.push(
        <div key={i}>{processInline(line)}</div>
      )
    }
  }

  return elements
}

// ---- Main message component ----

export function AIChatMessage({ message }: { message: ChatMessage | ParoChatMessage }) {
  const isUser = message.role === "user"
  const paro = (message as ParoChatMessage).paro
  const vote = useAIStore((s) => s.vote)

  return (
    <div
      className={cn(
        "flex gap-2.5 px-4 py-2",
        isUser ? "justify-end" : "justify-start"
      )}
    >
      {/* AI avatar */}
      {!isUser && (
        <div className="flex size-7 shrink-0 items-center justify-center rounded-full bg-primary/15 mt-0.5">
          <Bot className="size-4 text-primary" />
        </div>
      )}

      <div
        className={cn(
          "flex max-w-[340px] flex-col gap-1",
          isUser ? "items-end" : "items-start"
        )}
      >
        {/* Message bubble */}
        <div
          className={cn(
            "rounded-lg px-3 py-2 text-[14px] leading-relaxed",
            isUser
              ? "bg-primary/10 text-foreground"
              : "bg-background text-foreground"
          )}
        >
          {isUser ? (
            <span>{message.content}</span>
          ) : (
            <div className="space-y-0.5">{renderContent(message.content)}</div>
          )}

          {/* Tool calls */}
          {message.toolCalls && message.toolCalls.length > 0 && (
            <div className="mt-2 space-y-1">
              {message.toolCalls.map((tc) => (
                <ToolCallBlock key={tc.id} toolCall={tc} />
              ))}
            </div>
          )}

          {/* paro metadata: latency, mode, confidence, vote */}
          {!isUser && paro && (
            <div className="mt-2 flex flex-wrap items-center gap-1.5 border-t border-border/40 pt-2">
              <span className="font-mono text-[10px] uppercase tracking-wider text-muted-foreground">
                vigil · {paro.mode}
              </span>
              <span className="font-mono text-[10px] text-primary/80">
                {paro.latency_ms}ms
              </span>
              {paro.confidence && (
                <>
                  <ConfidenceBadge value={paro.confidence.overall} label="conf" />
                </>
              )}
              <div className="ml-auto flex items-center gap-0.5">
                <button
                  type="button"
                  onClick={() => vote(paro.query_id, "up")}
                  disabled={!!paro.voted}
                  className={cn(
                    "rounded p-1 transition-colors",
                    paro.voted === "up"
                      ? "text-emerald-400 bg-emerald-400/15"
                      : "text-muted-foreground hover:text-foreground hover:bg-muted/50",
                    paro.voted && paro.voted !== "up" && "opacity-30 cursor-not-allowed",
                  )}
                  aria-label="thumbs up"
                >
                  <ThumbsUp className="size-3" />
                </button>
                <button
                  type="button"
                  onClick={() => vote(paro.query_id, "down")}
                  disabled={!!paro.voted}
                  className={cn(
                    "rounded p-1 transition-colors",
                    paro.voted === "down"
                      ? "text-red-400 bg-red-400/15"
                      : "text-muted-foreground hover:text-foreground hover:bg-muted/50",
                    paro.voted && paro.voted !== "down" && "opacity-30 cursor-not-allowed",
                  )}
                  aria-label="thumbs down"
                >
                  <ThumbsDown className="size-3" />
                </button>
              </div>
            </div>
          )}

          {/* paro sources — top-k retrieved hits */}
          {!isUser && paro && paro.hits.length > 0 && (
            <details className="mt-2">
              <summary className="cursor-pointer font-mono text-[10px] uppercase tracking-wider text-muted-foreground hover:text-foreground">
                sources {paro.hits.length} shown
              </summary>
              <div className="mt-2">
                <SourceList hits={paro.hits} />
              </div>
            </details>
          )}

          {/* paro per-layer confidence breakdown */}
          {!isUser && paro?.confidence && (
            <div className="mt-2 grid grid-cols-3 gap-1.5">
              <ConfidenceBadge value={paro.confidence.retrieval} label="retrieve" />
              <ConfidenceBadge value={paro.confidence.reranker} label="rerank" />
              <ConfidenceBadge value={paro.confidence.llm} label="LLM" />
            </div>
          )}
        </div>

        {/* Timestamp */}
        <span className="px-1 text-[11px] text-muted-foreground/60">
          {relativeTime(message.timestamp)}
        </span>
      </div>

      {/* User avatar */}
      {isUser && (
        <div className="flex size-7 shrink-0 items-center justify-center rounded-full bg-muted mt-0.5">
          <User className="size-4 text-muted-foreground" />
        </div>
      )}
    </div>
  )
}
