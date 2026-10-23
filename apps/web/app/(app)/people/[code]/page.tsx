"use client";

import {
  ArrowLeft, Download, FileWarning, Handshake, History, MessageSquare, Pencil, ShieldCheck, Target, UserX,
} from "lucide-react";
import Link from "next/link";
import { useParams, useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Textarea } from "@/components/ui/textarea";
import { ErrorText, fmtDate, tableCls as t } from "@/components/common";
import { EmployeeForm } from "@/components/employee-form";
import { Avatar, CaseStatePill, EmptyState, PageHeader, Panel } from "@/components/kit";
import { useAuth } from "@/components/auth";
import { Detail, Field, FormDialog, Select, download, humanize, today } from "@/components/form-bits";
import { EvidenceLinks, EvidenceUpload, NewPipDialog, PipCard, type Pip } from "@/components/pip-card";
import { useQuery } from "@/lib/use-query";
import { fmtDay, fmtPaise, patch, post, put, type CaseState, type Employee, type EmployeeMeta, type Evidence } from "@/lib/api";
import { cn } from "@/lib/utils";

type Review = {
  id: number; cycle: string; cycle_id: number; period_end: string; self_rating: number | null;
  self_comment: string | null; manager_rating: number | null; manager_comment: string | null; peer_input: string | null;
  calibrated_rating: number | null; calibrated_by: string | null;
};
type Goal = { id: number; title: string; description: string; weight: number; target: string; due_date: string | null;
  objective: string | null; progress_pct: number; status: string; created_by: string };
type Checkin = { id: number; scheduled_for: string; held_on: string | null; summary: string; sentiment: string;
  private_note: string | null; has_private_note: boolean; created_by: string;
  actions: { id: number; text: string; owner: string; due_date: string | null; done: boolean }[] };
type Feedback = { id: number; author: string; strength: string; improvement: string; example: string; given_on: string };
type HistoryRow = { id: number; field: string; old_value: unknown; new_value: unknown; changed_by: string; changed_at: string };
type Profile = {
  employee: Employee; reviews: Review[]; goals: Goal[]; checkins: Checkin[]; feedback: Feedback[]; pips: Pip[];
  evidence: Evidence[]; history: HistoryRow[];
  exit_cases: { id: number; plan_id: number; state: CaseState; reason_code: string | null; last_working_day: string | null }[];
};
type Payroll = { id: number; period: string; data: Record<string, number>; source: string; updated_by: string; updated_at: string };

const DAY_KEYS = new Set(["leave_encashable_days", "days_worked_final_month", "days_in_month", "bonus_months_worked"]);
const SENTIMENT: Record<string, string> = { positive: "var(--status-good)", neutral: "var(--viz-muted)", concern: "var(--status-warning)" };

function fmtValue(v: unknown) {
  if (v === null || v === undefined || v === "") return "–";
  return typeof v === "object" ? JSON.stringify(v) : String(v);
}

export default function ProfilePage() {
  return <Suspense><Profile /></Suspense>;
}

function Profile() {
  const { code } = useParams<{ code: string }>();
  const params = useSearchParams();
  const { can } = useAuth();
  const q = useQuery<Profile>(`/employees/by-code/${encodeURIComponent(code)}`);
  const meta = useQuery<EmployeeMeta>("/employees/meta");
  const [tab, setTab] = useState(params.get("tab") ?? "overview");
  const [editing, setEditing] = useState(false);
  const [confirmPseudo, setConfirmPseudo] = useState(false);
  const p = q.data;
  const e = p?.employee;

  if (q.error && !p) return <ErrorText error={q.error} />;
  if (!p || !e) return <div className="h-40 animate-pulse rounded-2xl bg-muted/40" />;

  const reload = q.reload;
  const masked = (f: string) => e.masked.includes(f);
  const evidenceFor = (type: string, id: number) => p.evidence.filter((v) => v.entity_type === type && v.entity_id === id);

  return (
    <div className="space-y-6">
      <Link href="/people" className="inline-flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground">
        <ArrowLeft className="size-4" />People
      </Link>
      <PageHeader
        eyebrow={`${e.employee_code} · ${e.department}`}
        title={<span className="flex items-center gap-3"><Avatar name={e.full_name} />{e.full_name}</span>}
        description={<>{e.role} · {e.location} · {humanize(e.status)}</>}
        actions={
          <>
            {can("legal") && (
              <Button variant="outline" className="gap-2 rounded-xl" onClick={async () => {
                try {
                  await download(`/employees/${e.id}/export`, `${e.employee_code}-data-export.json`);
                  toast.success("Data export downloaded (recorded in the audit log)");
                } catch (err) { toast.error((err as Error).message); }
              }}><Download className="size-4" />Data export</Button>
            )}
            {can() && e.status === "exited" && (
              <Button variant="outline" className="gap-2 rounded-xl" onClick={() => setConfirmPseudo(true)}>
                <UserX className="size-4" />Pseudonymise
              </Button>
            )}
            {can("hr") && (
              <Button className="gap-2 rounded-xl" onClick={() => setEditing(true)}><Pencil className="size-4" />Edit</Button>
            )}
          </>
        }
      />

      {e.exclusion_reason && (
        <div className="flex items-center gap-3 rounded-xl border px-4 py-2.5 text-sm"
             style={{ borderColor: "color-mix(in oklab, var(--status-good) 40%, transparent)",
                      background: "color-mix(in oklab, var(--status-good) 8%, transparent)" }}>
          <ShieldCheck className="size-4 text-[var(--status-good)]" aria-hidden="true" />
          <span><span className="font-medium">Protected from selection:</span> {e.exclusion_reason}. No plan or override can select this person.</span>
        </div>
      )}

      <Tabs value={tab} onValueChange={(v) => setTab(String(v))}>
        <TabsList variant="line" className="flex-wrap">
          <TabsTrigger value="overview">Overview</TabsTrigger>
          <TabsTrigger value="performance">Performance</TabsTrigger>
          <TabsTrigger value="pips">PIPs ({p.pips.length})</TabsTrigger>
          <TabsTrigger value="evidence">Evidence ({p.evidence.length})</TabsTrigger>
          <TabsTrigger value="cases">Exit cases ({p.exit_cases.length})</TabsTrigger>
          {can("hr", "finance") && <TabsTrigger value="payroll">Payroll</TabsTrigger>}
          {can("hr", "legal") && <TabsTrigger value="history">History</TabsTrigger>}
        </TabsList>

        <TabsContent value="overview" className="mt-4">
          <Panel>
            <dl className="grid gap-x-6 gap-y-4 sm:grid-cols-2 lg:grid-cols-4">
              <Detail label="Work email">{e.email ?? "–"}</Detail>
              <Detail label="Personal email">{masked("personal_email") ? <Masked /> : e.personal_email ?? "–"}</Detail>
              <Detail label="Manager">{e.manager_code ? <Link className="hover:text-primary" href={`/people/${e.manager_code}`}>{e.manager_code}</Link> : "–"}</Detail>
              <Detail label="Employment type">{humanize(e.employment_type)}</Detail>
              <Detail label="Hire date">{fmtDay(e.hire_date)}</Detail>
              <Detail label="Confirmation date">{fmtDay(e.confirmation_date)}</Detail>
              <Detail label="Contract end">{fmtDay(e.contract_end_date)}</Detail>
              <Detail label="Contract notice">{e.contract_notice_days ?? "–"} days</Detail>
              <Detail label="Annual CTC">{e.annual_ctc_paise === null ? <Masked /> : fmtPaise(e.annual_ctc_paise)}</Detail>
              <Detail label="Performance">{e.performance_rating.toFixed(1)} / 5</Detail>
              <Detail label="Potential">{e.potential_rating.toFixed(1)} / 5</Detail>
              <Detail label="Critical skills">{e.critical_skill_score.toFixed(1)} / 5</Detail>
              <Detail label="Gender">{masked("gender") ? <Masked /> : e.gender ?? "–"}</Detail>
              <Detail label="Age band">{masked("age_band") ? <Masked /> : e.age_band ?? "–"}</Detail>
              <Detail label="Leave status">{masked("leave_status") ? <Masked /> : humanize(e.leave_status)}</Detail>
              <Detail label="Legal hold">{masked("legal_hold") ? <Masked /> : e.legal_hold ? "Yes" : "No"}</Detail>
            </dl>
            {e.custom_metrics && Object.keys(e.custom_metrics).length > 0 && (
              <div className="mt-5 border-t pt-4">
                <div className="mb-2 text-xs text-muted-foreground">Custom metrics</div>
                <div className="flex flex-wrap gap-2">
                  {Object.entries(e.custom_metrics).map(([k, v]) => (
                    <span key={k} className="rounded-lg bg-muted/50 px-2 py-1 font-mono text-xs">{k}: {v}</span>
                  ))}
                </div>
              </div>
            )}
            {e.masked.length > 0 && (
              <p className="mt-4 text-xs text-muted-foreground">Some fields are hidden for your role: {e.masked.map(humanize).join(", ")}.</p>
            )}
          </Panel>
        </TabsContent>

        <TabsContent value="performance" className="mt-4 space-y-6">
          <PerformanceTab p={p} employeeId={e.id} reload={reload} evidenceFor={evidenceFor} />
        </TabsContent>

        <TabsContent value="pips" className="mt-4 space-y-4">
          <StartPip employeeId={e.id} disabled={p.pips.some((x) => x.status !== "closed")} onDone={reload} />
          {p.pips.length === 0 ? <Panel><EmptyState icon={FileWarning} title="No PIPs" /></Panel>
            : p.pips.map((x) => <PipCard key={x.id} pip={x} evidence={p.evidence} onChange={reload} />)}
        </TabsContent>

        <TabsContent value="evidence" className="mt-4">
          <Panel bodyClassName="p-0">
            {p.evidence.length === 0 ? <EmptyState icon={FileWarning} title="No evidence on file" /> : (
              <table className={t.table}>
                <thead className={t.thead}><tr className="border-b">
                  <th className={t.th}>File</th><th className={t.th}>Type</th><th className={t.th}>Attached to</th>
                  <th className={t.th}>Integrity</th><th className={t.th}>Uploaded</th></tr></thead>
                <tbody>
                  {p.evidence.map((v) => (
                    <tr key={v.id} className={t.tr}>
                      <td className={t.td}>
                        <a className="inline-flex items-center gap-1.5 hover:text-primary" href={`/api/employees/evidence/${v.id}/download`}>
                          <Download className="size-3.5" />{v.filename}
                        </a>
                        <div className="text-xs text-muted-foreground">{(v.size / 1024).toFixed(1)} KB</div>
                      </td>
                      <td className={t.td}>{humanize(v.evidence_type)}</td>
                      <td className={t.td}>{humanize(v.entity_type)} #{v.entity_id}</td>
                      <td className={t.td}><span className="font-mono text-xs" title={v.sha256}>{v.sha256.slice(0, 12)}…</span>
                        <div className="text-xs text-muted-foreground">{humanize(v.scan_status)}</div></td>
                      <td className={t.td}>{v.uploaded_by}<div className="text-xs text-muted-foreground">{fmtDate(v.uploaded_at)}</div></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </Panel>
        </TabsContent>

        <TabsContent value="cases" className="mt-4">
          <Panel>
            {p.exit_cases.length === 0 ? <EmptyState icon={Handshake} title="No exit cases" /> : (
              <ul className="divide-y">
                {p.exit_cases.map((c) => (
                  <li key={c.id}>
                    <Link href={`/cases/${c.id}`} className="flex items-center gap-3 py-2.5 text-sm hover:text-primary">
                      <Handshake className="size-4 text-muted-foreground" />
                      <span className="flex-1">Case #{c.id}{c.reason_code && <span className="text-muted-foreground"> · {c.reason_code}</span>}</span>
                      <CaseStatePill state={c.state} label={humanize(c.state)} />
                      <span className="w-28 text-right text-xs text-muted-foreground">LWD {fmtDay(c.last_working_day)}</span>
                    </Link>
                  </li>
                ))}
              </ul>
            )}
          </Panel>
        </TabsContent>

        {can("hr", "finance") && (
          <TabsContent value="payroll" className="mt-4">
            <PayrollTab employeeId={e.id} />
          </TabsContent>
        )}

        {can("hr", "legal") && (
          <TabsContent value="history" className="mt-4">
            <Panel bodyClassName="p-0">
              {p.history.length === 0 ? <EmptyState icon={History} title="No recorded changes" /> : (
                <table className={t.table}>
                  <thead className={t.thead}><tr className="border-b"><th className={t.th}>When</th><th className={t.th}>Field</th>
                    <th className={t.th}>From</th><th className={t.th}>To</th><th className={t.th}>By</th></tr></thead>
                  <tbody>
                    {p.history.map((h) => (
                      <tr key={h.id} className={t.tr}>
                        <td className={`${t.td} whitespace-nowrap`}>{fmtDate(h.changed_at)}</td>
                        <td className={t.td}>{humanize(h.field)}</td>
                        <td className={`${t.td} font-mono text-xs text-muted-foreground`}>{fmtValue(h.old_value)}</td>
                        <td className={`${t.td} font-mono text-xs`}>{fmtValue(h.new_value)}</td>
                        <td className={t.td}>{h.changed_by}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </Panel>
          </TabsContent>
        )}
      </Tabs>

      <Dialog open={editing} onOpenChange={setEditing}>
        <DialogContent className="max-h-[90vh] overflow-y-auto rounded-2xl sm:max-w-2xl">
          <DialogHeader><DialogTitle>Edit {e.full_name}</DialogTitle></DialogHeader>
          {editing && (
            <EmployeeForm initial={e} metricNames={meta.data?.metrics ?? []} onCancel={() => setEditing(false)}
                          onSubmit={async (v) => {
                            // Send only what changed; masked fields come back null and must not be overwritten.
                            const { employee_code: _code, ...rest } = v;
                            void _code;
                            const changes = Object.fromEntries(Object.entries(rest).filter(([k, val]) =>
                              !e.masked.includes(k) && JSON.stringify(val) !== JSON.stringify((e as unknown as Record<string, unknown>)[k] ?? (k === "custom_metrics" ? {} : null))));
                            if (Object.keys(changes).length) await patch(`/employees/${e.id}`, changes);
                            toast.success(Object.keys(changes).length ? "Saved; every change is in the history" : "Nothing changed");
                            setEditing(false);
                            reload();
                          }} />
          )}
        </DialogContent>
      </Dialog>

      <FormDialog open={confirmPseudo} onOpenChange={setConfirmPseudo} title="Pseudonymise this person?" destructive
                  submitLabel="Pseudonymise"
                  description="Name, contact details and free text are replaced irreversibly. The audit trail keeps the employee ID. People under legal hold or with an open exit case can't be pseudonymised."
                  onSubmit={async () => {
                    await post(`/employees/${e.id}/pseudonymise`);
                    toast.success("Pseudonymised");
                    reload();
                  }} />
    </div>
  );
}

function Masked() {
  return <span className="text-muted-foreground italic">hidden for your role</span>;
}

function PerformanceTab({ p, employeeId, reload, evidenceFor }: {
  p: Profile; employeeId: number; reload: () => void; evidenceFor: (type: string, id: number) => Evidence[];
}) {
  const { can } = useAuth();
  const write = can("hr", "manager");
  const [goalOpen, setGoalOpen] = useState(false);
  const [checkinOpen, setCheckinOpen] = useState(false);
  const [feedbackOpen, setFeedbackOpen] = useState(false);
  const [progress, setProgress] = useState<Goal | null>(null);
  const [goal, setGoal] = useState({ title: "", description: "", target: "", weight: 1, due_date: "" });
  const [pct, setPct] = useState(0);
  const [checkin, setCheckin] = useState({ scheduled_for: today(), held_on: today(), summary: "", sentiment: "neutral",
                                           private_note: "", action: "", action_owner: "" });
  const [fb, setFb] = useState({ strength: "", improvement: "", example: "", given_on: today() });

  return (
    <>
      {write && (
        <div className="flex flex-wrap gap-2">
          <Button variant="outline" className="gap-2 rounded-xl" onClick={() => setGoalOpen(true)}><Target className="size-4" />Add goal</Button>
          <Button variant="outline" className="gap-2 rounded-xl" onClick={() => setCheckinOpen(true)}><MessageSquare className="size-4" />Log check-in</Button>
          <Button variant="outline" className="gap-2 rounded-xl" onClick={() => setFeedbackOpen(true)}>Give feedback</Button>
        </div>
      )}

      <Panel title="Reviews" bodyClassName="p-0">
        {p.reviews.length === 0 ? <EmptyState icon={FileWarning} title="No reviews yet" /> : (
          <table className={t.table}>
            <thead className={t.thead}><tr className="border-b"><th className={t.th}>Cycle</th><th className={t.th}>Self</th>
              <th className={t.th}>Manager</th><th className={t.th}>Calibrated</th><th className={t.th}>Manager comment</th><th className={t.th} /></tr></thead>
            <tbody>
              {p.reviews.map((r) => (
                <tr key={r.id} className={t.tr}>
                  <td className={t.td}><Link className="hover:text-primary" href={`/performance/cycles/${r.cycle_id}`}>{r.cycle}</Link></td>
                  <td className={`${t.td} tabular-nums`}>{r.self_rating ?? "–"}</td>
                  <td className={`${t.td} tabular-nums`}>{r.manager_rating ?? "–"}</td>
                  <td className={`${t.td} font-medium tabular-nums`}>{r.calibrated_rating ?? "–"}</td>
                  <td className={`${t.td} max-w-md text-muted-foreground`}>{r.manager_comment || <span className="italic">not documented</span>}</td>
                  <td className={t.td}>
                    <EvidenceLinks items={evidenceFor("review", r.id)} />
                    {can("hr", "legal", "manager") && <EvidenceUpload entityType="review" entityId={r.id} onDone={reload} label="Attach" />}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Panel>

      <div className="grid gap-6 xl:grid-cols-2">
        <Panel title="Goals">
          {p.goals.length === 0 ? <p className="text-sm text-muted-foreground">No goals set.</p> : (
            <ul className="space-y-3">
              {p.goals.map((g) => (
                <li key={g.id} className="space-y-1.5">
                  <div className="flex items-center gap-2 text-sm">
                    <span className="flex-1 font-medium">{g.title}</span>
                    <span className="text-xs text-muted-foreground">{g.due_date ? `due ${fmtDay(g.due_date)}` : ""}</span>
                    {write && <Button size="xs" variant="ghost" onClick={() => { setPct(g.progress_pct); setProgress(g); }}>Update</Button>}
                  </div>
                  <div className="flex items-center gap-2">
                    <span className="h-1.5 flex-1 overflow-hidden rounded-full bg-muted">
                      <span className="block h-full rounded-full bg-[var(--series-1)]" style={{ width: `${g.progress_pct}%` }} />
                    </span>
                    <span className="w-10 text-right text-xs tabular-nums">{Math.round(g.progress_pct)}%</span>
                  </div>
                  {g.target && <div className="text-xs text-muted-foreground">Target: {g.target}</div>}
                </li>
              ))}
            </ul>
          )}
        </Panel>

        <Panel title="Feedback">
          {p.feedback.length === 0 ? <p className="text-sm text-muted-foreground">No feedback recorded.</p> : (
            <ul className="space-y-3 text-sm">
              {p.feedback.map((f) => (
                <li key={f.id} className="rounded-xl bg-muted/30 p-3">
                  <div className="text-xs text-muted-foreground">{fmtDay(f.given_on)} · {f.author === "hidden" ? "author hidden" : f.author}</div>
                  {f.strength && <p className="mt-1"><span className="text-muted-foreground">Strength:</span> {f.strength}</p>}
                  {f.improvement && <p className="mt-1"><span className="text-muted-foreground">To improve:</span> {f.improvement}</p>}
                  {f.example && <p className="mt-1 text-muted-foreground">Example: {f.example}</p>}
                </li>
              ))}
            </ul>
          )}
        </Panel>
      </div>

      <Panel title="Check-ins">
        {p.checkins.length === 0 ? <p className="text-sm text-muted-foreground">No check-ins recorded.</p> : (
          <ul className="space-y-3">
            {p.checkins.map((c) => (
              <li key={c.id} className="rounded-xl border p-3 text-sm">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="font-medium">{fmtDay(c.held_on ?? c.scheduled_for)}</span>
                  <span className="inline-flex items-center gap-1.5 text-xs">
                    <span className="size-2 rounded-full" style={{ background: SENTIMENT[c.sentiment] }} />{humanize(c.sentiment)}
                  </span>
                  <span className="text-xs text-muted-foreground">{c.held_on ? "held" : "scheduled"} · {c.created_by}</span>
                </div>
                {c.summary && <p className="mt-1">{c.summary}</p>}
                {c.private_note && <p className="mt-1 rounded-lg bg-muted/40 px-2 py-1 text-xs">Your private note: {c.private_note}</p>}
                {!c.private_note && c.has_private_note && <p className="mt-1 text-xs text-muted-foreground">Has a private note visible only to its author.</p>}
                {c.actions.length > 0 && (
                  <ul className="mt-2 space-y-1">
                    {c.actions.map((a) => (
                      <li key={a.id} className="flex items-center gap-2 text-xs">
                        <input type="checkbox" checked={a.done} disabled={!write} aria-label={a.text}
                               onChange={async () => {
                                 try { await post(`/performance/checkin-actions/${a.id}/toggle`); reload(); }
                                 catch (err) { toast.error((err as Error).message); }
                               }} />
                        <span className={cn(a.done && "text-muted-foreground line-through")}>{a.text}</span>
                        <span className="text-muted-foreground">· {a.owner}{a.due_date ? ` · ${fmtDay(a.due_date)}` : ""}</span>
                      </li>
                    ))}
                  </ul>
                )}
              </li>
            ))}
          </ul>
        )}
      </Panel>

      <FormDialog open={goalOpen} onOpenChange={setGoalOpen} title="Add goal" onSubmit={async () => {
        await post("/performance/goals", { employee_id: employeeId, title: goal.title, description: goal.description,
                                           target: goal.target, weight: goal.weight, due_date: goal.due_date || null });
        toast.success("Goal added");
        setGoal({ title: "", description: "", target: "", weight: 1, due_date: "" });
        reload();
      }}>
        <Field label="Title" htmlFor="g-title"><Input id="g-title" required value={goal.title} onChange={(ev) => setGoal({ ...goal, title: ev.target.value })} /></Field>
        <Field label="Description" htmlFor="g-desc"><Textarea id="g-desc" rows={2} value={goal.description} onChange={(ev) => setGoal({ ...goal, description: ev.target.value })} /></Field>
        <div className="grid grid-cols-3 gap-3">
          <Field label="Target" htmlFor="g-target"><Input id="g-target" value={goal.target} onChange={(ev) => setGoal({ ...goal, target: ev.target.value })} /></Field>
          <Field label="Weight" htmlFor="g-weight"><Input id="g-weight" type="number" min={0.1} step={0.1} value={goal.weight} onChange={(ev) => setGoal({ ...goal, weight: Number(ev.target.value) })} /></Field>
          <Field label="Due" htmlFor="g-due"><Input id="g-due" type="date" value={goal.due_date} onChange={(ev) => setGoal({ ...goal, due_date: ev.target.value })} /></Field>
        </div>
      </FormDialog>

      <FormDialog open={!!progress} onOpenChange={(o) => !o && setProgress(null)} title={`Progress: ${progress?.title ?? ""}`}
                  onSubmit={async () => {
                    await post(`/performance/goals/${progress!.id}/progress`, { pct, note: "" });
                    toast.success("Progress recorded");
                    reload();
                  }}>
        <Field label={`Complete: ${pct}%`} htmlFor="g-pct">
          <input id="g-pct" type="range" min={0} max={100} step={5} value={pct} className="w-full accent-[var(--primary)]"
                 onChange={(ev) => setPct(Number(ev.target.value))} />
        </Field>
      </FormDialog>

      <FormDialog open={checkinOpen} onOpenChange={setCheckinOpen} title="Log check-in" onSubmit={async () => {
        await post("/performance/checkins", {
          employee_id: employeeId, scheduled_for: checkin.scheduled_for, held_on: checkin.held_on || null,
          summary: checkin.summary, sentiment: checkin.sentiment, private_note: checkin.private_note || null,
          actions: checkin.action ? [{ text: checkin.action, owner: checkin.action_owner || "manager" }] : [],
        });
        toast.success("Check-in logged");
        reload();
      }}>
        <div className="grid grid-cols-3 gap-3">
          <Field label="Scheduled" htmlFor="c-s"><Input id="c-s" type="date" required value={checkin.scheduled_for} onChange={(ev) => setCheckin({ ...checkin, scheduled_for: ev.target.value })} /></Field>
          <Field label="Held on" htmlFor="c-h"><Input id="c-h" type="date" value={checkin.held_on} onChange={(ev) => setCheckin({ ...checkin, held_on: ev.target.value })} /></Field>
          <Field label="Sentiment" htmlFor="c-sent"><Select id="c-sent" value={checkin.sentiment} onChange={(v) => setCheckin({ ...checkin, sentiment: v })}
                                                             options={[["positive", "Positive"], ["neutral", "Neutral"], ["concern", "Concern"]]} /></Field>
        </div>
        <Field label="Summary" htmlFor="c-sum"><Textarea id="c-sum" rows={3} value={checkin.summary} onChange={(ev) => setCheckin({ ...checkin, summary: ev.target.value })} /></Field>
        <Field label="Private note (encrypted; only you can read it)" htmlFor="c-priv">
          <Textarea id="c-priv" rows={2} value={checkin.private_note} onChange={(ev) => setCheckin({ ...checkin, private_note: ev.target.value })} />
        </Field>
        <div className="grid grid-cols-[1fr_10rem] gap-3">
          <Field label="Action item (optional)" htmlFor="c-act"><Input id="c-act" value={checkin.action} onChange={(ev) => setCheckin({ ...checkin, action: ev.target.value })} /></Field>
          <Field label="Owner" htmlFor="c-own"><Input id="c-own" value={checkin.action_owner} placeholder="manager" onChange={(ev) => setCheckin({ ...checkin, action_owner: ev.target.value })} /></Field>
        </div>
      </FormDialog>

      <FormDialog open={feedbackOpen} onOpenChange={setFeedbackOpen} title="Give feedback" onSubmit={async () => {
        await post("/performance/feedback", { employee_id: employeeId, ...fb });
        toast.success("Feedback recorded");
        setFb({ strength: "", improvement: "", example: "", given_on: today() });
        reload();
      }}>
        <Field label="Strength" htmlFor="f-s"><Textarea id="f-s" rows={2} value={fb.strength} onChange={(ev) => setFb({ ...fb, strength: ev.target.value })} /></Field>
        <Field label="To improve" htmlFor="f-i"><Textarea id="f-i" rows={2} value={fb.improvement} onChange={(ev) => setFb({ ...fb, improvement: ev.target.value })} /></Field>
        <Field label="Specific example" htmlFor="f-e"><Textarea id="f-e" rows={2} value={fb.example} onChange={(ev) => setFb({ ...fb, example: ev.target.value })} /></Field>
        <Field label="Date" htmlFor="f-d"><Input id="f-d" type="date" required value={fb.given_on} onChange={(ev) => setFb({ ...fb, given_on: ev.target.value })} /></Field>
      </FormDialog>
    </>
  );
}

function StartPip({ employeeId, disabled, onDone }: { employeeId: number; disabled: boolean; onDone: () => void }) {
  const { can } = useAuth();
  const [open, setOpen] = useState(false);
  if (!can("hr", "legal", "manager")) return null;
  return (
    <div className="flex items-center gap-3">
      <Button className="gap-2 rounded-xl" disabled={disabled} onClick={() => setOpen(true)}><FileWarning className="size-4" />
        {can("hr", "legal") ? "Start a PIP" : "Propose a PIP"}
      </Button>
      {disabled && <span className="text-xs text-muted-foreground">This person already has an open PIP.</span>}
      <NewPipDialog open={open} onOpenChange={setOpen} employeeId={employeeId} onDone={onDone} />
    </div>
  );
}

function PayrollTab({ employeeId }: { employeeId: number }) {
  const { can } = useAuth();
  const q = useQuery<Payroll[]>(`/employees/${employeeId}/payroll`);
  const [open, setOpen] = useState(false);
  const latest = q.data?.[0];
  const [period, setPeriod] = useState("");
  const [rows, setRows] = useState<[string, string][]>([]);

  const show = (k: string, v: number) => (DAY_KEYS.has(k) ? `${v} days` : fmtPaise(v, 2));
  const openEditor = () => {
    setPeriod(latest?.period ?? today().slice(0, 7));
    setRows(Object.entries(latest?.data ?? { basic: 0, da: 0, hra: 0, special: 0 })
      .map(([k, v]) => [k, String(DAY_KEYS.has(k) ? v : v / 100)]));
    setOpen(true);
  };

  return (
    <Panel title="Payroll inputs" description="Monthly components used for FNF. Amounts in ₹; stored in paise."
           actions={can("finance") && <Button size="sm" className="rounded-xl" onClick={openEditor}>{latest ? "Edit / new period" : "Enter payroll"}</Button>}>
      <ErrorText error={q.error} />
      {q.data && q.data.length === 0 && <p className="text-sm text-muted-foreground">No payroll inputs yet. Import the payroll CSV or enter them here.</p>}
      <div className="space-y-4">
        {q.data?.map((pi) => (
          <div key={pi.id} className="rounded-xl border p-4">
            <div className="mb-3 flex items-center gap-2 text-sm">
              <span className="font-medium">{pi.period}</span>
              <span className="text-xs text-muted-foreground">{pi.source} · {pi.updated_by} · {fmtDate(pi.updated_at)}</span>
            </div>
            <dl className="grid gap-3 sm:grid-cols-3 lg:grid-cols-4">
              {Object.entries(pi.data).map(([k, v]) => <Detail key={k} label={humanize(k)}><span className="tabular-nums">{show(k, v)}</span></Detail>)}
            </dl>
          </div>
        ))}
      </div>
      <FormDialog open={open} onOpenChange={setOpen} title="Payroll inputs" submitLabel="Save"
                  description="Day counts are plain numbers; everything else is ₹ per month."
                  onSubmit={async () => {
                    const data = Object.fromEntries(rows.filter(([k]) => k.trim()).map(([k, v]) => {
                      const n = Number(v);
                      if (Number.isNaN(n)) throw new Error(`${k}: not a number`);
                      return [k.trim(), DAY_KEYS.has(k.trim()) ? n : Math.round(n * 100)];
                    }));
                    await put(`/employees/${employeeId}/payroll`, { period, data });
                    toast.success("Payroll inputs saved");
                    q.reload();
                  }}>
        <Field label="Period (YYYY-MM)" htmlFor="pp"><Input id="pp" required pattern="\d{4}-\d{2}" value={period} onChange={(ev) => setPeriod(ev.target.value)} /></Field>
        <div className="space-y-2">
          {rows.map(([k, v], i) => (
            <div key={i} className="grid grid-cols-[1fr_10rem] gap-2">
              <Input aria-label="Component" value={k} className="font-mono text-xs"
                     onChange={(ev) => setRows(rows.map((r, j) => (j === i ? [ev.target.value, r[1]] : r)))} />
              <Input aria-label={`${k} amount`} type="number" step="any" value={v}
                     onChange={(ev) => setRows(rows.map((r, j) => (j === i ? [r[0], ev.target.value] : r)))} />
            </div>
          ))}
          <Button type="button" size="sm" variant="ghost" onClick={() => setRows([...rows, ["", "0"]])}>Add component</Button>
        </div>
      </FormDialog>
    </Panel>
  );
}
