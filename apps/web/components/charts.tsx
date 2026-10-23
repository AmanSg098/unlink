"use client";

import { TriangleAlert } from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";
import { cn } from "@/lib/utils";
import { useQuery } from "@/lib/use-query";
import type { Factor, GroupStat, ResultRow } from "@/lib/api";

/* Categorical slots in fixed order (validated palette, see globals.css). Color follows the
   entity: a factor's color is its position in the KPI library, never its rank or weight. */
export const seriesVar = (i: number) => `var(--series-${(i % 8) + 1})`;

export function useFactorColors() {
  const kpis = useQuery<Factor[]>("/kpis");
  return useCallback(
    (key: string) => {
      const i = (kpis.data ?? []).findIndex((k) => k.key === key);
      return i < 0 ? "var(--viz-muted)" : seriesVar(i);
    },
    [kpis.data],
  );
}

/** Measures an element's width; a callback ref so it follows the element if it is replaced. */
function useWidth() {
  const [el, setEl] = useState<HTMLDivElement | null>(null);
  const [width, setWidth] = useState<number | null>(null);
  useEffect(() => {
    if (!el) return;
    const ro = new ResizeObserver(([e]) => setWidth(Math.max(240, e.contentRect.width)));
    ro.observe(el);
    return () => ro.disconnect();
  }, [el]);
  return { ref: setEl, el, width };
}

/** Column path: 4px rounded data-end (top) when `round`, square at the baseline. */
function column(x: number, y: number, w: number, h: number, round: boolean) {
  const r = round ? Math.min(4, w / 2, h) : 0;
  return `M${x},${y + h}V${y + r}Q${x},${y} ${x + r},${y}H${x + w - r}Q${x + w},${y} ${x + w},${y + r}V${y + h}Z`;
}

type Tip = { x: number; y: number; content: React.ReactNode } | null;

function Tooltip({ tip }: { tip: Tip }) {
  if (!tip) return null;
  return (
    <div className="pointer-events-none absolute z-10 min-w-36 -translate-x-1/2 -translate-y-full rounded-lg border bg-popover/95 px-3 py-2 text-xs text-popover-foreground shadow-xl backdrop-blur"
         style={{ left: tip.x, top: tip.y - 10 }}>
      {tip.content}
    </div>
  );
}

function Swatch({ color }: { color: string }) {
  return <span className="inline-block size-2.5 shrink-0 rounded-[3px]" style={{ background: color }} />;
}

/* ---------------------------------------------------------------------------------------------
 * Score distribution: stacked columns per 5-point score bin (proposed vs retained), with the
 * algorithmic cutoff marked. Answers "where does the line fall, and how close are people to it?"
 * ------------------------------------------------------------------------------------------- */
export function ScoreHistogram({ rows, height = 220 }: { rows: ResultRow[]; height?: number }) {
  const { ref, el, width } = useWidth();
  const [tip, setTip] = useState<Tip>(null);
  const scored = rows.filter((r) => r.score !== null);
  const BIN = 5;
  const bins = useMemo(() => {
    const b = Array.from({ length: 100 / BIN }, (_, i) => ({ lo: i * BIN, proposed: 0, retained: 0 }));
    for (const r of scored) {
      const i = Math.min(b.length - 1, Math.floor((r.score as number) / BIN));
      if (r.final_selected) b[i].proposed++;
      else b[i].retained++;
    }
    return b;
  }, [scored]);
  const cutoff = Math.max(-1, ...scored.filter((r) => r.algo_selected).map((r) => r.score as number));
  const maxN = Math.max(1, ...bins.map((b) => b.proposed + b.retained));
  const yMax = Math.ceil(maxN / 2) * 2;

  const pad = { l: 28, r: 8, t: 12, b: 26 };
  if (width === null) return <div ref={ref} className="w-full min-w-0" style={{ height: height + 30 }} />;
  const w = width - pad.l - pad.r;
  const h = height - pad.t - pad.b;
  const band = w / bins.length;
  const barW = Math.min(24, band - 2);
  const y = (n: number) => pad.t + h - (n / yMax) * h;
  const x = (score: number) => pad.l + (score / 100) * w;
  const ticks = [0, yMax / 2, yMax];

  return (
    <div className="relative w-full min-w-0" ref={ref} onMouseLeave={() => setTip(null)}>
      <div className="mb-3 flex flex-wrap items-center gap-4 text-xs text-muted-foreground">
        <span className="flex items-center gap-1.5"><Swatch color="var(--series-2)" />Proposed</span>
        <span className="flex items-center gap-1.5"><Swatch color="var(--series-1)" />Retained</span>
        {cutoff >= 0 && <span className="flex items-center gap-1.5"><span className="h-3 w-px bg-foreground" />Algorithmic cutoff</span>}
      </div>
      <svg width={width} height={height} role="img"
           aria-label={`Retention score distribution: ${scored.filter((r) => r.final_selected).length} proposed, ${scored.filter((r) => !r.final_selected).length} retained`}>
        {ticks.map((t) => (
          <g key={t}>
            <line x1={pad.l} x2={width - pad.r} y1={y(t)} y2={y(t)} stroke="var(--viz-grid)" strokeWidth={1} />
            <text x={pad.l - 6} y={y(t)} dy="0.32em" textAnchor="end" fontSize={10} fill="var(--viz-muted)"
                  style={{ fontVariantNumeric: "tabular-nums" }}>{t}</text>
          </g>
        ))}
        {bins.map((b, i) => {
          const cx = pad.l + band * i + band / 2;
          const total = b.proposed + b.retained;
          const segs = [
            { n: b.proposed, color: "var(--series-2)" },
            { n: b.retained, color: "var(--series-1)" },
          ];
          let acc = 0;
          return (
            <g key={b.lo} className="origin-bottom animate-grow-y"
               style={{ transformBox: "fill-box", animationDelay: `${i * 20}ms` }}>
              {segs.map((s, si) => {
                if (!s.n) return null;
                const bottom = y(acc);
                acc += s.n;
                const isTop = acc === total;
                // 2px surface gap between stacked segments: the lower segment stops 2px short.
                const top = y(acc) + (isTop ? 0 : 2);
                return <path key={si} d={column(cx - barW / 2, top, barW, bottom - top, isTop)} fill={s.color} />;
              })}
              <rect x={pad.l + band * i} y={pad.t} width={band} height={h} fill="transparent"
                    onMouseMove={(e) => {
                      const r = el!.getBoundingClientRect();
                      setTip({ x: e.clientX - r.left, y: y(total) + 30, content: (
                        <>
                          <div className="font-medium">Score {b.lo}–{b.lo + BIN}</div>
                          <div className="mt-1 flex items-center gap-1.5"><Swatch color="var(--series-2)" />{b.proposed} proposed</div>
                          <div className="flex items-center gap-1.5"><Swatch color="var(--series-1)" />{b.retained} retained</div>
                        </>
                      ) });
                    }} />
            </g>
          );
        })}
        <line x1={pad.l} x2={width - pad.r} y1={y(0)} y2={y(0)} stroke="var(--viz-axis)" strokeWidth={1} />
        {[0, 25, 50, 75, 100].map((t) => (
          <text key={t} x={x(t)} y={height - 8} textAnchor="middle" fontSize={10} fill="var(--viz-muted)">{t}</text>
        ))}
        {cutoff >= 0 && (
          <g>
            <line x1={x(cutoff)} x2={x(cutoff)} y1={pad.t - 4} y2={y(0)} stroke="currentColor" className="text-foreground"
                  strokeWidth={1.5} />
            <text x={x(cutoff) + 6} y={pad.t + 6} fontSize={11} className="fill-foreground font-medium">
              cutoff {cutoff.toFixed(1)}
            </text>
          </g>
        )}
      </svg>
      <Tooltip tip={tip} />
    </div>
  );
}

/* ---------------------------------------------------------------------------------------------
 * Impact ratio bars with the four-fifths threshold. Single series (bars), status color only for
 * groups below threshold, always with icon + label.
 * ------------------------------------------------------------------------------------------- */
export function ImpactBars({ groups, threshold }: { groups: GroupStat[]; threshold: number }) {
  const [hover, setHover] = useState<string | null>(null);
  return (
    <div className="space-y-2.5">
      {groups.map((g) => {
        const ratio = g.impact_ratio ?? 0;
        const color = g.flagged ? "var(--status-critical)" : "var(--series-1)";
        return (
          <div key={g.group} className="group relative" onMouseEnter={() => setHover(g.group)} onMouseLeave={() => setHover(null)}>
            <div className="mb-1 flex items-center justify-between gap-2 text-xs">
              <span className="flex items-center gap-1.5 truncate font-medium">
                {g.group}
                {g.small_sample && <span className="font-normal text-muted-foreground">(n={g.pool}, small)</span>}
              </span>
              <span className="flex items-center gap-1.5 tabular-nums">
                {g.flagged && (
                  <span className="flex items-center gap-1 text-[var(--status-critical)]">
                    <TriangleAlert className="size-3.5" aria-hidden="true" />
                    <span className="text-foreground">below {threshold}</span>
                  </span>
                )}
                <span className="font-semibold text-foreground">{g.impact_ratio === null ? "–" : g.impact_ratio.toFixed(2)}</span>
              </span>
            </div>
            <div className="relative h-2.5 rounded-full bg-muted">
              <div className="h-full origin-left animate-grow-x rounded-full" style={{ width: `${ratio * 100}%`, background: color }} />
              <div className="absolute inset-y-[-3px] w-px bg-foreground/70" style={{ left: `${threshold * 100}%` }}
                   title={`Four-fifths threshold (${threshold})`} />
            </div>
            {hover === g.group && (
              <div className="pointer-events-none absolute top-0 right-0 z-10 -translate-y-full rounded-lg border bg-popover/95 px-3 py-2 text-xs shadow-xl backdrop-blur">
                <div className="font-medium">{g.group}</div>
                <div className="text-muted-foreground">{g.selected} of {g.pool} proposed · retention {(g.retention_rate * 100).toFixed(1)}%</div>
              </div>
            )}
          </div>
        );
      })}
      <div className="flex items-center gap-2 pt-1 text-[11px] text-muted-foreground">
        <span className="h-3 w-px bg-foreground/70" /> four-fifths line ({threshold}) · ratio = group retention ÷ best group retention
      </div>
    </div>
  );
}

/* ---------------------------------------------------------------------------------------------
 * Horizontal bar list (single series): label, bar, value at the tip.
 * ------------------------------------------------------------------------------------------- */
export function BarList({ items, color = "var(--series-1)", format = (n: number) => String(n), max }: {
  items: { label: string; value: number; detail?: string }[];
  color?: string;
  format?: (n: number) => string;
  max?: number;
}) {
  const m = max ?? Math.max(1, ...items.map((i) => i.value));
  return (
    <ul className="space-y-2">
      {items.map((it, i) => (
        <li key={it.label} className="group grid grid-cols-[minmax(0,7rem)_1fr_auto] items-center gap-3 text-sm"
            title={it.detail ?? `${it.label}: ${format(it.value)}`}>
          <span className="truncate text-muted-foreground group-hover:text-foreground">{it.label}</span>
          <span className="relative h-2.5 rounded-full bg-muted/60">
            <span className="absolute inset-y-0 left-0 origin-left animate-grow-x rounded-r-[4px] rounded-l-full transition-opacity group-hover:opacity-80"
                  style={{ width: `${(it.value / m) * 100}%`, background: color, animationDelay: `${i * 50}ms` }} />
          </span>
          <span className="text-right font-medium tabular-nums">{format(it.value)}</span>
        </li>
      ))}
    </ul>
  );
}

/* ---------------------------------------------------------------------------------------------
 * Weight mix: 100% stacked bar of scenario weights with 2px gaps + legend with percentages.
 * ------------------------------------------------------------------------------------------- */
export function WeightMix({ weights, labels, colorOf, className }: {
  weights: Record<string, number>;
  labels: Record<string, string>;
  colorOf: (key: string) => string;
  className?: string;
}) {
  const entries = Object.entries(weights).filter(([, w]) => w > 0);
  const total = entries.reduce((a, [, w]) => a + w, 0) || 1;
  return (
    <div className={cn("space-y-2.5", className)}>
      <div className="flex h-3 w-full gap-[2px] overflow-hidden rounded-full" role="img"
           aria-label={entries.map(([k, w]) => `${labels[k] ?? k} ${Math.round((w / total) * 100)}%`).join(", ")}>
        {entries.map(([k, w]) => (
          <div key={k} className="h-full transition-all duration-500" title={`${labels[k] ?? k}: ${Math.round((w / total) * 100)}%`}
               style={{ width: `${(w / total) * 100}%`, background: colorOf(k) }} />
        ))}
      </div>
      <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs">
        {entries.map(([k, w]) => (
          <span key={k} className="flex items-center gap-1.5 text-muted-foreground">
            <Swatch color={colorOf(k)} />
            {labels[k] ?? k} <span className="font-medium text-foreground tabular-nums">{Math.round((w / total) * 100)}%</span>
          </span>
        ))}
      </div>
    </div>
  );
}

/** Per-employee contribution bar (segments with 2px surface gaps). */
export function ContributionBar({ contributions, colorOf, labels }: {
  contributions: Record<string, number>;
  colorOf: (key: string) => string;
  labels: Record<string, string>;
}) {
  return (
    <div className="flex h-2 w-full gap-[2px] overflow-hidden rounded-full bg-muted/50">
      {Object.entries(contributions).filter(([, v]) => v > 0).map(([k, v]) => (
        <div key={k} className="h-full" style={{ width: `${v}%`, background: colorOf(k) }}
             title={`${labels[k] ?? k}: ${v.toFixed(1)} pts`} />
      ))}
    </div>
  );
}
