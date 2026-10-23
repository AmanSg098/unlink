"use client";

import { Download, FileSpreadsheet, ShieldAlert, ShieldCheck } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";
import { Button, buttonVariants } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { AuditTable } from "@/components/audit-table";
import { ErrorText } from "@/components/common";
import { PageHeader, Panel, Pill } from "@/components/kit";
import { useAuth } from "@/components/auth";
import { useQuery } from "@/lib/use-query";
import { api, type AuditEntry } from "@/lib/api";
import { cn } from "@/lib/utils";

type Verify = { ok: boolean; checked: number; first_bad_id: number | null };

const ENTITY_TYPES = [
  "plan", "override", "exit_case", "exit_task", "notice_batch", "notice_draft", "notice_message", "template", "fnf",
  "document", "clearance", "grievance", "employee", "payroll", "evidence", "pip", "review", "review_cycle", "kpi",
  "ruleset", "reason", "integration", "user", "org", "session", "report", "audit",
];

export default function AuditPage() {
  const { can } = useAuth();
  const [entityType, setEntityType] = useState("");
  const [entityId, setEntityId] = useState("");
  const [actor, setActor] = useState("");
  const [limit, setLimit] = useState(200);
  const [verify, setVerify] = useState<Verify | null>(null);
  const [busy, setBusy] = useState(false);

  const params = new URLSearchParams({ limit: String(limit) });
  if (entityType) params.set("entity_type", entityType);
  if (entityId && /^\d+$/.test(entityId)) params.set("entity_id", entityId);
  if (actor) params.set("actor", actor.trim());
  const q = useQuery<AuditEntry[]>(`/audit?${params}`);
  const rows = q.data ?? [];

  async function runVerify() {
    setBusy(true);
    try {
      const r = await api<Verify>("/audit/verify");
      setVerify(r);
      if (r.ok) toast.success(`Chain intact: ${r.checked.toLocaleString("en-IN")} entries checked`);
      else toast.error(`Chain broken at entry #${r.first_bad_id}`);
      q.reload();
    } catch (e) {
      toast.error((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-8">
      <PageHeader
        eyebrow="Govern"
        title="Audit log"
        description="Append-only and hash-chained: every entry includes the hash of the one before it, so any edit or deletion breaks the chain. Database triggers block updates and deletes."
        actions={
          <>
            <Button variant="outline" className="gap-2 rounded-xl" disabled={busy} onClick={runVerify}>
              <ShieldCheck className="size-4" />{busy ? "Checking…" : "Verify chain"}
            </Button>
            <a href="/api/audit/export.json" className={cn(buttonVariants({ variant: "outline" }), "gap-2 rounded-xl")}>
              <Download className="size-4" />Export JSON
            </a>
            {can("hr", "finance") && (
              <a href="/api/reports/hris.csv" className={cn(buttonVariants({ variant: "outline" }), "gap-2 rounded-xl")}>
                <FileSpreadsheet className="size-4" />HRIS exits CSV
              </a>
            )}
          </>
        }
      />

      {verify && (
        <div className="flex items-center gap-3 rounded-xl border px-4 py-3 text-sm"
             style={{ borderColor: `color-mix(in oklab, var(--status-${verify.ok ? "good" : "critical"}) 45%, transparent)`,
                      background: `color-mix(in oklab, var(--status-${verify.ok ? "good" : "critical"}) 8%, transparent)` }}>
          <Pill spec={verify.ok ? { label: "Intact", icon: ShieldCheck, color: "var(--status-good)" }
                                : { label: "Broken", icon: ShieldAlert, color: "var(--status-critical)" }} />
          <span>
            {verify.ok
              ? `All ${verify.checked.toLocaleString("en-IN")} entries recomputed and matched.`
              : `Entry #${verify.first_bad_id} doesn't match its recorded hash (checked ${verify.checked}). Treat the log as tampered and escalate.`}
          </span>
        </div>
      )}

      <Panel bodyClassName="p-0">
        <div className="flex flex-wrap items-center gap-2 border-b p-4">
          <select className="h-9 rounded-xl border bg-background/50 px-3 text-sm" aria-label="Entity type" value={entityType}
                  onChange={(e) => setEntityType(e.target.value)}>
            <option value="">All entities</option>
            {ENTITY_TYPES.map((e) => <option key={e} value={e}>{e.replace(/_/g, " ")}</option>)}
          </select>
          <Input className="h-9 w-28 rounded-xl" placeholder="Entity ID" inputMode="numeric" value={entityId}
                 onChange={(e) => setEntityId(e.target.value.replace(/\D/g, ""))} />
          <Input className="h-9 w-56 rounded-xl" placeholder="Actor (exact email)" value={actor}
                 onChange={(e) => setActor(e.target.value)} />
          <select className="h-9 rounded-xl border bg-background/50 px-3 text-sm" aria-label="Limit" value={limit}
                  onChange={(e) => setLimit(Number(e.target.value))}>
            {[100, 200, 500, 1000].map((n) => <option key={n} value={n}>Latest {n}</option>)}
          </select>
          <span className="ml-auto text-xs text-muted-foreground">{rows.length} entries</span>
        </div>
        <ErrorText error={q.error} />
        <div className="p-6">
          {!q.loading && <AuditTable entries={rows} />}
        </div>
      </Panel>
    </div>
  );
}
