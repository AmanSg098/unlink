"use client";

import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { ErrorText } from "@/components/common";
import type { Employee } from "@/lib/api";

export type EmployeeInput = {
  employee_code: string; full_name: string; email: string | null; personal_email: string | null; department: string;
  role: string; location: string; manager_code: string | null; hire_date: string; employment_type: string;
  contract_end_date: string | null; contract_notice_days: number; annual_ctc_paise: number;
  performance_rating: number; potential_rating: number; critical_skill_score: number; gender: string;
  age_band: string; leave_status: string; protected_flag: boolean; legal_hold: boolean;
  custom_metrics: Record<string, number>;
};

const EMPTY: EmployeeInput = {
  employee_code: "", full_name: "", email: null, personal_email: null, department: "", role: "", location: "",
  manager_code: null, hire_date: "", employment_type: "permanent", contract_end_date: null, contract_notice_days: 30,
  annual_ctc_paise: 0, performance_rating: 3, potential_rating: 3, critical_skill_score: 3, gender: "",
  age_band: "30-39", leave_status: "none", protected_flag: false, legal_hold: false, custom_metrics: {},
};

function fromEmployee(e: Employee): EmployeeInput {
  return {
    employee_code: e.employee_code, full_name: e.full_name, email: e.email, personal_email: e.personal_email,
    department: e.department, role: e.role, location: e.location, manager_code: e.manager_code, hire_date: e.hire_date,
    employment_type: e.employment_type, contract_end_date: e.contract_end_date,
    contract_notice_days: e.contract_notice_days ?? 30, annual_ctc_paise: e.annual_ctc_paise ?? 0,
    performance_rating: e.performance_rating, potential_rating: e.potential_rating,
    critical_skill_score: e.critical_skill_score, gender: e.gender ?? "", age_band: e.age_band ?? "30-39",
    leave_status: e.leave_status ?? "none", protected_flag: !!e.protected_flag, legal_hold: !!e.legal_hold,
    custom_metrics: e.custom_metrics ?? {},
  };
}

type Props = {
  initial?: Employee;
  metricNames: string[];
  onSubmit: (v: EmployeeInput) => Promise<void>;
  onCancel: () => void;
};

export function EmployeeForm({ initial, metricNames, onSubmit, onCancel }: Props) {
  const [v, setV] = useState<EmployeeInput>(initial ? fromEmployee(initial) : EMPTY);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const set = <K extends keyof EmployeeInput>(k: K, val: EmployeeInput[K]) => setV((p) => ({ ...p, [k]: val }));
  const metrics = Array.from(new Set([...metricNames, ...Object.keys(v.custom_metrics)])).sort();

  const text = (k: keyof EmployeeInput, label: string, type = "text", required = true) => (
    <div className="space-y-1">
      <Label htmlFor={k}>{label}</Label>
      <Input id={k} type={type} required={required} value={String(v[k] ?? "")} disabled={k === "employee_code" && !!initial}
             onChange={(e) => set(k, (e.target.value === "" && !required ? null : e.target.value) as never)} />
    </div>
  );
  const rating = (k: "performance_rating" | "potential_rating" | "critical_skill_score", label: string) => (
    <div className="space-y-1">
      <Label htmlFor={k}>{label}</Label>
      <Input id={k} type="number" min={1} max={5} step={0.1} required value={v[k]} onChange={(e) => set(k, Number(e.target.value))} />
    </div>
  );
  const select = (k: "employment_type" | "age_band" | "leave_status", label: string, options: [string, string][]) => (
    <div className="space-y-1">
      <Label htmlFor={k}>{label}</Label>
      <select id={k} className="h-8 w-full rounded-md border bg-background px-2 text-sm" value={v[k]}
              onChange={(e) => set(k, e.target.value)}>
        {options.map(([val, lab]) => <option key={val} value={val}>{lab}</option>)}
      </select>
    </div>
  );

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await onSubmit(v);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <form onSubmit={submit} className="space-y-5">
      <div className="grid gap-3 sm:grid-cols-2">
        {text("employee_code", "Employee ID")}
        {text("full_name", "Full name")}
        {text("email", "Work email", "email", false)}
        {text("personal_email", "Personal email (exit communications)", "email", false)}
        {text("department", "Department")}
        {text("role", "Role")}
        {text("location", "Location")}
        {text("manager_code", "Manager's employee ID", "text", false)}
        {text("hire_date", "Hire date", "date")}
        {select("employment_type", "Employment type", [["permanent", "Permanent"], ["fixed_term", "Fixed term"],
                                                       ["contract", "Contract"], ["intern", "Intern"]])}
        {(v.employment_type === "fixed_term" || v.employment_type === "contract") && text("contract_end_date", "Contract end date", "date", false)}
        <div className="space-y-1">
          <Label htmlFor="notice">Contract notice (days)</Label>
          <Input id="notice" type="number" min={0} max={365} value={v.contract_notice_days}
                 onChange={(e) => set("contract_notice_days", Number(e.target.value))} />
        </div>
        <div className="space-y-1">
          <Label htmlFor="ctc">Annual CTC (₹)</Label>
          <Input id="ctc" type="number" min={0} step={1000} required value={v.annual_ctc_paise / 100}
                 onChange={(e) => set("annual_ctc_paise", Math.round(Number(e.target.value) * 100))} />
        </div>
        {rating("performance_rating", "Performance (1-5)")}
        {rating("potential_rating", "Potential (1-5)")}
        {rating("critical_skill_score", "Critical skills (1-5)")}
        {text("gender", "Gender (fairness analysis only)")}
        {select("age_band", "Age band (fairness analysis only)", [["<30", "<30"], ["30-39", "30-39"], ["40-49", "40-49"], ["50+", "50+"]])}
        {select("leave_status", "Leave status", [["none", "None"], ["maternity", "Maternity (protected)"],
                                                 ["medical", "Medical (protected)"], ["other", "Other"]])}
      </div>
      <div className="flex flex-wrap gap-6 text-sm">
        <label className="flex items-center gap-2">
          <input type="checkbox" checked={v.protected_flag} onChange={(e) => set("protected_flag", e.target.checked)} />
          Protected status (can&apos;t be selected)
        </label>
        <label className="flex items-center gap-2">
          <input type="checkbox" checked={v.legal_hold} onChange={(e) => set("legal_hold", e.target.checked)} />
          Legal hold
        </label>
      </div>
      {metrics.length > 0 && (
        <fieldset className="space-y-2">
          <legend className="text-sm font-medium">Custom metrics</legend>
          <div className="grid gap-3 sm:grid-cols-3">
            {metrics.map((m) => (
              <div key={m} className="space-y-1">
                <Label htmlFor={`m-${m}`}>{m}</Label>
                <Input id={`m-${m}`} type="number" step="any" placeholder="blank = not applicable"
                       value={v.custom_metrics[m] ?? ""}
                       onChange={(e) => {
                         const next = { ...v.custom_metrics };
                         if (e.target.value === "") delete next[m];
                         else next[m] = Number(e.target.value);
                         set("custom_metrics", next);
                       }} />
              </div>
            ))}
          </div>
        </fieldset>
      )}
      <ErrorText error={error} />
      <div className="flex gap-2">
        <Button type="submit" disabled={busy}>{busy ? "Saving…" : initial ? "Save changes" : "Add employee"}</Button>
        <Button type="button" variant="outline" onClick={onCancel}>Cancel</Button>
      </div>
    </form>
  );
}
