"use client";

import {
  CalendarDays, CircleCheck, CircleDashed, Download, FileText, Hourglass, Lock, Mail, MessageSquareWarning, Wallet,
} from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { ErrorText, fmtDate } from "@/components/common";
import { EmptyState, PageHeader, Panel, Pill } from "@/components/kit";
import { useQuery } from "@/lib/use-query";
import { fmtDay, fmtPaise, post } from "@/lib/api";

type MyCase = {
  company: string;
  hr_contact: string | null;
  state: string;
  state_label: string;
  dates: { notice_date: string | null; notice_days: number | null; pay_in_lieu: boolean; last_working_day: string | null };
  notices: { id: number; subject: string; sent_at: string; body: string; acknowledged_at: string | null }[];
  documents: { id: number; title: string; version: number; issued_at: string; password_protected: boolean }[];
  fnf: {
    version: number; status: string; net_paise: number; earnings_paise: number; deductions_paise: number;
    payment_due_on: string | null; paid_at: string | null;
    lines: { label: string; kind: "earning" | "deduction"; amount_paise: number; basis: string }[];
  } | null;
  clearance: { label: string; category: string; status: string }[];
  grievances: {
    id: number; ref: string; category: string; status: string; logged_at: string; outcome: string | null;
    outcome_reasons: string | null; can_appeal: boolean;
    appeal: { status: string; outcome: string | null; reasons: string | null } | null;
  }[];
};

const CATEGORIES: [string, string][] = [
  ["process", "How the process was carried out"],
  ["reason", "The reason given for my exit"],
  ["selection", "How I was selected"],
  ["fnf", "My final settlement"],
  ["other", "Something else"],
];
const COMPLETE = new Set(["verified", "returned", "done", "waived"]);
const OUTCOME: Record<string, string> = { upheld: "Upheld", partly_upheld: "Partly upheld", rejected: "Not upheld" };

function GrievanceForm({ onDone }: { onDone: () => void }) {
  const [category, setCategory] = useState("process");
  const [description, setDescription] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const r = await post<{ ref: string }>("/me/grievances", { category, description });
      toast.success(`Your concern was logged as ${r.ref}. HR will acknowledge it in writing.`);
      setDescription("");
      onDone();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <form onSubmit={submit} className="space-y-3 rounded-xl border p-4">
      <div className="font-medium">Raise a concern</div>
      <div className="space-y-1">
        <Label htmlFor="g-cat">What is it about?</Label>
        <select id="g-cat" className="h-9 w-full rounded-md border bg-background px-2 text-sm" value={category}
                onChange={(e) => setCategory(e.target.value)}>
          {CATEGORIES.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
        </select>
      </div>
      <div className="space-y-1">
        <Label htmlFor="g-desc">Describe your concern</Label>
        <Textarea id="g-desc" required minLength={10} rows={4} value={description} onChange={(e) => setDescription(e.target.value)} />
      </div>
      <p className="text-xs text-muted-foreground">
        A concern about the process, the reason or how you were selected pauses your exit until it is decided.
        Someone not involved in your case decides it, and you can appeal the outcome once.
      </p>
      <ErrorText error={error} />
      <Button type="submit" disabled={busy}>{busy ? "Sending…" : "Submit"}</Button>
    </form>
  );
}

function AppealForm({ id, onDone }: { id: number; onDone: () => void }) {
  const [grounds, setGrounds] = useState("");
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  if (!open) return <Button size="sm" variant="outline" onClick={() => setOpen(true)}>Appeal this outcome</Button>;

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await post(`/me/grievances/${id}/appeal`, { grounds });
      toast.success("Your appeal was submitted");
      onDone();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <form onSubmit={submit} className="mt-2 space-y-2">
      <Label htmlFor={`ap-${id}`}>Grounds for appeal</Label>
      <Textarea id={`ap-${id}`} required minLength={10} rows={3} value={grounds} onChange={(e) => setGrounds(e.target.value)} />
      <ErrorText error={error} />
      <div className="flex gap-2">
        <Button size="sm" type="submit" disabled={busy}>Submit appeal</Button>
        <Button size="sm" type="button" variant="ghost" onClick={() => setOpen(false)}>Cancel</Button>
      </div>
    </form>
  );
}

export default function MyCasePage() {
  const q = useQuery<MyCase>("/me/case");
  const [openNotice, setOpenNotice] = useState<number | null>(null);
  const c = q.data;

  async function acknowledge(id: number) {
    try {
      await post(`/me/acknowledge/${id}`);
      toast.success("Receipt confirmed");
      q.reload();
    } catch (e) {
      toast.error((e as Error).message);
    }
  }

  if (q.error && !c) {
    return (
      <Panel>
        <EmptyState icon={FileText} title="Nothing to show yet">
          {q.error === "No exit case" ? "There is no exit process open for you." : q.error}
        </EmptyState>
      </Panel>
    );
  }
  if (!c) return null;

  return (
    <div className="space-y-6">
      <PageHeader eyebrow={c.company} title="Your exit"
                  description={<>Everything sent to you, your dates, documents and settlement in one place.
                    {c.hr_contact && <> Questions? Write to <a className="underline" href={`mailto:${c.hr_contact}`}>{c.hr_contact}</a>.</>}</>} />

      <div className="grid gap-4 sm:grid-cols-3">
        <div className="glass rounded-2xl p-4">
          <div className="text-xs text-muted-foreground">Status</div>
          <div className="mt-1 font-semibold">{c.state_label}</div>
        </div>
        <div className="glass rounded-2xl p-4">
          <div className="text-xs text-muted-foreground">Notice given</div>
          <div className="mt-1 font-semibold">{fmtDay(c.dates.notice_date)}</div>
          {c.dates.notice_days !== null && (
            <div className="text-xs text-muted-foreground">{c.dates.notice_days} days{c.dates.pay_in_lieu ? " · paid in lieu" : ""}</div>
          )}
        </div>
        <div className="glass rounded-2xl p-4">
          <div className="flex items-center gap-1.5 text-xs text-muted-foreground"><CalendarDays className="size-3.5" />Last working day</div>
          <div className="mt-1 font-semibold">{fmtDay(c.dates.last_working_day)}</div>
        </div>
      </div>

      <Panel title="Letters and notices">
        {c.notices.length ? (
          <ul className="divide-y">
            {c.notices.map((n) => (
              <li key={n.id} className="py-3">
                <div className="flex flex-wrap items-center gap-3 text-sm">
                  <Mail className="size-4 text-muted-foreground" />
                  <button className="flex-1 text-left font-medium hover:text-primary" onClick={() => setOpenNotice(openNotice === n.id ? null : n.id)}>
                    {n.subject}
                  </button>
                  <span className="text-xs text-muted-foreground">{fmtDate(n.sent_at)}</span>
                  {n.acknowledged_at
                    ? <Pill spec={{ label: "Receipt confirmed", icon: CircleCheck, color: "var(--status-good)" }} />
                    : <Button size="sm" onClick={() => acknowledge(n.id)}>Confirm receipt</Button>}
                </div>
                {openNotice === n.id && (
                  <div className="mt-3 rounded-xl border bg-background/40 p-4 text-sm whitespace-pre-wrap">{n.body}</div>
                )}
              </li>
            ))}
          </ul>
        ) : <p className="text-sm text-muted-foreground">Nothing has been sent to you yet.</p>}
        <p className="mt-3 text-xs text-muted-foreground">Confirming receipt only records that you received the letter. It does not mean you agree with it.</p>
      </Panel>

      <div className="grid gap-6 lg:grid-cols-2">
        <Panel title="Documents">
          {c.documents.length ? (
            <ul className="divide-y">
              {c.documents.map((d) => (
                <li key={d.id} className="flex items-center gap-3 py-2.5 text-sm">
                  <FileText className="size-4 text-muted-foreground" />
                  <span className="flex-1">{d.title}{d.version > 1 && <span className="text-xs text-muted-foreground"> v{d.version}</span>}
                    {d.password_protected && <Lock className="ml-1.5 inline size-3 text-muted-foreground" aria-label="Password protected" />}
                  </span>
                  <a href={`/api/me/documents/${d.id}/download`} className="inline-flex items-center gap-1 text-xs hover:text-primary">
                    <Download className="size-3.5" />Download
                  </a>
                </li>
              ))}
            </ul>
          ) : <p className="text-sm text-muted-foreground">No documents issued yet.</p>}
          {c.documents.some((d) => d.password_protected) && (
            <p className="mt-3 text-xs text-muted-foreground">Locked PDFs open with the password sent to you in a separate email.</p>
          )}
        </Panel>

        <Panel title="Clearance">
          {c.clearance.length ? (
            <ul className="space-y-1.5 text-sm">
              {c.clearance.map((i) => (
                <li key={i.label} className="flex items-center gap-2">
                  {COMPLETE.has(i.status)
                    ? <CircleCheck className="size-4 text-[var(--status-good)]" aria-hidden="true" />
                    : <CircleDashed className="size-4 text-muted-foreground" aria-hidden="true" />}
                  <span className="flex-1">{i.label}</span>
                  <span className="text-xs text-muted-foreground capitalize">{i.status.replace(/_/g, " ")}</span>
                </li>
              ))}
            </ul>
          ) : <p className="text-sm text-muted-foreground">Your clearance checklist appears after notice is given.</p>}
        </Panel>
      </div>

      <Panel title="Final settlement" actions={c.fnf && <Wallet className="size-4 text-muted-foreground" />}>
        {c.fnf ? (
          <div className="space-y-4">
            <div className="flex flex-wrap items-end gap-6">
              <div>
                <div className="text-xs text-muted-foreground">Net payable</div>
                <div className="text-3xl font-semibold tabular-nums">{fmtPaise(c.fnf.net_paise)}</div>
              </div>
              <div className="text-sm text-muted-foreground">
                {c.fnf.paid_at ? <>Paid on {fmtDay(c.fnf.paid_at)}</> : <>Due by {fmtDay(c.fnf.payment_due_on)}</>}
              </div>
              <Pill className="ml-auto" spec={c.fnf.paid_at ? { label: "Paid", icon: CircleCheck, color: "var(--status-good)" }
                                                            : { label: "Approved", icon: Hourglass, color: "var(--series-1)" }} />
            </div>
            <table className="w-full text-sm">
              <tbody>
                {c.fnf.lines.map((l, i) => (
                  <tr key={i} className="border-b border-border/60 last:border-0">
                    <td className="py-2">{l.label}<div className="text-xs text-muted-foreground">{l.basis}</div></td>
                    <td className="py-2 text-right tabular-nums">{l.kind === "deduction" ? "−" : ""}{fmtPaise(l.amount_paise, 2)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : <p className="text-sm text-muted-foreground">Your settlement statement will appear here once it has been approved.</p>}
      </Panel>

      <Panel title="Concerns and appeals" actions={<MessageSquareWarning className="size-4 text-muted-foreground" />}>
        <div className="space-y-4">
          {c.grievances.map((g) => (
            <div key={g.id} className="rounded-xl border p-4 text-sm">
              <div className="flex flex-wrap items-center gap-2">
                <span className="font-mono text-xs">{g.ref}</span>
                <span className="text-muted-foreground">{CATEGORIES.find(([v]) => v === g.category)?.[1] ?? g.category}</span>
                <span className="ml-auto text-xs text-muted-foreground">Raised {fmtDay(g.logged_at)}</span>
              </div>
              <div className="mt-2">
                Status: <span className="capitalize">{g.status.replace(/_/g, " ")}</span>
                {g.outcome && <> · Outcome: <span className="font-medium">{OUTCOME[g.outcome] ?? g.outcome}</span></>}
              </div>
              {g.outcome_reasons && <p className="mt-1 text-muted-foreground">{g.outcome_reasons}</p>}
              {g.appeal && (
                <div className="mt-2 border-t pt-2">
                  Appeal: <span className="capitalize">{g.appeal.status.replace(/_/g, " ")}</span>
                  {g.appeal.outcome && <> · {OUTCOME[g.appeal.outcome] ?? g.appeal.outcome}</>}
                  {g.appeal.reasons && <p className="mt-1 text-muted-foreground">{g.appeal.reasons}</p>}
                </div>
              )}
              {g.can_appeal && <div className="mt-3"><AppealForm id={g.id} onDone={q.reload} /></div>}
            </div>
          ))}
          <GrievanceForm onDone={q.reload} />
        </div>
      </Panel>
    </div>
  );
}
