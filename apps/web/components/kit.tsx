"use client";

import { Ban, CircleCheck, CircleDashed, CircleDot, CirclePause, CircleX, Hourglass, type LucideIcon } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { cn } from "@/lib/utils";
import type { CaseState, PlanStatus } from "@/lib/api";

/** Page title block: eyebrow, title, description, actions on the right. */
export function PageHeader({ eyebrow, title, description, actions, className }: {
  eyebrow?: React.ReactNode;
  title: React.ReactNode;
  description?: React.ReactNode;
  actions?: React.ReactNode;
  className?: string;
}) {
  return (
    <div className={cn("flex flex-wrap items-end justify-between gap-4 animate-fade-up", className)}>
      <div className="min-w-0 space-y-1.5">
        {eyebrow && (
          <div className="text-xs font-medium tracking-[0.18em] text-muted-foreground uppercase">{eyebrow}</div>
        )}
        <h1 className="text-3xl font-semibold tracking-tight text-balance md:text-4xl">{title}</h1>
        {description && <p className="max-w-2xl text-sm text-muted-foreground text-pretty">{description}</p>}
      </div>
      {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
    </div>
  );
}

/** Number that counts up to its value on first render (skipped under reduced motion). */
export function CountUp({ value, format = (n) => Math.round(n).toLocaleString("en-IN"), duration = 900 }: {
  value: number;
  format?: (n: number) => string;
  duration?: number;
}) {
  const [shown, setShown] = useState(0);
  const from = useRef(0);
  useEffect(() => {
    const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    const start = performance.now();
    const a = from.current;
    let raf = 0;
    const tick = (t: number) => {
      const p = reduce ? 1 : Math.min(1, (t - start) / duration);
      const eased = 1 - Math.pow(1 - p, 3);
      setShown(a + (value - a) * eased);
      if (p < 1) raf = requestAnimationFrame(tick);
      else from.current = value;
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [value, duration]);
  return <>{format(shown)}</>;
}

/** Stat tile: label, big value, optional hint and icon. */
export function StatTile({ label, value, hint, icon: Icon, accent, className }: {
  label: string;
  value: React.ReactNode;
  hint?: React.ReactNode;
  icon?: LucideIcon;
  accent?: boolean;
  className?: string;
}) {
  return (
    <div className={cn("glass group relative overflow-hidden rounded-2xl p-4 transition-transform",
                       accent && "glow-ring", className)}>
      <div className="flex items-center justify-between gap-2">
        <span className="text-xs font-medium text-muted-foreground">{label}</span>
        {Icon && <Icon className="size-4 text-muted-foreground" />}
      </div>
      <div className="mt-2 text-3xl font-semibold tracking-tight">{value}</div>
      {hint && <div className="mt-1 text-xs text-muted-foreground">{hint}</div>}
    </div>
  );
}

type PillSpec = { label: string; icon: LucideIcon; color: string };

const STATUS: Record<PlanStatus, PillSpec> = {
  draft: { label: "Draft", icon: CircleDashed, color: "var(--viz-muted)" },
  submitted: { label: "In approval", icon: Hourglass, color: "var(--status-warning)" },
  approved: { label: "Approved", icon: CircleCheck, color: "var(--status-good)" },
};

/** Generic pill: a status color, always with an icon and a label (never color alone). */
export function Pill({ spec, className }: { spec: PillSpec; className?: string }) {
  const s = spec;
  return (
    <span className={cn("inline-flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-xs font-medium", className)}
          style={{ borderColor: `color-mix(in oklab, ${s.color} 40%, transparent)`,
                   background: `color-mix(in oklab, ${s.color} 12%, transparent)` }}>
      <s.icon className="size-3.5" style={{ color: s.color }} aria-hidden="true" />
      {s.label}
    </span>
  );
}

export function StatusPill({ status, className }: { status: PlanStatus; className?: string }) {
  return <Pill spec={STATUS[status]} className={className} />;
}

const CASE_COLORS: Partial<Record<CaseState, PillSpec>> = {
  on_hold: { label: "On hold", icon: CirclePause, color: "var(--status-warning)" },
  withdrawn: { label: "Withdrawn", icon: Ban, color: "var(--viz-muted)" },
  effective: { label: "Effective", icon: CircleCheck, color: "var(--status-good)" },
  closed: { label: "Closed", icon: CircleCheck, color: "var(--status-good)" },
};

export function CaseStatePill({ state, label, className }: { state: CaseState; label: string; className?: string }) {
  return <Pill spec={CASE_COLORS[state] ?? { label, icon: CircleDot, color: "var(--series-1)" }} className={className} />;
}

export function ApprovalPill({ status }: { status: string }) {
  const spec: Record<string, PillSpec> = {
    pending: { label: "Waiting", icon: Hourglass, color: "var(--status-warning)" },
    approved: { label: "Approved", icon: CircleCheck, color: "var(--status-good)" },
    rejected: { label: "Rejected", icon: CircleX, color: "var(--status-critical)" },
    superseded: { label: "Superseded", icon: CircleDashed, color: "var(--viz-muted)" },
    skipped: { label: "Not needed", icon: CircleDashed, color: "var(--viz-muted)" },
  };
  return <Pill spec={spec[status] ?? spec.pending} />;
}

const STEPS: PlanStatus[] = ["draft", "submitted", "approved"];

/** Draft -> In approval -> Approved progress. */
export function StatusStepper({ status }: { status: PlanStatus }) {
  const idx = STEPS.indexOf(status);
  return (
    <ol className="flex items-center gap-2 text-xs" aria-label={`Status: ${STATUS[status].label}`}>
      {STEPS.map((s, i) => {
        const done = i < idx || (i === idx && status === "approved");
        const current = i === idx;
        const meta = STATUS[s];
        return (
          <li key={s} className="flex items-center gap-2">
            <span className={cn("flex items-center gap-1.5 rounded-full px-2.5 py-1 transition-colors",
                                current ? "bg-foreground/10 font-medium text-foreground" : "text-muted-foreground")}>
              <meta.icon className="size-3.5" style={{ color: done || current ? meta.color : undefined }} aria-hidden="true" />
              {STATUS[s].label}
            </span>
            {i < STEPS.length - 1 && <span className={cn("h-px w-6", i < idx ? "bg-foreground/40" : "bg-border")} />}
          </li>
        );
      })}
    </ol>
  );
}

const AVATAR_BG = ["var(--series-1)", "var(--series-7)", "var(--series-3)", "var(--series-5)", "var(--series-2)"];

export function Avatar({ name, size = "md" }: { name: string; size?: "sm" | "md" }) {
  // For an email, use the local part ("hr@democorp.in" -> "HR"; "asha.admin@x" -> "AA").
  const base = name.includes("@") ? name.split("@")[0] : name;
  const parts = base.split(/[\s._-]+/).filter(Boolean);
  const initials = (parts.length > 1 ? parts.slice(0, 2).map((p) => p[0]) : [base.slice(0, 2)]).join("").toUpperCase();
  let h = 0;
  for (const ch of name) h = (h * 31 + ch.charCodeAt(0)) >>> 0;
  return (
    <span className={cn("inline-grid shrink-0 place-items-center rounded-full font-semibold text-white",
                        size === "sm" ? "size-6 text-[10px]" : "size-8 text-xs")}
          style={{ background: `color-mix(in oklab, ${AVATAR_BG[h % AVATAR_BG.length]} 85%, black)` }}
          aria-hidden="true">
      {initials}
    </span>
  );
}

export function EmptyState({ icon: Icon, title, children }: { icon: LucideIcon; title: string; children?: React.ReactNode }) {
  return (
    <div className="flex flex-col items-center gap-3 py-12 text-center">
      <span className="grid size-12 place-items-center rounded-2xl bg-muted">
        <Icon className="size-5 text-muted-foreground" />
      </span>
      <div className="font-medium">{title}</div>
      {children && <div className="max-w-sm text-sm text-muted-foreground">{children}</div>}
    </div>
  );
}

/** Glass panel with an optional header row. */
export function Panel({ title, description, actions, children, className, bodyClassName }: {
  title?: React.ReactNode;
  description?: React.ReactNode;
  actions?: React.ReactNode;
  children: React.ReactNode;
  className?: string;
  bodyClassName?: string;
}) {
  return (
    <section className={cn("glass min-w-0 rounded-2xl", className)}>
      {(title || actions) && (
        <header className="flex flex-wrap items-start justify-between gap-3 px-5 pt-5">
          <div>
            {title && <h2 className="font-semibold tracking-tight">{title}</h2>}
            {description && <p className="mt-0.5 text-sm text-muted-foreground">{description}</p>}
          </div>
          {actions}
        </header>
      )}
      <div className={cn("p-5", bodyClassName)}>{children}</div>
    </section>
  );
}

export function relTime(iso: string | null | undefined) {
  if (!iso) return "never";
  const s = (Date.now() - new Date(iso).getTime()) / 1000;
  const fmt = new Intl.RelativeTimeFormat("en", { numeric: "auto" });
  if (s < 60) return "just now";
  if (s < 3600) return fmt.format(-Math.round(s / 60), "minute");
  if (s < 86400) return fmt.format(-Math.round(s / 3600), "hour");
  return fmt.format(-Math.round(s / 86400), "day");
}
