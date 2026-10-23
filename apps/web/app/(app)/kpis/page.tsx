"use client";

import { Archive, ArrowDown, ArrowUp, Play, Plus, SquareFunction } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { ErrorText } from "@/components/common";
import { useFactorColors } from "@/components/charts";
import { PageHeader, Panel } from "@/components/kit";
import { useAuth } from "@/components/auth";
import { useQuery } from "@/lib/use-query";
import { post, type Factor, type KpiPreview } from "@/lib/api";

type Fields = { fields: Record<string, string>; metrics: string[]; functions: string[] };

const EMPTY = { key: "", label: "", description: "", expression: "", higher_is_better: true };

export default function KpisPage() {
  const { can } = useAuth();
  const kpis = useQuery<Factor[]>("/kpis");
  const fields = useQuery<Fields>("/kpis/fields");
  const colorOf = useFactorColors();
  const [form, setForm] = useState(EMPTY);
  const [preview, setPreview] = useState<KpiPreview | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function act(fn: () => Promise<unknown>) {
    setBusy(true);
    setError(null);
    try {
      await fn();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  const insert = (snippet: string) => {
    setForm((f) => ({ ...f, expression: f.expression ? `${f.expression} ${snippet}` : snippet }));
    setPreview(null);
  };

  return (
    <div className="space-y-8">
      <PageHeader eyebrow="Scoring" title="KPI library"
                  description="Factors a reduction plan can weight. Custom KPIs are deterministic formulas over employee data, evaluated by a safe expression parser (no code execution). A KPI weighted in an open plan can't be archived." />

      <div className="grid gap-6 xl:grid-cols-[1fr_440px]">
        <div className="stagger grid content-start gap-4 md:grid-cols-2">
          {(kpis.data ?? []).map((k) => (
            <div key={k.key} className="glass group relative overflow-hidden rounded-2xl p-5">
              <div className="absolute inset-x-0 top-0 h-0.5" style={{ background: colorOf(k.key) }} />
              <div className="flex items-start justify-between gap-3">
                <div>
                  <div className="flex items-center gap-2">
                    <span className="size-2.5 rounded-[3px]" style={{ background: colorOf(k.key) }} />
                    <span className="font-semibold">{k.label}</span>
                  </div>
                  <div className="mt-0.5 font-mono text-xs text-muted-foreground">{k.key}</div>
                </div>
                <span className="rounded-full border px-2 py-0.5 text-[11px] text-muted-foreground">
                  {k.custom ? `Custom · ${k.created_by}` : "Built-in"}
                </span>
              </div>
              <p className="mt-3 text-sm text-muted-foreground">{k.description}</p>
              {k.expression && k.expression !== k.description && (
                <code className="mt-3 block rounded-lg border bg-background/50 px-3 py-2 font-mono text-xs">{k.expression}</code>
              )}
              <div className="mt-4 flex items-center justify-between text-xs">
                <span className="flex items-center gap-1.5 text-muted-foreground">
                  {k.higher_is_better ? <ArrowUp className="size-3.5" /> : <ArrowDown className="size-3.5" />}
                  {k.higher_is_better ? "Higher is better" : "Lower is better"}
                </span>
                {k.custom && can("hr") && (
                  <Button size="sm" variant="ghost" className="gap-1.5" disabled={busy}
                          onClick={() => act(async () => { await post(`/kpis/${k.id}/archive`); kpis.reload(); toast.success(`${k.label} archived`); })}>
                    <Archive className="size-3.5" />Archive
                  </Button>
                )}
              </div>
            </div>
          ))}
        </div>

        {can("hr") && (
          <Panel className="h-fit xl:sticky xl:top-20"
                 title={<span className="flex items-center gap-2"><SquareFunction className="size-4 text-primary" />New custom KPI</span>}
                 description="Write a formula, preview it across everyone, then create it.">
            <form className="space-y-4" onSubmit={(e) => {
              e.preventDefault();
              act(async () => {
                await post("/kpis", form);
                toast.success(`${form.label} added to the library`);
                setForm(EMPTY);
                setPreview(null);
                kpis.reload();
              });
            }}>
              <div className="grid grid-cols-2 gap-3">
                <div className="space-y-1.5">
                  <Label htmlFor="label">Label</Label>
                  <Input id="label" required value={form.label} placeholder="Engagement" className="rounded-xl"
                         onChange={(e) => setForm({ ...form, label: e.target.value })} />
                </div>
                <div className="space-y-1.5">
                  <Label htmlFor="key">Key</Label>
                  <Input id="key" required value={form.key} placeholder="engagement" className="rounded-xl font-mono"
                         onChange={(e) => setForm({ ...form, key: e.target.value.toLowerCase() })} />
                </div>
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="expr">Formula</Label>
                <Textarea id="expr" required rows={3} value={form.expression}
                          className="rounded-xl bg-background/60 font-mono text-sm"
                          placeholder={'metric("engagement_score", 3) * 0.5 + performance_rating * 0.5'}
                          onChange={(e) => { setForm({ ...form, expression: e.target.value }); setPreview(null); }} />
                {fields.data && (
                  <div className="flex flex-wrap gap-1.5 pt-1">
                    {Object.keys(fields.data.fields).map((f) => (
                      <button key={f} type="button" onClick={() => insert(f)}
                              className="rounded-md border bg-background/40 px-1.5 py-0.5 font-mono text-[11px] text-muted-foreground hover:border-primary hover:text-foreground">
                        {f}
                      </button>
                    ))}
                    {fields.data.metrics.map((m) => (
                      <button key={m} type="button" onClick={() => insert(`metric("${m}", 0)`)}
                              className="rounded-md border border-primary/30 bg-primary/10 px-1.5 py-0.5 font-mono text-[11px] hover:border-primary">
                        metric(&quot;{m}&quot;)
                      </button>
                    ))}
                  </div>
                )}
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="desc">Description</Label>
                <Input id="desc" value={form.description} placeholder="What this measures and why" className="rounded-xl"
                       onChange={(e) => setForm({ ...form, description: e.target.value })} />
              </div>
              <label className="flex items-center gap-2 text-sm">
                <input type="checkbox" checked={form.higher_is_better} className="accent-[var(--primary)]"
                       onChange={(e) => setForm({ ...form, higher_is_better: e.target.checked })} />
                Higher values are better (raise the retention score)
              </label>
              <ErrorText error={error} />
              {preview && (
                <div className="space-y-3 rounded-xl border bg-background/40 p-3 animate-fade-up">
                  <div className="text-xs text-muted-foreground">
                    Evaluated for {preview.count} employees
                    {preview.errors > 0 && <span className="text-[var(--status-critical)]"> · {preview.errors} errors</span>}
                  </div>
                  {preview.stats && (
                    <div className="grid grid-cols-3 gap-2 text-center">
                      {(["min", "mean", "max"] as const).map((s) => (
                        <div key={s} className="rounded-lg bg-muted/50 py-2">
                          <div className="text-[10px] text-muted-foreground uppercase">{s}</div>
                          <div className="font-semibold tabular-nums">{preview.stats![s]}</div>
                        </div>
                      ))}
                    </div>
                  )}
                  <div className="flex flex-wrap gap-1.5">
                    {preview.sample.map((s) => (
                      <span key={s.employee_code} className="rounded-md bg-muted/60 px-1.5 py-0.5 font-mono text-[11px]">
                        {s.employee_code}: {s.value}
                      </span>
                    ))}
                  </div>
                </div>
              )}
              <div className="flex gap-2">
                <Button type="button" variant="outline" className="gap-2 rounded-xl" disabled={busy || !form.expression}
                        onClick={() => act(async () => setPreview(await post<KpiPreview>("/kpis/preview", { expression: form.expression })))}>
                  <Play className="size-3.5" />Preview
                </Button>
                <Button type="submit" className="gap-2 rounded-xl" disabled={busy}>
                  <Plus className="size-4" />Create KPI
                </Button>
              </div>
              {fields.data && (
                <p className="text-xs text-muted-foreground">
                  Functions: {fields.data.functions.join(" · ")}. Operators: + − × ÷ and parentheses.
                </p>
              )}
            </form>
          </Panel>
        )}
      </div>
    </div>
  );
}
