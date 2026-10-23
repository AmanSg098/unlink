"use client";

import { ArrowLeft, Calculator, CheckSquare, RefreshCw, Send, Wallet } from "lucide-react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { Suspense, useState } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { ErrorText, fmtDate, tableCls as t } from "@/components/common";
import { ApprovalPill, PageHeader, Panel, Pill } from "@/components/kit";
import { useAuth } from "@/components/auth";
import { Detail, Field, FormDialog, humanize, useAction } from "@/components/form-bits";
import { FNF_STATUS } from "@/components/fnf-bits";
import { useQuery } from "@/lib/use-query";
import { fmtDay, fmtPaise, post, type FnfLine, type FnfStatement, type Role } from "@/lib/api";
import { cn } from "@/lib/utils";

type WhatIf = Record<"pay_in_lieu" | "work_notice", { net_paise: number; earnings_paise: number; deductions_paise: number }>;

export default function FnfStatementPage() {
  return <Suspense><Statement /></Suspense>;
}

function Lines({ title, lines, total }: { title: string; lines: FnfLine[]; total: number }) {
  return (
    <Panel title={title} bodyClassName="p-0">
      <table className={t.table}>
        <thead className={t.thead}><tr className="border-b"><th className={t.th}>Component</th><th className={t.th}>How it was calculated</th>
          <th className={t.th}>Rule</th><th className={`${t.th} text-right`}>Amount</th></tr></thead>
        <tbody>
          {lines.map((l) => (
            <tr key={l.id} className={t.tr}>
              <td className={t.td}>{l.label}<div className="font-mono text-[11px] text-muted-foreground">{l.component}</div></td>
              <td className={`${t.td} max-w-md font-mono text-xs text-muted-foreground`}>{l.formula}</td>
              <td className={t.td}>
                {l.rule_key ? <Link href="/rules" className="rounded-md border px-1.5 py-0.5 font-mono text-[11px] whitespace-nowrap hover:border-primary">{l.rule_key}</Link>
                            : <span className="text-xs text-muted-foreground">payroll input</span>}
              </td>
              <td className={`${t.td} text-right tabular-nums`}>{fmtPaise(l.amount_paise, 2)}</td>
            </tr>
          ))}
          {lines.length === 0 && <tr><td colSpan={4} className={`${t.td} text-muted-foreground`}>None</td></tr>}
        </tbody>
        <tfoot><tr className="border-t font-medium"><td className={t.td} colSpan={3}>Total</td>
          <td className={`${t.td} text-right tabular-nums`}>{fmtPaise(total, 2)}</td></tr></tfoot>
      </table>
    </Panel>
  );
}

function Statement() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const { me, can } = useAuth();
  const q = useQuery<FnfStatement>(`/fnf/${id}`);
  const s = q.data;
  const caseQ = useQuery<{ fnf: FnfStatement[] }>(s ? `/exit-cases/${s.exit_case_id}` : null);
  const whatIf = useQuery<WhatIf>(s && can("hr", "finance") ? `/exit-cases/${s.exit_case_id}/fnf/what-if` : null);
  const [deciding, setDeciding] = useState<boolean | null>(null);
  const [comment, setComment] = useState("");
  const [paying, setPaying] = useState(false);
  const [reference, setReference] = useState("");
  const act = useAction();

  if (q.error && !s) return <ErrorText error={q.error} />;
  if (!s) return <div className="h-40 animate-pulse rounded-2xl bg-muted/40" />;

  const lines = s.lines ?? [];
  const step = s.current_step;
  const myTurn = !!step && !!me && (me.role === "admin" || step.roles.includes(me.role as Role));
  const rounding = Number(s.inputs.rounding_adjustment ?? 0);
  const versions = caseQ.data?.fnf ?? [];
  const wi = whatIf.data;

  return (
    <div className="space-y-6">
      <Link href="/fnf" className="inline-flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground">
        <ArrowLeft className="size-4" />FNF
      </Link>
      <PageHeader eyebrow={`${s.employee?.employee_code} · ${s.employee?.department} · case #${s.exit_case_id}`}
                  title={<span className="flex flex-wrap items-center gap-3">{s.employee?.full_name} · FNF v{s.version}<Pill spec={FNF_STATUS[s.status] ?? FNF_STATUS.draft} /></span>}
                  description={<>Computed by {s.computed_by} · {fmtDate(s.computed_at)} · hash <span className="font-mono text-xs">{s.content_hash.slice(0, 12)}…</span></>}
                  actions={
                    <>
                      {can("hr", "finance") && ["draft", "rejected"].includes(s.status) && (
                        <Button variant="outline" className="gap-2 rounded-xl" disabled={act.busy} onClick={() => act.run(async () => {
                          const n = await post<FnfStatement>(`/exit-cases/${s.exit_case_id}/fnf`);
                          router.push(`/fnf/${n.id}`);
                        }, "Recomputed as a new version")}><RefreshCw className="size-4" />Recompute</Button>
                      )}
                      {can("hr", "finance") && s.status === "draft" && (
                        <Button className="gap-2 rounded-xl" disabled={act.busy}
                                onClick={() => act.run(async () => { await post(`/fnf/${s.id}/submit`); q.reload(); }, "Submitted for approval")}>
                          <Send className="size-4" />Submit for approval
                        </Button>
                      )}
                      {s.status === "submitted" && myTurn && (
                        <>
                          <Button variant="outline" className="rounded-xl" onClick={() => { setComment(""); setDeciding(false); }}>Reject</Button>
                          <Button className="gap-2 rounded-xl" onClick={() => { setComment(""); setDeciding(true); }}><CheckSquare className="size-4" />Approve</Button>
                        </>
                      )}
                      {s.status === "approved" && can("finance") && (
                        <Button className="gap-2 rounded-xl" onClick={() => setPaying(true)}><Wallet className="size-4" />Mark paid</Button>
                      )}
                    </>
                  } />
      <ErrorText error={act.error} />

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <Panel><Detail label="Earnings"><span className="text-xl font-semibold tabular-nums">{fmtPaise(s.earnings_paise, 2)}</span></Detail></Panel>
        <Panel><Detail label="Deductions"><span className="text-xl font-semibold tabular-nums">{fmtPaise(s.deductions_paise, 2)}</span></Detail></Panel>
        <Panel className="ring-1 ring-primary/30"><Detail label="Net payable"><span className="text-xl font-semibold tabular-nums">{fmtPaise(s.net_paise, 2)}</span></Detail></Panel>
        <Panel><Detail label={s.status === "paid" ? "Paid" : "Pay by"}>
          <span className="text-xl font-semibold">{s.status === "paid" ? fmtDay(s.paid_at) : fmtDay(s.payment_due_on)}</span>
          {s.payment_reference && <div className="text-xs text-muted-foreground">Ref {s.payment_reference}</div>}
        </Detail></Panel>
      </div>

      <div className="grid gap-6 xl:grid-cols-2">
        <Lines title="Earnings" lines={lines.filter((l) => l.kind === "earning")} total={s.earnings_paise} />
        <Lines title="Deductions" lines={lines.filter((l) => l.kind === "deduction")} total={s.deductions_paise} />
      </div>
      {rounding !== 0 && (
        <p className="text-xs text-muted-foreground">Net rounded to the rupee; rounding adjustment {fmtPaise(rounding, 2)}.</p>
      )}

      <div className="grid gap-6 xl:grid-cols-3">
        <Panel title="Inputs used">
          <dl className="grid grid-cols-2 gap-4">
            <Detail label="Payroll period">{String(s.inputs.period ?? "–")}</Detail>
            <Detail label="Last working day">{fmtDay(s.inputs.last_working_day as string)}</Detail>
            <Detail label="Notice days">{String(s.inputs.notice_days ?? "–")}</Detail>
            <Detail label="Notice shortfall">{String(s.inputs.shortfall_days ?? 0)} days</Detail>
            <Detail label="Pay in lieu of notice">{s.pay_in_lieu ? "Yes" : "No"}</Detail>
            <Detail label="Reason">{String(s.inputs.reason_code ?? "–")}</Detail>
          </dl>
        </Panel>

        <Panel title="Approvals" description={s.needs_legal ? "Finance, then Legal (compensation or gratuity present)." : "Finance."}>
          {s.approvals && s.approvals.length > 0 ? (
            <ol className="space-y-3">
              {s.approvals.map((a) => (
                <li key={a.id} className="text-sm">
                  <div className="flex items-center gap-2">
                    <span className="flex-1 font-medium">{humanize(a.step)}<span className="ml-1 text-xs font-normal text-muted-foreground">round {a.round}</span></span>
                    <ApprovalPill status={a.status} />
                  </div>
                  <div className="text-xs text-muted-foreground">
                    {a.decided_by ? `${a.decided_by} · ${fmtDate(a.decided_at)}` : `Waiting for ${a.roles.join(" / ")}`}
                  </div>
                  {a.comment && <p className="mt-1 text-xs">“{a.comment}”</p>}
                </li>
              ))}
            </ol>
          ) : <p className="text-sm text-muted-foreground">Not submitted yet.</p>}
        </Panel>

        <Panel title="Compare" description="Versions of this case's FNF, and paying notice in lieu vs working it out.">
          {versions.length > 1 && (
            <ul className="mb-4 space-y-1.5 text-sm">
              {versions.map((v) => (
                <li key={v.id} className={cn("flex items-center gap-2", v.id === s.id && "font-medium")}>
                  <Link href={`/fnf/${v.id}`} className="w-10 hover:text-primary">v{v.version}</Link>
                  <span className="flex-1 text-xs text-muted-foreground">{humanize(v.status)}</span>
                  <span className="tabular-nums">{fmtPaise(v.net_paise)}</span>
                  <span className={cn("w-24 text-right text-xs tabular-nums", v.net_paise - s.net_paise > 0 ? "text-[var(--status-good)]" : "text-muted-foreground")}>
                    {v.id === s.id ? "this" : `${v.net_paise >= s.net_paise ? "+" : "−"}${fmtPaise(Math.abs(v.net_paise - s.net_paise))}`}
                  </span>
                </li>
              ))}
            </ul>
          )}
          {wi ? (
            <div className="grid grid-cols-2 gap-3">
              {(["pay_in_lieu", "work_notice"] as const).map((k) => (
                <div key={k} className={cn("rounded-xl border p-3", (k === "pay_in_lieu") === s.pay_in_lieu && "border-primary/50")}>
                  <div className="text-xs text-muted-foreground">{k === "pay_in_lieu" ? "Pay in lieu" : "Work the notice"}</div>
                  <div className="mt-1 font-semibold tabular-nums">{fmtPaise(wi[k].net_paise)}</div>
                  <div className="text-[11px] text-muted-foreground">+{fmtPaise(wi[k].earnings_paise)} / −{fmtPaise(wi[k].deductions_paise)}</div>
                </div>
              ))}
            </div>
          ) : whatIf.error ? <p className="text-xs text-muted-foreground">{whatIf.error}</p>
            : versions.length <= 1 && <p className="flex items-center gap-2 text-sm text-muted-foreground"><Calculator className="size-4" />Nothing to compare yet.</p>}
        </Panel>
      </div>

      <FormDialog open={deciding !== null} onOpenChange={(o) => !o && setDeciding(null)}
                  title={deciding ? `Approve ${humanize(step?.step)}` : "Reject this statement"}
                  submitLabel={deciding ? "Approve" : "Reject"} destructive={deciding === false}
                  description={deciding ? `You're approving the statement with hash ${s.content_hash.slice(0, 12)}…; any change after this needs a new version and fresh approval.`
                                        : "The statement goes back to draft for correction."}
                  onSubmit={async () => {
                    await post(`/fnf/${s.id}/decision`, { approve: deciding, comment: comment || null });
                    toast.success(deciding ? "Approved" : "Rejected");
                    q.reload();
                  }}>
        <Field label={deciding ? "Comment (optional)" : "Reason"} htmlFor="fnf-c">
          <Textarea id="fnf-c" rows={3} required={!deciding} value={comment} onChange={(e) => setComment(e.target.value)} />
        </Field>
      </FormDialog>

      <FormDialog open={paying} onOpenChange={setPaying} title="Mark as paid" submitLabel="Mark paid"
                  onSubmit={async () => {
                    await post(`/fnf/${s.id}/mark-paid`, { reference });
                    toast.success("Marked paid");
                    q.reload();
                  }}>
        <Field label="Payment reference" htmlFor="fnf-ref"><Input id="fnf-ref" required minLength={3} value={reference} onChange={(e) => setReference(e.target.value)} /></Field>
      </FormDialog>
    </div>
  );
}
