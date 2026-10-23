import {
  CircleCheck, CircleX, Download, Eye, FileText, Hand, KeyRound, LogIn, LogOut, Mail, Pause, Pencil, Play, Plus, Send,
  ShieldCheck, Sparkles, Undo2, Upload, type LucideIcon,
} from "lucide-react";
import { fmtDate } from "@/components/common";
import { Avatar, EmptyState } from "@/components/kit";
import type { AuditEntry } from "@/lib/api";

const ICON: Record<string, LucideIcon> = {
  create: Plus, update: Pencil, run: Play, submit: Send, approve: CircleCheck, reject: CircleX, reopen: Undo2,
  export: FileText, report_pdf: FileText, override_include: Hand, override_exclude: Hand, override_revoke: Undo2,
  import: Upload, ai_draft_summary: Sparkles, ai_draft_explanation: Sparkles, archive: Undo2,
  sign_in: LogIn, sign_out: LogOut, mfa_verified: KeyRound, mfa_enrolled: KeyRound, verify: ShieldCheck,
  verify_chain: ShieldCheck, view: Eye, self_service_view: Eye, download: Download, employee_download: Download,
  sent: Mail, release: Send, test_send: Mail, acknowledged: CircleCheck, hold: Pause, release_hold: Play,
  withdraw: Undo2, export_json: FileText, export_hris_csv: FileText,
};

function Diff({ before, after }: { before: AuditEntry["before"]; after: AuditEntry["after"] }) {
  const keys = Array.from(new Set([...Object.keys(before ?? {}), ...Object.keys(after ?? {})]));
  if (!keys.length) return null;
  const show = (v: unknown) => (v === undefined ? "–" : typeof v === "object" ? JSON.stringify(v) : String(v));
  return (
    <div className="mt-2 grid gap-1 rounded-lg border bg-background/40 p-2 font-mono text-[11px]">
      {keys.map((k) => {
        const b = before?.[k];
        const a = after?.[k];
        return (
          <div key={k} className="flex flex-wrap gap-x-2 break-all">
            <span className="text-muted-foreground">{k}:</span>
            {before && <span className="text-muted-foreground line-through decoration-[var(--status-critical)]/60">{show(b)}</span>}
            {before && <span className="text-muted-foreground">→</span>}
            <span>{show(a)}</span>
          </div>
        );
      })}
    </div>
  );
}

/** Audit entries as a timeline: who did what, when, what changed, and why. */
export function AuditTable({ entries }: { entries: AuditEntry[] }) {
  if (entries.length === 0) return <EmptyState icon={FileText} title="No entries yet" />;
  return (
    <ol className="relative space-y-5 border-l border-border pl-6">
      {entries.map((a) => {
        const Icon = ICON[a.action] ?? Pencil;
        return (
          <li key={a.id} className="relative">
            <span className="absolute top-0.5 -left-[37px] grid size-6 place-items-center rounded-full border bg-background">
              <Icon className="size-3 text-primary" />
            </span>
            <div className="flex flex-wrap items-center gap-x-2 gap-y-1 text-sm">
              <Avatar name={a.actor} size="sm" />
              <span className="font-medium">{a.actor}</span>
              <span className="rounded-md bg-muted px-1.5 py-0.5 font-mono text-xs">{a.action}</span>
              <span className="text-muted-foreground">
                {a.entity_type}{a.entity_id !== null && ` #${a.entity_id}`}
              </span>
              <span className="ml-auto text-xs text-muted-foreground">{fmtDate(a.created_at)}</span>
              {a.request_id && (
                <span className="w-full font-mono text-[10px] text-muted-foreground/70" title="Request ID">
                  req {a.request_id.slice(0, 12)} · #{a.id} · {a.hash.slice(0, 10)}
                </span>
              )}
            </div>
            {a.justification && <p className="mt-1.5 text-sm">“{a.justification}”</p>}
            <Diff before={a.before} after={a.after} />
          </li>
        );
      })}
    </ol>
  );
}
