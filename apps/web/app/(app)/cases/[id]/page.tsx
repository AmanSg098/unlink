"use client";

import { ArrowLeft, Ban, CircleCheck, CirclePause, CirclePlay, FileDown, TriangleAlert } from "lucide-react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { Suspense, useState } from "react";
import { toast } from "sonner";
import { Button, buttonVariants } from "@/components/ui/button";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { ErrorText, fmtDate } from "@/components/common";
import { AuditTable } from "@/components/audit-table";
import { ReasonDialog } from "@/components/case-ui";
import {
  AiSection, ClearanceSection, ClosingSection, DatesSection, NoticesSection, ReasonSection, SettlementSection, TasksSection,
  type CaseDetail,
} from "@/components/case-sections";
import { Avatar, CaseStatePill, PageHeader, Panel } from "@/components/kit";
import { useAuth } from "@/components/auth";
import { useQuery } from "@/lib/use-query";
import { fmtDay, post } from "@/lib/api";
import { cn } from "@/lib/utils";

/** The main path as a horizontal stepper; on hold shows where it was paused. */
function Stepper({ d }: { d: CaseDetail }) {
  const c = d.case;
  const at = c.state === "on_hold" ? c.held_from_state : c.state;
  const idx = d.states.findIndex((s) => s.key === at);
  return (
    <ol className="flex gap-1 overflow-x-auto pb-1" aria-label={`Stage: ${c.state_label}`}>
      {d.states.map((s, i) => {
        const done = i < idx || (i === idx && s.key === "closed");
        const current = i === idx && c.state !== "withdrawn";
        return (
          <li key={s.key} className="min-w-24 flex-1">
            <div className={cn("h-1.5 rounded-full",
                               done ? "bg-[var(--status-good)]" : current ? (c.state === "on_hold" ? "bg-[var(--status-warning)]" : "bg-primary") : "bg-muted")} />
            <div className={cn("mt-1.5 flex items-center gap-1 text-[11px]", current ? "font-medium text-foreground" : "text-muted-foreground")}>
              {done && <CircleCheck className="size-3 text-[var(--status-good)]" aria-hidden="true" />}
              {current && c.state === "on_hold" && <CirclePause className="size-3 text-[var(--status-warning)]" aria-hidden="true" />}
              {s.label}
            </div>
          </li>
        );
      })}
    </ol>
  );
}

function CaseView() {
  const { id } = useParams<{ id: string }>();
  const { can } = useAuth();
  const q = useQuery<CaseDetail>(`/exit-cases/${id}`);
  const [dialog, setDialog] = useState<null | "hold" | "release" | "withdraw">(null);
  const d = q.data;
  if (!d) return <ErrorText error={q.error} />;
  const c = d.case;
  const props = { d, reload: q.reload };
  const ended = c.state === "withdrawn" || c.state === "closed";

  return (
    <div className="space-y-8">
      <Link href="/cases" className="inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground">
        <ArrowLeft className="size-4" />Exit cases
      </Link>
      <PageHeader
        eyebrow={<Link href={`/plans/${c.plan_id}`} className="hover:text-foreground">{c.plan_name}</Link>}
        title={<span className="flex items-center gap-3"><Avatar name={c.employee.full_name} />{c.employee.full_name}</span>}
        description={<span className="inline-flex flex-wrap items-center gap-2">
          <CaseStatePill state={c.state} label={c.state_label} />
          <Link href={`/people/${c.employee.employee_code}`} className="hover:text-foreground">{c.employee.employee_code}</Link>
          <span>· {c.employee.role}, {c.employee.department} · owner {c.owner}</span>
        </span>}
        actions={
          <div className="flex flex-wrap gap-2">
            {can("hr", "legal") && (
              <a href={`/api/exit-cases/${c.id}/file.pdf`} className={buttonVariants({ variant: "outline" })}>
                <FileDown className="size-4" />Exit file PDF
              </a>
            )}
            {can("legal") && !ended && c.state !== "on_hold" && (
              <Button variant="outline" onClick={() => setDialog("hold")}><CirclePause className="size-4" />Put on hold</Button>
            )}
            {can("legal") && c.state === "on_hold" && (
              <Button variant="outline" onClick={() => setDialog("release")}><CirclePlay className="size-4" />Release hold</Button>
            )}
            {can("hr") && !ended && c.state !== "effective" && (
              <Button variant="destructive" onClick={() => setDialog("withdraw")}><Ban className="size-4" />Withdraw</Button>
            )}
          </div>
        }
      />

      <Panel bodyClassName="p-5"><Stepper d={d} /></Panel>

      {c.state === "on_hold" && (
        <div className="flex items-start gap-3 rounded-xl border p-4 text-sm"
             style={{ borderColor: "color-mix(in oklab, var(--status-warning) 45%, transparent)",
                      background: "color-mix(in oklab, var(--status-warning) 8%, transparent)" }}>
          <CirclePause className="mt-0.5 size-4 shrink-0 text-[var(--status-warning)]" />
          <div><div className="font-medium">On hold since the {d.states.find((s) => s.key === c.held_from_state)?.label ?? c.held_from_state} stage</div>
            <div className="text-muted-foreground">{c.hold_reason}. Termination steps are blocked until Legal releases the hold.</div></div>
        </div>
      )}
      {c.state === "withdrawn" && (
        <div className="flex items-start gap-3 rounded-xl border p-4 text-sm">
          <Ban className="mt-0.5 size-4 shrink-0 text-muted-foreground" />
          <div><div className="font-medium">Withdrawn</div><div className="text-muted-foreground">{c.withdrawn_reason}</div></div>
        </div>
      )}
      {c.overdue_tasks > 0 && (
        <p className="flex items-center gap-2 text-sm"><TriangleAlert className="size-4 text-[var(--status-critical)]" />
          {c.overdue_tasks} overdue task{c.overdue_tasks > 1 ? "s" : ""}</p>
      )}

      <dl className="grid grid-cols-2 gap-4 text-sm lg:grid-cols-5">
        {[
          ["Reason", c.reason_code ?? "Not set"],
          ["Notice date", fmtDay(c.notice_date)],
          ["Last working day", fmtDay(c.actual_last_day ?? c.last_working_day)],
          ["Selection basis", c.selection_basis.replace(/_/g, " ")],
          ["Opened", fmtDate(c.created_at)],
        ].map(([k, v]) => (
          <div key={k} className="rounded-xl border bg-background/40 px-4 py-3">
            <dt className="text-xs text-muted-foreground">{k}</dt>
            <dd className="mt-0.5 font-medium">{v}</dd>
          </div>
        ))}
      </dl>

      <Tabs defaultValue="overview">
        <TabsList className="flex-wrap">
          <TabsTrigger value="overview">Overview</TabsTrigger>
          <TabsTrigger value="notices">Notices</TabsTrigger>
          <TabsTrigger value="settlement">Settlement and documents</TabsTrigger>
          <TabsTrigger value="clearance">Clearance</TabsTrigger>
          <TabsTrigger value="closing">Effective and close</TabsTrigger>
          <TabsTrigger value="audit">Audit trail</TabsTrigger>
          {can("hr", "legal") && <TabsTrigger value="ai">AI drafts</TabsTrigger>}
        </TabsList>
        <TabsContent value="overview" className="mt-6 space-y-6">
          <ReasonSection {...props} />
          <DatesSection {...props} />
          <TasksSection {...props} />
        </TabsContent>
        <TabsContent value="notices" className="mt-6"><NoticesSection {...props} /></TabsContent>
        <TabsContent value="settlement" className="mt-6"><SettlementSection {...props} /></TabsContent>
        <TabsContent value="clearance" className="mt-6"><ClearanceSection {...props} /></TabsContent>
        <TabsContent value="closing" className="mt-6"><ClosingSection {...props} /></TabsContent>
        <TabsContent value="audit" className="mt-6">
          <Panel title="Audit trail" description="Every action on this case and its notices, settlement, documents and clearance.">
            <AuditTable entries={d.audit} />
          </Panel>
        </TabsContent>
        {can("hr", "legal") && <TabsContent value="ai" className="mt-6"><AiSection d={d} /></TabsContent>}
      </Tabs>

      <ReasonDialog open={dialog === "hold"} onOpenChange={(o) => !o && setDialog(null)} title="Put this case on hold"
                    label="Why? (for example a legal query or a grievance)" cta="Put on hold"
                    onSubmit={async (text) => { await post(`/exit-cases/${c.id}/hold`, { text }); toast.success("Case on hold"); q.reload(); }} />
      <ReasonDialog open={dialog === "release"} onOpenChange={(o) => !o && setDialog(null)} title="Release the hold"
                    label="Note for the record" cta="Release"
                    onSubmit={async (text) => { await post(`/exit-cases/${c.id}/release-hold`, { text }); toast.success("Hold released"); q.reload(); }} />
      <ReasonDialog open={dialog === "withdraw"} onOpenChange={(o) => !o && setDialog(null)} title="Withdraw this exit"
                    label="Why is the exit being withdrawn? Unsent notices are cancelled and open tasks closed." cta="Withdraw" destructive
                    onSubmit={async (text) => { await post(`/exit-cases/${c.id}/withdraw`, { text }); toast.success("Exit withdrawn"); q.reload(); }} />
    </div>
  );
}

export default function CasePage() {
  return <Suspense><CaseView /></Suspense>;
}
