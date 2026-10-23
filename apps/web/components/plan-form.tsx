"use client";

import { Gauge, ListChecks, Network } from "lucide-react";
import { useMemo, useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { ErrorText } from "@/components/common";
import { Panel } from "@/components/kit";
import { WeightMix, seriesVar } from "@/components/charts";
import { useQuery } from "@/lib/use-query";
import type { EmployeeMeta, Factor, Plan, PlanInput, SelectionMethod } from "@/lib/api";
import { cn } from "@/lib/utils";

const METHODS: { key: SelectionMethod; label: string; icon: typeof Gauge; text: string }[] = [
  { key: "score_ranked", label: "Score-ranked", icon: Gauge,
    text: "Rank the eligible pool by a weighted score and select the lowest until the headcount and/or cost target is met." },
  { key: "role_redundancy", label: "Role redundancy", icon: Network,
    text: "Everyone eligible in the roles being eliminated is selected. Scoring is optional and for reference only." },
  { key: "manual_list", label: "Manual list", icon: ListChecks,
    text: "Select the listed employee IDs. Hard exclusions still apply; every name needs a recorded reason later." },
];

function blank(factors: Factor[]): PlanInput {
  return {
    name: "", description: "", selection_method: "score_ranked", target_count: null, target_cost_paise: null,
    filters: { departments: [], locations: [], roles: [] },
    weights: Object.fromEntries(factors.map((f) => [f.key, f.default_weight])),
    eliminated_roles: [], manual_codes: [],
  };
}

function fromPlan(p: Plan): PlanInput {
  return {
    name: p.name, description: p.description, selection_method: p.selection_method, target_count: p.target_count,
    target_cost_paise: p.target_cost_paise, filters: p.filters, weights: p.weights ?? {},
    eliminated_roles: p.eliminated_roles ?? [], manual_codes: p.manual_codes ?? [],
  };
}

/** Toggleable chips for a multi-select over a short list (empty selection = everyone). */
function Chips({ options, value, onChange, empty }: {
  options: string[]; value: string[]; onChange: (v: string[]) => void; empty: string;
}) {
  return (
    <div className="flex flex-wrap gap-1.5">
      {options.length === 0 && <span className="text-xs text-muted-foreground">{empty}</span>}
      {options.map((o) => {
        const on = value.includes(o);
        return (
          <button key={o} type="button" aria-pressed={on}
                  onClick={() => onChange(on ? value.filter((x) => x !== o) : [...value, o])}
                  className={cn("rounded-full border px-2.5 py-0.5 text-xs transition-colors",
                                on ? "border-primary bg-primary/10 text-foreground" : "text-muted-foreground hover:border-foreground/40")}>
            {o}
          </button>
        );
      })}
    </div>
  );
}

type Props = { initial?: Plan; onSubmit: (v: PlanInput) => Promise<void>; onCancel?: () => void; submitLabel: string };

export function PlanForm(props: Props) {
  const kpis = useQuery<Factor[]>("/kpis");
  const meta = useQuery<EmployeeMeta>("/employees/meta");
  if (!kpis.data || !meta.data) {
    return <div className="py-12 text-center text-sm text-muted-foreground">{kpis.error ?? meta.error ?? "Loading…"}</div>;
  }
  return <PlanFormBody {...props} factors={kpis.data} meta={meta.data} />;
}

function PlanFormBody({ initial, onSubmit, onCancel, submitLabel, factors, meta }: Props & {
  factors: Factor[]; meta: EmployeeMeta;
}) {
  const [v, setV] = useState<PlanInput>(() => (initial ? fromPlan(initial) : blank(factors)));
  const [scoreToo, setScoreToo] = useState(() => !initial || Object.values(initial.weights ?? {}).some((w) => w > 0));
  const [codes, setCodes] = useState(() => (initial?.manual_codes ?? []).join("\n"));
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const set = <K extends keyof PlanInput>(k: K, val: PlanInput[K]) => setV((p) => ({ ...p, [k]: val }));

  const labels = useMemo(() => Object.fromEntries(factors.map((f) => [f.key, f.label])), [factors]);
  const colorOf = (key: string) => {
    const i = factors.findIndex((f) => f.key === key);
    return i < 0 ? "var(--viz-muted)" : seriesVar(i);
  };
  const scored = v.selection_method === "score_ranked" || scoreToo;
  const totalWeight = Object.values(v.weights).reduce((a, w) => a + (w > 0 ? w : 0), 0);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await onSubmit({
        ...v,
        weights: scored ? Object.fromEntries(Object.entries(v.weights).filter(([, w]) => w > 0)) : {},
        manual_codes: v.selection_method === "manual_list"
          ? codes.split(/[\s,]+/).map((c) => c.trim()).filter(Boolean) : [],
        eliminated_roles: v.selection_method === "role_redundancy" ? v.eliminated_roles : [],
        target_count: v.selection_method === "score_ranked" ? v.target_count : null,
        target_cost_paise: v.selection_method === "score_ranked" ? v.target_cost_paise : null,
      });
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <form onSubmit={submit} className="space-y-6">
      <Panel title="About this plan">
        <div className="grid gap-4">
          <div className="space-y-1.5">
            <Label htmlFor="name">Name</Label>
            <Input id="name" required maxLength={200} value={v.name} onChange={(e) => set("name", e.target.value)}
                   placeholder="e.g. Support restructuring, Q4" />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="description">Business rationale</Label>
            <Textarea id="description" rows={3} value={v.description} onChange={(e) => set("description", e.target.value)}
                      placeholder="Why this reduction is needed. This goes into the defensibility pack." />
          </div>
        </div>
      </Panel>

      <Panel title="Selection method" description="How people in scope are proposed. Protected people are always excluded.">
        <div className="grid gap-3 md:grid-cols-3">
          {METHODS.map((m) => {
            const on = v.selection_method === m.key;
            return (
              <button key={m.key} type="button" aria-pressed={on} onClick={() => set("selection_method", m.key)}
                      className={cn("rounded-xl border p-4 text-left transition-colors",
                                    on ? "border-primary bg-primary/5" : "hover:border-foreground/30")}>
                <div className="flex items-center gap-2 font-medium">
                  <m.icon className={cn("size-4", on ? "text-primary" : "text-muted-foreground")} />{m.label}
                </div>
                <p className="mt-1.5 text-xs text-muted-foreground">{m.text}</p>
              </button>
            );
          })}
        </div>

        {v.selection_method === "score_ranked" && (
          <div className="mt-5 grid gap-4 sm:grid-cols-2">
            <div className="space-y-1.5">
              <Label htmlFor="count">Headcount target</Label>
              <Input id="count" type="number" min={1} value={v.target_count ?? ""}
                     onChange={(e) => set("target_count", e.target.value ? Number(e.target.value) : null)} />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="cost">Annual cost-saving target (₹)</Label>
              <Input id="cost" type="number" min={1} step={1000}
                     value={v.target_cost_paise === null ? "" : v.target_cost_paise / 100}
                     onChange={(e) => set("target_cost_paise", e.target.value ? Math.round(Number(e.target.value) * 100) : null)} />
            </div>
            <p className="text-xs text-muted-foreground sm:col-span-2">
              Set one or both. With both, selection continues until each target is met.
            </p>
          </div>
        )}
        {v.selection_method === "role_redundancy" && (
          <div className="mt-5 space-y-1.5">
            <Label>Roles being eliminated</Label>
            <Chips options={meta.roles} value={v.eliminated_roles} onChange={(r) => set("eliminated_roles", r)}
                   empty="No roles found" />
          </div>
        )}
        {v.selection_method === "manual_list" && (
          <div className="mt-5 space-y-1.5">
            <Label htmlFor="codes">Employee IDs</Label>
            <Textarea id="codes" rows={4} value={codes} onChange={(e) => setCodes(e.target.value)}
                      placeholder="One per line, or separated by commas" className="font-mono" />
          </div>
        )}
      </Panel>

      <Panel title="Scope" description="Leave a group empty to include everyone.">
        <div className="space-y-4">
          <div className="space-y-1.5"><Label>Departments</Label>
            <Chips options={meta.departments} value={v.filters.departments} empty="No departments"
                   onChange={(d) => set("filters", { ...v.filters, departments: d })} /></div>
          <div className="space-y-1.5"><Label>Locations</Label>
            <Chips options={meta.locations} value={v.filters.locations} empty="No locations"
                   onChange={(d) => set("filters", { ...v.filters, locations: d })} /></div>
          <div className="space-y-1.5"><Label>Roles</Label>
            <Chips options={meta.roles} value={v.filters.roles} empty="No roles"
                   onChange={(d) => set("filters", { ...v.filters, roles: d })} /></div>
        </div>
      </Panel>

      <Panel title="Scoring weights"
             description="Weights are normalised to 100%. A higher score means stronger reason to retain."
             actions={v.selection_method !== "score_ranked" && (
               <label className="flex items-center gap-2 text-sm">
                 <input type="checkbox" checked={scoreToo} onChange={(e) => setScoreToo(e.target.checked)} />
                 Score the pool for reference
               </label>
             )}>
        {scored ? (
          <div className="space-y-5">
            {totalWeight > 0 && <WeightMix weights={v.weights} labels={labels} colorOf={colorOf} />}
            <div className="grid gap-x-8 gap-y-4 md:grid-cols-2">
              {factors.map((f) => {
                const w = v.weights[f.key] ?? 0;
                return (
                  <div key={f.key} className="space-y-1">
                    <div className="flex items-center justify-between gap-2 text-sm">
                      <label htmlFor={`w-${f.key}`} className="flex items-center gap-2 font-medium">
                        <span className="size-2.5 rounded-sm" style={{ background: colorOf(f.key) }} />
                        {f.label}
                        {f.custom && <span className="rounded-md bg-muted px-1.5 text-[10px] text-muted-foreground">custom</span>}
                      </label>
                      <span className="tabular-nums text-muted-foreground">
                        {totalWeight > 0 && w > 0 ? `${Math.round((w / totalWeight) * 100)}%` : "off"}
                      </span>
                    </div>
                    <input id={`w-${f.key}`} type="range" min={0} max={1} step={0.05} value={w} className="w-full accent-[var(--primary)]"
                           onChange={(e) => set("weights", { ...v.weights, [f.key]: Number(e.target.value) })} />
                    <p className="text-xs text-muted-foreground">
                      {f.description} · {f.higher_is_better ? "higher is better" : "lower is better"}
                    </p>
                  </div>
                );
              })}
            </div>
          </div>
        ) : (
          <p className="text-sm text-muted-foreground">The pool won&apos;t be scored. Turn on reference scoring to see a ranking.</p>
        )}
      </Panel>

      <ErrorText error={error} />
      <div className="flex gap-2">
        <Button type="submit" disabled={busy} className="rounded-xl">{busy ? "Saving…" : submitLabel}</Button>
        {onCancel && <Button type="button" variant="outline" className="rounded-xl" onClick={onCancel}>Cancel</Button>}
      </div>
    </form>
  );
}
