"use client";

import {
  CircleAlert, CircleCheck, Hand, Handshake, Info, OctagonX, ShieldCheck, Sparkles, TriangleAlert, Undo2, type LucideIcon,
} from "lucide-react";
import Link from "next/link";
import { useMemo, useState } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { AiDraftCard } from "@/components/ai-draft";
import { AuditTable } from "@/components/audit-table";
import { ContributionBar, ImpactBars, ScoreHistogram, useFactorColors } from "@/components/charts";
import { ErrorText, fmtDate, tableCls as t } from "@/components/common";
import { ApprovalPill, CaseStatePill, EmptyState, Panel, Pill } from "@/components/kit";
import { useAuth } from "@/components/auth";
import { useQuery } from "@/lib/use-query";
import {
  ApiError, fmtPaise, post, type AiDraft, type Approval, type AuditEntry, type CaseState, type CaseSummary,
  type ComplianceCheck, type Fairness, type Plan, type ResultRow, type Results,
} from "@/lib/api";
import { cn } from "@/lib/utils";

const pretty = (s: string) => s.replace(/_/g, " ").replace(/^\w/, (c) => c.toUpperCase());

/* ------------------------------------------------------------------ ranking */

type OverrideTarget = { row: ResultRow; mode: "include" | "exclude" | "revoke" };

function OverrideDialog({ plan, target, onClose, onDone }: {
  plan: Plan; target: OverrideTarget | null; onClose: () => void; onDone: () => void;
}) {
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const row = target?.row;
  const title = target?.mode === "revoke" ? "Revoke override" : target?.mode === "include" ? "Add to the proposal" : "Remove from the proposal";

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!target || !row) return;
    setBusy(true);
    setError(null);
    try {
      if (target.mode === "revoke") {
        await post(`/plans/${plan.id}/overrides/${row.override!.id}/revoke`, { justification: text });
      } else {
        await post(`/plans/${plan.id}/overrides`, { employee_id: row.employee_id, action: target.mode, justification: text });
      }
      toast.success("Override recorded in the audit log");
      setText("");
      onDone();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <Dialog open={!!target} onOpenChange={(o) => { if (!o) { setText(""); setError(null); onClose(); } }}>
      <DialogContent className="rounded-2xl sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>{title}</DialogTitle>
          <DialogDescription>
            {row?.full_name} ({row?.employee_code}). Overrides need a written justification of at least 10 characters,
            are shown to approvers and are kept in the audit log.
          </DialogDescription>
        </DialogHeader>
        <form onSubmit={submit} className="space-y-3">
          <Label htmlFor="justification">Justification</Label>
          <Textarea id="justification" rows={4} required minLength={10} value={text} onChange={(e) => setText(e.target.value)} />
          <ErrorText error={error} />
          <div className="flex gap-2">
            <Button type="submit" disabled={busy || text.trim().length < 10}>{busy ? "Saving…" : "Record override"}</Button>
            <Button type="button" variant="outline" onClick={onClose}>Cancel</Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  );
}

type RowFilter = "all" | "proposed" | "retained" | "excluded" | "overridden";

export function RankingTab({ plan, results, onChanged }: { plan: Plan; results: Results | undefined; onChanged: () => void }) {
  const { can } = useAuth();
  const colorOf = useFactorColors();
  const [filter, setFilter] = useState<RowFilter>("all");
  const [target, setTarget] = useState<OverrideTarget | null>(null);
  const editable = plan.status === "draft" && can("hr");
  const labels = useMemo(() => Object.fromEntries(Object.entries(plan.kpi_snapshot ?? {}).map(([k, v]) => [k, v.label])),
                         [plan.kpi_snapshot]);

  if (!plan.last_run_at) return <EmptyState icon={Sparkles} title="Not run yet">Run the plan to see the ranking.</EmptyState>;
  if (!results) return <div className="py-12 text-center text-sm text-muted-foreground">Loading…</div>;

  const rows = results.rows.filter((r) =>
    filter === "all" ? true : filter === "proposed" ? r.final_selected : filter === "excluded" ? r.excluded
      : filter === "overridden" ? !!r.override : !r.final_selected && !r.excluded);
  const hasScores = results.rows.some((r) => r.score !== null);

  return (
    <div className="space-y-6">
      {hasScores && (
        <Panel title="Score distribution" description="Proposed vs retained, by retention score. Lower scores are proposed first.">
          <ScoreHistogram rows={results.rows} />
        </Panel>
      )}
      <Panel bodyClassName="p-0">
        <div className="flex flex-wrap items-center gap-1.5 border-b p-4">
          {(["all", "proposed", "retained", "excluded", "overridden"] as RowFilter[]).map((f) => (
            <button key={f} type="button" onClick={() => setFilter(f)} aria-pressed={filter === f}
                    className={cn("rounded-full border px-3 py-1 text-xs capitalize transition-colors",
                                  filter === f ? "border-primary bg-primary/10" : "text-muted-foreground hover:text-foreground")}>
              {f === "excluded" ? "protected" : f}
            </button>
          ))}
          <span className="ml-auto text-xs text-muted-foreground">{rows.length} shown</span>
        </div>
        <div className="max-h-[70vh] overflow-auto">
          <table className={t.table}>
            <thead className={`${t.thead} sticky top-0 z-10 bg-background/90 backdrop-blur`}>
              <tr className="border-b">
                <th className={`${t.th} w-12`}>#</th>
                <th className={t.th}>Person</th>
                {hasScores && <th className={`${t.th} min-w-48`}>Score</th>}
                <th className={`${t.th} text-right`}>CTC</th>
                <th className={t.th}>Outcome</th>
                {editable && <th className={t.th} />}
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.employee_id} className={cn(t.tr, r.excluded && "opacity-70")}>
                  <td className={`${t.td} tabular-nums text-muted-foreground`}>{r.rank ?? "–"}</td>
                  <td className={t.td}>
                    <Link href={`/people/${r.employee_code}`} className="font-medium hover:text-primary">{r.full_name}</Link>
                    <div className="text-xs text-muted-foreground">{r.employee_code} · {r.department} · {r.role}</div>
                  </td>
                  {hasScores && (
                    <td className={t.td}>
                      {r.score === null ? <span className="text-xs text-muted-foreground">not scored</span> : (
                        <div className="space-y-1">
                          <span className="text-sm font-medium tabular-nums">{r.score.toFixed(1)}</span>
                          <ContributionBar contributions={r.contributions} colorOf={colorOf} labels={labels} />
                        </div>
                      )}
                    </td>
                  )}
                  <td className={`${t.td} text-right tabular-nums`}>
                    {r.annual_ctc_paise === null ? <span className="text-muted-foreground">masked</span> : fmtPaise(r.annual_ctc_paise)}
                  </td>
                  <td className={t.td}>
                    <div className="flex flex-col items-start gap-1">
                      {r.excluded ? (
                        <span className="inline-flex items-center gap-1.5 text-xs">
                          <ShieldCheck className="size-3.5 text-[var(--status-good)]" aria-hidden="true" />
                          Protected: {r.exclusion_reason}
                        </span>
                      ) : r.final_selected ? (
                        <Pill spec={{ label: "Proposed", icon: CircleAlert, color: "var(--status-warning)" }} />
                      ) : <span className="text-xs text-muted-foreground">Retained</span>}
                      {r.override && (
                        <span className="inline-flex items-center gap-1 text-xs text-muted-foreground" title={r.override.justification}>
                          <Hand className="size-3" aria-hidden="true" />
                          Override: {r.override.action === "include" ? "added" : "removed"} by {r.override.created_by}
                        </span>
                      )}
                      {r.case && (
                        <Link href={`/cases/${r.case.id}`} className="text-xs text-primary hover:underline">
                          Exit case · {pretty(r.case.state)}
                        </Link>
                      )}
                    </div>
                  </td>
                  {editable && (
                    <td className={`${t.td} text-right`}>
                      {r.override ? (
                        <Button size="sm" variant="ghost" className="gap-1" onClick={() => setTarget({ row: r, mode: "revoke" })}>
                          <Undo2 className="size-3.5" />Revoke
                        </Button>
                      ) : r.excluded ? (
                        <span className="text-xs text-muted-foreground" title="Hard exclusions can't be overridden">Locked</span>
                      ) : (
                        <Button size="sm" variant="outline" onClick={() => setTarget({ row: r, mode: r.final_selected ? "exclude" : "include" })}>
                          {r.final_selected ? "Remove" : "Add"}
                        </Button>
                      )}
                    </td>
                  )}
                </tr>
              ))}
            </tbody>
          </table>
          {rows.length === 0 && <EmptyState icon={Sparkles} title="No one in this view" />}
        </div>
      </Panel>
      <OverrideDialog plan={plan} target={target} onClose={() => setTarget(null)}
                      onDone={() => { setTarget(null); onChanged(); }} />
    </div>
  );
}

/* ------------------------------------------------------------------ fairness */

export function FairnessTab({ plan, fairness }: { plan: Plan; fairness: Fairness | undefined }) {
  if (!plan.last_run_at) return <EmptyState icon={Sparkles} title="Not run yet">Run the plan to check fairness.</EmptyState>;
  if (!fairness) return <div className="py-12 text-center text-sm text-muted-foreground">Loading…</div>;
  return (
    <div className="space-y-6">
      <div className={cn("flex items-start gap-3 rounded-xl border px-4 py-3 text-sm")}
           style={{ borderColor: `color-mix(in oklab, var(--status-${fairness.any_flagged ? "critical" : "good"}) 40%, transparent)`,
                    background: `color-mix(in oklab, var(--status-${fairness.any_flagged ? "critical" : "good"}) 8%, transparent)` }}>
        {fairness.any_flagged
          ? <TriangleAlert className="mt-0.5 size-4 shrink-0 text-[var(--status-critical)]" aria-hidden="true" />
          : <CircleCheck className="mt-0.5 size-4 shrink-0 text-[var(--status-good)]" aria-hidden="true" />}
        <div className="space-y-1">
          <div className="font-medium">
            {fairness.any_flagged ? "Adverse-impact flags: final approval needs a written justification" : "No group falls below the four-fifths line"}
          </div>
          {fairness.flags.map((f) => <div key={f} className="text-muted-foreground">{f}</div>)}
          {fairness.justification && <div className="pt-1">Justification on record: “{fairness.justification}”</div>}
        </div>
      </div>
      <div className="grid gap-6 lg:grid-cols-2">
        {Object.entries(fairness.by_attribute).map(([attr, groups]) => (
          <Panel key={attr} title={pretty(attr)}>
            <ImpactBars groups={groups} threshold={fairness.threshold} />
          </Panel>
        ))}
        {fairness.intersectional.length > 0 && (
          <Panel title="Gender × age band" description="Intersectional view. Small groups are marked and not flagged on their own."
                 className="lg:col-span-2">
            <ImpactBars groups={fairness.intersectional} threshold={fairness.threshold} />
          </Panel>
        )}
      </div>
      <p className="text-xs text-muted-foreground">
        Protected attributes are used only for this analysis. They are never inputs to scoring or selection.
      </p>
    </div>
  );
}

/* ------------------------------------------------------------------ compliance */

const SEVERITY: Record<ComplianceCheck["severity"], { icon: LucideIcon; color: string; label: string }> = {
  block: { icon: OctagonX, color: "var(--status-critical)", label: "Blocks approval" },
  warning: { icon: TriangleAlert, color: "var(--status-warning)", label: "Warning" },
  info: { icon: Info, color: "var(--series-1)", label: "Note" },
};

export function ComplianceTab({ plan, checks }: { plan: Plan; checks: ComplianceCheck[] | undefined }) {
  return (
    <div className="space-y-6">
      {plan.ruleset && (
        <Panel title={`${plan.ruleset.title} · ${plan.ruleset.version}`}
               description={plan.ruleset.unverified
                 ? `${plan.ruleset.unverified} of ${plan.ruleset.total} rules are not yet verified by a lawyer.`
                 : `All ${plan.ruleset.total} rules verified.`}
               actions={<Link href="/rules" className="text-xs text-muted-foreground hover:text-foreground">View rules</Link>}>
          <div className="h-2 overflow-hidden rounded-full bg-muted">
            <div className="h-full rounded-full bg-[var(--status-good)]"
                 style={{ width: `${((plan.ruleset.total - plan.ruleset.unverified) / Math.max(1, plan.ruleset.total)) * 100}%` }} />
          </div>
        </Panel>
      )}
      <Panel title="Checks" bodyClassName="p-0">
        {!checks ? <div className="p-5 text-sm text-muted-foreground">Loading…</div>
          : checks.length === 0 ? <EmptyState icon={CircleCheck} title="No compliance issues found" />
          : (
            <ul className="divide-y">
              {checks.map((c, i) => {
                const s = SEVERITY[c.severity];
                return (
                  <li key={i} className="flex items-start gap-3 px-5 py-3 text-sm">
                    <s.icon className="mt-0.5 size-4 shrink-0" style={{ color: s.color }} aria-hidden="true" />
                    <div className="flex-1">
                      <div>{c.message}</div>
                      <div className="mt-0.5 text-xs text-muted-foreground">{s.label}{c.rule && ` · ${c.rule}`}</div>
                    </div>
                  </li>
                );
              })}
            </ul>
          )}
      </Panel>
    </div>
  );
}

/* ------------------------------------------------------------------ approvals */

export function ApprovalsTab({ plan }: { plan: Plan }) {
  const q = useQuery<Approval[]>(`/plans/${plan.id}/approvals`);
  const rounds = useMemo(() => {
    const m = new Map<number, Approval[]>();
    for (const a of q.data ?? []) m.set(a.round, [...(m.get(a.round) ?? []), a]);
    return [...m.entries()].sort((a, b) => b[0] - a[0]);
  }, [q.data]);
  return (
    <div className="space-y-6">
      <ErrorText error={q.error} />
      {!q.loading && rounds.length === 0 && (
        <EmptyState icon={Handshake} title="Not submitted yet">
          Submitting sends the plan to legal review, then finance review, then final approval. The person who prepared
          it can&apos;t approve any step, and any change after submission resets the approvals.
        </EmptyState>
      )}
      {rounds.map(([round, steps]) => (
        <Panel key={round} title={`Round ${round}`} description={`Prepared by ${steps[0].prepared_by}`} bodyClassName="p-0">
          <ol className="divide-y">
            {steps.sort((a, b) => a.step_index - b.step_index).map((a) => (
              <li key={a.id} className="flex flex-wrap items-center gap-3 px-5 py-3 text-sm">
                <span className="w-6 text-muted-foreground tabular-nums">{a.step_index + 1}</span>
                <div className="min-w-40 flex-1">
                  <div className="font-medium">{pretty(a.step)}</div>
                  <div className="text-xs text-muted-foreground">{a.roles.join(" or ")}</div>
                </div>
                <ApprovalPill status={a.status} />
                <div className="w-full text-xs text-muted-foreground sm:w-auto sm:text-right">
                  {a.decided_by ? <>{a.decided_by} · {fmtDate(a.decided_at)}</> : `opened ${fmtDate(a.created_at)}`}
                  <div className="font-mono" title="Content hash the decision is bound to">#{a.content_hash.slice(0, 10)}</div>
                </div>
                {a.comment && <p className="w-full pl-9 text-muted-foreground">“{a.comment}”</p>}
              </li>
            ))}
          </ol>
        </Panel>
      ))}
    </div>
  );
}

/* ------------------------------------------------------------------ cases */

export function CasesTab({ plan, onChanged }: { plan: Plan; onChanged: () => void }) {
  const { can } = useAuth();
  const q = useQuery<CaseSummary[]>(`/exit-cases?plan_id=${plan.id}`);
  const [busy, setBusy] = useState(false);

  async function open() {
    setBusy(true);
    try {
      const created = await post<CaseSummary[]>("/exit-cases", { plan_id: plan.id });
      toast.success(`${created.length} exit case${created.length === 1 ? "" : "s"} opened`);
      q.reload();
      onChanged();
    } catch (e) {
      toast.error((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  const cases = q.data ?? [];
  return (
    <div className="space-y-6">
      {plan.status !== "approved" ? (
        <EmptyState icon={Handshake} title="Exit cases open after final approval">
          Once the plan is approved, HR opens one exit case per proposed person. Notices, FNF and documents run from there.
        </EmptyState>
      ) : (
        <>
          {can("hr") && (
            <Panel title="Open exit cases"
                   description="Creates a case for each proposed person who doesn't have one yet. Nothing is sent to anyone.">
              <Button onClick={open} disabled={busy} className="gap-2 rounded-xl">
                <Handshake className="size-4" />{busy ? "Opening…" : "Open exit cases"}
              </Button>
            </Panel>
          )}
          <ErrorText error={q.error} />
          {cases.length > 0 && (
            <Panel bodyClassName="p-0">
              <table className={t.table}>
                <thead className={t.thead}>
                  <tr className="border-b">
                    <th className={t.th}>Person</th>
                    <th className={t.th}>Stage</th>
                    <th className={t.th}>Reason</th>
                    <th className={t.th}>Last working day</th>
                    <th className={t.th}>Open tasks</th>
                  </tr>
                </thead>
                <tbody>
                  {cases.map((c) => (
                    <tr key={c.id} className={t.tr}>
                      <td className={t.td}>
                        <Link href={`/cases/${c.id}`} className="font-medium hover:text-primary">{c.employee.full_name}</Link>
                        <div className="text-xs text-muted-foreground">{c.employee.employee_code} · {c.employee.department}</div>
                      </td>
                      <td className={t.td}><CaseStatePill state={c.state as CaseState} label={c.state_label} /></td>
                      <td className={`${t.td} font-mono text-xs`}>{c.reason_code ?? "–"}</td>
                      <td className={`${t.td} text-xs`}>{c.last_working_day ?? "–"}</td>
                      <td className={`${t.td} tabular-nums`}>
                        {c.open_tasks}
                        {c.overdue_tasks > 0 && <span className="ml-1 text-xs text-[var(--status-critical)]">({c.overdue_tasks} overdue)</span>}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </Panel>
          )}
        </>
      )}
    </div>
  );
}

/* ------------------------------------------------------------------ audit */

export function AuditTab({ plan }: { plan: Plan }) {
  const q = useQuery<AuditEntry[]>(`/audit?plan_id=${plan.id}`);
  return (
    <Panel title="Audit trail" description="Every change to this plan and its overrides, newest first. The log is append-only and hash-chained.">
      <ErrorText error={q.error} />
      {q.data && <AuditTable entries={q.data} />}
    </Panel>
  );
}

/* ------------------------------------------------------------------ AI */

export function AiTab({ plan, results }: { plan: Plan; results: Results | undefined }) {
  const { can } = useAuth();
  const q = useQuery<AiDraft[]>(`/plans/${plan.id}/ai/drafts`);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [who, setWho] = useState("");
  const canDraft = can("hr", "approver");
  const names = useMemo(() => Object.fromEntries((results?.rows ?? []).map((r) => [r.employee_id, r])), [results]);

  async function run(kind: string, path: string, body?: unknown) {
    setBusy(kind);
    setError(null);
    try {
      await post(path, body);
      q.reload();
    } catch (e) {
      setError(e instanceof ApiError && e.status === 503
        ? `AI drafting isn't available: ${e.message}. Everything else in the plan works without it.`
        : (e as Error).message);
    } finally {
      setBusy(null);
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex items-start gap-3 rounded-xl border border-dashed px-4 py-3 text-sm text-muted-foreground">
        <Sparkles className="mt-0.5 size-4 shrink-0 text-primary" aria-hidden="true" />
        <span>
          AI only drafts text from data you can already see. It never scores, selects or decides, and its prompts
          carry employee IDs, not names or pay. Every draft is labelled and must be reviewed before anyone uses it.
        </span>
      </div>
      {canDraft && (
        <Panel title="Draft something">
          <div className="flex flex-wrap items-end gap-3">
            <Button variant="outline" className="gap-2 rounded-xl" disabled={!!busy || !plan.last_run_at}
                    onClick={() => run("summary", `/plans/${plan.id}/ai/summary`)}>
              <Sparkles className="size-4" />{busy === "summary" ? "Drafting…" : "Executive summary"}
            </Button>
            <div className="flex items-end gap-2">
              <div className="space-y-1">
                <Label htmlFor="explain-who">Explain one person&apos;s position</Label>
                <select id="explain-who" className="h-8 w-64 rounded-md border bg-background px-2 text-sm" value={who}
                        onChange={(e) => setWho(e.target.value)} disabled={!results}>
                  <option value="">Choose…</option>
                  {(results?.rows ?? []).map((r) => (
                    <option key={r.employee_id} value={r.employee_id}>
                      {r.rank ? `#${r.rank} ` : ""}{r.full_name} ({r.employee_code})
                    </option>
                  ))}
                </select>
              </div>
              <Button variant="outline" className="rounded-xl" disabled={!!busy || !who}
                      onClick={() => run("explain", `/plans/${plan.id}/ai/explain`, { employee_id: Number(who) })}>
                {busy === "explain" ? "Drafting…" : "Explain"}
              </Button>
            </div>
          </div>
          {!plan.last_run_at && <p className="mt-3 text-xs text-muted-foreground">Run the plan first.</p>}
          <div className="mt-3"><ErrorText error={error} /></div>
        </Panel>
      )}
      <ErrorText error={q.error} />
      {q.data?.length === 0 && <EmptyState icon={Sparkles} title="No AI drafts yet" />}
      {q.data?.map((d) => (
        <AiDraftCard key={d.id} draft={d}
                     title={d.kind === "summary" ? "Executive summary"
                       : `Explanation${d.employee_id && names[d.employee_id] ? ` · ${names[d.employee_id].employee_code}` : ""}`} />
      ))}
    </div>
  );
}
