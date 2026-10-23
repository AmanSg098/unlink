"use client";

import { Download, Wallet } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { ErrorText, tableCls as t } from "@/components/common";
import { EmptyState, PageHeader, Panel, Pill } from "@/components/kit";
import { useAuth } from "@/components/auth";
import { download, humanize } from "@/components/form-bits";
import { FNF_STATUS } from "@/components/fnf-bits";
import { useQuery } from "@/lib/use-query";
import { fmtDay, fmtPaise, type FnfStatement } from "@/lib/api";
import { cn } from "@/lib/utils";

const FILTERS: [string, string][] = [["", "Current"], ["draft", "Draft"], ["submitted", "In approval"],
  ["approved", "Approved"], ["paid", "Paid"], ["superseded", "Superseded"]];

export default function FnfPage() {
  const { can } = useAuth();
  const [status, setStatus] = useState("");
  const q = useQuery<FnfStatement[]>(`/fnf${status ? `?status=${status}` : ""}`);
  const list = q.data ?? [];
  const today = new Date().toISOString().slice(0, 10);

  return (
    <div className="space-y-8">
      <PageHeader eyebrow="Act" title="Full and final settlement"
                  description="Statements are computed from payroll inputs and the jurisdiction rules, in paise, with every line traced to a rule. The person who computes a statement can't approve it."
                  actions={can("finance") && (
                    <Button variant="outline" className="gap-2 rounded-xl" onClick={async () => {
                      try { await download("/fnf/export/payroll.csv", "fnf-payroll.csv"); toast.success("Payroll CSV downloaded"); }
                      catch (e) { toast.error((e as Error).message); }
                    }}><Download className="size-4" />Payroll CSV</Button>
                  )} />

      <Panel bodyClassName="p-0">
        <div className="flex flex-wrap gap-1 border-b p-3">
          {FILTERS.map(([v, l]) => (
            <button key={v} onClick={() => setStatus(v)}
                    className={cn("rounded-lg px-3 py-1.5 text-sm transition-colors",
                                  status === v ? "bg-muted font-medium" : "text-muted-foreground hover:text-foreground")}>
              {l}
            </button>
          ))}
        </div>
        <ErrorText error={q.error} />
        {!q.loading && list.length === 0 ? (
          <EmptyState icon={Wallet} title="No statements">FNF is computed from an exit case once its last working day is set.</EmptyState>
        ) : (
          <table className={t.table}>
            <thead className={t.thead}><tr className="border-b"><th className={t.th}>Person</th><th className={t.th}>Version</th>
              <th className={t.th}>Status</th><th className={t.th}>Waiting on</th><th className={`${t.th} text-right`}>Net payable</th>
              <th className={t.th}>Pay by</th><th className={t.th}>Case</th></tr></thead>
            <tbody>
              {list.map((s) => (
                <tr key={s.id} className={t.tr}>
                  <td className={t.td}>
                    <Link href={`/fnf/${s.id}`} className="hover:text-primary">
                      <div className="font-medium">{s.employee?.full_name}</div>
                      <div className="text-xs text-muted-foreground">{s.employee?.employee_code} · {s.employee?.department}</div>
                    </Link>
                  </td>
                  <td className={`${t.td} tabular-nums`}>v{s.version}</td>
                  <td className={t.td}><Pill spec={FNF_STATUS[s.status] ?? FNF_STATUS.draft} /></td>
                  <td className={`${t.td} text-xs`}>
                    {s.current_step ? <>{humanize(s.current_step.step)} <span className="text-muted-foreground">({s.current_step.roles.join(" / ")})</span></> : "–"}
                    {s.needs_legal && <div className="text-muted-foreground">Legal review needed</div>}
                  </td>
                  <td className={`${t.td} text-right font-medium tabular-nums`}>{fmtPaise(s.net_paise)}</td>
                  <td className={cn(t.td, "whitespace-nowrap", s.status !== "paid" && s.payment_due_on && s.payment_due_on < today && "font-medium text-[var(--status-critical)]")}>
                    {fmtDay(s.payment_due_on)}
                  </td>
                  <td className={t.td}><Link href={`/cases/${s.exit_case_id}`} className="text-xs text-muted-foreground hover:text-foreground">#{s.exit_case_id}</Link></td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Panel>
    </div>
  );
}
