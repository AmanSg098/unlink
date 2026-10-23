"use client";

import {
  CalendarDays, CircleCheck, CircleDashed, Download, FileCheck2, FileText, KeyRound, Paperclip, Scale, Sparkles,
  TriangleAlert, Upload, Wallet,
} from "lucide-react";
import Link from "next/link";
import { useRef, useState } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { fmtDate, tableCls as t } from "@/components/common";
import { AiDraftCard } from "@/components/ai-draft";
import { AckPill, ApprovalTrail, DecisionDialog, Hash, MessageStatusPill, useAct } from "@/components/case-ui";
import { DraftIssues, DraftStatusPill } from "@/components/notice-ui";
import { EmptyState, Panel, Pill } from "@/components/kit";
import { useAuth } from "@/components/auth";
import { useQuery } from "@/lib/use-query";
import {
  api, fmtDay, fmtPaise, post, upload, type AiDraft, type Approval, type AuditEntry, type CaseSummary,
  type ClearanceItem, type Doc, type Evidence, type FnfStatement, type NoticeMessage, type Role, type Task,
} from "@/lib/api";
import { cn } from "@/lib/utils";

export type ReasonCode = { code: string; name: string; evidence: string; evidence_type: string | null };
export type CaseDetail = {
  case: CaseSummary;
  states: { key: string; label: string }[];
  reason: {
    codes: ReasonCode[];
    evidence: { ok: boolean; requirement: string | null; found: string[]; missing: string | null };
    other_approved: boolean;
  };
  evidence: Evidence[];
  tasks: Task[];
  drafts: { id: number; version: number; subject: string; status: string; template: string; missing_fields: string[];
    flagged_terms: string[]; created_by: string; created_at: string }[];
  messages: NoticeMessage[];
  fnf: FnfStatement[];
  documents: Doc[];
  clearance: ClearanceItem[];
  clearance_complete: boolean;
  grievances: { id: number; category: string; status: string; logged_at: string; outcome: string | null }[];
  approvals: Record<"exit_effective" | "hris_push" | "reason_other" | "clearance_exception", Approval[]>;
  self_service: { invited: boolean; active: boolean };
  audit: AuditEntry[];
};

type Props = { d: CaseDetail; reload: () => void };

const EVIDENCE_TYPES = ["review_form", "email", "incident_note", "attendance_record", "investigation_outcome",
  "role_elimination_record", "restructuring_record", "location_decision", "signed_acceptance", "decision_record", "other"];
const label = (s: string) => s.replace(/_/g, " ");
const sel = "h-9 w-full rounded-xl border bg-background/50 px-3 text-sm";
const pending = (items: Approval[]) => items.find((a) => a.status === "pending");
const reached = (d: CaseDetail, key: string) => {
  const s = d.case.state === "on_hold" ? d.case.held_from_state ?? "" : d.case.state;
  const keys = d.states.map((x) => x.key);
  return keys.indexOf(s) >= keys.indexOf(key) && keys.indexOf(s) >= 0;
};

function Check({ ok, children }: { ok: boolean; children: React.ReactNode }) {
  return (
    <div className="flex items-start gap-2 text-sm">
      {ok ? <CircleCheck className="mt-0.5 size-4 shrink-0 text-[var(--status-good)]" aria-label="Done" />
          : <CircleDashed className="mt-0.5 size-4 shrink-0 text-muted-foreground" aria-label="Not done" />}
      <div>{children}</div>
    </div>
  );
}

// ------------------------------------------------------------------ reason and evidence
export function ReasonSection({ d, reload }: Props) {
  const { can } = useAuth();
  const c = d.case;
  const locked = reached(d, "notice_sent") || c.state === "on_hold" || c.state === "withdrawn";
  const [code, setCode] = useState(c.reason_code ?? "");
  const [detail, setDetail] = useState(c.reason_detail ?? "");
  const [evType, setEvType] = useState("");
  const [deciding, setDeciding] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);
  const { busy, run } = useAct();
  const chosen = d.reason.codes.find((x) => x.code === code);
  const otherPending = pending(d.approvals.reason_other);

  async function save() {
    if (await run(() => post(`/exit-cases/${c.id}/reason`, { reason_code: code, reason_detail: detail || null,
                                                               evidence_ids: d.evidence.map((e) => e.id) }),
                  code === "OTHER" ? "Saved. Legal must approve an 'Other' reason." : "Reason saved")) reload();
  }

  async function onFile(f: File) {
    const type = evType || chosen?.evidence_type || "other";
    if (await run(() => upload(`/exit-cases/${c.id}/evidence`, { evidence_type: type }, f), "Evidence attached")) reload();
    if (fileRef.current) fileRef.current.value = "";
  }

  return (
    <Panel title="Reason and evidence" description="Every exit needs a reason code backed by the evidence that code requires.">
      <div className="grid gap-6 lg:grid-cols-2">
        <div className="space-y-3">
          <div className="space-y-1.5">
            <Label htmlFor="reason-code">Reason code</Label>
            <select id="reason-code" className={sel} value={code} disabled={locked || !can("hr")} onChange={(e) => setCode(e.target.value)}>
              <option value="">Choose…</option>
              {d.reason.codes.map((x) => <option key={x.code} value={x.code}>{x.code} · {x.name}</option>)}
            </select>
            {chosen && <p className="text-xs text-muted-foreground">Needs: {chosen.evidence}</p>}
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="reason-detail">Detail {code === "OTHER" && "(at least 20 characters; Legal approves)"}</Label>
            <Textarea id="reason-detail" rows={3} value={detail} disabled={locked || !can("hr")} onChange={(e) => setDetail(e.target.value)} />
            <p className="text-xs text-muted-foreground">Text citing protected characteristics or leave is refused.</p>
          </div>
          {can("hr") && !locked && (
            <Button disabled={busy || !code} onClick={save}>Save reason</Button>
          )}
          {locked && reached(d, "notice_sent") && <p className="text-xs text-muted-foreground">The reason is fixed once the notice is sent.</p>}
        </div>
        <div className="space-y-3">
          <div className="rounded-xl border p-3"
               style={{ borderColor: `color-mix(in oklab, var(--status-${d.reason.evidence.ok ? "good" : "warning"}) 45%, transparent)` }}>
            <div className="flex items-center gap-2 text-sm font-medium">
              {d.reason.evidence.ok
                ? <><CircleCheck className="size-4 text-[var(--status-good)]" />Evidence requirement met</>
                : <><TriangleAlert className="size-4 text-[var(--status-warning)]" />Evidence missing</>}
            </div>
            {d.reason.evidence.missing && <p className="mt-1 text-sm text-muted-foreground">{d.reason.evidence.missing}</p>}
            {d.reason.evidence.found.length > 0 && (
              <ul className="mt-2 list-disc pl-5 text-sm">{d.reason.evidence.found.map((f) => <li key={f}>{f}</li>)}</ul>
            )}
          </div>
          {c.reason_code === "OTHER" && (
            <div className="space-y-2">
              <ApprovalTrail items={d.approvals.reason_other} />
              {otherPending && can("legal") && (
                <Button size="sm" onClick={() => setDeciding(true)}><Scale className="size-4" />Review justification</Button>
              )}
            </div>
          )}
          <div className="space-y-2">
            <div className="text-sm font-medium">Attached evidence</div>
            {d.evidence.length ? (
              <ul className="space-y-1 text-sm">
                {d.evidence.map((e) => (
                  <li key={e.id} className="flex items-center gap-2">
                    <Paperclip className="size-3.5 text-muted-foreground" />
                    <a className="hover:text-primary" href={`/api/employees/evidence/${e.id}/download`}>{e.filename}</a>
                    <span className="text-xs text-muted-foreground">{label(e.evidence_type)} · {e.uploaded_by}</span>
                  </li>
                ))}
              </ul>
            ) : <p className="text-sm text-muted-foreground">None yet.</p>}
            {can("hr", "legal") && c.state !== "withdrawn" && (
              <div className="flex flex-wrap items-center gap-2">
                <select className={`${sel} w-56`} aria-label="Evidence type" value={evType || chosen?.evidence_type || "other"}
                        onChange={(e) => setEvType(e.target.value)}>
                  {EVIDENCE_TYPES.map((x) => <option key={x} value={x}>{label(x)}</option>)}
                </select>
                <input ref={fileRef} type="file" className="hidden" accept=".pdf,.png,.jpg,.jpeg,.txt,.eml"
                       onChange={(e) => e.target.files?.[0] && onFile(e.target.files[0])} />
                <Button size="sm" variant="outline" disabled={busy} onClick={() => fileRef.current?.click()}>
                  <Upload className="size-3.5" />Attach file
                </Button>
              </div>
            )}
          </div>
        </div>
      </div>
      <DecisionDialog open={deciding} onOpenChange={setDeciding} title="Approve this 'Other' justification?"
                      description={<span className="block whitespace-pre-wrap">“{c.reason_detail}”</span>}
                      hash={otherPending?.content_hash}
                      onDecide={async (approve, comment) => {
                        await post(`/exit-cases/${c.id}/reason/decision`, { approve, comment: comment || null });
                        toast.success(approve ? "Justification approved" : "Justification rejected");
                        reload();
                      }} />
    </Panel>
  );
}

// ------------------------------------------------------------------ notice dates and last day
export function DatesSection({ d, reload }: Props) {
  const { can } = useAuth();
  const c = d.case;
  const sent = reached(d, "notice_sent");
  const [noticeDate, setNoticeDate] = useState(c.notice_date ?? "");
  const [pil, setPil] = useState(c.pay_in_lieu);
  const [actual, setActual] = useState(c.actual_last_day ?? "");
  const { busy, run } = useAct();
  const active = c.state !== "on_hold" && c.state !== "withdrawn" && c.state !== "closed";

  return (
    <Panel title="Notice and last working day" description="The notice period and last day are computed from the jurisdiction rules; every step is shown.">
      <div className="grid gap-6 lg:grid-cols-2">
        <div className="space-y-3">
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1.5">
              <Label htmlFor="notice-date">Planned notice date</Label>
              <Input id="notice-date" type="date" value={noticeDate} disabled={sent || !can("hr") || !active}
                     onChange={(e) => setNoticeDate(e.target.value)} />
            </div>
            <label className="mt-6 flex items-center gap-2 text-sm">
              <input type="checkbox" checked={pil} disabled={sent || !can("hr") || !active} onChange={(e) => setPil(e.target.checked)} />
              Pay in lieu of notice
            </label>
          </div>
          {can("hr") && !sent && active && (
            <Button disabled={busy || !noticeDate} onClick={async () => {
              const r = await run(() => post<{ notice_days: number; last_working_day: string }>(
                `/exit-cases/${c.id}/dates`, { notice_date: noticeDate, pay_in_lieu: pil }));
              if (r) {
                toast.success(`${r.notice_days} days' notice; last working day ${fmtDay(r.last_working_day)}`,
                              { description: "Existing unbatched drafts quoted the old dates and were superseded." });
                reload();
              }
            }}>
              <CalendarDays className="size-4" />Compute dates
            </Button>
          )}
          <dl className="grid grid-cols-2 gap-3 text-sm">
            <div><dt className="text-xs text-muted-foreground">Notice period</dt><dd>{c.notice_days !== null ? `${c.notice_days} days` : "–"}</dd></div>
            <div><dt className="text-xs text-muted-foreground">Computed last working day</dt><dd>{fmtDay(c.last_working_day)}</dd></div>
            <div><dt className="text-xs text-muted-foreground">Confirmed last day</dt><dd>{fmtDay(c.actual_last_day)}</dd></div>
            <div><dt className="text-xs text-muted-foreground">Pay in lieu</dt><dd>{c.pay_in_lieu ? "Yes" : "No"}</dd></div>
          </dl>
        </div>
        <div className="space-y-3">
          <div className="text-sm font-medium">How the last day was computed</div>
          {c.lwd_trace?.steps.length ? (
            <ol className="space-y-1.5 text-sm">
              {c.lwd_trace.steps.map((s, i) => (
                <li key={i} className="flex gap-2">
                  <span className="w-5 shrink-0 text-right text-xs text-muted-foreground tabular-nums">{i + 1}.</span>
                  <span className="flex-1">{s.step}</span>
                  {s.rule && <code className="shrink-0 rounded bg-muted px-1.5 text-[11px]">{s.rule}</code>}
                </li>
              ))}
            </ol>
          ) : <p className="text-sm text-muted-foreground">Set a notice date to compute it.</p>}
          {sent && can("hr") && active && !reached(d, "last_day_set") && (
            <div className="space-y-2 rounded-xl border p-3">
              <Label htmlFor="actual">Confirm the last day actually worked</Label>
              <div className="flex gap-2">
                <Input id="actual" type="date" value={actual} max={c.last_working_day ?? undefined} onChange={(e) => setActual(e.target.value)} />
                <Button disabled={busy} onClick={async () => {
                  if (await run(() => post(`/exit-cases/${c.id}/last-day`, { actual_last_day: actual || null }), "Last day confirmed")) reload();
                }}>Confirm</Button>
              </div>
              <p className="text-xs text-muted-foreground">Leave blank to confirm the computed day. An earlier day creates a notice shortfall in the FNF.</p>
            </div>
          )}
        </div>
      </div>
    </Panel>
  );
}

// ------------------------------------------------------------------ tasks
export function TasksSection({ d, reload }: Props) {
  const { me, can } = useAuth();
  const { busy, run } = useAct();
  const mine = (x: Task) => can(x.owner_role as Role, "hr") || (x.owner_role === "manager" && me?.role === "manager");
  const today = new Date().toISOString().slice(0, 10);
  return (
    <Panel title="Tasks" description="Created automatically as the case moves through each stage.">
      {d.tasks.length ? (
        <ul className="divide-y">
          {d.tasks.map((x) => {
            const overdue = x.status === "open" && x.due_date !== null && x.due_date < today;
            return (
              <li key={x.id} className="flex items-center gap-3 py-2 text-sm">
                <input type="checkbox" aria-label={`Mark ${x.title} done`} checked={x.status === "done"}
                       disabled={busy || x.status === "cancelled" || !mine(x)}
                       onChange={async () => {
                         if (await run(() => api(`/exit-cases/${d.case.id}/tasks/${x.id}`,
                                                 { method: "PATCH", body: JSON.stringify({ status: x.status === "done" ? "open" : "done" }) }))) reload();
                       }} />
                <span className={cn("flex-1", x.status !== "open" && "text-muted-foreground line-through")}>{x.title}</span>
                <span className="text-xs text-muted-foreground capitalize">{x.owner_role}</span>
                <span className={cn("w-28 text-right text-xs", overdue ? "text-[var(--status-critical)]" : "text-muted-foreground")}>
                  {x.status === "done" ? `Done · ${x.completed_by ?? ""}` : x.status === "cancelled" ? "Cancelled" : `${overdue ? "Overdue · " : ""}${fmtDay(x.due_date)}`}
                </span>
              </li>
            );
          })}
        </ul>
      ) : <EmptyState icon={CircleCheck} title="No tasks yet" />}
    </Panel>
  );
}

// ------------------------------------------------------------------ communications
export function NoticesSection({ d, reload }: Props) {
  const { can } = useAuth();
  const { busy, run } = useAct();
  const c = d.case;
  return (
    <div className="space-y-6">
      <Panel title="Notice drafts" actions={<Link href="/notices" className="text-xs text-muted-foreground hover:text-foreground">Prepare drafts in Notices</Link>}>
        {d.drafts.length ? (
          <ul className="divide-y">
            {d.drafts.map((x) => (
              <li key={x.id} className="flex flex-wrap items-center gap-3 py-2 text-sm">
                <Link href={`/notices/drafts/${x.id}`} className="flex-1 hover:text-primary">{x.template} · v{x.version}</Link>
                <DraftIssues draft={x} />
                <DraftStatusPill status={x.status} />
              </li>
            ))}
          </ul>
        ) : <p className="text-sm text-muted-foreground">No drafts yet.</p>}
      </Panel>
      <Panel title="Messages sent" description="Only messages released from an approved batch appear here.">
        {d.messages.length ? (
          <ul className="divide-y">
            {d.messages.map((m) => (
              <li key={m.id} className="flex flex-wrap items-center gap-3 py-2 text-sm">
                <Link href={`/notices/batches/${m.batch_id}`} className="flex-1 hover:text-primary">{m.subject}</Link>
                <span className="text-xs text-muted-foreground">{m.sent_at ? fmtDate(m.sent_at) : ""}</span>
                <MessageStatusPill status={m.status} />
                {["sent", "delivered"].includes(m.status) && <AckPill at={m.acknowledged_at} />}
              </li>
            ))}
          </ul>
        ) : <p className="text-sm text-muted-foreground">Nothing sent yet.</p>}
      </Panel>
      <Panel title="Employee self-service" description="Lets the employee see their letters, dates and statements, confirm receipt and raise a concern.">
        <div className="flex flex-wrap items-center gap-3 text-sm">
          <Pill spec={d.self_service.active ? { label: "Active", icon: CircleCheck, color: "var(--status-good)" }
                    : d.self_service.invited ? { label: "Invited", icon: CircleDashed, color: "var(--status-warning)" }
                    : { label: "Not invited", icon: CircleDashed, color: "var(--viz-muted)" }} />
          {can("hr") && c.state !== "withdrawn" && (
            <Button size="sm" variant="outline" disabled={busy} onClick={async () => {
              const r = await run(() => post<{ email: string }>(`/exit-cases/${c.id}/invite`));
              if (r) {
                toast.success(`Invitation sent to ${r.email}`);
                reload();
              }
            }}>
              <KeyRound className="size-3.5" />{d.self_service.invited ? "Send a new invitation" : "Invite employee"}
            </Button>
          )}
        </div>
        {d.grievances.length > 0 && (
          <div className="mt-4 space-y-1 text-sm">
            <div className="font-medium">Grievances</div>
            {d.grievances.map((g) => (
              <Link key={g.id} href={`/grievances?id=${g.id}`} className="flex gap-3 hover:text-primary">
                <span className="capitalize">{g.category}</span>
                <span className="text-muted-foreground">{label(g.status)}</span>
                <span className="text-xs text-muted-foreground">{fmtDate(g.logged_at)}</span>
              </Link>
            ))}
          </div>
        )}
      </Panel>
    </div>
  );
}

// ------------------------------------------------------------------ FNF and documents
const DOC_KINDS: [string, string][] = [
  ["fnf_statement", "FNF statement"], ["relieving_letter", "Relieving letter"], ["experience_letter", "Experience letter"],
  ["certificate_of_service", "Certificate of service"], ["acknowledgement_form", "Acknowledgement form"],
  ["notice_letter", "Notice letter"], ["termination_letter", "Termination letter"],
  ["role_elimination_notice", "Notice of role elimination"],
];

export function SettlementSection({ d, reload }: Props) {
  const { can } = useAuth();
  const c = d.case;
  const { busy, run } = useAct();
  const whatIf = useQuery<Record<"pay_in_lieu" | "work_notice", { net_paise: number; earnings_paise: number; deductions_paise: number }>>(
    can("hr", "finance") && reached(d, "last_day_set") ? `/exit-cases/${c.id}/fnf/what-if` : null);
  const [kind, setKind] = useState("fnf_statement");
  const [protect, setProtect] = useState(true);
  const [password, setPassword] = useState<string | null>(null);
  const latest = d.fnf[0];

  return (
    <div className="space-y-6">
      {can("hr", "finance", "legal") && (
        <Panel title="Full and final settlement"
               actions={can("hr", "finance") && reached(d, "last_day_set") && c.state !== "on_hold" && (
                 <Button size="sm" disabled={busy} onClick={async () => {
                   const r = await run(() => post<FnfStatement>(`/exit-cases/${c.id}/fnf`), "Statement computed");
                   if (r) reload();
                 }}><Wallet className="size-3.5" />{latest ? "Recompute" : "Compute"}</Button>
               )}>
          {!reached(d, "last_day_set") && <p className="text-sm text-muted-foreground">The FNF is computed once the last working day is confirmed.</p>}
          {d.fnf.length > 0 && (
            <table className={t.table}>
              <thead className={t.thead}>
                <tr className="border-b">
                  <th className={t.th}>Version</th><th className={t.th}>Status</th>
                  <th className={`${t.th} text-right`}>Earnings</th><th className={`${t.th} text-right`}>Deductions</th>
                  <th className={`${t.th} text-right`}>Net</th><th className={t.th}>Due</th>
                </tr>
              </thead>
              <tbody>
                {d.fnf.map((s) => (
                  <tr key={s.id} className={t.tr}>
                    <td className={t.td}><Link href={`/fnf/${s.id}`} className="font-medium hover:text-primary">v{s.version}</Link></td>
                    <td className={`${t.td} capitalize`}>{label(s.status)}{s.needs_legal && <span className="ml-1 text-xs text-muted-foreground">(needs Legal)</span>}</td>
                    <td className={`${t.td} text-right tabular-nums`}>{fmtPaise(s.earnings_paise, 2)}</td>
                    <td className={`${t.td} text-right tabular-nums`}>{fmtPaise(s.deductions_paise, 2)}</td>
                    <td className={`${t.td} text-right font-medium tabular-nums`}>{fmtPaise(s.net_paise, 2)}</td>
                    <td className={t.td}>{fmtDay(s.payment_due_on)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
          {whatIf.data && (
            <div className="mt-4 grid gap-3 sm:grid-cols-2">
              {(["pay_in_lieu", "work_notice"] as const).map((k) => (
                <div key={k} className={cn("rounded-xl border p-3", (k === "pay_in_lieu") === c.pay_in_lieu && "border-primary/50")}>
                  <div className="text-xs text-muted-foreground">What if: {k === "pay_in_lieu" ? "pay notice in lieu" : "employee works the notice"}
                    {(k === "pay_in_lieu") === c.pay_in_lieu && " (current)"}</div>
                  <div className="mt-1 text-lg font-semibold tabular-nums">{fmtPaise(whatIf.data![k].net_paise, 2)}</div>
                  <div className="text-xs text-muted-foreground tabular-nums">
                    {fmtPaise(whatIf.data![k].earnings_paise)} earnings − {fmtPaise(whatIf.data![k].deductions_paise)} deductions
                  </div>
                </div>
              ))}
            </div>
          )}
        </Panel>
      )}

      <Panel title="Documents" description="Every issued PDF's SHA-256 is sealed in the audit log.">
        {d.documents.length ? (
          <ul className="divide-y">
            {d.documents.map((doc) => (
              <li key={doc.id} className="flex flex-wrap items-center gap-3 py-2 text-sm">
                <FileText className="size-4 text-muted-foreground" />
                <span className="flex-1">{doc.title} · v{doc.version}</span>
                {doc.password_protected && <span className="text-xs text-muted-foreground">password-protected</span>}
                <Hash value={doc.sha256} />
                <span className="text-xs text-muted-foreground">{doc.issued_by} · {fmtDate(doc.issued_at)}</span>
                {can("hr", "legal", "finance") && (
                  <a href={`/api/exit-cases/${c.id}/documents/${doc.id}/download`} className="inline-flex items-center gap-1 text-xs hover:text-primary">
                    <Download className="size-3.5" />Download
                  </a>
                )}
              </li>
            ))}
          </ul>
        ) : <p className="text-sm text-muted-foreground">No documents issued yet.</p>}
        {can("hr") && !["on_hold", "withdrawn"].includes(c.state) && (
          <div className="mt-4 flex flex-wrap items-center gap-2 border-t pt-4">
            <select className={`${sel} w-64`} aria-label="Document" value={kind} onChange={(e) => setKind(e.target.value)}>
              {DOC_KINDS.map(([k, l]) => <option key={k} value={k}>{l}</option>)}
            </select>
            <label className="flex items-center gap-2 text-sm">
              <input type="checkbox" checked={protect} onChange={(e) => setProtect(e.target.checked)} />Password-protect
            </label>
            <Button size="sm" disabled={busy} onClick={async () => {
              const r = await run(() => post<Doc & { password: string | null }>(`/exit-cases/${c.id}/documents`,
                                                                                  { kind, password_protect: protect }), "Document issued");
              if (r) {
                if (r.password) setPassword(r.password);
                reload();
              }
            }}><FileCheck2 className="size-3.5" />Issue</Button>
            <p className="w-full text-xs text-muted-foreground">
              Relieving, experience and service letters are issued after the FNF is approved; the relieving letter also needs
              clearance complete or an approved exception.
            </p>
          </div>
        )}
      </Panel>

      <Dialog open={!!password} onOpenChange={(o) => !o && setPassword(null)}>
        <DialogContent className="rounded-2xl sm:max-w-md">
          <DialogHeader>
            <DialogTitle>Document password</DialogTitle>
            <DialogDescription>Shown once. Share it with the employee separately from the document.</DialogDescription>
          </DialogHeader>
          <code className="rounded-xl border bg-muted/40 p-3 text-center text-lg tracking-wider">{password}</code>
          <Button onClick={() => setPassword(null)}>Done</Button>
        </DialogContent>
      </Dialog>
    </div>
  );
}

// ------------------------------------------------------------------ clearance
const CLEARANCE_STATUSES: Record<ClearanceItem["category"], string[]> = {
  access: ["pending", "requested", "revoked", "verified", "waived"],
  asset: ["pending", "returned", "missing", "waived"],
  handover: ["pending", "done", "waived"],
  signoff: ["pending", "done"],
};
const DONE = new Set(["verified", "returned", "done", "waived"]);

export function ClearanceSection({ d, reload }: Props) {
  const { me, can } = useAuth();
  const c = d.case;
  const { busy, run } = useAct();
  const [deciding, setDeciding] = useState(false);
  const exceptionPending = pending(d.approvals.clearance_exception);
  const exceptionApproved = d.approvals.clearance_exception.some((a) => a.status === "approved") && !exceptionPending;
  const active = !["on_hold", "withdrawn", "closed"].includes(c.state);

  async function setStatus(it: ClearanceItem, status: string) {
    let note: string | null = null;
    if (status === "waived") {
      note = window.prompt(`Why is "${it.label}" being waived?`);
      if (!note) return;
    }
    if (await run(() => api(`/exit-cases/${c.id}/clearance/${it.id}`, { method: "PATCH", body: JSON.stringify({ status, note }) }))) reload();
  }

  const groups = (["access", "asset", "handover", "signoff"] as const).map((cat) => [cat, d.clearance.filter((i) => i.category === cat)] as const);
  return (
    <Panel title="Clearance" description={d.clearance.length ? `${d.clearance.filter((i) => DONE.has(i.status)).length} of ${d.clearance.length} complete` : undefined}
           actions={d.clearance_complete
             ? <Pill spec={{ label: "Complete", icon: CircleCheck, color: "var(--status-good)" }} />
             : exceptionApproved ? <Pill spec={{ label: "Exception approved", icon: CircleCheck, color: "var(--status-warning)" }} />
             : undefined}>
      {!d.clearance.length && <p className="text-sm text-muted-foreground">The checklist is created when the notice is sent.</p>}
      <div className="grid gap-6 lg:grid-cols-2">
        {groups.filter(([, items]) => items.length).map(([cat, items]) => (
          <div key={cat}>
            <div className="mb-2 text-xs font-medium tracking-wide text-muted-foreground uppercase">{cat}</div>
            <ul className="space-y-2">
              {items.map((it) => {
                const editable = active && (can("hr") || (it.owner_role === "manager" && me?.role === "manager"));
                return (
                  <li key={it.id} className="flex flex-wrap items-center gap-2 text-sm">
                    {DONE.has(it.status) ? <CircleCheck className="size-4 text-[var(--status-good)]" aria-hidden="true" />
                                         : <CircleDashed className="size-4 text-muted-foreground" aria-hidden="true" />}
                    <span className="flex-1">{it.label}{it.ticket_ref && <span className="ml-1 font-mono text-xs text-muted-foreground">{it.ticket_ref}</span>}
                      {it.note && <span className="block text-xs text-muted-foreground">{it.note}</span>}</span>
                    <select className="h-8 rounded-lg border bg-background/50 px-2 text-xs capitalize" aria-label={`${it.label} status`}
                            value={it.status} disabled={!editable || busy} onChange={(e) => setStatus(it, e.target.value)}>
                      {CLEARANCE_STATUSES[it.category].map((s) => <option key={s} value={s}>{s}</option>)}
                    </select>
                  </li>
                );
              })}
            </ul>
          </div>
        ))}
      </div>
      {!d.clearance_complete && d.clearance.length > 0 && (
        <div className="mt-6 space-y-3 border-t pt-4">
          <div className="text-sm font-medium">Clearance exception</div>
          <p className="text-xs text-muted-foreground">
            If items can&apos;t be completed, an approver (not the case owner) can let the relieving letter be issued anyway.
            The exception covers exactly the items open now.
          </p>
          <ApprovalTrail items={d.approvals.clearance_exception} />
          <div className="flex gap-2">
            {can("hr") && !exceptionPending && !exceptionApproved && (
              <Button size="sm" variant="outline" disabled={busy} onClick={async () => {
                if (await run(() => post(`/exit-cases/${c.id}/clearance/exception`), "Exception requested")) reload();
              }}>Request exception</Button>
            )}
            {can("approver") && exceptionPending && <Button size="sm" onClick={() => setDeciding(true)}>Review exception</Button>}
          </div>
        </div>
      )}
      <DecisionDialog open={deciding} onOpenChange={setDeciding} title="Approve the clearance exception?"
                      description={`Open items: ${d.clearance.filter((i) => !DONE.has(i.status)).map((i) => i.label).join(", ")}`}
                      hash={exceptionPending?.content_hash}
                      onDecide={async (approve, comment) => {
                        await post(`/exit-cases/${c.id}/clearance/exception/decision`, { approve, comment: comment || null });
                        reload();
                      }} />
    </Panel>
  );
}

// ------------------------------------------------------------------ effective, HRIS, close
export function ClosingSection({ d, reload }: Props) {
  const { can } = useAuth();
  const c = d.case;
  const { busy, run } = useAct();
  const [deciding, setDeciding] = useState<null | "effective" | "hris">(null);
  const effPending = pending(d.approvals.exit_effective);
  const hrisPending = pending(d.approvals.hris_push);

  return (
    <div className="grid gap-6 xl:grid-cols-3">
      <Panel title="Mark effective" description="An approver who isn't the case owner or the employee's manager confirms the exit.">
        <Check ok={reached(d, "effective")}>{reached(d, "effective") ? `Effective ${fmtDate(c.effective_at)}` : "Not yet effective"}</Check>
        <div className="mt-3"><ApprovalTrail items={d.approvals.exit_effective} /></div>
        <div className="mt-3 flex gap-2">
          {can("hr") && c.state === "documents_issued" && !effPending && (
            <Button size="sm" disabled={busy} onClick={async () => {
              if (await run(() => post(`/exit-cases/${c.id}/mark-effective`), "Sent for approval")) reload();
            }}>Request approval</Button>
          )}
          {can("approver") && effPending && <Button size="sm" onClick={() => setDeciding("effective")}>Review</Button>}
        </div>
      </Panel>
      <Panel title="Update HRIS" description="Finance prepares and a second Finance user approves the exit record export.">
        <Check ok={!!c.hris_pushed_at}>{c.hris_pushed_at ? `Written ${fmtDate(c.hris_pushed_at)}` : "Not written to the HRIS"}</Check>
        <div className="mt-3"><ApprovalTrail items={d.approvals.hris_push} /></div>
        <div className="mt-3 flex gap-2">
          {can("finance") && ["effective", "closed"].includes(c.state) && !hrisPending && !c.hris_pushed_at && (
            <Button size="sm" disabled={busy} onClick={async () => {
              if (await run(() => post(`/exit-cases/${c.id}/push-hris`), "Sent for approval")) reload();
            }}>Request push</Button>
          )}
          {can("finance") && hrisPending && <Button size="sm" onClick={() => setDeciding("hris")}>Review</Button>}
        </div>
      </Panel>
      <Panel title="Close the case" description="Needs every task done except closing itself.">
        <Check ok={c.state === "closed"}>{c.state === "closed" ? `Closed ${fmtDate(c.closed_at)}` : "Open"}</Check>
        {can("hr") && c.state === "effective" && (
          <Button size="sm" className="mt-3" disabled={busy} onClick={async () => {
            if (await run(() => post(`/exit-cases/${c.id}/close`), "Case closed")) reload();
          }}>Close case</Button>
        )}
      </Panel>
      <DecisionDialog open={deciding !== null} onOpenChange={(o) => !o && setDeciding(null)}
                      title={deciding === "hris" ? "Approve writing this exit to the HRIS?" : "Approve this exit as effective?"}
                      description={deciding === "effective" ? "The employee's status becomes exited." : undefined}
                      hash={(deciding === "hris" ? hrisPending : effPending)?.content_hash}
                      onDecide={async (approve, comment) => {
                        const path = deciding === "hris" ? "push-hris" : "mark-effective";
                        await post(`/exit-cases/${c.id}/${path}/decision`, { approve, comment: comment || null });
                        reload();
                      }} />
    </div>
  );
}

// ------------------------------------------------------------------ AI drafts
export function AiSection({ d }: { d: CaseDetail }) {
  const { can } = useAuth();
  const drafts = useQuery<AiDraft[]>(can("hr", "legal") ? `/exit-cases/${d.case.id}/ai/drafts` : null);
  const [question, setQuestion] = useState("");
  const { busy, run } = useAct();
  return (
    <div className="space-y-6">
      {can("hr") && (
        <Panel title={<span className="flex items-center gap-2"><Sparkles className="size-4 text-primary" />Draft a reply to the employee</span>}
               description="Paste the employee's question. The AI sees case facts but no amounts; names are redacted. You review and send the reply yourself.">
          <Textarea rows={3} value={question} placeholder="e.g. When will I receive my relieving letter?" onChange={(e) => setQuestion(e.target.value)} />
          <Button className="mt-3" variant="outline" disabled={busy || question.trim().length < 5} onClick={async () => {
            if (await run(() => post(`/exit-cases/${d.case.id}/ai/reply`, { question }), "Draft ready")) {
              setQuestion("");
              drafts.reload();
            }
          }}><Sparkles className="size-4" />Draft reply</Button>
        </Panel>
      )}
      {(drafts.data ?? []).map((a) => (
        <AiDraftCard key={a.id} draft={a} title={a.kind === "notice" ? "Notice wording suggestion" : a.kind === "reply" ? "Reply draft" : label(a.kind)} />
      ))}
      {drafts.data && !drafts.data.length && <EmptyState icon={Sparkles} title="No AI drafts for this case" />}
    </div>
  );
}
