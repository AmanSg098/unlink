"use client";

import { ArrowLeft, CircleCheck, Eye, FlaskConical, Mail, Send, ShieldAlert, TriangleAlert, Users } from "lucide-react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { Suspense, useState } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { ErrorText, fmtDate, tableCls as t } from "@/components/common";
import { AckPill, ApprovalTrail, DecisionDialog, Hash, MessageStatusPill, useAct } from "@/components/case-ui";
import { BatchStatusPill, HumanApprovalNote } from "@/components/notice-ui";
import { EmptyState, PageHeader, Panel, StatTile } from "@/components/kit";
import { useAuth } from "@/components/auth";
import { useQuery } from "@/lib/use-query";
import { api, post, type Batch, type NoticeMessage, type Role } from "@/lib/api";

function Preview({ batchId, message, onClose }: { batchId: number; message: NoticeMessage | null; onClose: () => void }) {
  const full = useQuery<NoticeMessage>(message ? `/notice-batches/${batchId}/messages/${message.id}` : null);
  return (
    <Dialog open={!!message} onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-h-[90vh] overflow-y-auto rounded-2xl sm:max-w-2xl">
        <DialogHeader>
          <DialogTitle>{message?.subject}</DialogTitle>
          <DialogDescription>
            To {message?.to_addresses.join(", ") || "no address"}{message?.is_test && " · internal test copy"}
          </DialogDescription>
        </DialogHeader>
        <div className="flex flex-wrap items-center gap-2 text-xs">
          {message && <MessageStatusPill status={message.status} />}
          <Hash value={message?.content_hash} />
        </div>
        <ErrorText error={full.error} />
        <pre className="rounded-xl border bg-background/50 p-4 font-sans text-sm leading-relaxed whitespace-pre-wrap">
          {full.loading ? "Loading…" : full.data?.body}
        </pre>
        <p className="text-xs text-muted-foreground">Opening a message is recorded in the audit log.</p>
      </DialogContent>
    </Dialog>
  );
}

function BatchDetail() {
  const { id } = useParams<{ id: string }>();
  const { me, can } = useAuth();
  const q = useQuery<Batch>(`/notice-batches/${id}`);
  const b = q.data;
  const { busy, run } = useAct();
  const [deciding, setDeciding] = useState(false);
  const [releasing, setReleasing] = useState(false);
  const [preview, setPreview] = useState<NoticeMessage | null>(null);

  if (!b) return <ErrorText error={q.error} />;

  const real = (b.messages ?? []).filter((m) => !m.is_test);
  const tests = (b.messages ?? []).filter((m) => m.is_test);
  const pending = b.approvals.find((a) => a.status === "pending");
  const editable = b.status === "draft" || b.status === "pending_approval";
  const canDecide = b.status === "pending_approval" && !!pending && can(...(pending.roles as Role[]));

  async function exclude(m: NoticeMessage) {
    const r = await run(() => post<Batch>(`/notice-batches/${b!.id}/exclude`, { message_id: m.id, excluded: !m.excluded }));
    if (r) {
      if (b!.status === "pending_approval") toast.info("Batch changed, so it went back to draft. Submit it again.");
      q.reload();
    }
  }

  return (
    <div className="space-y-8">
      <Link href="/notices" className="inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground">
        <ArrowLeft className="size-4" />Notices
      </Link>
      <PageHeader
        eyebrow={`Notice batch #${b.id}`}
        title={b.name}
        description={<span className="inline-flex flex-wrap items-center gap-2"><BatchStatusPill status={b.status} />
          <span>Created by {b.created_by} · {fmtDate(b.created_at)}</span></span>}
        actions={
          <div className="flex flex-wrap gap-2">
            {can("hr") && b.status !== "released" && b.status !== "completed" && (
              <Button variant="outline" disabled={busy} onClick={async () => {
                const r = await run(() => post<{ queued: number }>(`/notice-batches/${b.id}/test-send`),
                                    "Test copies queued to the internal test addresses");
                if (r) q.reload();
              }}>
                <FlaskConical className="size-4" />Send test copies
              </Button>
            )}
            {can("hr") && b.status === "draft" && (
              <Button disabled={busy || b.problems.length > 0} onClick={async () => {
                if (await run(() => post(`/notice-batches/${b.id}/submit`), "Submitted for approval")) q.reload();
              }}>
                <Send className="size-4" />Submit for approval
              </Button>
            )}
            {canDecide && (
              <Button onClick={() => setDeciding(true)}><CircleCheck className="size-4" />Review and decide</Button>
            )}
            {can("hr") && b.status === "approved" && (
              <Button onClick={() => setReleasing(true)}><Mail className="size-4" />Release to employees</Button>
            )}
          </div>
        }
      />

      <HumanApprovalNote />

      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <StatTile label="Messages" icon={Users} value={b.counts.messages ?? 0}
                  hint={b.counts.excluded ? `${b.counts.excluded} excluded` : "None excluded"} />
        <StatTile label="Delivered or sent" icon={Send} value={(b.counts.delivered ?? 0) + (b.counts.sent ?? 0)}
                  hint={b.counts.queued ? `${b.counts.queued} queued` : undefined} />
        <StatTile label="Bounced or failed" icon={TriangleAlert} value={(b.counts.bounced ?? 0) + (b.counts.failed ?? 0)} />
        <StatTile label="Acknowledged" icon={CircleCheck} value={b.counts.acknowledged ?? 0} />
      </div>

      {b.problems.length > 0 && (
        <Panel title={<span className="flex items-center gap-2"><ShieldAlert className="size-4 text-[var(--status-critical)]" />Fix before approval or release</span>}>
          <ul className="list-disc space-y-1 pl-5 text-sm">
            {b.problems.map((p) => <li key={p}>{p}</li>)}
          </ul>
        </Panel>
      )}

      <Panel title="Messages" description={editable ? "Exclude anyone who shouldn't receive this batch. Changing the batch resets approval." : "Frozen: these exact messages were approved."}
             bodyClassName="p-0">
        <div className="overflow-x-auto">
          <table className={t.table}>
            <thead className={t.thead}>
              <tr className="border-b">
                <th className={t.th}>Employee</th>
                <th className={t.th}>To</th>
                <th className={t.th}>Subject</th>
                <th className={t.th}>Delivery</th>
                <th className={t.th}>Acknowledgement</th>
                <th className={t.th}><span className="sr-only">Actions</span></th>
              </tr>
            </thead>
            <tbody>
              {real.map((m) => (
                <tr key={m.id} className={`${t.tr} ${m.excluded ? "opacity-50" : ""}`}>
                  <td className={t.td}>
                    <Link href={`/cases/${m.exit_case_id}`} className="font-medium hover:text-primary">{m.full_name}</Link>
                    <div className="text-xs text-muted-foreground">{m.employee_code}</div>
                  </td>
                  <td className={`${t.td} text-xs`}>{m.to_addresses.join(", ") || <span className="text-[var(--status-critical)]">no address</span>}</td>
                  <td className={`${t.td} max-w-xs`}>
                    <div className="line-clamp-1">{m.subject}</div>
                    <Hash value={m.content_hash} />
                    {m.last_error && <div className="text-xs text-[var(--status-critical)]">{m.last_error}</div>}
                  </td>
                  <td className={t.td}>{m.excluded ? <span className="text-xs">Excluded</span> : <MessageStatusPill status={m.status} />}</td>
                  <td className={t.td}>{!m.excluded && m.status !== "pending" && <AckPill at={m.acknowledged ? "yes" : null} />}</td>
                  <td className={`${t.td} whitespace-nowrap text-right`}>
                    <Button size="sm" variant="ghost" onClick={() => setPreview(m)}><Eye className="size-3.5" />Preview</Button>
                    {editable && can("hr", "legal", "approver") && (
                      <Button size="sm" variant="ghost" disabled={busy} onClick={() => exclude(m)}>
                        {m.excluded ? "Include" : "Exclude"}
                      </Button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {!real.length && <EmptyState icon={Mail} title="No messages" />}
        </div>
      </Panel>

      <div className="grid gap-6 xl:grid-cols-2">
        <Panel title="Approval" description="Bound to the content hash of every message in the batch.">
          <ApprovalTrail items={b.approvals} />
        </Panel>
        <Panel title="Test copies" description={b.test_sent_at ? `Last test send ${fmtDate(b.test_sent_at)}` : "Send test copies to internal addresses before releasing."}>
          {tests.length ? (
            <ul className="divide-y text-sm">
              {tests.map((m) => (
                <li key={m.id} className="flex items-center gap-3 py-2">
                  <span className="flex-1 truncate">{m.subject}</span>
                  <span className="text-xs text-muted-foreground">{m.to_addresses.join(", ")}</span>
                  <MessageStatusPill status={m.status} />
                </li>
              ))}
            </ul>
          ) : <p className="text-sm text-muted-foreground">No test copies sent.</p>}
        </Panel>
      </div>

      <Preview batchId={b.id} message={preview} onClose={() => setPreview(null)} />

      <DecisionDialog
        open={deciding} onOpenChange={setDeciding}
        title="Approve sending this batch?"
        description={<>You are approving {b.counts.messages ?? 0} exact message{b.counts.messages === 1 ? "" : "s"}. Preview them first.
          If you drafted any of them, the system will refuse your approval.</>}
        hash={pending?.content_hash}
        onDecide={async (approve, comment) => {
          await post(`/notice-batches/${b.id}/approve`, { approve, comment: comment || null });
          toast.success(approve ? "Approved" : "Rejected; the batch is back in draft");
          q.reload();
        }}
      />

      <Dialog open={releasing} onOpenChange={setReleasing}>
        <DialogContent className="rounded-2xl sm:max-w-md">
          <DialogHeader>
            <DialogTitle>Release {b.counts.messages ?? 0} messages?</DialogTitle>
            <DialogDescription>
              The approved messages are queued and sent at a throttled rate. Unless the server runs in staging or
              production, mail is captured locally and nothing leaves the machine.
            </DialogDescription>
          </DialogHeader>
          <ul className="space-y-1 text-sm text-muted-foreground">
            <li>· The approval is checked against the message hashes again.</li>
            <li>· Termination notices whose planned notice date has passed are refused.</li>
            <li>· Consultation timing rules are checked.</li>
          </ul>
          <p className="text-xs text-muted-foreground">Releasing as {me?.full_name}. This can&apos;t be undone.</p>
          <div className="flex justify-end gap-2">
            <Button variant="outline" onClick={() => setReleasing(false)}>Cancel</Button>
            <Button disabled={busy} onClick={async () => {
              const r = await run(() => api<{ queued: number }>(`/notice-batches/${b.id}/release`, { method: "POST" }));
              if (r) {
                toast.success(`${r.queued} messages queued for sending`);
                setReleasing(false);
                q.reload();
              }
            }}>
              <Mail className="size-4" />Release
            </Button>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
}

export default function BatchPage() {
  return <Suspense><BatchDetail /></Suspense>;
}
