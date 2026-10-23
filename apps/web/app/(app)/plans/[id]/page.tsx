"use client";

import {
  CircleCheck, CopyPlus, Download, FileText, Pencil, Play, Send, ShieldCheck, Target, TriangleAlert, UsersRound, Wallet,
} from "lucide-react";
import { useParams, useRouter } from "next/navigation";
import { Suspense, useState } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Label } from "@/components/ui/label";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Textarea } from "@/components/ui/textarea";
import { ErrorText, fmtDate } from "@/components/common";
import { CountUp, PageHeader, Panel, StatTile, StatusStepper, relTime } from "@/components/kit";
import { WeightMix, useFactorColors } from "@/components/charts";
import { PlanForm } from "@/components/plan-form";
import { AiTab, ApprovalsTab, AuditTab, CasesTab, ComplianceTab, FairnessTab, RankingTab } from "@/components/plan-tabs";
import { useAuth } from "@/components/auth";
import { useQuery } from "@/lib/use-query";
import {
  errorDetail, fmtPaise, patch, post, type ComplianceCheck, type Fairness, type Plan, type Results,
} from "@/lib/api";

const METHOD_LABEL: Record<Plan["selection_method"], string> = {
  score_ranked: "Score-ranked", role_redundancy: "Role redundancy", manual_list: "Manual list",
};

async function download(path: string, filename: string) {
  const res = await fetch(`/api${path}`, { credentials: "same-origin" });
  if (!res.ok) throw new Error(errorDetail(await res.json().catch(() => null)));
  const url = URL.createObjectURL(await res.blob());
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

function DecisionDialog({ plan, fairness, open, onClose, onDone }: {
  plan: Plan; fairness: Fairness | undefined; open: boolean; onClose: () => void; onDone: () => void;
}) {
  const [comment, setComment] = useState("");
  const [justification, setJustification] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const finalStep = plan.current_step?.step === "final_approval";
  const needsJustification = finalStep && !!fairness?.any_flagged && !plan.fairness_justification;

  async function decide(approve: boolean) {
    setBusy(true);
    setError(null);
    try {
      await post(`/plans/${plan.id}/decision`, {
        approve, comment: comment || null, fairness_justification: needsJustification ? justification : null,
      });
      toast.success(approve ? "Approval recorded" : "Returned to draft");
      setComment("");
      setJustification("");
      onDone();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <Dialog open={open} onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="rounded-2xl sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>{plan.current_step ? plan.current_step.step.replace(/_/g, " ").replace(/^\w/, (c) => c.toUpperCase()) : "Decision"}</DialogTitle>
          <DialogDescription>
            Your decision is bound to the plan as it is now. Any later change to the plan resets the approvals.
            Returning it sends it back to draft.
          </DialogDescription>
        </DialogHeader>
        <div className="space-y-4">
          {needsJustification && (
            <div className="space-y-1.5">
              <Label htmlFor="fj" className="flex items-center gap-1.5">
                <TriangleAlert className="size-3.5 text-[var(--status-critical)]" aria-hidden="true" />
                Fairness justification (required to approve)
              </Label>
              <p className="text-xs text-muted-foreground">{fairness?.flags.join(" · ")}</p>
              <Textarea id="fj" rows={3} value={justification} onChange={(e) => setJustification(e.target.value)} />
            </div>
          )}
          <div className="space-y-1.5">
            <Label htmlFor="comment">Comment {needsJustification ? "" : "(optional)"}</Label>
            <Textarea id="comment" rows={3} value={comment} onChange={(e) => setComment(e.target.value)} />
          </div>
          <ErrorText error={error} />
          <div className="flex flex-wrap gap-2">
            <Button disabled={busy || (needsJustification && justification.trim().length < 10)} onClick={() => decide(true)}
                    className="gap-2"><CircleCheck className="size-4" />Approve</Button>
            <Button variant="outline" disabled={busy || !comment.trim()} onClick={() => decide(false)}
                    title={comment.trim() ? undefined : "Add a comment explaining what needs to change"}>
              Return to draft
            </Button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}

function PlanDetail() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const { me, can } = useAuth();
  const colorOf = useFactorColors();
  const plan = useQuery<Plan>(`/plans/${id}`);
  const results = useQuery<Results>(plan.data?.last_run_at ? `/plans/${id}/results` : null);
  const fairness = useQuery<Fairness>(plan.data?.last_run_at ? `/plans/${id}/fairness` : null);
  const compliance = useQuery<ComplianceCheck[]>(`/plans/${id}/compliance`);
  const [tab, setTab] = useState("overview");
  const [editing, setEditing] = useState(false);
  const [deciding, setDeciding] = useState(false);
  const [busy, setBusy] = useState<string | null>(null);
  const [nonce, setNonce] = useState(0);

  const p = plan.data;
  const reloadAll = () => {
    plan.reload();
    results.reload();
    fairness.reload();
    compliance.reload();
    setNonce((n) => n + 1);
  };

  async function act(kind: string, fn: () => Promise<unknown>, ok: string) {
    setBusy(kind);
    try {
      await fn();
      toast.success(ok);
      reloadAll();
    } catch (e) {
      toast.error((e as Error).message);
    } finally {
      setBusy(null);
    }
  }

  if (!p) {
    return <div className="py-24 text-center text-sm text-muted-foreground">{plan.error ?? "Loading…"}</div>;
  }

  const s = results.data?.summary;
  const isHr = can("hr");
  const draft = p.status === "draft";
  const canDecide = p.status === "submitted" && !!p.current_step && can(...(p.current_step.roles as Parameters<typeof can>))
    && me?.email !== p.submitted_by;
  const labels = Object.fromEntries(Object.entries(p.kpi_snapshot ?? {}).map(([k, v]) => [k, v.label]));
  const blocks = (compliance.data ?? []).filter((c) => c.severity === "block").length;

  return (
    <div className="space-y-8">
      <PageHeader
        eyebrow={<>Reduction plan · v{p.version}{p.parent_plan_id && ` (from #${p.parent_plan_id})`}</>}
        title={p.name}
        description={p.description || undefined}
        actions={
          <>
            {draft && isHr && (
              <>
                <Button variant="outline" className="gap-2 rounded-xl" onClick={() => setEditing(true)}>
                  <Pencil className="size-4" />Edit
                </Button>
                <Button variant="outline" className="gap-2 rounded-xl" disabled={!!busy}
                        onClick={() => act("run", () => post(`/plans/${p.id}/run`), "Plan run; results updated")}>
                  <Play className="size-4" />{busy === "run" ? "Running…" : p.last_run_at ? "Re-run" : "Run"}
                </Button>
                <Button className="gap-2 rounded-xl" disabled={!!busy || !p.last_run_at || !s?.final_selected}
                        onClick={() => act("submit", () => post(`/plans/${p.id}/submit`), "Submitted for approval")}>
                  <Send className="size-4" />Submit for approval
                </Button>
              </>
            )}
            {canDecide && (
              <Button className="gap-2 rounded-xl" onClick={() => setDeciding(true)}>
                <CircleCheck className="size-4" />Review &amp; decide
              </Button>
            )}
            {p.status === "approved" && isHr && (
              <Button variant="outline" className="gap-2 rounded-xl" disabled={!!busy}
                      onClick={async () => {
                        setBusy("version");
                        try {
                          const n = await post<Plan>(`/plans/${p.id}/new-version`);
                          toast.success(`Draft v${n.version} created`);
                          router.push(`/plans/${n.id}`);
                        } catch (e) {
                          toast.error((e as Error).message);
                          setBusy(null);
                        }
                      }}>
                <CopyPlus className="size-4" />New version
              </Button>
            )}
          </>
        }
      />

      <div className="flex flex-wrap items-center gap-4">
        <StatusStepper status={p.status} />
        {p.current_step && (
          <span className="text-xs text-muted-foreground">
            Waiting on {p.current_step.step.replace(/_/g, " ")} ({p.current_step.roles.join(" or ")})
            {me?.email === p.submitted_by && " · you prepared this plan, so you can't approve it"}
          </span>
        )}
      </div>

      <Tabs value={tab} onValueChange={(v) => setTab(String(v))} className="gap-6">
        <div className="overflow-x-auto">
          <TabsList variant="line">
            <TabsTrigger value="overview">Overview</TabsTrigger>
            <TabsTrigger value="ranking">Ranking</TabsTrigger>
            <TabsTrigger value="fairness">
              Fairness{fairness.data?.any_flagged && <TriangleAlert className="size-3.5 text-[var(--status-critical)]" aria-label="flagged" />}
            </TabsTrigger>
            <TabsTrigger value="compliance">Compliance</TabsTrigger>
            <TabsTrigger value="approvals">Approvals</TabsTrigger>
            <TabsTrigger value="cases">Exit cases</TabsTrigger>
            {can("legal") && <TabsTrigger value="audit">Audit</TabsTrigger>}
            <TabsTrigger value="ai">AI drafts</TabsTrigger>
          </TabsList>
        </div>

        <TabsContent value="overview" className="space-y-6">
          <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
            <StatTile label="In scope" icon={UsersRound} value={<CountUp value={s?.pool ?? 0} />}
                      hint={s ? `${s.eligible} eligible` : "Run the plan to see"} />
            <StatTile label="Protected (can't be selected)" icon={ShieldCheck} value={<CountUp value={s?.excluded ?? 0} />} />
            <StatTile label="Proposed" icon={Target} accent={!!s?.final_selected}
                      value={<CountUp value={s?.final_selected ?? 0} />}
                      hint={s ? `${s.algo_selected} by method · ${s.overrides} override${s.overrides === 1 ? "" : "s"}` : undefined} />
            <StatTile label="Annual cost reduction" icon={Wallet}
                      value={s?.annual_cost_reduction_paise != null ? fmtPaise(s.annual_cost_reduction_paise) : "–"}
                      hint={p.target_cost_paise ? `Target ${fmtPaise(p.target_cost_paise)}` : undefined} />
          </div>

          {(blocks > 0 || fairness.data?.any_flagged) && (
            <div className="space-y-2">
              {blocks > 0 && (
                <button type="button" onClick={() => setTab("compliance")}
                        className="flex w-full items-center gap-3 rounded-xl border px-4 py-2.5 text-left text-sm"
                        style={{ borderColor: "color-mix(in oklab, var(--status-critical) 45%, transparent)" }}>
                  <TriangleAlert className="size-4 text-[var(--status-critical)]" aria-hidden="true" />
                  {blocks} compliance check{blocks === 1 ? "" : "s"} block approval
                </button>
              )}
              {fairness.data?.any_flagged && (
                <button type="button" onClick={() => setTab("fairness")}
                        className="flex w-full items-center gap-3 rounded-xl border px-4 py-2.5 text-left text-sm"
                        style={{ borderColor: "color-mix(in oklab, var(--status-warning) 45%, transparent)" }}>
                  <TriangleAlert className="size-4 text-[var(--status-warning)]" aria-hidden="true" />
                  Fairness flags: {fairness.data.flags.length} · final approval needs a justification
                </button>
              )}
            </div>
          )}

          <div className="grid gap-6 lg:grid-cols-2">
            <Panel title="Method">
              <dl className="grid grid-cols-[8rem_1fr] gap-x-4 gap-y-2 text-sm">
                <dt className="text-muted-foreground">Method</dt><dd>{METHOD_LABEL[p.selection_method]}</dd>
                {p.selection_method === "score_ranked" && (
                  <>
                    <dt className="text-muted-foreground">Targets</dt>
                    <dd>{[p.target_count && `${p.target_count} people`, p.target_cost_paise && `${fmtPaise(p.target_cost_paise)} a year`]
                      .filter(Boolean).join(" and ")}</dd>
                  </>
                )}
                {p.selection_method === "role_redundancy" && (
                  <><dt className="text-muted-foreground">Roles eliminated</dt><dd>{p.eliminated_roles.join(", ")}</dd></>
                )}
                {p.selection_method === "manual_list" && (
                  <><dt className="text-muted-foreground">Listed</dt><dd className="font-mono text-xs">{p.manual_codes.join(", ")}</dd></>
                )}
                <dt className="text-muted-foreground">Scope</dt>
                <dd>
                  {[p.filters.departments.join(", "), p.filters.locations.join(", "), p.filters.roles.join(", ")]
                    .filter(Boolean).join(" · ") || "Whole organisation"}
                </dd>
                <dt className="text-muted-foreground">Data as of</dt><dd>{p.as_of_date}</dd>
                <dt className="text-muted-foreground">Last run</dt><dd>{p.last_run_at ? `${relTime(p.last_run_at)} (${fmtDate(p.last_run_at)})` : "Not run"}</dd>
                <dt className="text-muted-foreground">Created</dt><dd>{p.created_by} · {fmtDate(p.created_at)}</dd>
                {p.submitted_by && <><dt className="text-muted-foreground">Submitted</dt><dd>{p.submitted_by} · {fmtDate(p.submitted_at)}</dd></>}
                {p.approved_at && <><dt className="text-muted-foreground">Approved</dt><dd>{fmtDate(p.approved_at)}</dd></>}
              </dl>
            </Panel>
            <Panel title="Scoring weights">
              {Object.values(p.weights ?? {}).some((w) => w > 0) ? (
                <WeightMix weights={p.weights} labels={{ ...labels, ...Object.fromEntries(Object.keys(p.weights).filter((k) => !labels[k]).map((k) => [k, k])) }}
                           colorOf={colorOf} />
              ) : <p className="text-sm text-muted-foreground">This plan doesn&apos;t score the pool.</p>}
              {p.ruleset && (
                <div className="mt-6 border-t pt-4 text-sm">
                  <div className="font-medium">{p.ruleset.title} · {p.ruleset.version}</div>
                  <div className="text-xs text-muted-foreground">
                    {p.ruleset.unverified ? `${p.ruleset.unverified} of ${p.ruleset.total} rules unverified` : "All rules verified"}
                  </div>
                </div>
              )}
            </Panel>
          </div>

          <Panel title="Exports" description="Exports and reports are logged in the audit trail.">
            <div className="flex flex-wrap gap-2">
              <Button variant="outline" className="gap-2 rounded-xl" disabled={!p.last_run_at}
                      onClick={() => download(`/plans/${p.id}/export.csv`, `unlink-plan-${p.id}.csv`).catch((e) => toast.error(e.message))}>
                <Download className="size-4" />Results CSV
              </Button>
              <Button variant="outline" className="gap-2 rounded-xl" disabled={!p.last_run_at}
                      onClick={() => download(`/plans/${p.id}/report.pdf`, `unlink-plan-${p.id}.pdf`).catch((e) => toast.error(e.message))}>
                <FileText className="size-4" />Defensibility pack (internal)
              </Button>
              <Button variant="outline" className="gap-2 rounded-xl" disabled={!p.last_run_at}
                      onClick={() => download(`/plans/${p.id}/report.pdf?external=true`, `unlink-plan-${p.id}-external.pdf`).catch((e) => toast.error(e.message))}>
                <FileText className="size-4" />Defensibility pack (external, no names)
              </Button>
            </div>
          </Panel>
        </TabsContent>

        <TabsContent value="ranking">
          <RankingTab plan={p} results={results.data} onChanged={reloadAll} />
        </TabsContent>
        <TabsContent value="fairness"><FairnessTab plan={p} fairness={fairness.data} /></TabsContent>
        <TabsContent value="compliance"><ComplianceTab plan={p} checks={compliance.data} /></TabsContent>
        <TabsContent value="approvals"><ApprovalsTab key={nonce} plan={p} /></TabsContent>
        <TabsContent value="cases"><CasesTab key={nonce} plan={p} onChanged={plan.reload} /></TabsContent>
        {can("legal") && <TabsContent value="audit"><AuditTab key={nonce} plan={p} /></TabsContent>}
        <TabsContent value="ai"><AiTab plan={p} results={results.data} /></TabsContent>
      </Tabs>

      <Dialog open={editing} onOpenChange={setEditing}>
        <DialogContent className="max-h-[90vh] overflow-y-auto rounded-2xl sm:max-w-4xl">
          <DialogHeader><DialogTitle>Edit draft plan</DialogTitle></DialogHeader>
          {editing && (
            <PlanForm initial={p} submitLabel="Save changes" onCancel={() => setEditing(false)}
                      onSubmit={async (v) => {
                        await patch(`/plans/${p.id}`, v);
                        toast.success(p.last_run_at ? "Saved and re-run" : "Saved");
                        setEditing(false);
                        reloadAll();
                      }} />
          )}
        </DialogContent>
      </Dialog>
      <DecisionDialog plan={p} fairness={fairness.data} open={deciding} onClose={() => setDeciding(false)}
                      onDone={() => { setDeciding(false); reloadAll(); }} />
    </div>
  );
}

export default function PlanPage() {
  return (
    <Suspense>
      <PlanDetail />
    </Suspense>
  );
}
