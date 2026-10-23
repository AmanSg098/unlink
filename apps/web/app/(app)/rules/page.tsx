"use client";

import { BadgeCheck, CircleAlert, RefreshCw, Scale, ShieldQuestion } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { ErrorText, tableCls as t } from "@/components/common";
import { EmptyState, PageHeader, Panel, Pill } from "@/components/kit";
import { useAuth } from "@/components/auth";
import { useQuery } from "@/lib/use-query";
import { fmtDay, post } from "@/lib/api";

type Ruleset = {
  id: number; key: string; version: string; jurisdiction: string; title: string; source_file: string;
  file_hash: string; active: boolean; loaded_at: string; total?: number; verified?: number;
};
type Rule = {
  id: number; rule_key: string; title: string; category: string; applies_to: Record<string, unknown>;
  value: unknown; source: string; effective_date: string; notes: string; verified_by: string | null;
  verified_on: string | null; verified_note: string | null;
};
type Reason = {
  code: string; name: string; evidence: string; evidence_type: string | null; wording: string;
  wording_approved: { by: string; at: string; wording: string } | null;
};

const UNVERIFIED = { label: "Unverified", icon: ShieldQuestion, color: "var(--status-warning)" };
const VERIFIED = { label: "Verified", icon: BadgeCheck, color: "var(--status-good)" };

function showValue(v: unknown) {
  if (v === null || v === undefined) return "–";
  if (typeof v === "object") return JSON.stringify(v);
  return String(v);
}

function VerifyDialog({ ruleset, ruleIds, onClose, onDone }: {
  ruleset: Ruleset; ruleIds: number[] | null; onClose: () => void; onDone: () => void;
}) {
  const [by, setBy] = useState("");
  const [on, setOn] = useState(new Date().toISOString().slice(0, 10));
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const r = await post<{ verified: string[] }>(`/rulesets/${ruleset.id}/verify`,
                                                   { rule_ids: ruleIds, verified_by: by, verified_on: on, note });
      toast.success(`Recorded verification of ${r.verified.length} rule${r.verified.length === 1 ? "" : "s"}`);
      onDone();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <form onSubmit={submit} className="space-y-4">
      <p className="text-sm text-muted-foreground">
        Record that a qualified lawyer has checked {ruleIds ? `${ruleIds.length} selected rule(s)` : "every rule"} in{" "}
        <span className="font-medium text-foreground">{ruleset.title} {ruleset.version}</span> against current law.
      </p>
      <div className="grid gap-3 sm:grid-cols-2">
        <div className="space-y-1">
          <Label htmlFor="vby">Verified by (lawyer&apos;s name and firm)</Label>
          <Input id="vby" required minLength={3} value={by} onChange={(e) => setBy(e.target.value)} />
        </div>
        <div className="space-y-1">
          <Label htmlFor="von">Verified on</Label>
          <Input id="von" type="date" required value={on} onChange={(e) => setOn(e.target.value)} />
        </div>
      </div>
      <div className="space-y-1">
        <Label htmlFor="vnote">Note</Label>
        <Textarea id="vnote" value={note} onChange={(e) => setNote(e.target.value)}
                  placeholder="Opinion reference, caveats, scope of review" />
      </div>
      <ErrorText error={error} />
      <div className="flex gap-2">
        <Button type="submit" disabled={busy}>{busy ? "Saving…" : "Record verification"}</Button>
        <Button type="button" variant="outline" onClick={onClose}>Cancel</Button>
      </div>
    </form>
  );
}

function RulesetDetail({ ruleset, isLegal, onChanged }: { ruleset: Ruleset; isLegal: boolean; onChanged: () => void }) {
  const q = useQuery<{ ruleset: Ruleset; rules: Rule[]; mode: string }>(`/rulesets/${ruleset.id}`);
  const [selected, setSelected] = useState<number[]>([]);
  const [verifying, setVerifying] = useState<number[] | null | false>(false);
  const rules = q.data?.rules ?? [];
  const categories = Array.from(new Set(rules.map((r) => r.category)));
  const toggle = (id: number) => setSelected((s) => (s.includes(id) ? s.filter((x) => x !== id) : [...s, id]));

  return (
    <Panel
      title={<>{ruleset.title} <span className="font-normal text-muted-foreground">v{ruleset.version}</span></>}
      description={<>Jurisdiction {ruleset.jurisdiction} · loaded from <span className="font-mono">{ruleset.source_file}</span></>}
      actions={isLegal && (
        <div className="flex gap-2">
          <Button variant="outline" size="sm" disabled={!selected.length} onClick={() => setVerifying(selected)}>
            Verify selected ({selected.length})
          </Button>
          <Button size="sm" onClick={() => setVerifying(null)}>Verify all</Button>
        </div>
      )}
      bodyClassName="p-0"
    >
      <ErrorText error={q.error} />
      {categories.map((cat) => (
        <div key={cat} className="border-t">
          <div className="bg-muted/30 px-5 py-2 text-xs font-medium tracking-wide text-muted-foreground uppercase">{cat}</div>
          <table className={t.table}>
            <tbody>
              {rules.filter((r) => r.category === cat).map((r) => (
                <tr key={r.id} className={`${t.tr} align-top`}>
                  {isLegal && (
                    <td className="w-8 py-3 pl-5">
                      <input type="checkbox" aria-label={`Select ${r.rule_key}`} checked={selected.includes(r.id)}
                             onChange={() => toggle(r.id)} />
                    </td>
                  )}
                  <td className={`${t.td} w-36 font-mono text-xs`}>{r.rule_key}</td>
                  <td className={t.td}>
                    <div className="font-medium">{r.title}</div>
                    <div className="mt-1 font-mono text-xs break-all text-muted-foreground">{showValue(r.value)}</div>
                    {Object.keys(r.applies_to ?? {}).length > 0 && (
                      <div className="mt-1 text-xs text-muted-foreground">Applies to: {showValue(r.applies_to)}</div>
                    )}
                    <div className="mt-1 text-xs text-muted-foreground">Source: {r.source}</div>
                    {r.notes && <div className="mt-1 text-xs text-muted-foreground">{r.notes}</div>}
                  </td>
                  <td className={`${t.td} w-28 text-xs text-muted-foreground`}>from {fmtDay(r.effective_date)}</td>
                  <td className={`${t.td} w-56`}>
                    <Pill spec={r.verified_by ? VERIFIED : UNVERIFIED} />
                    {r.verified_by && (
                      <div className="mt-1 text-xs text-muted-foreground">{r.verified_by} · {fmtDay(r.verified_on)}</div>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ))}
      <Dialog open={verifying !== false} onOpenChange={(o) => !o && setVerifying(false)}>
        <DialogContent className="rounded-2xl sm:max-w-lg">
          <DialogHeader><DialogTitle>Record legal verification</DialogTitle></DialogHeader>
          {verifying !== false && (
            <VerifyDialog ruleset={ruleset} ruleIds={verifying} onClose={() => setVerifying(false)}
                          onDone={() => { setVerifying(false); setSelected([]); q.reload(); onChanged(); }} />
          )}
        </DialogContent>
      </Dialog>
    </Panel>
  );
}

export default function RulesPage() {
  const { can } = useAuth();
  const isLegal = can("legal");
  const sets = useQuery<{ mode: string; rulesets: Ruleset[] }>("/rulesets");
  const reasons = useQuery<Reason[]>("/reasons");
  const [openId, setOpenId] = useState<number | null>(null);
  const [busy, setBusy] = useState(false);
  const list = sets.data?.rulesets ?? [];
  const active = list.find((r) => r.id === openId) ?? list.find((r) => r.active) ?? list[0];
  const unverified = list.filter((r) => r.active).reduce((n, r) => n + ((r.total ?? 0) - (r.verified ?? 0)), 0);

  async function reload() {
    setBusy(true);
    try {
      const r = await post<{ loaded: Ruleset[] }>("/rulesets/reload");
      toast.success(`Reloaded ${r.loaded.length} ruleset file(s)`);
      sets.reload();
    } catch (e) {
      toast.error((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function approveWording(code: string) {
    try {
      await post(`/reasons/${code}/approve-wording`);
      toast.success(`Wording approved for ${code}`);
      reasons.reload();
    } catch (e) {
      toast.error((e as Error).message);
    }
  }

  return (
    <div className="space-y-8">
      <PageHeader
        eyebrow="Govern"
        title="Jurisdiction rules"
        description="Notice periods, statutory payments, thresholds and timelines come from versioned rule files, never from code. Every rule stays unverified until a lawyer signs it off."
        actions={isLegal && (
          <Button variant="outline" className="gap-2 rounded-xl" disabled={busy} onClick={reload}>
            <RefreshCw className="size-4" />Reload rule files
          </Button>
        )}
      />

      {unverified > 0 && (
        <div className="flex items-start gap-3 rounded-xl border px-4 py-3 text-sm"
             style={{ borderColor: "color-mix(in oklab, var(--status-warning) 45%, transparent)",
                      background: "color-mix(in oklab, var(--status-warning) 8%, transparent)" }}>
          <CircleAlert className="mt-0.5 size-4 shrink-0 text-[var(--status-warning)]" aria-hidden="true" />
          <div>
            <div className="font-medium">{unverified} active rule{unverified === 1 ? " is" : "s are"} unverified</div>
            <div className="text-muted-foreground">
              These values are placeholders and must not be relied on for real exits. Plans, notices and FNF statements
              that use them say so.{" "}
              {sets.data?.mode === "production"
                ? "Production mode is on: final plan approval is blocked until they are verified."
                : `Ruleset mode is "${sets.data?.mode ?? "…"}": approvals show a warning but are not blocked.`}
            </div>
          </div>
        </div>
      )}

      <ErrorText error={sets.error} />
      {list.length > 1 && (
        <div className="flex flex-wrap gap-2">
          {list.map((r) => (
            <button key={r.id} onClick={() => setOpenId(r.id)}
                    className={`rounded-xl border px-3 py-1.5 text-sm transition-colors ${r.id === active?.id ? "border-primary bg-primary/10" : "hover:bg-muted/40"}`}>
              {r.title} v{r.version} <span className="text-xs text-muted-foreground">{r.verified}/{r.total} verified{r.active ? "" : " · inactive"}</span>
            </button>
          ))}
        </div>
      )}
      {active ? <RulesetDetail key={active.id} ruleset={active} isLegal={isLegal} onChanged={sets.reload} />
              : !sets.loading && <Panel><EmptyState icon={Scale} title="No rulesets loaded">Run <code>uv run python -m app.cli load-rules</code> or reload rule files.</EmptyState></Panel>}

      <Panel title="Reason codes" description="Every exit needs a reason code with its required evidence. Legal approves the standard wording before it can appear in a notice."
             bodyClassName="p-0">
        <ErrorText error={reasons.error} />
        <table className={t.table}>
          <thead className={t.thead}>
            <tr className="border-b">
              <th className={t.th}>Code</th>
              <th className={t.th}>Evidence required</th>
              <th className={t.th}>Standard wording</th>
              <th className={t.th}>Wording</th>
            </tr>
          </thead>
          <tbody>
            {(reasons.data ?? []).map((r) => {
              const stale = r.wording_approved && r.wording_approved.wording !== r.wording;
              return (
                <tr key={r.code} className={`${t.tr} align-top`}>
                  <td className={t.td}>
                    <div className="font-mono text-xs">{r.code}</div>
                    <div className="font-medium">{r.name}</div>
                  </td>
                  <td className={`${t.td} max-w-56 text-xs text-muted-foreground`}>{r.evidence}</td>
                  <td className={`${t.td} max-w-md text-xs`}>{r.wording}</td>
                  <td className={`${t.td} w-52`}>
                    {r.wording_approved && !stale ? (
                      <>
                        <Pill spec={{ label: "Approved", icon: BadgeCheck, color: "var(--status-good)" }} />
                        <div className="mt-1 text-xs text-muted-foreground">{r.wording_approved.by} · {fmtDay(r.wording_approved.at)}</div>
                      </>
                    ) : (
                      <>
                        <Pill spec={{ label: stale ? "Changed since approval" : "Not approved", icon: ShieldQuestion,
                                      color: "var(--status-warning)" }} />
                        {isLegal && (
                          <Button size="sm" variant="outline" className="mt-2" onClick={() => approveWording(r.code)}>Approve wording</Button>
                        )}
                      </>
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </Panel>
    </div>
  );
}
