"use client";

import { CircleCheck, KeyRound, LogOut, Monitor } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { ErrorText, fmtDate } from "@/components/common";
import { Avatar, PageHeader, Panel, Pill, relTime } from "@/components/kit";
import { useAuth } from "@/components/auth";
import { useQuery } from "@/lib/use-query";
import { api, patch } from "@/lib/api";

type Session = { id: number; ip: string | null; created_at: string; last_seen_at: string | null; current: boolean;
  mfa_verified: boolean };

export default function AccountPage() {
  const { me, refresh, logout } = useAuth();
  const sessions = useQuery<Session[]>("/auth/sessions");

  async function toggleNotify(v: boolean) {
    try {
      await patch("/auth/me", { notify_email: v });
      await refresh();
      toast.success(v ? "Email notifications on" : "Email notifications off");
    } catch (e) {
      toast.error((e as Error).message);
    }
  }

  async function end(s: Session) {
    try {
      await api(`/auth/sessions/${s.id}`, { method: "DELETE" });
      if (s.current) return logout();
      toast.success("Session ended");
      sessions.reload();
    } catch (e) {
      toast.error((e as Error).message);
    }
  }

  if (!me) return null;
  return (
    <div className="space-y-8">
      <PageHeader eyebrow={me.org_name} title="My account" />

      <div className="grid gap-6 lg:grid-cols-2">
        <Panel title="Profile">
          <div className="flex items-center gap-4">
            <Avatar name={me.full_name} />
            <div>
              <div className="font-medium">{me.full_name}</div>
              <div className="text-sm text-muted-foreground">{me.email}</div>
            </div>
          </div>
          <dl className="mt-5 grid grid-cols-[10rem_1fr] gap-y-2 text-sm">
            <dt className="text-muted-foreground">Role</dt><dd className="capitalize">{me.role}</dd>
            <dt className="text-muted-foreground">Organisation</dt><dd>{me.org_name}</dd>
            {me.employee_code && <><dt className="text-muted-foreground">Employee ID</dt><dd className="font-mono">{me.employee_code}</dd></>}
          </dl>
          <p className="mt-4 text-xs text-muted-foreground">Ask an admin to change your role or details.</p>
        </Panel>

        <Panel title="Security & notifications">
          <div className="space-y-5 text-sm">
            <div className="flex items-start gap-3">
              <KeyRound className="mt-0.5 size-4 text-muted-foreground" />
              <div className="flex-1">
                <div className="font-medium">Two-step sign-in</div>
                <div className="text-muted-foreground">
                  {me.mfa_required ? "Required for your role." : "Not required for your role."}
                  {me.mfa_enabled ? " Your authenticator app is set up. An admin can reset it if you lose your device." : ""}
                </div>
              </div>
              {me.mfa_enabled ? <Pill spec={{ label: "Enrolled", icon: CircleCheck, color: "var(--status-good)" }} />
                             : <Pill spec={{ label: "Off", icon: KeyRound, color: "var(--viz-muted)" }} />}
            </div>
            <label className="flex items-start gap-3">
              <input type="checkbox" className="mt-1" checked={!!me.notify_email} onChange={(e) => toggleNotify(e.target.checked)} />
              <span>
                <span className="font-medium">Email me about approvals and escalations</span>
                <span className="block text-muted-foreground">In-app notifications always appear under the bell.</span>
              </span>
            </label>
          </div>
        </Panel>
      </div>

      <Panel title="Active sessions" description="Sessions last 12 hours. End any you don't recognise.">
        <ErrorText error={sessions.error} />
        <ul className="divide-y">
          {(sessions.data ?? []).map((s) => (
            <li key={s.id} className="flex flex-wrap items-center gap-3 py-3 text-sm">
              <Monitor className="size-4 text-muted-foreground" />
              <div className="flex-1">
                <div>{s.ip ?? "Unknown address"}{s.current && <span className="ml-2 text-xs text-[var(--status-good)]">This device</span>}</div>
                <div className="text-xs text-muted-foreground">
                  Signed in {fmtDate(s.created_at)} · last active {relTime(s.last_seen_at ?? s.created_at)}
                  {s.mfa_verified ? " · two-step verified" : ""}
                </div>
              </div>
              <Button size="sm" variant="outline" className="gap-1.5" onClick={() => end(s)}>
                <LogOut className="size-3.5" />{s.current ? "Sign out" : "End"}
              </Button>
            </li>
          ))}
        </ul>
      </Panel>
    </div>
  );
}
