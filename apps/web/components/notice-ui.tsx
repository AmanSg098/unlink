import { CircleCheck, CircleDashed, FilePen, Hourglass, Send, ShieldCheck, TriangleAlert } from "lucide-react";
import { Pill } from "@/components/kit";
import type { Batch, Draft, Template } from "@/lib/api";

const BATCH = {
  draft: { label: "Draft", icon: CircleDashed, color: "var(--viz-muted)" },
  pending_approval: { label: "Waiting for approval", icon: Hourglass, color: "var(--status-warning)" },
  approved: { label: "Approved, not sent", icon: CircleCheck, color: "var(--series-1)" },
  released: { label: "Released", icon: Send, color: "var(--status-good)" },
  completed: { label: "Completed", icon: CircleCheck, color: "var(--status-good)" },
};

export function BatchStatusPill({ status }: { status: Batch["status"] }) {
  return <Pill spec={BATCH[status] ?? BATCH.draft} />;
}

const DRAFT: Record<string, { label: string; icon: typeof CircleCheck; color: string }> = {
  draft: { label: "Draft", icon: FilePen, color: "var(--viz-muted)" },
  in_batch: { label: "In a batch", icon: Hourglass, color: "var(--series-1)" },
  sent: { label: "Sent", icon: Send, color: "var(--status-good)" },
  superseded: { label: "Superseded", icon: CircleDashed, color: "var(--viz-muted)" },
};

export function DraftStatusPill({ status }: { status: string }) {
  return <Pill spec={DRAFT[status] ?? DRAFT.draft} />;
}

export function TemplateStatusPill({ status }: { status: Template["status"] }) {
  const spec = {
    draft: { label: "Awaiting Legal", icon: Hourglass, color: "var(--status-warning)" },
    legal_approved: { label: "Legal approved", icon: ShieldCheck, color: "var(--status-good)" },
    retired: { label: "Retired", icon: CircleDashed, color: "var(--viz-muted)" },
  }[status];
  return <Pill spec={spec} />;
}

/** Inline indicator of what's wrong with a draft: missing merge fields and protected terms. */
export function DraftIssues({ draft }: { draft: Pick<Draft, "missing_fields" | "flagged_terms"> }) {
  const n = draft.missing_fields.length + draft.flagged_terms.length;
  if (!n) {
    return (
      <span className="inline-flex items-center gap-1 text-xs text-muted-foreground">
        <CircleCheck className="size-3.5 text-[var(--status-good)]" aria-hidden="true" />Ready
      </span>
    );
  }
  return (
    <span className="inline-flex items-center gap-1 text-xs">
      <TriangleAlert className="size-3.5 text-[var(--status-critical)]" aria-hidden="true" />
      {draft.missing_fields.length > 0 && `${draft.missing_fields.length} missing`}
      {draft.missing_fields.length > 0 && draft.flagged_terms.length > 0 && " · "}
      {draft.flagged_terms.length > 0 && `${draft.flagged_terms.length} protected term${draft.flagged_terms.length > 1 ? "s" : ""}`}
    </span>
  );
}

/** The rule the whole notices area is built around, stated where people act on it. */
export function HumanApprovalNote({ className = "" }: { className?: string }) {
  return (
    <div className={`flex items-start gap-2 rounded-xl border border-dashed p-3 text-sm text-muted-foreground ${className}`}>
      <ShieldCheck className="mt-0.5 size-4 shrink-0 text-[var(--status-good)]" aria-hidden="true" />
      <span>
        Nothing reaches an employee until a person other than the drafter approves these exact messages. Approval is bound
        to each message&apos;s content hash, so any edit after approval sends the batch back for approval.
      </span>
    </div>
  );
}
