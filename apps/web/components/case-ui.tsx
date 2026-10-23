"use client";

import {
  Ban, CircleCheck, CircleDashed, CircleX, Clock, Fingerprint, Hourglass, MailCheck, MailWarning, Send,
  type LucideIcon,
} from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { fmtDate } from "@/components/common";
import { ApprovalPill, Pill } from "@/components/kit";
import type { Approval } from "@/lib/api";

/** Runs a mutation with a busy flag; failures become an error toast, success an optional toast. */
export function useAct() {
  const [busy, setBusy] = useState(false);
  async function run<T>(fn: () => Promise<T>, success?: string): Promise<T | undefined> {
    setBusy(true);
    try {
      const r = await fn();
      if (success) toast.success(success);
      return r;
    } catch (e) {
      toast.error((e as Error).message);
      return undefined;
    } finally {
      setBusy(false);
    }
  }
  return { busy, run };
}

const MSG: Record<string, { label: string; icon: LucideIcon; color: string }> = {
  pending: { label: "Not sent", icon: CircleDashed, color: "var(--viz-muted)" },
  queued: { label: "Queued", icon: Clock, color: "var(--status-warning)" },
  sent: { label: "Sent", icon: Send, color: "var(--series-1)" },
  delivered: { label: "Delivered", icon: MailCheck, color: "var(--status-good)" },
  bounced: { label: "Bounced", icon: MailWarning, color: "var(--status-critical)" },
  failed: { label: "Failed", icon: CircleX, color: "var(--status-critical)" },
  cancelled: { label: "Cancelled", icon: Ban, color: "var(--viz-muted)" },
};

export function MessageStatusPill({ status }: { status: string }) {
  return <Pill spec={MSG[status] ?? { label: status, icon: CircleDashed, color: "var(--viz-muted)" }} />;
}

export function AckPill({ at }: { at: string | null | undefined }) {
  return at
    ? <Pill spec={{ label: "Acknowledged", icon: CircleCheck, color: "var(--status-good)" }} />
    : <Pill spec={{ label: "Not acknowledged", icon: Hourglass, color: "var(--viz-muted)" }} />;
}

/** Short, monospace content hash with the full value on hover. */
export function Hash({ value }: { value: string | null | undefined }) {
  if (!value) return null;
  return (
    <span className="inline-flex items-center gap-1 font-mono text-[11px] text-muted-foreground" title={value}>
      <Fingerprint className="size-3" aria-hidden="true" />{value.slice(0, 12)}…
    </span>
  );
}

/** Each step of an approval: who prepared it, who decided, and the exact content hash it was bound to. */
export function ApprovalTrail({ items }: { items: Approval[] }) {
  if (!items.length) return <p className="text-sm text-muted-foreground">No approval requested yet.</p>;
  return (
    <ol className="space-y-2">
      {items.map((a) => (
        <li key={a.id} className="rounded-xl border bg-background/40 p-3 text-sm">
          <div className="flex flex-wrap items-center gap-2">
            <span className="font-medium capitalize">{a.step.replace(/_/g, " ")}</span>
            <span className="text-xs text-muted-foreground">round {a.round} · {a.roles.join(" or ")}</span>
            <span className="ml-auto"><ApprovalPill status={a.status} /></span>
          </div>
          <div className="mt-1.5 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-muted-foreground">
            <span>Prepared by {a.prepared_by}</span>
            {a.decided_by && <span>Decided by {a.decided_by} · {fmtDate(a.decided_at)}</span>}
            <Hash value={a.content_hash} />
          </div>
          {a.comment && <p className="mt-1.5 text-sm">“{a.comment}”</p>}
        </li>
      ))}
    </ol>
  );
}

/** Approve or reject with an optional comment. Shows the hash of exactly what is being approved. */
export function DecisionDialog({ open, onOpenChange, title, description, hash, onDecide }: {
  open: boolean;
  onOpenChange: (o: boolean) => void;
  title: string;
  description?: React.ReactNode;
  hash?: string | null;
  onDecide: (approve: boolean, comment: string) => Promise<unknown>;
}) {
  const [comment, setComment] = useState("");
  const [busy, setBusy] = useState(false);
  async function decide(approve: boolean) {
    setBusy(true);
    try {
      await onDecide(approve, comment);
      setComment("");
      onOpenChange(false);
    } catch (e) {
      toast.error((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="rounded-2xl sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>{title}</DialogTitle>
          {description && <DialogDescription>{description}</DialogDescription>}
        </DialogHeader>
        {hash && (
          <div className="rounded-xl border bg-muted/40 p-3 text-xs">
            <div className="mb-1 text-muted-foreground">Your decision is bound to this exact content:</div>
            <code className="break-all">{hash}</code>
            <div className="mt-1 text-muted-foreground">If anything changes afterwards, the approval stops counting.</div>
          </div>
        )}
        <div className="space-y-1.5">
          <Label htmlFor="decision-comment">Comment (required to reject)</Label>
          <Textarea id="decision-comment" rows={3} value={comment} onChange={(e) => setComment(e.target.value)} />
        </div>
        <div className="flex justify-end gap-2">
          <Button variant="outline" disabled={busy || comment.trim().length < 3} onClick={() => decide(false)}>
            <CircleX className="size-4" />Reject
          </Button>
          <Button disabled={busy} onClick={() => decide(true)}><CircleCheck className="size-4" />Approve</Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}

/** Asks for a written reason (hold, release, withdraw) before running an action. */
export function ReasonDialog({ open, onOpenChange, title, label, cta, onSubmit, destructive }: {
  open: boolean;
  onOpenChange: (o: boolean) => void;
  title: string;
  label: string;
  cta: string;
  destructive?: boolean;
  onSubmit: (text: string) => Promise<unknown>;
}) {
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  async function submit() {
    setBusy(true);
    try {
      await onSubmit(text);
      setText("");
      onOpenChange(false);
    } catch (e) {
      toast.error((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="rounded-2xl sm:max-w-lg">
        <DialogHeader><DialogTitle>{title}</DialogTitle></DialogHeader>
        <div className="space-y-1.5">
          <Label htmlFor="reason-text">{label}</Label>
          <Textarea id="reason-text" rows={3} value={text} onChange={(e) => setText(e.target.value)} />
        </div>
        <div className="flex justify-end gap-2">
          <Button variant="outline" onClick={() => onOpenChange(false)}>Cancel</Button>
          <Button variant={destructive ? "destructive" : "default"} disabled={busy || text.trim().length < 3}
                  onClick={submit}>{cta}</Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}
