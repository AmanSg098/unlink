"use client";

import { Search, ShieldCheck, Upload, UserPlus } from "lucide-react";
import Link from "next/link";
import { useRef, useState } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { ErrorText, tableCls as t } from "@/components/common";
import { EmployeeForm } from "@/components/employee-form";
import { Avatar, CountUp, EmptyState, PageHeader, Panel } from "@/components/kit";
import { useAuth } from "@/components/auth";
import { useQuery } from "@/lib/use-query";
import { api, fmtPaise, post, type Employee, type EmployeeMeta } from "@/lib/api";

function Rating({ value }: { value: number }) {
  return (
    <span className="inline-flex items-center gap-1.5 tabular-nums">
      <span className="h-1.5 w-10 overflow-hidden rounded-full bg-muted">
        <span className="block h-full rounded-full bg-[var(--series-1)]" style={{ width: `${((value - 1) / 4) * 100}%` }} />
      </span>
      {value.toFixed(1)}
    </span>
  );
}

const STATUS_LABEL: Record<string, string> = { active: "Active", on_notice: "On notice", exited: "Exited", on_hold: "On hold" };

export default function PeoplePage() {
  const { can } = useAuth();
  const canEdit = can("hr");
  const [dept, setDept] = useState("");
  const [status, setStatus] = useState("");
  const [q, setQ] = useState("");
  const params = new URLSearchParams();
  if (dept) params.set("department", dept);
  if (status) params.set("status", status);
  if (q) params.set("q", q);
  const people = useQuery<Employee[]>(`/employees?${params}`);
  const meta = useQuery<EmployeeMeta>("/employees/meta");
  const fileRef = useRef<HTMLInputElement>(null);
  const payrollRef = useRef<HTMLInputElement>(null);
  const [adding, setAdding] = useState(false);

  async function onImport(file: File, path: string, ref: React.RefObject<HTMLInputElement | null>) {
    const fd = new FormData();
    fd.append("file", file);
    try {
      const r = await api<{ created: number; updated: number; errors: string[] }>(path, { method: "POST", body: fd });
      toast.success(`Imported: ${r.created} created, ${r.updated} updated`,
                    r.errors.length ? { description: r.errors.slice(0, 3).join("; ") } : undefined);
      people.reload();
      meta.reload();
    } catch (e) {
      toast.error((e as Error).message);
    } finally {
      if (ref.current) ref.current.value = "";
    }
  }

  const list = people.data ?? [];

  return (
    <div className="space-y-8">
      <PageHeader
        eyebrow="Workforce"
        title="People"
        description={meta.data ? <><CountUp value={meta.data.total} /> people · <CountUp value={meta.data.hard_excluded} /> protected from selection</> : " "}
        actions={
          <>
            {can("hr", "finance") && (
              <>
                <input ref={payrollRef} type="file" accept=".csv" className="hidden"
                       onChange={(e) => e.target.files?.[0] && onImport(e.target.files[0], "/employees/payroll/import", payrollRef)} />
                <Button variant="outline" className="gap-2 rounded-xl" onClick={() => payrollRef.current?.click()}>
                  <Upload className="size-4" />Payroll CSV
                </Button>
              </>
            )}
            {canEdit && (
              <>
                <input ref={fileRef} type="file" accept=".csv" className="hidden"
                       onChange={(e) => e.target.files?.[0] && onImport(e.target.files[0], "/employees/import", fileRef)} />
                <Button variant="outline" className="gap-2 rounded-xl" onClick={() => fileRef.current?.click()}>
                  <Upload className="size-4" />People CSV
                </Button>
                <Button className="gap-2 rounded-xl" onClick={() => setAdding(true)}><UserPlus className="size-4" />Add</Button>
              </>
            )}
          </>
        }
      />

      <Panel bodyClassName="p-0">
        <div className="flex flex-wrap items-center gap-2 border-b p-4">
          <div className="relative">
            <Search className="absolute top-1/2 left-3 size-4 -translate-y-1/2 text-muted-foreground" />
            <Input className="h-9 w-64 rounded-xl pl-9" placeholder="Search name or ID" value={q} onChange={(e) => setQ(e.target.value)} />
          </div>
          <select className="h-9 rounded-xl border bg-background/50 px-3 text-sm" value={dept} onChange={(e) => setDept(e.target.value)}
                  aria-label="Department">
            <option value="">All departments</option>
            {meta.data?.departments.map((d) => <option key={d}>{d}</option>)}
          </select>
          <select className="h-9 rounded-xl border bg-background/50 px-3 text-sm" value={status} onChange={(e) => setStatus(e.target.value)}
                  aria-label="Status">
            <option value="">Any status</option>
            {Object.entries(STATUS_LABEL).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
          </select>
          <span className="ml-auto text-xs text-muted-foreground">{list.length} shown</span>
        </div>
        <ErrorText error={people.error} />
        <div className="max-h-[70vh] overflow-auto">
          <table className={t.table}>
            <thead className={`${t.thead} sticky top-0 z-10 bg-background/90 backdrop-blur`}>
              <tr className="border-b">
                <th className={t.th}>Person</th>
                <th className={t.th}>Department</th>
                <th className={t.th}>Type</th>
                <th className={`${t.th} text-right`}>CTC</th>
                <th className={t.th}>Performance</th>
                <th className={t.th}>Skills</th>
                <th className={t.th}>Status</th>
                <th className={t.th}>Protection</th>
              </tr>
            </thead>
            <tbody>
              {list.map((e) => (
                <tr key={e.id} className={t.tr}>
                  <td className={t.td}>
                    <Link href={`/people/${e.employee_code}`} className="flex items-center gap-3 hover:text-primary">
                      <Avatar name={e.full_name} />
                      <div>
                        <div className="font-medium">{e.full_name}</div>
                        <div className="text-xs text-muted-foreground">{e.employee_code}</div>
                      </div>
                    </Link>
                  </td>
                  <td className={t.td}>{e.department}<div className="text-xs text-muted-foreground">{e.role}</div></td>
                  <td className={`${t.td} capitalize`}>{e.employment_type.replace("_", " ")}</td>
                  <td className={`${t.td} text-right tabular-nums`}>{e.annual_ctc_paise === null ? <span className="text-muted-foreground">masked</span> : fmtPaise(e.annual_ctc_paise)}</td>
                  <td className={t.td}><Rating value={e.performance_rating} /></td>
                  <td className={t.td}><Rating value={e.critical_skill_score} /></td>
                  <td className={t.td}><span className="text-xs">{STATUS_LABEL[e.status] ?? e.status}</span></td>
                  <td className={t.td}>
                    {e.exclusion_reason && (
                      <span className="inline-flex items-center gap-1.5 text-xs whitespace-nowrap">
                        <ShieldCheck className="size-3.5 text-[var(--status-good)]" aria-hidden="true" />{e.exclusion_reason}
                      </span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {!people.loading && list.length === 0 && <EmptyState icon={Search} title="No one matches" />}
        </div>
        <p className="border-t px-4 py-3 text-xs text-muted-foreground">
          People CSV: employee_code, full_name, department, role, location, hire_date, annual_ctc (₹), performance_rating,
          potential_rating, critical_skill_score, gender, age_band; optional email, personal_email, manager_code,
          employment_type, confirmation_date, contract_end_date, contract_notice_days, leave_status, protected_flag and
          kpi_&lt;name&gt; metrics. Payroll CSV: employee_code, period (YYYY-MM), basic, da, hra, special (₹ per month) and FNF
          inputs such as leave_encashable_days, reimbursements_approved, loans_outstanding, tds.
        </p>
      </Panel>

      <Dialog open={adding} onOpenChange={setAdding}>
        <DialogContent className="max-h-[90vh] overflow-y-auto rounded-2xl sm:max-w-2xl">
          <DialogHeader><DialogTitle>Add employee</DialogTitle></DialogHeader>
          {adding && (
            <EmployeeForm metricNames={meta.data?.metrics ?? []} onCancel={() => setAdding(false)}
                          onSubmit={async (v) => {
                            await post("/employees", v);
                            toast.success("Employee added");
                            setAdding(false);
                            people.reload();
                            meta.reload();
                          }} />
          )}
        </DialogContent>
      </Dialog>
    </div>
  );
}
