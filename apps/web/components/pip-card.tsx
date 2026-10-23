"use client";

import { CircleCheck, CircleDashed, CircleX, Download, Hourglass, Paperclip, Plus, TriangleAlert } from "lucide-react";
import { useRef, useState } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Pill } from "@/components/kit";
import { useAuth } from "@/components/auth";
import { Field, FormDialog, Select, findEmployee, humanize, today, type PillSpec } from "@/components/form-bits";
import { fmtDay, post, upload, type Evidence } from "@/lib/api";

export type Milestone = {
  id: number; pip_id: number; on_date: string; evidence_reviewed: string; outcome: string; notes: string;
  manager_signed_by: string; manager_signed_at: string; employee_ack: string; employee_ack_at: string | null;
};

export type Pip = {
  id: number; employee_id: number; reason_category: string; gaps: string; success_criteria: string; support: string;
  start_date: string; end_date: string; checkin_dates: string[]; status: "proposed" | "active" | "closed";
  outcome: string | null; final_review: string | null; final_review_on: string | null; employee_ack: string;
  employee_ack_at: string | null; proposed_by: string; activated_by: string | null; closed_by: string | null;
  milestones?: Milestone[];
  employee_code?: string; full_name?: string; department?: string;
};

export const PIP_STATUS: Record<string, PillSpec> = {
  proposed: { label: "Proposed", icon: CircleDashed, color: "var(--viz-muted)" },
  active: { label: "Active", icon: Hourglass, color: "var(--status-warning)" },
  closed: { label: "Closed", icon: CircleCheck, color: "var(--status-good)" },
};

export const OUTCOME: Record<string, PillSpec> = {
  met: { label: "Met", icon: CircleCheck, color: "var(--status-good)" },
  partially_met: { label: "Partially met", icon: TriangleAlert, color: "var(--status-warning)" },
  not_met: { label: "Not met", icon: CircleX, color: "var(--status-critical)" },
};

export type Cycle = { id: number; name: string; period_start: string; period_end: string; scale_max: number;
  status: "open" | "calibrating" | "closed"; created_by: string };

export const CYCLE_STATUS: Record<string, PillSpec> = {
  open: { label: "Open", icon: CircleDashed, color: "var(--series-1)" },
  calibrating: { label: "Calibrating", icon: Hourglass, color: "var(--status-warning)" },
  closed: { label: "Closed", icon: CircleCheck, color: "var(--status-good)" },
};

const OUTCOME_OPTIONS: [string, string][] = [["met", "Met"], ["partially_met", "Partially met"], ["not_met", "Not met"]];
export const EVIDENCE_TYPES = ["review_form", "email", "incident_note", "attendance_record", "investigation_outcome",
  "decision_record", "signed_acceptance", "other"];

/** Upload evidence against a review, PIP, milestone, check-in or feedback item. */
export function EvidenceUpload({ entityType, entityId, onDone, label = "Attach evidence" }: {
  entityType: string; entityId: number; onDone: () => void; label?: string;
}) {
  const ref = useRef<HTMLInputElement>(null);
  const [type, setType] = useState("review_form");
  return (
    <span className="inline-flex items-center gap-1.5">
      <Select value={type} onChange={setType} className="h-7 w-auto rounded-lg px-2 text-xs" aria-label="Evidence type"
              options={EVIDENCE_TYPES.map((t) => [t, humanize(t)])} />
      <input ref={ref} type="file" className="hidden" accept=".pdf,.png,.jpg,.jpeg,.txt,.eml,.docx"
             onChange={async (e) => {
               const f = e.target.files?.[0];
               if (!f) return;
               try {
                 await upload<Evidence>("/performance/evidence",
                                        { entity_type: entityType, entity_id: String(entityId), evidence_type: type }, f);
                 toast.success("Evidence stored (encrypted)");
                 onDone();
               } catch (err) {
                 toast.error((err as Error).message);
               } finally {
                 if (ref.current) ref.current.value = "";
               }
             }} />
      <Button size="sm" variant="outline" className="gap-1.5" onClick={() => ref.current?.click()}>
        <Paperclip className="size-3.5" />{label}
      </Button>
    </span>
  );
}

function AckButtons({ path, onDone }: { path: string; onDone: () => void }) {
  const act = async (status: "acknowledged" | "declined") => {
    try {
      await post(path, { status });
      toast.success(status === "acknowledged" ? "Acknowledgement recorded" : "Recorded that the employee declined to sign");
      onDone();
    } catch (e) {
      toast.error((e as Error).message);
    }
  };
  return (
    <span className="inline-flex gap-1">
      <Button size="xs" variant="outline" onClick={() => act("acknowledged")}>Signed</Button>
      <Button size="xs" variant="ghost" onClick={() => act("declined")}>Declined to sign</Button>
    </span>
  );
}

export function PipCard({ pip, evidence, onChange }: { pip: Pip; evidence: Evidence[]; onChange: () => void }) {
  const { can } = useAuth();
  const [milestoneOpen, setMilestoneOpen] = useState(false);
  const [closeOpen, setCloseOpen] = useState(false);
  const [m, setM] = useState({ on_date: today(), evidence_reviewed: "", outcome: "partially_met", notes: "" });
  const [c, setC] = useState({ outcome: "met", final_review: "", final_review_on: today() });
  const milestones = pip.milestones ?? [];
  const datedCheckins = new Set(milestones.map((x) => x.on_date)).size;
  const files = (type: string, id: number) => evidence.filter((v) => v.entity_type === type && v.entity_id === id);

  return (
    <div className="space-y-4 rounded-2xl border p-5">
      <div className="flex flex-wrap items-center gap-2">
        <span className="font-medium">{humanize(pip.reason_category)} PIP</span>
        <Pill spec={PIP_STATUS[pip.status]} />
        {pip.outcome && <Pill spec={OUTCOME[pip.outcome]} />}
        <span className="text-xs text-muted-foreground">{fmtDay(pip.start_date)} → {fmtDay(pip.end_date)}</span>
        <div className="ml-auto flex flex-wrap gap-2">
          {pip.status === "proposed" && can("hr", "legal") && (
            <Button size="sm" onClick={async () => {
              try { await post(`/performance/pips/${pip.id}/activate`); toast.success("PIP started"); onChange(); }
              catch (e) { toast.error((e as Error).message); }
            }}>Start PIP</Button>
          )}
          {pip.status === "active" && can("hr", "manager") && (
            <Button size="sm" variant="outline" className="gap-1.5" onClick={() => setMilestoneOpen(true)}>
              <Plus className="size-3.5" />Record check-in
            </Button>
          )}
          {pip.status === "active" && can("hr", "legal") && (
            <Button size="sm" variant="outline" onClick={() => setCloseOpen(true)}>Close PIP</Button>
          )}
        </div>
      </div>

      <dl className="grid gap-4 text-sm md:grid-cols-3">
        <div><dt className="text-xs text-muted-foreground">Gaps</dt><dd className="mt-1 whitespace-pre-wrap">{pip.gaps}</dd></div>
        <div><dt className="text-xs text-muted-foreground">Success criteria</dt><dd className="mt-1 whitespace-pre-wrap">{pip.success_criteria}</dd></div>
        <div><dt className="text-xs text-muted-foreground">Support offered</dt><dd className="mt-1 whitespace-pre-wrap">{pip.support || "–"}</dd></div>
      </dl>

      <div className="flex flex-wrap items-center gap-3 text-xs text-muted-foreground">
        <span>Proposed by {pip.proposed_by}{pip.activated_by ? ` · started by ${pip.activated_by}` : ""}</span>
        <span>·</span>
        <span>Employee: {pip.employee_ack === "pending" ? "not yet signed" : `${humanize(pip.employee_ack)} ${fmtDay(pip.employee_ack_at)}`}</span>
        {pip.employee_ack === "pending" && pip.status !== "proposed" && can("hr") && (
          <AckButtons path={`/performance/pips/${pip.id}/ack`} onDone={onChange} />
        )}
        {pip.checkin_dates.length > 0 && <span>· Planned check-ins: {pip.checkin_dates.map(fmtDay).join(", ")}</span>}
      </div>

      <div>
        <div className="mb-2 text-xs font-medium text-muted-foreground">Dated check-ins ({milestones.length})</div>
        {milestones.length === 0 ? (
          <p className="text-sm text-muted-foreground">None recorded yet.</p>
        ) : (
          <ol className="space-y-2">
            {milestones.map((x) => (
              <li key={x.id} className="rounded-xl bg-muted/30 p-3 text-sm">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="font-medium">{fmtDay(x.on_date)}</span>
                  <Pill spec={OUTCOME[x.outcome]} />
                  <span className="text-xs text-muted-foreground">signed by {x.manager_signed_by}</span>
                  <span className="text-xs text-muted-foreground">· employee {x.employee_ack === "pending" ? "not signed" : x.employee_ack}</span>
                  {x.employee_ack === "pending" && can("hr") && (
                    <AckButtons path={`/performance/milestones/${x.id}/ack`} onDone={onChange} />
                  )}
                </div>
                <p className="mt-1 text-muted-foreground">Evidence reviewed: {x.evidence_reviewed}</p>
                {x.notes && <p className="mt-1">{x.notes}</p>}
                <EvidenceLinks items={files("pip_milestone", x.id)} />
                {can("hr", "legal", "manager") && (
                  <div className="mt-2"><EvidenceUpload entityType="pip_milestone" entityId={x.id} onDone={onChange} /></div>
                )}
              </li>
            ))}
          </ol>
        )}
      </div>

      {pip.final_review && (
        <div className="rounded-xl border p-3 text-sm">
          <div className="text-xs text-muted-foreground">Final review · {fmtDay(pip.final_review_on)} · {pip.closed_by}</div>
          <p className="mt-1 whitespace-pre-wrap">{pip.final_review}</p>
        </div>
      )}

      <div className="flex flex-wrap items-center gap-3">
        <EvidenceLinks items={files("pip", pip.id)} />
        {can("hr", "legal", "manager") && <EvidenceUpload entityType="pip" entityId={pip.id} onDone={onChange} />}
      </div>

      <FormDialog open={milestoneOpen} onOpenChange={setMilestoneOpen} title="Record a PIP check-in"
                  description="A dated, signed record of progress against the success criteria."
                  onSubmit={async () => {
                    await post(`/performance/pips/${pip.id}/milestones`, m);
                    toast.success("Check-in recorded");
                    setM({ on_date: today(), evidence_reviewed: "", outcome: "partially_met", notes: "" });
                    onChange();
                  }}>
        <div className="grid grid-cols-2 gap-3">
          <Field label="Date" htmlFor="m-date">
            <Input id="m-date" type="date" required value={m.on_date} onChange={(e) => setM({ ...m, on_date: e.target.value })} />
          </Field>
          <Field label="Progress" htmlFor="m-outcome">
            <Select id="m-outcome" value={m.outcome} onChange={(v) => setM({ ...m, outcome: v })} options={OUTCOME_OPTIONS} />
          </Field>
        </div>
        <Field label="Evidence reviewed" htmlFor="m-ev">
          <Textarea id="m-ev" required minLength={5} rows={2} value={m.evidence_reviewed}
                    onChange={(e) => setM({ ...m, evidence_reviewed: e.target.value })} />
        </Field>
        <Field label="Notes" htmlFor="m-notes">
          <Textarea id="m-notes" rows={2} value={m.notes} onChange={(e) => setM({ ...m, notes: e.target.value })} />
        </Field>
      </FormDialog>

      <FormDialog open={closeOpen} onOpenChange={setCloseOpen} title="Close PIP" submitLabel="Close PIP"
                  description={<>A PIP can only close as <em>not met</em> with at least two dated check-ins. This one has {datedCheckins}.</>}
                  onSubmit={async () => {
                    await post(`/performance/pips/${pip.id}/close`, c);
                    toast.success("PIP closed");
                    onChange();
                  }}>
        <div className="grid grid-cols-2 gap-3">
          <Field label="Outcome" htmlFor="c-outcome">
            <Select id="c-outcome" value={c.outcome} onChange={(v) => setC({ ...c, outcome: v })} options={OUTCOME_OPTIONS} />
          </Field>
          <Field label="Final review date" htmlFor="c-date">
            <Input id="c-date" type="date" required value={c.final_review_on}
                   onChange={(e) => setC({ ...c, final_review_on: e.target.value })} />
          </Field>
        </div>
        {c.outcome === "not_met" && datedCheckins < 2 && (
          <p className="flex items-center gap-2 text-sm">
            <TriangleAlert className="size-4 text-[var(--status-warning)]" aria-hidden="true" />
            Record at least two dated check-ins before closing as not met.
          </p>
        )}
        <Field label="Documented final review" htmlFor="c-review">
          <Textarea id="c-review" required minLength={10} rows={4} value={c.final_review}
                    onChange={(e) => setC({ ...c, final_review: e.target.value })} />
        </Field>
      </FormDialog>
    </div>
  );
}

export function EvidenceLinks({ items }: { items: Evidence[] }) {
  if (!items.length) return null;
  return (
    <ul className="mt-2 flex flex-wrap gap-2">
      {items.map((v) => (
        <li key={v.id}>
          <a href={`/api/employees/evidence/${v.id}/download`}
             className="inline-flex items-center gap-1.5 rounded-lg border px-2 py-1 text-xs hover:border-primary hover:text-primary"
             title={`SHA-256 ${v.sha256} · ${v.scan_status.replace("_", " ")}`}>
            <Download className="size-3" />{v.filename}
            <span className="text-muted-foreground">· {humanize(v.evidence_type)}</span>
          </a>
        </li>
      ))}
    </ul>
  );
}

/** Create a PIP. Pass `employeeId`, or leave it out to ask for an employee ID. */
export function NewPipDialog({ open, onOpenChange, employeeId, onDone }: {
  open: boolean; onOpenChange: (o: boolean) => void; employeeId?: number; onDone: () => void;
}) {
  const { can } = useAuth();
  const starts = can("hr", "legal");
  const [code, setCode] = useState("");
  const [v, setV] = useState({ reason_category: "performance", gaps: "", success_criteria: "", support: "",
                               start_date: today(), end_date: "" });
  return (
    <FormDialog open={open} onOpenChange={onOpenChange} wide title={starts ? "Start a PIP" : "Propose a PIP"}
                description={starts ? "The PIP starts as active. An active PIP protects this person from selection until it ends."
                                    : "Managers propose; HR or Legal start the PIP."}
                submitLabel={starts ? "Start PIP" : "Propose"}
                onSubmit={async () => {
                  const id = employeeId ?? (await findEmployee(code)).id;
                  await post("/performance/pips", { employee_id: id, ...v, end_date: v.end_date || null });
                  toast.success(starts ? "PIP started" : "PIP proposed to HR");
                  setV({ ...v, gaps: "", success_criteria: "", support: "" });
                  setCode("");
                  onDone();
                }}>
      {employeeId === undefined && (
        <Field label="Employee ID" htmlFor="p-code">
          <Input id="p-code" required value={code} placeholder="E0042" onChange={(ev) => setCode(ev.target.value)} />
        </Field>
      )}
      <div className="grid grid-cols-3 gap-3">
        <Field label="Reason" htmlFor="p-r"><Select id="p-r" value={v.reason_category} onChange={(x) => setV({ ...v, reason_category: x })}
                                                     options={[["performance", "Performance"], ["conduct", "Conduct"], ["attendance", "Attendance"]]} /></Field>
        <Field label="Start" htmlFor="p-s"><Input id="p-s" type="date" required value={v.start_date} onChange={(ev) => setV({ ...v, start_date: ev.target.value })} /></Field>
        <Field label="End (default 60 days)" htmlFor="p-e"><Input id="p-e" type="date" value={v.end_date} onChange={(ev) => setV({ ...v, end_date: ev.target.value })} /></Field>
      </div>
      <Field label="Specific gaps" htmlFor="p-g"><Textarea id="p-g" required minLength={10} rows={3} value={v.gaps} onChange={(ev) => setV({ ...v, gaps: ev.target.value })} /></Field>
      <Field label="Measurable success criteria" htmlFor="p-c"><Textarea id="p-c" required minLength={10} rows={3} value={v.success_criteria} onChange={(ev) => setV({ ...v, success_criteria: ev.target.value })} /></Field>
      <Field label="Support offered" htmlFor="p-sup"><Textarea id="p-sup" rows={2} value={v.support} onChange={(ev) => setV({ ...v, support: ev.target.value })} /></Field>
    </FormDialog>
  );
}
