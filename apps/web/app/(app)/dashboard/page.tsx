"use client";

import { ArrowUpRight, CalendarClock, CheckSquare, FileText, Handshake, Plus, TriangleAlert, UsersRound } from "lucide-react";
import Link from "next/link";
import { buttonVariants } from "@/components/ui/button";
import { BarList } from "@/components/charts";
import { CountUp, EmptyState, PageHeader, Panel, StatTile, StatusPill, relTime } from "@/components/kit";
import { useAuth } from "@/components/auth";
import { useQuery } from "@/lib/use-query";
import { fmtDay, type Approval, type Plan, type Task } from "@/lib/api";
import { cn } from "@/lib/utils";

type Dashboard = {
  tasks: Task[];
  approvals: Approval[];
  cases: { open: number; by_state: { state: string; label: string; count: number }[] };
  plans: Pick<Plan, "id" | "name" | "status" | "version" | "created_by" | "created_at" | "last_run_at" |
    "target_count" | "selection_method" | "filters">[];
  alerts: { kind: string; severity: string; text: string; link: string }[];
  people: { total: number };
};

function greeting() {
  const h = new Date().getHours();
  return h < 12 ? "Good morning" : h < 18 ? "Good afternoon" : "Good evening";
}

export default function DashboardPage() {
  const { me, can } = useAuth();
  const q = useQuery<Dashboard>("/dashboard");
  const d = q.data;
  const overdue = d?.tasks.filter((t) => t.overdue).length ?? 0;

  return (
    <div className="space-y-8">
      <PageHeader
        eyebrow={me?.org_name}
        title={<>{greeting()}, {me?.full_name.split(" ")[0]}</>}
        description="What needs your attention across plans, notices and exits."
        actions={can("hr") && (
          <Link href="/plans/new" className={cn(buttonVariants(), "gap-2 rounded-xl lg:hidden")}>
            <Plus className="size-4" /> New reduction plan
          </Link>
        )}
      />

      {d?.alerts.length ? (
        <div className="space-y-2">
          {d.alerts.map((a) => (
            <Link key={a.kind} href={a.link}
                  className="flex items-center gap-3 rounded-xl border px-4 py-2.5 text-sm transition-colors hover:bg-muted/40"
                  style={{ borderColor: `color-mix(in oklab, var(--status-${a.severity === "block" ? "critical" : "warning"}) 45%, transparent)`,
                           background: `color-mix(in oklab, var(--status-${a.severity === "block" ? "critical" : "warning"}) 8%, transparent)` }}>
              <TriangleAlert className="size-4 shrink-0" style={{ color: `var(--status-${a.severity === "block" ? "critical" : "warning"})` }} />
              <span className="flex-1">{a.text}</span>
              <ArrowUpRight className="size-4 text-muted-foreground" />
            </Link>
          ))}
        </div>
      ) : null}

      <div className="stagger grid grid-cols-2 gap-4 lg:grid-cols-4">
        <StatTile label="Approvals waiting for you" icon={CheckSquare} accent={(d?.approvals.length ?? 0) > 0}
                  value={<CountUp value={d?.approvals.length ?? 0} />} hint="Respecting separation of duties" />
        <StatTile label="Tasks due this week" icon={CalendarClock} value={<CountUp value={d?.tasks.length ?? 0} />}
                  hint={overdue ? `${overdue} overdue` : "None overdue"} />
        <StatTile label="Open exit cases" icon={Handshake} value={<CountUp value={d?.cases.open ?? 0} />} />
        <StatTile label="People" icon={UsersRound} value={<CountUp value={d?.people.total ?? 0} />}
                  hint={me?.role === "manager" ? "In your reporting line" : "In this organisation"} />
      </div>

      <div className="grid gap-6 xl:grid-cols-2">
        <Panel title="Waiting for your approval">
          {d?.approvals.length ? (
            <ul className="divide-y">
              {d.approvals.map((a) => (
                <li key={a.id}>
                  <Link href={a.link ?? "#"} className="flex items-center gap-3 py-2.5 text-sm hover:text-primary">
                    <CheckSquare className="size-4 text-muted-foreground" />
                    <span className="flex-1">{a.title}</span>
                    <span className="text-xs text-muted-foreground">{a.step.replace(/_/g, " ")} · {relTime(a.created_at)}</span>
                  </Link>
                </li>
              ))}
            </ul>
          ) : <EmptyState icon={CheckSquare} title="Nothing waiting for you" />}
        </Panel>

        <Panel title="Tasks due this week">
          {d?.tasks.length ? (
            <ul className="divide-y">
              {d.tasks.map((t) => (
                <li key={t.id}>
                  <Link href={`/cases/${t.exit_case_id}`} className="flex items-center gap-3 py-2.5 text-sm hover:text-primary">
                    <span className={cn("size-2 shrink-0 rounded-full", t.overdue ? "bg-[var(--status-critical)]" : "bg-muted-foreground/40")} />
                    <span className="flex-1">{t.title}</span>
                    <span className="font-mono text-xs text-muted-foreground">{t.employee_code}</span>
                    <span className={cn("w-24 text-right text-xs", t.overdue ? "text-[var(--status-critical)]" : "text-muted-foreground")}>
                      {t.overdue ? "Overdue · " : ""}{fmtDay(t.due_date)}
                    </span>
                  </Link>
                </li>
              ))}
            </ul>
          ) : <EmptyState icon={CalendarClock} title="No tasks due" />}
        </Panel>
      </div>

      <div className="grid gap-6 xl:grid-cols-[1fr_1.4fr]">
        <Panel title="Exit cases by stage" actions={<Link href="/cases" className="text-xs text-muted-foreground hover:text-foreground">All cases</Link>}>
          {d?.cases.by_state.length ? (
            <BarList items={d.cases.by_state.map((s) => ({ label: s.label, value: s.count }))} />
          ) : <EmptyState icon={Handshake} title="No exit cases yet" />}
        </Panel>
        {d && d.plans.length > 0 && (
          <Panel title="Reduction plans" actions={<Link href="/plans" className="text-xs text-muted-foreground hover:text-foreground">All plans</Link>}>
            <ul className="divide-y">
              {d.plans.slice(0, 6).map((p) => (
                <li key={p.id}>
                  <Link href={`/plans/${p.id}`} className="flex items-center gap-3 py-2.5 text-sm hover:text-primary">
                    <FileText className="size-4 text-muted-foreground" />
                    <span className="flex-1 truncate">{p.name}{p.version > 1 && <span className="ml-1 text-xs text-muted-foreground">v{p.version}</span>}</span>
                    <StatusPill status={p.status} />
                    <span className="hidden w-24 text-right text-xs text-muted-foreground sm:block">{relTime(p.last_run_at ?? p.created_at)}</span>
                  </Link>
                </li>
              ))}
            </ul>
          </Panel>
        )}
      </div>
    </div>
  );
}
