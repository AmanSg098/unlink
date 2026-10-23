"use client";

import { ArrowLeft, Lock, Scale, Search, TriangleAlert } from "lucide-react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { Suspense, useState } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { ErrorText, tableCls as t } from "@/components/common";
import { EmptyState, PageHeader, Panel, Pill } from "@/components/kit";
import { useAuth } from "@/components/auth";
import { Field, FormDialog } from "@/components/form-bits";
import { CYCLE_STATUS, type Cycle } from "@/components/pip-card";
import { useQuery } from "@/lib/use-query";
import { fmtDay, post, put } from "@/lib/api";
import { cn } from "@/lib/utils";

type Review = { id: number; self_rating: number | null; self_comment: string | null; manager_rating: number | null;
  manager_comment: string | null; peer_input: string | null; calibrated_rating: number | null; calibrated_by: string | null };
type Row = { employee_id: number; employee_code: string; full_name: string; department: string; role: string;
  review: Review | null };
type DeptStat = { count: number; mean: number; stdev: number; distribution: Record<string, number> };
type Outlier = { review_id: number; employee_id: number; employee_code: string; department: string;
  manager_rating: number; calibrated_rating: number | null; why: string };
type CycleDetail = { cycle: Cycle; rows: Row[];
  calibration: { departments: Record<string, DeptStat>; outliers: Outlier[] } | null };

export default function CyclePage() {
  return <Suspense><CycleView /></Suspense>;
}

function CycleView() {
  const { id } = useParams<{ id: string }>();
  const { can } = useAuth();
  const q = useQuery<CycleDetail>(`/performance/cycles/${id}`);
  const [search, setSearch] = useState("");
  const [onlyOpen, setOnlyOpen] = useState(false);
  const [editing, setEditing] = useState<Row | null>(null);
  const [form, setForm] = useState({ self_rating: "", self_comment: "", manager_rating: "", manager_comment: "", peer_input: "" });
  const [calibrating, setCalibrating] = useState<{ reviewId: number; label: string; manager: number | null } | null>(null);
  const [calibrated, setCalibrated] = useState("");
  const [closing, setClosing] = useState(false);
  const d = q.data;

  if (q.error && !d) return <ErrorText error={q.error} />;
  if (!d) return <div className="h-40 animate-pulse rounded-2xl bg-muted/40" />;

  const c = d.cycle;
  const closed = c.status === "closed";
  const outlierIds = new Set(d.calibration?.outliers.map((o) => o.review_id));
  const reviewed = d.rows.filter((r) => r.review);
  const uncalibrated = reviewed.filter((r) => r.review!.calibrated_rating === null).length;
  const rows = d.rows.filter((r) => (!search || `${r.full_name} ${r.employee_code} ${r.department}`.toLowerCase().includes(search.toLowerCase()))
    && (!onlyOpen || (r.review !== null && r.review.calibrated_rating === null)));

  const openEdit = (r: Row) => {
    const v = r.review;
    setForm({ self_rating: v?.self_rating?.toString() ?? "", self_comment: v?.self_comment ?? "",
              manager_rating: v?.manager_rating?.toString() ?? "", manager_comment: v?.manager_comment ?? "",
              peer_input: v?.peer_input ?? "" });
    setEditing(r);
  };
  const openCalibrate = (reviewId: number, label: string, manager: number | null, current: number | null) => {
    setCalibrated(String(current ?? manager ?? ""));
    setCalibrating({ reviewId, label, manager });
  };
  const num = (s: string) => (s === "" ? null : Number(s));

  return (
    <div className="space-y-6">
      <Link href="/performance" className="inline-flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground">
        <ArrowLeft className="size-4" />Performance
      </Link>
      <PageHeader eyebrow="Review cycle" title={<span className="flex items-center gap-3">{c.name}<Pill spec={CYCLE_STATUS[c.status]} /></span>}
                  description={<>{fmtDay(c.period_start)} – {fmtDay(c.period_end)} · scale 1–{c.scale_max} · {reviewed.length} of {d.rows.length} reviewed · {uncalibrated} not yet calibrated</>}
                  actions={can("hr") && !closed && (
                    <Button className="gap-2 rounded-xl" onClick={() => setClosing(true)}><Lock className="size-4" />Close cycle</Button>
                  )} />

      {d.calibration && (
        <div className="grid gap-6 xl:grid-cols-[1.2fr_1fr]">
          <Panel title="Calibration by department" description="Manager ratings. Spread and mean help spot lenient or harsh rating." bodyClassName="p-0">
            <table className={t.table}>
              <thead className={t.thead}><tr className="border-b"><th className={t.th}>Department</th><th className={`${t.th} text-right`}>Reviews</th>
                <th className={`${t.th} text-right`}>Mean</th><th className={`${t.th} text-right`}>Std dev</th><th className={t.th}>Distribution (1 → {c.scale_max})</th></tr></thead>
              <tbody>
                {Object.entries(d.calibration.departments).sort().map(([dept, s]) => {
                  const max = Math.max(1, ...Object.values(s.distribution));
                  return (
                    <tr key={dept} className={t.tr}>
                      <td className={t.td}>{dept}</td>
                      <td className={`${t.td} text-right tabular-nums`}>{s.count}</td>
                      <td className={`${t.td} text-right tabular-nums`}>{s.mean.toFixed(2)}</td>
                      <td className={`${t.td} text-right tabular-nums`}>{s.stdev.toFixed(2)}</td>
                      <td className={t.td}>
                        <div className="flex h-6 items-end gap-0.5" title={Object.entries(s.distribution).map(([k, v]) => `${k}: ${v}`).join(" · ")}>
                          {Object.entries(s.distribution).map(([k, v]) => (
                            <span key={k} className="w-3 rounded-t-[3px] bg-[var(--series-1)]" style={{ height: `${Math.max(2, (v / max) * 24)}px`, opacity: v ? 1 : 0.25 }} />
                          ))}
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
            {Object.keys(d.calibration.departments).length === 0 && <EmptyState icon={Scale} title="No manager ratings yet" />}
          </Panel>

          <Panel title={`Outliers (${d.calibration.outliers.length})`}
                 description="More than 1.5 standard deviations from the department mean, or calibrated far from the manager's rating.">
            {d.calibration.outliers.length === 0 ? <p className="text-sm text-muted-foreground">None.</p> : (
              <ul className="max-h-80 divide-y overflow-auto">
                {d.calibration.outliers.map((o) => (
                  <li key={o.review_id} className="flex items-center gap-3 py-2 text-sm">
                    <TriangleAlert className="size-4 shrink-0 text-[var(--status-warning)]" aria-hidden="true" />
                    <span className="flex-1">
                      <Link className="font-mono text-xs hover:text-primary" href={`/people/${o.employee_code}?tab=performance`}>{o.employee_code}</Link>
                      <span className="ml-2 text-xs text-muted-foreground">{o.department} · {o.why}</span>
                    </span>
                    <span className="text-xs tabular-nums">{o.manager_rating}{o.calibrated_rating !== null && ` → ${o.calibrated_rating}`}</span>
                    {can("hr") && !closed && (
                      <Button size="xs" variant="outline" onClick={() => openCalibrate(o.review_id, o.employee_code, o.manager_rating, o.calibrated_rating)}>Calibrate</Button>
                    )}
                  </li>
                ))}
              </ul>
            )}
          </Panel>
        </div>
      )}

      <Panel bodyClassName="p-0">
        <div className="flex flex-wrap items-center gap-3 border-b p-4">
          <div className="relative">
            <Search className="absolute top-1/2 left-3 size-4 -translate-y-1/2 text-muted-foreground" />
            <Input className="h-9 w-64 rounded-xl pl-9" placeholder="Search name, ID or department" value={search}
                   onChange={(e) => setSearch(e.target.value)} />
          </div>
          <label className="flex items-center gap-2 text-sm">
            <input type="checkbox" checked={onlyOpen} onChange={(e) => setOnlyOpen(e.target.checked)} />Only reviews awaiting calibration
          </label>
          <span className="ml-auto text-xs text-muted-foreground">{rows.length} shown</span>
        </div>
        <div className="max-h-[65vh] overflow-auto">
          <table className={t.table}>
            <thead className={`${t.thead} sticky top-0 z-10 bg-background/90 backdrop-blur`}>
              <tr className="border-b"><th className={t.th}>Person</th><th className={t.th}>Department</th>
                <th className={`${t.th} text-right`}>Self</th><th className={`${t.th} text-right`}>Manager</th>
                <th className={`${t.th} text-right`}>Calibrated</th><th className={t.th}>Documented</th><th className={t.th} /></tr>
            </thead>
            <tbody>
              {rows.map((r) => {
                const v = r.review;
                return (
                  <tr key={r.employee_id} className={cn(t.tr, v && outlierIds.has(v.id) && "bg-[color-mix(in_oklab,var(--status-warning)_6%,transparent)]")}>
                    <td className={t.td}>
                      <Link href={`/people/${r.employee_code}?tab=performance`} className="hover:text-primary">
                        <div className="font-medium">{r.full_name}</div>
                        <div className="text-xs text-muted-foreground">{r.employee_code}</div>
                      </Link>
                    </td>
                    <td className={t.td}>{r.department}<div className="text-xs text-muted-foreground">{r.role}</div></td>
                    <td className={`${t.td} text-right tabular-nums`}>{v?.self_rating ?? "–"}</td>
                    <td className={`${t.td} text-right tabular-nums`}>{v?.manager_rating ?? "–"}</td>
                    <td className={`${t.td} text-right font-medium tabular-nums`}>{v?.calibrated_rating ?? "–"}</td>
                    <td className={`${t.td} text-xs`}>{v?.manager_comment ? "Yes" : <span className="text-muted-foreground">No comment</span>}</td>
                    <td className={`${t.td} text-right whitespace-nowrap`}>
                      {!closed && can("hr", "manager") && <Button size="xs" variant="ghost" onClick={() => openEdit(r)}>{v ? "Edit" : "Review"}</Button>}
                      {!closed && can("hr") && v && (
                        <Button size="xs" variant="outline" onClick={() => openCalibrate(v.id, r.employee_code, v.manager_rating, v.calibrated_rating)}>Calibrate</Button>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </Panel>

      <FormDialog open={!!editing} onOpenChange={(o) => !o && setEditing(null)} wide
                  title={`Review: ${editing?.full_name ?? ""}`} description={`Ratings on a 1–${c.scale_max} scale. Every change is audited.`}
                  onSubmit={async () => {
                    await put(`/performance/cycles/${c.id}/reviews`, {
                      employee_id: editing!.employee_id, self_rating: num(form.self_rating), self_comment: form.self_comment || null,
                      manager_rating: num(form.manager_rating), manager_comment: form.manager_comment || null,
                      peer_input: form.peer_input || null,
                    });
                    toast.success("Review saved");
                    q.reload();
                  }}>
        <div className="grid grid-cols-2 gap-3">
          <Field label="Self rating" htmlFor="r-self"><Input id="r-self" type="number" min={1} max={c.scale_max} step={0.5} value={form.self_rating} onChange={(e) => setForm({ ...form, self_rating: e.target.value })} /></Field>
          <Field label="Manager rating" htmlFor="r-mgr"><Input id="r-mgr" type="number" min={1} max={c.scale_max} step={0.5} value={form.manager_rating} onChange={(e) => setForm({ ...form, manager_rating: e.target.value })} /></Field>
        </div>
        <Field label="Self assessment" htmlFor="r-sc"><Textarea id="r-sc" rows={2} value={form.self_comment} onChange={(e) => setForm({ ...form, self_comment: e.target.value })} /></Field>
        <Field label="Manager comment" htmlFor="r-mc" hint="A rating without a documented comment won't support a performance-based reason.">
          <Textarea id="r-mc" rows={3} value={form.manager_comment} onChange={(e) => setForm({ ...form, manager_comment: e.target.value })} />
        </Field>
        <Field label="Peer input" htmlFor="r-pi"><Textarea id="r-pi" rows={2} value={form.peer_input} onChange={(e) => setForm({ ...form, peer_input: e.target.value })} /></Field>
      </FormDialog>

      <FormDialog open={!!calibrating} onOpenChange={(o) => !o && setCalibrating(null)} title={`Calibrate ${calibrating?.label ?? ""}`}
                  description={`Manager rating: ${calibrating?.manager ?? "none"}. The calibrated rating becomes the current performance rating when this cycle closes.`}
                  onSubmit={async () => {
                    await post(`/performance/reviews/${calibrating!.reviewId}/calibrate`, { calibrated_rating: Number(calibrated) });
                    toast.success("Calibrated");
                    q.reload();
                  }}>
        <Field label="Calibrated rating" htmlFor="cal"><Input id="cal" type="number" required min={1} max={c.scale_max} step={0.5}
                                                             value={calibrated} onChange={(e) => setCalibrated(e.target.value)} /></Field>
      </FormDialog>

      <FormDialog open={closing} onOpenChange={setClosing} title="Close this cycle?" submitLabel="Close cycle"
                  description={uncalibrated ? `${uncalibrated} reviews still need a calibrated rating; the cycle can't close until they have one.`
                                            : "Calibrated ratings become current performance ratings (if this is the newest closed cycle). This can't be reopened."}
                  onSubmit={async () => {
                    const r = await post<{ ratings_updated: number }>(`/performance/cycles/${c.id}/close`);
                    toast.success(`Cycle closed · ${r.ratings_updated} ratings updated`);
                    q.reload();
                  }} />
    </div>
  );
}
