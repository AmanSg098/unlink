"use client";

import { CircleCheck, CircleDashed, CircleX, Clock, Hourglass, Plug, RefreshCw, Settings2 } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { ErrorText, fmtDate, tableCls as t } from "@/components/common";
import { EmptyState, PageHeader, Panel, Pill } from "@/components/kit";
import { useQuery } from "@/lib/use-query";
import { post, put } from "@/lib/api";

type ProviderSpec = { label: string; implemented: boolean; env?: boolean; config?: string[]; secrets?: string[] };
type Integration = {
  id: number; type: string; provider: string; enabled: boolean; config: Record<string, string>;
  secret_keys: string[]; updated_by: string; updated_at: string;
};
type Conflict = { employee_code: string; field: string; current: unknown; incoming: unknown };
type Run = {
  id: number; integration_id: number; kind: string; status: "running" | "succeeded" | "failed" | "needs_review";
  summary: { rows?: number; new?: string[]; conflicts?: Conflict[]; errors?: string[]; applied?: string[] };
  error: string | null; started_at: string; finished_at: string | null;
};
type Data = {
  providers: Record<string, Record<string, ProviderSpec>>;
  integrations: Integration[];
  runs: Run[];
  mail: { provider: string; live: boolean };
};

const TYPE_LABEL: Record<string, string> = {
  hris: "HRIS", payroll: "Payroll", email: "Email", esign: "E-signature", ticketing: "IT ticketing",
  messaging: "Messaging", sso: "Single sign-on",
};
const TYPE_HINT: Record<string, string> = {
  hris: "People data in, exits out. Differences are flagged for review; nothing is overwritten automatically.",
  payroll: "Payroll components in by CSV; approved FNF statements out by CSV.",
  email: "Set with environment variables (MAIL_PROVIDER, SMTP_*). Development captures every message instead of sending.",
  esign: "Signed acknowledgements.",
  ticketing: "Clearance items (access removal, asset return) create tickets.",
  messaging: "Approval and escalation notifications to a channel. No employee details are posted.",
  sso: "Staff sign-in through your identity provider.",
};

const RUN_STATUS = {
  running: { label: "Running", icon: Hourglass, color: "var(--status-warning)" },
  succeeded: { label: "Succeeded", icon: CircleCheck, color: "var(--status-good)" },
  failed: { label: "Failed", icon: CircleX, color: "var(--status-critical)" },
  needs_review: { label: "Needs review", icon: Clock, color: "var(--status-warning)" },
};

function ConfigureForm({ type, providers, current, onDone, onCancel }: {
  type: string; providers: Record<string, ProviderSpec>; current: Integration | undefined;
  onDone: () => void; onCancel: () => void;
}) {
  const choices = Object.entries(providers).filter(([, s]) => s.implemented && !s.env);
  const [provider, setProvider] = useState(current?.provider ?? choices[0]?.[0] ?? "");
  const [enabled, setEnabled] = useState(current?.enabled ?? true);
  const [config, setConfig] = useState<Record<string, string>>(current?.config ?? {});
  const [secrets, setSecrets] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const spec = providers[provider];

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await put("/integrations", { type, provider, enabled, config, secrets });
      toast.success(`${TYPE_LABEL[type]} saved`);
      onDone();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <form onSubmit={submit} className="space-y-4">
      <div className="space-y-1">
        <Label htmlFor="provider">Provider</Label>
        <select id="provider" className="h-9 w-full rounded-md border bg-background px-2 text-sm" value={provider}
                onChange={(e) => { setProvider(e.target.value); setConfig({}); setSecrets({}); }}>
          {choices.map(([k, s]) => <option key={k} value={k}>{s.label}</option>)}
        </select>
      </div>
      {spec?.config?.map((k) => (
        <div key={k} className="space-y-1">
          <Label htmlFor={`c-${k}`}>{k.replace(/_/g, " ")}</Label>
          <Input id={`c-${k}`} value={config[k] ?? ""} onChange={(e) => setConfig({ ...config, [k]: e.target.value })} />
        </div>
      ))}
      {spec?.secrets?.map((k) => (
        <div key={k} className="space-y-1">
          <Label htmlFor={`s-${k}`}>{k.replace(/_/g, " ")} (secret)</Label>
          <Input id={`s-${k}`} type="password" autoComplete="off" value={secrets[k] ?? ""}
                 placeholder={current?.secret_keys.includes(k) ? "Stored. Leave blank to keep it" : ""}
                 onChange={(e) => setSecrets({ ...secrets, [k]: e.target.value })} />
        </div>
      ))}
      <p className="text-xs text-muted-foreground">Secrets are encrypted at rest and never shown again.</p>
      <label className="flex items-center gap-2 text-sm">
        <input type="checkbox" checked={enabled} onChange={(e) => setEnabled(e.target.checked)} />Enabled
      </label>
      <ErrorText error={error} />
      <div className="flex gap-2">
        <Button type="submit" disabled={busy || !provider}>{busy ? "Saving…" : "Save"}</Button>
        <Button type="button" variant="outline" onClick={onCancel}>Cancel</Button>
      </div>
    </form>
  );
}

function ReviewRun({ run, onDone }: { run: Run; onDone: () => void }) {
  const conflicts = run.summary.conflicts ?? [];
  const codes = Array.from(new Set(conflicts.map((c) => c.employee_code)));
  const applied = new Set(run.summary.applied ?? []);
  const [picked, setPicked] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);

  async function apply() {
    setBusy(true);
    try {
      const r = await post<{ applied: string[] }>(`/integrations/runs/${run.id}/apply`, picked);
      toast.success(`Applied changes for ${r.applied.length} employee(s)`);
      setPicked([]);
      onDone();
    } catch (e) {
      toast.error((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-4">
      <p className="text-sm text-muted-foreground">
        {run.summary.rows} rows read. Tick the employees whose incoming values should replace what Unlink holds.
        Each change is written to history and the audit log.
      </p>
      {(run.summary.new?.length ?? 0) > 0 && (
        <p className="text-sm">New in HRIS (add them via People import): <span className="font-mono text-xs">{run.summary.new!.join(", ")}</span></p>
      )}
      <div className="max-h-[50vh] overflow-auto rounded-xl border">
        <table className={t.table}>
          <thead className={t.thead}>
            <tr className="border-b"><th className={t.th} /><th className={t.th}>Employee</th><th className={t.th}>Field</th>
              <th className={t.th}>Current</th><th className={t.th}>Incoming</th></tr>
          </thead>
          <tbody>
            {codes.map((code) => conflicts.filter((c) => c.employee_code === code).map((c, i) => (
              <tr key={`${code}-${c.field}`} className={t.tr}>
                <td className="w-8 pl-4">
                  {i === 0 && (applied.has(code) ? <CircleCheck className="size-4 text-[var(--status-good)]" aria-label="Applied" /> : (
                    <input type="checkbox" aria-label={`Apply ${code}`} checked={picked.includes(code)}
                           onChange={() => setPicked((p) => (p.includes(code) ? p.filter((x) => x !== code) : [...p, code]))} />
                  ))}
                </td>
                <td className={`${t.td} font-mono text-xs`}>{i === 0 ? code : ""}</td>
                <td className={t.td}>{c.field}</td>
                <td className={`${t.td} text-muted-foreground`}>{String(c.current ?? "–")}</td>
                <td className={t.td}>{String(c.incoming ?? "–")}</td>
              </tr>
            )))}
          </tbody>
        </table>
      </div>
      <Button disabled={busy || !picked.length} onClick={apply}>Apply {picked.length || ""} selected</Button>
    </div>
  );
}

export default function IntegrationsPage() {
  const q = useQuery<Data>("/integrations");
  const [editing, setEditing] = useState<string | null>(null);
  const [reviewing, setReviewing] = useState<Run | null>(null);
  const d = q.data;
  const byType = (type: string) => d?.integrations.find((i) => i.type === type);

  async function sync() {
    try {
      await post("/integrations/hris/sync");
      toast.success("Sync queued. The worker will read people.csv from the inbox.");
      q.reload();
    } catch (e) {
      toast.error((e as Error).message);
    }
  }

  return (
    <div className="space-y-8">
      <PageHeader
        eyebrow="Govern"
        title="Integrations"
        description="Connections to the systems around an exit. Planned connectors are listed so you can see what's coming; only implemented ones can be enabled."
        actions={byType("hris")?.enabled && (
          <Button variant="outline" className="gap-2 rounded-xl" onClick={sync}><RefreshCw className="size-4" />Sync HRIS now</Button>
        )}
      />
      <ErrorText error={q.error} />

      <div className="grid gap-4 md:grid-cols-2">
        {d && Object.entries(d.providers).map(([type, providers]) => {
          const cur = byType(type);
          const configurable = Object.values(providers).some((s) => s.implemented && !s.env);
          return (
            <Panel key={type} title={TYPE_LABEL[type] ?? type} description={TYPE_HINT[type]}
                   actions={configurable && (
                     <Button size="sm" variant="outline" className="gap-1.5" onClick={() => setEditing(type)}>
                       <Settings2 className="size-3.5" />Configure
                     </Button>
                   )}>
              <ul className="space-y-2">
                {Object.entries(providers).map(([key, s]) => {
                  const active = type === "email" ? d.mail.provider === key : cur?.provider === key && cur.enabled;
                  return (
                    <li key={key} className="flex items-center gap-3 text-sm">
                      <span className="flex-1">{s.label}</span>
                      {active ? <Pill spec={{ label: type === "email" && !d.mail.live ? "Active · capture only" : "Active", icon: CircleCheck, color: "var(--status-good)" }} />
                        : s.implemented ? <Pill spec={{ label: "Available", icon: Plug, color: "var(--series-1)" }} />
                        : <Pill spec={{ label: "Planned", icon: CircleDashed, color: "var(--viz-muted)" }} />}
                    </li>
                  );
                })}
              </ul>
              {cur && (
                <div className="mt-4 border-t pt-3 text-xs text-muted-foreground">
                  {Object.entries(cur.config).map(([k, v]) => <div key={k}><span className="font-mono">{k}</span>: {v}</div>)}
                  {cur.secret_keys.length > 0 && <div>Secrets stored: {cur.secret_keys.join(", ")}</div>}
                  <div>Updated by {cur.updated_by} · {fmtDate(cur.updated_at)}</div>
                </div>
              )}
            </Panel>
          );
        })}
      </div>

      <Panel title="Recent runs" bodyClassName="p-0">
        {d?.runs.length ? (
          <table className={t.table}>
            <thead className={t.thead}>
              <tr className="border-b"><th className={t.th}>Run</th><th className={t.th}>Status</th><th className={t.th}>Started</th>
                <th className={t.th}>Result</th><th className={t.th} /></tr>
            </thead>
            <tbody>
              {d.runs.map((r) => (
                <tr key={r.id} className={t.tr}>
                  <td className={t.td}>#{r.id} · {r.kind.replace(/_/g, " ")}</td>
                  <td className={t.td}><Pill spec={RUN_STATUS[r.status] ?? RUN_STATUS.running} /></td>
                  <td className={`${t.td} text-xs text-muted-foreground`}>{fmtDate(r.started_at)}</td>
                  <td className={`${t.td} text-xs`}>
                    {r.error ?? (r.summary.rows !== undefined
                      ? `${r.summary.rows} rows · ${r.summary.conflicts?.length ?? 0} differences · ${r.summary.new?.length ?? 0} new${r.summary.errors?.length ? ` · ${r.summary.errors.length} errors` : ""}`
                      : "")}
                  </td>
                  <td className={`${t.td} text-right`}>
                    {r.status === "needs_review" && <Button size="sm" variant="outline" onClick={() => setReviewing(r)}>Review</Button>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : <EmptyState icon={RefreshCw} title="No runs yet" />}
      </Panel>

      <Dialog open={!!editing} onOpenChange={(o) => !o && setEditing(null)}>
        <DialogContent className="rounded-2xl sm:max-w-md">
          <DialogHeader><DialogTitle>Configure {editing ? TYPE_LABEL[editing] : ""}</DialogTitle></DialogHeader>
          {editing && d && (
            <ConfigureForm type={editing} providers={d.providers[editing]} current={byType(editing)}
                           onCancel={() => setEditing(null)} onDone={() => { setEditing(null); q.reload(); }} />
          )}
        </DialogContent>
      </Dialog>
      <Dialog open={!!reviewing} onOpenChange={(o) => !o && setReviewing(null)}>
        <DialogContent className="rounded-2xl sm:max-w-3xl">
          <DialogHeader><DialogTitle>Review HRIS differences</DialogTitle></DialogHeader>
          {reviewing && <ReviewRun run={reviewing} onDone={() => { setReviewing(null); q.reload(); }} />}
        </DialogContent>
      </Dialog>
    </div>
  );
}
