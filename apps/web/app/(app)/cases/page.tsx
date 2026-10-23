"use client";

import { CirclePause, Handshake, ListChecks, Search, TriangleAlert } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { Input } from "@/components/ui/input";
import { ErrorText, tableCls as t } from "@/components/common";
import { Avatar, CaseStatePill, EmptyState, PageHeader, Panel, StatTile } from "@/components/kit";
import { useQuery } from "@/lib/use-query";
import { fmtDay, type CaseState, type CaseSummary } from "@/lib/api";

const STATES: [CaseState, string][] = [
  ["identified", "Identified"], ["notice_drafted", "Notice drafted"], ["notice_approved", "Notice approved"],
  ["notice_sent", "Notice sent"], ["notice_period", "Notice period"], ["last_day_set", "Last day set"],
  ["fnf_draft", "FNF draft"], ["fnf_approved", "FNF approved"], ["documents_issued", "Documents issued"],
  ["effective", "Effective"], ["closed", "Closed"], ["on_hold", "On hold"], ["withdrawn", "Withdrawn"],
];

export default function CasesPage() {
  const [state, setState] = useState("");
  const [q, setQ] = useState("");
  const cases = useQuery<CaseSummary[]>(`/exit-cases${state ? `?state=${state}` : ""}`);
  const all = cases.data ?? [];
  const needle = q.trim().toLowerCase();
  const list = needle
    ? all.filter((c) => c.employee.full_name.toLowerCase().includes(needle) || c.employee.employee_code.toLowerCase().includes(needle))
    : all;
  const open = all.filter((c) => !["closed", "withdrawn"].includes(c.state));

  return (
    <div className="space-y-8">
      <PageHeader eyebrow="Act" title="Exit cases"
                  description="One case per person leaving: reason, notice, last day, settlement, documents and clearance." />

      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <StatTile label="Open cases" icon={Handshake} value={open.length} />
        <StatTile label="On hold" icon={CirclePause} value={all.filter((c) => c.state === "on_hold").length} />
        <StatTile label="Open tasks" icon={ListChecks} value={open.reduce((n, c) => n + c.open_tasks, 0)} />
        <StatTile label="Overdue tasks" icon={TriangleAlert} value={open.reduce((n, c) => n + c.overdue_tasks, 0)}
                  accent={open.some((c) => c.overdue_tasks > 0)} />
      </div>

      <Panel bodyClassName="p-0">
        <div className="flex flex-wrap items-center gap-2 border-b p-4">
          <div className="relative">
            <Search className="absolute top-1/2 left-3 size-4 -translate-y-1/2 text-muted-foreground" />
            <Input className="h-9 w-64 rounded-xl pl-9" placeholder="Search name or ID" value={q} onChange={(e) => setQ(e.target.value)} />
          </div>
          <select className="h-9 rounded-xl border bg-background/50 px-3 text-sm" value={state} aria-label="Stage"
                  onChange={(e) => setState(e.target.value)}>
            <option value="">All stages</option>
            {STATES.map(([k, l]) => <option key={k} value={k}>{l}</option>)}
          </select>
          <span className="ml-auto text-xs text-muted-foreground">{list.length} shown</span>
        </div>
        <ErrorText error={cases.error} />
        <div className="overflow-x-auto">
          <table className={t.table}>
            <thead className={t.thead}>
              <tr className="border-b">
                <th className={t.th}>Employee</th>
                <th className={t.th}>Stage</th>
                <th className={t.th}>Reason</th>
                <th className={t.th}>Notice date</th>
                <th className={t.th}>Last working day</th>
                <th className={`${t.th} text-right`}>Tasks</th>
                <th className={t.th}>Plan</th>
                <th className={t.th}>Owner</th>
              </tr>
            </thead>
            <tbody>
              {list.map((c) => (
                <tr key={c.id} className={t.tr}>
                  <td className={t.td}>
                    <Link href={`/cases/${c.id}`} className="flex items-center gap-3 hover:text-primary">
                      <Avatar name={c.employee.full_name} />
                      <div>
                        <div className="font-medium">{c.employee.full_name}</div>
                        <div className="text-xs text-muted-foreground">{c.employee.employee_code} · {c.employee.department}</div>
                      </div>
                    </Link>
                  </td>
                  <td className={t.td}><CaseStatePill state={c.state} label={c.state_label} /></td>
                  <td className={`${t.td} font-mono text-xs`}>{c.reason_code ?? <span className="font-sans text-muted-foreground">Not set</span>}</td>
                  <td className={`${t.td} whitespace-nowrap`}>{fmtDay(c.notice_date)}</td>
                  <td className={`${t.td} whitespace-nowrap`}>{fmtDay(c.actual_last_day ?? c.last_working_day)}</td>
                  <td className={`${t.td} text-right tabular-nums`}>
                    {c.open_tasks}
                    {c.overdue_tasks > 0 && <span className="ml-1 text-xs text-[var(--status-critical)]">({c.overdue_tasks} overdue)</span>}
                  </td>
                  <td className={`${t.td} max-w-48 truncate`}><Link href={`/plans/${c.plan_id}`} className="hover:text-primary">{c.plan_name}</Link></td>
                  <td className={`${t.td} text-xs text-muted-foreground`}>{c.owner}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {!cases.loading && list.length === 0 && (
            <EmptyState icon={Handshake} title="No exit cases">Cases are opened from an approved reduction plan.</EmptyState>
          )}
        </div>
      </Panel>
    </div>
  );
}
