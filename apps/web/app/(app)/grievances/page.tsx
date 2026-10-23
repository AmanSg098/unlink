"use client";

import { CircleCheck, CircleDashed, CirclePause, Gavel, Hourglass, Plus, ShieldAlert, Sparkles, TriangleAlert } from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Textarea } from "@/components/ui/textarea";
import { ErrorText, fmtDate, tableCls as t } from "@/components/common";
import { AiDraftCard } from "@/components/ai-draft";
import { EmptyState, PageHeader, Panel, Pill } from "@/components/kit";
import { Detail, Field, FormDialog, Select, humanize, useAction, type PillSpec } from "@/components/form-bits";
import { useQuery } from "@/lib/use-query";
import { fmtDay, post, type AiDraft, type CaseSummary, type Grievance } from "@/lib/api";
import { cn } from "@/lib/utils";

const STATUS: Record<string, PillSpec> = {
  open: { label: "Open", icon: CircleDashed, color: "var(--status-warning)" },
  under_review: { label: "Under review", icon: Hourglass, color: "var(--series-1)" },
  decided: { label: "Decided", icon: Gavel, color: "var(--status-good)" },
  appealed: { label: "Appealed", icon: TriangleAlert, color: "var(--status-warning)" },
  closed: { label: "Closed", icon: CircleCheck, color: "var(--status-good)" },
};
const CATEGORIES: [string, string][] = [["process", "Process (puts the case on hold)"], ["reason", "Reason (puts the case on hold)"],
  ["selection", "Selection (puts the case on hold)"], ["fnf", "FNF / money"], ["other", "Other"]];
const OUTCOMES: [string, string][] = [["upheld", "Upheld"], ["partly_upheld", "Partly upheld"], ["rejected", "Not upheld"]];
const outcomeLabel = (o: string | null) => OUTCOMES.find(([k]) => k === o)?.[1] ?? "–";

export default function GrievancesPage() {
  return <Suspense><Grievances /></Suspense>;
}

function Grievances() {
  const params = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();
  const q = useQuery<Grievance[]>("/grievances");
  const cases = useQuery<CaseSummary[]>("/exit-cases");
  const [logOpen, setLogOpen] = useState(false);
  const [form, setForm] = useState({ exit_case_id: "", category: "process", description: "" });
  const openId = params.get("id");
  const list = q.data ?? [];
  const today = new Date().toISOString().slice(0, 10);
  const openCases = (cases.data ?? []).filter((c) => !["closed", "withdrawn"].includes(c.state));
  const setOpen = (id: number | null) => router.replace(id ? `${pathname}?id=${id}` : pathname, { scroll: false });

  return (
    <div className="space-y-8">
      <PageHeader eyebrow="Act" title="Grievances"
                  description="A grievance about the process, reason or selection puts the exit case on hold until it's decided. Acknowledgements and outcomes reach the employee only through an approved notice."
                  actions={<Button className="gap-2 rounded-xl" onClick={() => setLogOpen(true)}><Plus className="size-4" />Log grievance</Button>} />

      <Panel bodyClassName="p-0">
        <ErrorText error={q.error} />
        {!q.loading && list.length === 0 ? <EmptyState icon={ShieldAlert} title="No grievances" /> : (
          <table className={t.table}>
            <thead className={t.thead}><tr className="border-b"><th className={t.th}>Reference</th><th className={t.th}>Person</th>
              <th className={t.th}>Category</th><th className={t.th}>Status</th><th className={t.th}>Acknowledge by</th>
              <th className={t.th}>Outcome</th><th className={t.th}>Case</th></tr></thead>
            <tbody>
              {list.map((g) => {
                const ackLate = !g.acknowledged_at && g.ack_due_on < today;
                return (
                  <tr key={g.id} className={cn(t.tr, "cursor-pointer")} onClick={() => setOpen(g.id)}>
                    <td className={`${t.td} font-mono text-xs`}>{g.ref}</td>
                    <td className={t.td}>{g.employee.full_name}<div className="text-xs text-muted-foreground">{g.employee.employee_code}</div></td>
                    <td className={t.td}>{humanize(g.category)}</td>
                    <td className={t.td}><Pill spec={STATUS[g.status] ?? STATUS.open} /></td>
                    <td className={cn(t.td, "whitespace-nowrap text-xs", ackLate && "font-medium text-[var(--status-critical)]")}>
                      {g.acknowledged_at ? <span className="text-muted-foreground">Acknowledged {fmtDay(g.acknowledged_at)}</span>
                                         : <>{ackLate && "Overdue · "}{fmtDay(g.ack_due_on)}</>}
                    </td>
                    <td className={`${t.td} text-xs`}>
                      {outcomeLabel(g.outcome)}
                      {g.appeal && <div className="text-muted-foreground">Appeal: {g.appeal.status === "open" ? "open" : outcomeLabel(g.appeal.outcome)}</div>}
                    </td>
                    <td className={t.td} onClick={(e) => e.stopPropagation()}>
                      {g.exit_case_id && (
                        <Link href={`/cases/${g.exit_case_id}`} className="inline-flex items-center gap-1.5 text-xs text-muted-foreground hover:text-foreground">
                          #{g.exit_case_id}{g.case_state === "on_hold" && <CirclePause className="size-3.5 text-[var(--status-warning)]" aria-label="On hold" />}
                        </Link>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
      </Panel>

      <FormDialog open={logOpen} onOpenChange={setLogOpen} wide title="Log a grievance"
                  description="Record the employee's concern in their words. Process, reason and selection grievances put the case on hold; an acknowledgement draft is prepared for review."
                  submitLabel="Log grievance"
                  onSubmit={async () => {
                    if (!form.exit_case_id) throw new Error("Choose the exit case");
                    const g = await post<Grievance>("/grievances", { ...form, exit_case_id: Number(form.exit_case_id) });
                    toast.success(`${g.ref} logged`);
                    setForm({ exit_case_id: "", category: "process", description: "" });
                    q.reload();
                  }}>
        <Field label="Exit case" htmlFor="gv-case">
          <Select id="gv-case" required value={form.exit_case_id} onChange={(v) => setForm({ ...form, exit_case_id: v })}
                  options={[["", "Choose…"], ...openCases.map((c): [string, string] =>
                    [String(c.id), `#${c.id} · ${c.employee.full_name} (${c.employee.employee_code}) · ${c.state_label}`])]} />
        </Field>
        <Field label="Category" htmlFor="gv-cat">
          <Select id="gv-cat" value={form.category} onChange={(v) => setForm({ ...form, category: v })} options={CATEGORIES} />
        </Field>
        <Field label="Description" htmlFor="gv-desc" hint="Stored encrypted. AI summaries see it with names redacted.">
          <Textarea id="gv-desc" required minLength={10} rows={5} value={form.description}
                    onChange={(e) => setForm({ ...form, description: e.target.value })} />
        </Field>
      </FormDialog>

      <Dialog open={!!openId} onOpenChange={(o) => !o && setOpen(null)}>
        <DialogContent className="max-h-[90vh] overflow-y-auto rounded-2xl sm:max-w-3xl">
          {openId && <GrievanceDetail id={openId} onChange={q.reload} />}
        </DialogContent>
      </Dialog>
    </div>
  );
}

function GrievanceDetail({ id, onChange }: { id: string; onChange: () => void }) {
  const q = useQuery<Grievance>(`/grievances/${id}`);
  const [deciding, setDeciding] = useState(false);
  const [appealing, setAppealing] = useState(false);
  const [d, setD] = useState({ findings: "", outcome: "rejected", reasons: "" });
  const [a, setA] = useState({ outcome: "rejected", reasons: "" });
  const [summary, setSummary] = useState<AiDraft | null>(null);
  const act = useAction();
  const g = q.data;
  const refresh = () => { q.reload(); onChange(); };

  if (!g) return <><DialogHeader><DialogTitle>Grievance</DialogTitle></DialogHeader><ErrorText error={q.error} /></>;

  return (
    <div className="space-y-5">
      <DialogHeader>
        <DialogTitle className="flex flex-wrap items-center gap-2">{g.ref} · {g.employee.full_name}<Pill spec={STATUS[g.status] ?? STATUS.open} /></DialogTitle>
        <DialogDescription>{humanize(g.category)} · logged by {g.logged_by} · {fmtDate(g.logged_at)}</DialogDescription>
      </DialogHeader>

      <dl className="grid grid-cols-2 gap-4 sm:grid-cols-4">
        <Detail label="Acknowledge by">{fmtDay(g.ack_due_on)}</Detail>
        <Detail label="Acknowledged">{g.acknowledged_at ? fmtDate(g.acknowledged_at) : "Not yet"}</Detail>
        <Detail label="Exit case">{g.exit_case_id ? <Link className="hover:text-primary" href={`/cases/${g.exit_case_id}`}>#{g.exit_case_id} · {humanize(g.case_state)}</Link> : "–"}</Detail>
        <Detail label="Employee ID">{g.employee.employee_code}</Detail>
      </dl>

      <div className="rounded-xl bg-muted/30 p-4">
        <div className="mb-1 text-xs text-muted-foreground">Concern</div>
        <p className="text-sm whitespace-pre-wrap">{g.description}</p>
      </div>

      {g.outcome && (
        <div className="rounded-xl border p-4 text-sm">
          <div className="text-xs text-muted-foreground">Decision · {g.decided_by} · {fmtDate(g.decided_at)}</div>
          <div className="mt-1 font-medium">{outcomeLabel(g.outcome)}</div>
          <p className="mt-2"><span className="text-muted-foreground">Findings:</span> {g.findings}</p>
          <p className="mt-1"><span className="text-muted-foreground">Reasons:</span> {g.outcome_reasons}</p>
        </div>
      )}

      {g.appeal && (
        <div className="rounded-xl border p-4 text-sm">
          <div className="text-xs text-muted-foreground">Appeal · {g.appeal.status}</div>
          {g.appeal.grounds && <p className="mt-1 whitespace-pre-wrap">{g.appeal.grounds}</p>}
          {g.appeal.outcome && (
            <p className="mt-2"><span className="font-medium">{outcomeLabel(g.appeal.outcome)}</span> · {g.appeal.decided_by}: {g.appeal.reasons}</p>
          )}
        </div>
      )}

      {summary && <AiDraftCard draft={summary} title="Grievance summary" />}
      <ErrorText error={act.error} />

      <div className="flex flex-wrap gap-2 border-t pt-4">
        <Button variant="outline" className="gap-2" disabled={act.busy}
                onClick={() => act.run(async () => setSummary(await post<AiDraft>(`/grievances/${g.id}/ai/summary`)))}>
          <Sparkles className="size-4" />AI summary for the reviewer
        </Button>
        <span className="flex-1" />
        {!g.acknowledged_at && (
          <Button variant="outline" disabled={act.busy}
                  onClick={() => act.run(async () => { await post(`/grievances/${g.id}/acknowledge`); refresh(); }, "Marked acknowledged")}>
            Mark acknowledged
          </Button>
        )}
        {["open", "under_review"].includes(g.status) && <Button className="gap-2" onClick={() => setDeciding(true)}><Gavel className="size-4" />Decide</Button>}
        {g.status === "appealed" && <Button className="gap-2" onClick={() => setAppealing(true)}><Gavel className="size-4" />Decide appeal</Button>}
      </div>
      <p className="text-xs text-muted-foreground">
        The person deciding can&apos;t be the case owner or the person who logged it; an appeal needs a different decider again.
        The outcome message is prepared as a notice draft for approval.
      </p>

      <FormDialog open={deciding} onOpenChange={setDeciding} wide title={`Decide ${g.ref}`} submitLabel="Record decision"
                  onSubmit={async () => { await post(`/grievances/${g.id}/decision`, d); toast.success("Decision recorded"); refresh(); }}>
        <Field label="Findings" htmlFor="gd-f"><Textarea id="gd-f" required minLength={5} rows={4} value={d.findings} onChange={(e) => setD({ ...d, findings: e.target.value })} /></Field>
        <Field label="Outcome" htmlFor="gd-o"><Select id="gd-o" value={d.outcome} onChange={(v) => setD({ ...d, outcome: v })} options={OUTCOMES} /></Field>
        <Field label="Reasons" htmlFor="gd-r"><Textarea id="gd-r" required minLength={5} rows={3} value={d.reasons} onChange={(e) => setD({ ...d, reasons: e.target.value })} /></Field>
      </FormDialog>

      <FormDialog open={appealing} onOpenChange={setAppealing} title={`Decide appeal on ${g.ref}`} submitLabel="Record appeal decision"
                  onSubmit={async () => { await post(`/grievances/${g.id}/appeal/decision`, a); toast.success("Appeal decided"); refresh(); }}>
        <Field label="Outcome" htmlFor="ga-o"><Select id="ga-o" value={a.outcome} onChange={(v) => setA({ ...a, outcome: v })} options={OUTCOMES} /></Field>
        <Field label="Reasons" htmlFor="ga-r"><Textarea id="ga-r" required minLength={5} rows={3} value={a.reasons} onChange={(e) => setA({ ...a, reasons: e.target.value })} /></Field>
      </FormDialog>
    </div>
  );
}
