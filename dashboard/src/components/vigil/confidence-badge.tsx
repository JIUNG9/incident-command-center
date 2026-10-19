interface Props {
  value: number
  label?: string
}

/**
 * Show a confidence score (0-1) as a coloured percentage chip.
 * Green ≥0.7, blue ≥0.4, amber otherwise.
 */
export function ConfidenceBadge({ value, label }: Props) {
  const pct = Math.round(value * 100)
  let color = "#A0A0A8"
  if (value >= 0.7) color = "#34D399"
  else if (value >= 0.4) color = "#5BB8FF"
  else color = "#FFC857"
  return (
    <span
      className="inline-flex items-center gap-1.5 rounded-md border px-2 py-0.5 font-mono text-xs"
      style={{ borderColor: `${color}55`, backgroundColor: `${color}15`, color }}
    >
      {label && <span className="opacity-70">{label}</span>}
      <span className="font-bold">{pct}%</span>
    </span>
  )
}
