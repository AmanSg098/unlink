"use client";

import { FilePlus2, FileText, Inbox, Layers, Mail, Send } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { ErrorText, fmtDate, tableCls as t } from "@/components/common";
import { AckPill, MessageStatusPill, useAct } from "@/components/case-ui";
import { BatchStatusPill, DraftIssues, DraftStatusPill, HumanApprovalNote, TemplateStatusPill } from "@/components/notice-ui";
import { EmptyState, PageHeader, Panel, StatTile, relTime } from "@/components/kit";
import { useAuth } from "@/components/auth";
import { useQuery } from "@/lib/use-query";
import { post, type Batch, type Draft, type NoticeMessage, type Plan, type Template } from "@/lib/api";

const select = "h-9 w-full rounded-xl border bg-background/50 px-3 text-sm";

function PrepareDialog({ open, onOpenChange, templates, onDone }: {
  open: boolean;
  onOpenChange: (o: boolean) => void;
  templates: Template[];
  onDone: () => void;
}) {
  const plans = useQuery<Plan[]>(open ? "/plans" : null);
  const [planId, setPlanId] = useState("");
  const [templateId, setTemplateId] = useState("");
  const { busy, run } = useAct();
  const withCases = (plans.data ?? []).filter((p) => p.cases);
  const usable = templates.filter((x) => x.status !== "retired");

  async function submit() {
    const r = await run(() => post<Draft[]>(`/plans/${planId}/notice-drafts`, { template_id: Number(templateId) }));
    if (r) {
      toast.success(`${r.length} draft${r.length === 1 ? "" : "s"} prepared`,
                    { description: "Review each one, then put them in a batch for approval." });
      onOpenChange(false);
      onDone();
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="rounded-2xl sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>Prepare notice drafts</DialogTitle>
          <DialogDescription>
            Creates one draft per open exit case in the plan, merged from the template. Cases on hold are skipped for
            termination notices.
          </DialogDescription>
        </DialogHeader>
        <div className="space-y-3">
          <div className="space-y-1.5">
            <Label htmlFor="prep-plan">Reduction plan</Label>
            <select id="prep-plan" className={select} value={planId} onChange={(e) => setPlanId(e.target.value)}>
              <option value="">Choose a plan with exit cases…</option>
              {withCases.map((p) => <option key={p.id} value={p.id}>{p.name} (v{p.version})</option>)}
            </select>
            {plans.data && withCases.length === 0 && (
              <p className="text-xs text-muted-foreground">No plan has exit cases yet. Open cases from an approved plan first.</p>
            )}
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="prep-template">Template</Label>
            <select id="prep-template" className={select} value={templateId} onChange={(e) => setTemplateId(e.target.value)}>
              <option value="">Choose a template…</option>
              {usable.map((x) => (
                <option key={x.id} value={x.id}>
                  {x.title} v{x.version}{x.status === "draft" ? " (not yet legal-approved)" : ""}
                </option>
              ))}
            </select>
          </div>
        </div>
        <div className="flex justify-end gap-2">
          <Button variant="outline" onClick={() => onOpenChange(false)}>Cancel</Button>
          <Button disabled={busy || !planId || !templateId} onClick={submit}>Prepare drafts</Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}

function BatchesTab({ batches }: { batches: Batch[] }) {
  if (!batches.length) {
    return <EmptyState icon={Layers} title="No batches yet">Select ready drafts on the Drafts tab and group them into a batch.</EmptyState>;
  }
  return (
    <div className="overflow-x-auto">
      <table className={t.table}>
        <thead className={t.thead}>
          <tr className="border-b">
            <th className={t.th}>Batch</th>
            <th className={t.th}>Status</th>
            <th className={`${t.th} text-right`}>Messages</th>
            <th className={`${t.th} text-right`}>Delivered</th>
            <th className={`${t.th} text-right`}>Acknowledged</th>
            <th className={t.th}>Next step</th>
            <th className={t.th}>Created</th>
          </tr>
        </thead>
        <tbody>
          {batches.map((b) => (
            <tr key={b.id} className={t.tr}>
              <td className={t.td}>
                <Link href={`/notices/batches/${b.id}`} className="font-medium hover:text-primary">{b.name}</Link>
                {b.problems.length > 0 && (
                  <div className="text-xs text-[var(--status-critical)]">{b.problems.length} blocking problem{b.problems.length > 1 ? "s" : ""}</div>
                )}
              </td>
              <td className={t.td}><BatchStatusPill status={b.status} /></td>
              <td className={`${t.td} text-right tabular-nums`}>
                {b.counts.messages ?? 0}
                {(b.counts.excluded ?? 0) > 0 && <span className="text-xs text-muted-foreground"> (+{b.counts.excluded} excluded)</span>}
              </td>
              <td className={`${t.td} text-right tabular-nums`}>{(b.counts.delivered ?? 0) + (b.counts.sent ?? 0)}</td>
              <td className={`${t.td} text-right tabular-nums`}>{b.counts.acknowledged ?? 0}</td>
              <td className={`${t.td} text-xs text-muted-foreground`}>
                {b.current_step ? `${b.current_step.step.replace(/_/g, " ")} (${b.current_step.roles.join(" or ")})` : "–"}
              </td>
              <td className={`${t.td} text-xs text-muted-foreground`}>{b.created_by} · {relTime(b.created_at)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function DraftsTab({ drafts, canBatch, onBatched }: { drafts: Draft[]; canBatch: boolean; onBatched: (id: number) => void }) {
  const [picked, setPicked] = useState<Set<number>>(new Set());
  const [naming, setNaming] = useState(false);
  const [name, setName] = useState("");
  const { busy, run } = useAct();
  const ready = drafts.filter((d) => d.status === "draft");
  const toggle = (id: number) => setPicked((p) => {
    const n = new Set(p);
    if (n.has(id)) n.delete(id);
    else n.add(id);
    return n;
  });

  async function create() {
    const b = await run(() => post<Batch>("/notice-batches", { name, draft_ids: [...picked] }), "Batch created");
    if (b) {
      setNaming(false);
      setPicked(new Set());
      onBatched(b.id);
    }
  }

  if (!drafts.length) {
    return <EmptyState icon={FileText} title="No drafts">Prepare drafts for a plan&apos;s exit cases to get started.</EmptyState>;
  }
  return (
    <>
      {canBatch && (
        <div className="flex flex-wrap items-center gap-3 border-b px-4 py-3 text-sm">
          <span className="text-muted-foreground">{picked.size} selected</span>
          <Button size="sm" variant="ghost" disabled={!ready.length}
                  onClick={() => setPicked(picked.size === ready.length ? new Set() : new Set(ready.map((d) => d.id)))}>
            {picked.size === ready.length ? "Clear" : "Select all drafts"}
          </Button>
          <Button size="sm" className="ml-auto" disabled={!picked.size} onClick={() => setNaming(true)}>
            <Layers className="size-4" />Create batch
          </Button>
        </div>
      )}
      <div className="overflow-x-auto">
        <table className={t.table}>
          <thead className={t.thead}>
            <tr className="border-b">
              {canBatch && <th className={`${t.th} w-8`}><span className="sr-only">Select</span></th>}
              <th className={t.th}>Employee</th>
              <th className={t.th}>Template</th>
              <th className={t.th}>Subject</th>
              <th className={t.th}>Checks</th>
              <th className={t.th}>Status</th>
              <th className={t.th}>Drafted</th>
            </tr>
          </thead>
          <tbody>
            {drafts.map((d) => (
              <tr key={d.id} className={t.tr}>
                {canBatch && (
                  <td className={t.td}>
                    <input type="checkbox" aria-label={`Select draft for ${d.employee_code}`} disabled={d.status !== "draft"}
                           checked={picked.has(d.id)} onChange={() => toggle(d.id)} />
                  </td>
                )}
                <td className={t.td}>
                  <Link href={`/notices/drafts/${d.id}`} className="font-medium hover:text-primary">{d.full_name}</Link>
                  <div className="text-xs text-muted-foreground">{d.employee_code} · v{d.version}</div>
                </td>
                <td className={t.td}>{d.template.title}<div className="text-xs text-muted-foreground">v{d.template.version}</div></td>
                <td className={`${t.td} max-w-xs truncate`}>{d.subject}</td>
                <td className={t.td}><DraftIssues draft={d} /></td>
                <td className={t.td}><DraftStatusPill status={d.status} /></td>
                <td className={`${t.td} text-xs text-muted-foreground`}>{d.created_by} · {relTime(d.created_at)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <Dialog open={naming} onOpenChange={setNaming}>
        <DialogContent className="rounded-2xl sm:max-w-md">
          <DialogHeader>
            <DialogTitle>Create a batch</DialogTitle>
            <DialogDescription>{picked.size} draft{picked.size === 1 ? "" : "s"} will be frozen into messages for approval.</DialogDescription>
          </DialogHeader>
          <div className="space-y-1.5">
            <Label htmlFor="batch-name">Batch name</Label>
            <Input id="batch-name" value={name} placeholder="e.g. Support consolidation: termination notices"
                   onChange={(e) => setName(e.target.value)} />
          </div>
          <div className="flex justify-end gap-2">
            <Button variant="outline" onClick={() => setNaming(false)}>Cancel</Button>
            <Button disabled={busy || !name.trim()} onClick={create}>Create batch</Button>
          </div>
        </DialogContent>
      </Dialog>
    </>
  );
}

function TemplatesTab({ templates }: { templates: Template[] }) {
  return (
    <div className="overflow-x-auto">
      <table className={t.table}>
        <thead className={t.thead}>
          <tr className="border-b">
            <th className={t.th}>Template</th>
            <th className={t.th}>Type</th>
            <th className={t.th}>Version</th>
            <th className={t.th}>Status</th>
            <th className={t.th}>Delivery</th>
            <th className={t.th}>Approved</th>
          </tr>
        </thead>
        <tbody>
          {templates.map((x) => (
            <tr key={x.id} className={t.tr}>
              <td className={t.td}>
                <Link href={`/notices/templates/${x.id}`} className="font-medium hover:text-primary">{x.title}</Link>
                <div className="font-mono text-xs text-muted-foreground">{x.key}</div>
              </td>
              <td className={`${t.td} capitalize`}>{x.type}</td>
              <td className={`${t.td} tabular-nums`}>v{x.version}</td>
              <td className={t.td}><TemplateStatusPill status={x.status} /></td>
              <td className={`${t.td} text-xs text-muted-foreground`}>
                {[x.send_to_personal && "personal email", x.attach_pdf && "PDF", x.encrypt_attachment && "password-protected"]
                  .filter(Boolean).join(" · ") || "work email"}
              </td>
              <td className={`${t.td} text-xs text-muted-foreground`}>
                {x.approved_by ? `${x.approved_by} · ${fmtDate(x.approved_at)}` : "–"}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function MessagesTab({ messages }: { messages: NoticeMessage[] }) {
  if (!messages.length) return <EmptyState icon={Inbox} title="Nothing sent yet" />;
  return (
    <div className="overflow-x-auto">
      <table className={t.table}>
        <thead className={t.thead}>
          <tr className="border-b">
            <th className={t.th}>Employee</th>
            <th className={t.th}>Subject</th>
            <th className={t.th}>Delivery</th>
            <th className={t.th}>Acknowledgement</th>
            <th className={t.th}>Sent</th>
          </tr>
        </thead>
        <tbody>
          {messages.map((m) => (
            <tr key={m.id} className={t.tr}>
              <td className={t.td}>
                <Link href={`/cases/${m.exit_case_id}`} className="font-medium hover:text-primary">{m.full_name}</Link>
                <div className="text-xs text-muted-foreground">{m.employee_code}</div>
              </td>
              <td className={`${t.td} max-w-xs`}>
                <Link href={`/notices/batches/${m.batch_id}`} className="line-clamp-1 hover:text-primary">{m.subject}</Link>
                {m.last_error && <div className="text-xs text-[var(--status-critical)]">{m.last_error}</div>}
              </td>
              <td className={t.td}><MessageStatusPill status={m.status} /></td>
              <td className={t.td}><AckPill at={m.acknowledged_at} /></td>
              <td className={`${t.td} text-xs text-muted-foreground`}>{m.sent_at ? fmtDate(m.sent_at) : "–"}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export default function NoticesPage() {
  const router = useRouter();
  const { can } = useAuth();
  const batches = useQuery<Batch[]>("/notice-batches");
  const drafts = useQuery<Draft[]>("/notice-drafts");
  const templates = useQuery<Template[]>("/notice-templates");
  const messages = useQuery<NoticeMessage[]>("/notice-messages");
  const [preparing, setPreparing] = useState(false);

  const waiting = (batches.data ?? []).filter((b) => b.status === "pending_approval").length;
  const readyDrafts = (drafts.data ?? []).filter((d) => d.status === "draft").length;
  const bounced = (messages.data ?? []).filter((m) => m.status === "bounced" || m.status === "failed").length;
  const unacked = (messages.data ?? []).filter((m) => ["sent", "delivered"].includes(m.status) && !m.acknowledged_at).length;

  return (
    <div className="space-y-8">
      <PageHeader
        eyebrow="Act"
        title="Notices"
        description="Draft from legal-approved templates, batch, approve, test, then release."
        actions={can("hr") && (
          <Button className="gap-2 rounded-xl" onClick={() => setPreparing(true)}><FilePlus2 className="size-4" />Prepare drafts</Button>
        )}
      />

      <HumanApprovalNote />

      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <StatTile label="Drafts ready to batch" icon={FileText} value={readyDrafts} />
        <StatTile label="Batches waiting for approval" icon={Layers} value={waiting} accent={waiting > 0} />
        <StatTile label="Bounced or failed" icon={Mail} value={bounced} hint={bounced ? "Each one has a follow-up task" : "None"} />
        <StatTile label="Sent, not yet acknowledged" icon={Send} value={unacked} />
      </div>

      <ErrorText error={batches.error ?? drafts.error ?? templates.error ?? messages.error} />

      <Panel bodyClassName="p-0">
        <Tabs defaultValue="batches">
          <div className="border-b px-4 pt-4 pb-3">
            <TabsList>
              <TabsTrigger value="batches">Batches</TabsTrigger>
              <TabsTrigger value="drafts">Drafts</TabsTrigger>
              <TabsTrigger value="templates">Templates</TabsTrigger>
              <TabsTrigger value="messages">Sent messages</TabsTrigger>
            </TabsList>
          </div>
          <TabsContent value="batches"><BatchesTab batches={batches.data ?? []} /></TabsContent>
          <TabsContent value="drafts">
            <DraftsTab drafts={drafts.data ?? []} canBatch={can("hr")}
                       onBatched={(id) => router.push(`/notices/batches/${id}`)} />
          </TabsContent>
          <TabsContent value="templates"><TemplatesTab templates={templates.data ?? []} /></TabsContent>
          <TabsContent value="messages"><MessagesTab messages={messages.data ?? []} /></TabsContent>
        </Tabs>
      </Panel>

      <PrepareDialog open={preparing} onOpenChange={setPreparing} templates={templates.data ?? []}
                     onDone={() => drafts.reload()} />
    </div>
  );
}
