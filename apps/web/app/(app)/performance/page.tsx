"use client";

import { CalendarRange, CircleCheck, CircleDashed, FileWarning, Hourglass, Plus, TriangleAlert } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { ErrorText, tableCls as t } from "@/components/common";
import { BarList } from "@/components/charts";
import { CountUp, EmptyState, PageHeader, Panel, Pill, StatTile } from "@/components/kit";
import { useAuth } from "@/components/auth";
import { Field, FormDialog, Select, humanize } from "@/components/form-bits";
import { CYCLE_STATUS, NewPipDialog, OUTCOME, PIP_STATUS, type Cycle, type Pip } from "@/components/pip-card";
import { useQuery } from "@/lib/use-query";
import { fmtDay, post } from "@/lib/api";

type Overview = {
  pips: { proposed: number; active: number; ending_soon: number; overdue: number; closed_not_met: number };
  pipeline: Pip[];
  cycles: Cycle[];
  missing_evidence: number | null;
  rating_distribution: Record<string, number>;
};
type Missing = { employee_id: number; employee_code: string; full_name: string; department: string;
  performance_rating: number; missing: string };

export default function PerformancePage() {
  const { can } = useAuth();
  const q = useQuery<Overview>("/performance/overview");
  const missing = useQuery<Missing[]>(can("hr", "legal") ? "/performance/missing-evidence" : null);
  const [cycleOpen, setCycleOpen] = useState(false);
  const [pipOpen, setPipOpen] = useState(false);
  const [cycle, setCycle] = useState({ name: "", period_start: "", period_end: "", scale_max: "5" });
  const d = q.data;
  const now = new Date().toISOString().slice(0, 10);

  async function activate(p: Pip) {
    try {
      await post(`/performance/pips/${p.id}/activate`);
      toast.success(`PIP for ${p.employee_code} started`);
      q.reload();
    } catch (e) {
      toast.error((e as Error).message);
    }
  }

  return (
    <div className="space-y-8">
      <PageHeader eyebrow="Decide" title="Performance"
                  description="Reviews, calibration, goals, check-ins and PIPs. Documented evidence here is what a performance-based exit has to stand on."
                  actions={
                    <>
                      {can("hr", "legal", "manager") && (
                        <Button variant="outline" className="gap-2 rounded-xl" onClick={() => setPipOpen(true)}>
                          <FileWarning className="size-4" />{can("hr", "legal") ? "Start a PIP" : "Propose a PIP"}
                        </Button>
                      )}
                      {can("hr") && <Button className="gap-2 rounded-xl" onClick={() => setCycleOpen(true)}><Plus className="size-4" />New review cycle</Button>}
                    </>
                  } />
      <ErrorText error={q.error} />

      <div className="stagger grid grid-cols-2 gap-4 lg:grid-cols-5">
        <StatTile label="Active PIPs" icon={Hourglass} value={<CountUp value={d?.pips.active ?? 0} />} />
        <StatTile label="Ending in 14 days" icon={CalendarRange} value={<CountUp value={d?.pips.ending_soon ?? 0} />} />
        <StatTile label="Past end date" icon={TriangleAlert} accent={(d?.pips.overdue ?? 0) > 0}
                  value={<CountUp value={d?.pips.overdue ?? 0} />} hint="Need a final review" />
        <StatTile label="Proposed by managers" icon={CircleDashed} value={<CountUp value={d?.pips.proposed ?? 0} />} />
        <StatTile label="Missing evidence" icon={FileWarning} accent={(d?.missing_evidence ?? 0) > 0}
                  value={d?.missing_evidence === null ? "–" : <CountUp value={d?.missing_evidence ?? 0} />}
                  hint="Low ratings without documentation" />
      </div>

      <div className="grid gap-6 xl:grid-cols-[1.5fr_1fr]">
        <Panel title="PIPs" description="Open PIPs and those closed in the last 90 days." bodyClassName="p-0">
          {d && d.pipeline.length === 0 ? <EmptyState icon={FileWarning} title="No PIPs" /> : (
            <div className="max-h-[480px] overflow-auto">
              <table className={t.table}>
                <thead className={`${t.thead} sticky top-0 bg-background/90 backdrop-blur`}>
                  <tr className="border-b"><th className={t.th}>Person</th><th className={t.th}>Reason</th><th className={t.th}>Period</th>
                    <th className={t.th}>Status</th><th className={t.th}>Employee signed</th><th className={t.th} /></tr>
                </thead>
                <tbody>
                  {d?.pipeline.map((p) => (
                    <tr key={p.id} className={t.tr}>
                      <td className={t.td}>
                        <Link href={`/people/${p.employee_code}?tab=pips`} className="hover:text-primary">
                          <div className="font-medium">{p.full_name}</div>
                          <div className="text-xs text-muted-foreground">{p.employee_code} · {p.department}</div>
                        </Link>
                      </td>
                      <td className={t.td}>{humanize(p.reason_category)}</td>
                      <td className={`${t.td} whitespace-nowrap text-xs`}>
                        {fmtDay(p.start_date)} → <span className={p.status === "active" && p.end_date < now ? "font-medium text-[var(--status-critical)]" : ""}>{fmtDay(p.end_date)}</span>
                      </td>
                      <td className={t.td}><Pill spec={p.outcome ? OUTCOME[p.outcome] : PIP_STATUS[p.status]} /></td>
                      <td className={`${t.td} text-xs`}>{humanize(p.employee_ack)}</td>
                      <td className={`${t.td} text-right`}>
                        {p.status === "proposed" && can("hr", "legal")
                          ? <Button size="sm" onClick={() => activate(p)}>Start</Button>
                          : <Link href={`/people/${p.employee_code}?tab=pips`} className="text-xs text-muted-foreground hover:text-foreground">Open</Link>}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Panel>

        <div className="space-y-6">
          <Panel title="Review cycles">
            {d && d.cycles.length === 0 ? <p className="text-sm text-muted-foreground">No cycles yet.</p> : (
              <ul className="divide-y">
                {d?.cycles.map((c) => (
                  <li key={c.id}>
                    <Link href={`/performance/cycles/${c.id}`} className="flex items-center gap-3 py-2.5 text-sm hover:text-primary">
                      <span className="flex-1">
                        <span className="font-medium">{c.name}</span>
                        <span className="block text-xs text-muted-foreground">{fmtDay(c.period_start)} – {fmtDay(c.period_end)} · 1–{c.scale_max}</span>
                      </span>
                      <Pill spec={CYCLE_STATUS[c.status]} />
                    </Link>
                  </li>
                ))}
              </ul>
            )}
          </Panel>
          <Panel title="Current performance ratings" description="Rounded to the nearest point, people you can see.">
            {d && (
              <BarList items={["5", "4", "3", "2", "1"].map((k) => ({ label: `Rating ${k}`, value: d.rating_distribution[k] ?? 0 }))} />
            )}
          </Panel>
        </div>
      </div>

      {can("hr", "legal") && (
        <Panel title="Missing evidence" description="People rated 2 or below with no PIP and no documented review in the latest closed cycle. A performance-based reason can't rest on an undocumented rating."
               bodyClassName="p-0">
          <ErrorText error={missing.error} />
          {missing.data && missing.data.length === 0 ? <EmptyState icon={CircleCheck} title="Everyone rated low has documentation" /> : (
            <table className={t.table}>
              <thead className={t.thead}><tr className="border-b"><th className={t.th}>Person</th><th className={t.th}>Department</th>
                <th className={t.th}>Rating</th><th className={t.th}>What&apos;s missing</th></tr></thead>
              <tbody>
                {missing.data?.map((m) => (
                  <tr key={m.employee_id} className={t.tr}>
                    <td className={t.td}><Link className="hover:text-primary" href={`/people/${m.employee_code}?tab=performance`}>
                      {m.full_name}<span className="ml-2 text-xs text-muted-foreground">{m.employee_code}</span></Link></td>
                    <td className={t.td}>{m.department}</td>
                    <td className={`${t.td} tabular-nums`}>{m.performance_rating.toFixed(1)}</td>
                    <td className={`${t.td} text-muted-foreground`}>{m.missing}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </Panel>
      )}

      <NewPipDialog open={pipOpen} onOpenChange={setPipOpen} onDone={q.reload} />
      <FormDialog open={cycleOpen} onOpenChange={setCycleOpen} title="New review cycle" submitLabel="Create cycle"
                  description="When the cycle closes, calibrated ratings become each person's current performance rating (newest cycle only)."
                  onSubmit={async () => {
                    await post("/performance/cycles", { ...cycle, scale_max: Number(cycle.scale_max) });
                    toast.success("Cycle created");
                    setCycle({ name: "", period_start: "", period_end: "", scale_max: "5" });
                    q.reload();
                  }}>
        <Field label="Name" htmlFor="cy-n"><Input id="cy-n" required value={cycle.name} placeholder="H2 2026" onChange={(e) => setCycle({ ...cycle, name: e.target.value })} /></Field>
        <div className="grid grid-cols-3 gap-3">
          <Field label="Starts" htmlFor="cy-s"><Input id="cy-s" type="date" required value={cycle.period_start} onChange={(e) => setCycle({ ...cycle, period_start: e.target.value })} /></Field>
          <Field label="Ends" htmlFor="cy-e"><Input id="cy-e" type="date" required value={cycle.period_end} onChange={(e) => setCycle({ ...cycle, period_end: e.target.value })} /></Field>
          <Field label="Scale" htmlFor="cy-m"><Select id="cy-m" value={cycle.scale_max} onChange={(v) => setCycle({ ...cycle, scale_max: v })}
                                                       options={[["5", "1–5"], ["4", "1–4"], ["10", "1–10"]]} /></Field>
        </div>
      </FormDialog>
    </div>
  );
}
