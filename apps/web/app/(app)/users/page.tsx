"use client";

import { Ban, CircleCheck, KeyRound, ShieldOff, UserPlus } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { ErrorText, tableCls as t } from "@/components/common";
import { Avatar, PageHeader, Panel, Pill, relTime } from "@/components/kit";
import { useAuth } from "@/components/auth";
import { useQuery } from "@/lib/use-query";
import { patch, post, type Role, type User } from "@/lib/api";

type Org = {
  id: number; name: string; region: string; timezone: string;
  settings: { legal_name: string | null; address: string | null; hr_contact_email: string | null;
    test_addresses: string[] | null; establishment_size: number | null; escalation_days: number | null };
  mail: { provider: string; live: boolean };
};

const ROLES: { value: Role; label: string; hint: string }[] = [
  { value: "hr", label: "HR", hint: "Builds plans, drafts notices, runs exit cases" },
  { value: "manager", label: "Manager", hint: "Sees and acts on their own reporting line only" },
  { value: "legal", label: "Legal", hint: "Approves templates, rules, notice batches; reads the audit log" },
  { value: "finance", label: "Finance", hint: "Reviews plans for cost, computes and approves FNF" },
  { value: "approver", label: "Approver", hint: "Final sign-off on plans, notices, exits" },
  { value: "viewer", label: "Viewer", hint: "Read-only" },
  { value: "admin", label: "Admin", hint: "Everything, plus users and integrations" },
];
const MFA_ROLES = new Set(["legal", "finance", "approver", "admin"]);

function NewUserForm({ onDone, onCancel }: { onDone: () => void; onCancel: () => void }) {
  const [v, setV] = useState({ email: "", full_name: "", role: "hr" as Role, password: "", employee_code: "" });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await post("/users", { ...v, employee_code: v.employee_code || null });
      toast.success("User created. Share the temporary password through a separate channel.");
      onDone();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <form onSubmit={submit} className="space-y-4">
      <div className="grid gap-3 sm:grid-cols-2">
        <div className="space-y-1">
          <Label htmlFor="nu-name">Full name</Label>
          <Input id="nu-name" required value={v.full_name} onChange={(e) => setV({ ...v, full_name: e.target.value })} />
        </div>
        <div className="space-y-1">
          <Label htmlFor="nu-email">Email</Label>
          <Input id="nu-email" type="email" required value={v.email} onChange={(e) => setV({ ...v, email: e.target.value })} />
        </div>
        <div className="space-y-1">
          <Label htmlFor="nu-role">Role</Label>
          <select id="nu-role" className="h-8 w-full rounded-md border bg-background px-2 text-sm" value={v.role}
                  onChange={(e) => setV({ ...v, role: e.target.value as Role })}>
            {ROLES.map((r) => <option key={r.value} value={r.value}>{r.label}</option>)}
          </select>
        </div>
        <div className="space-y-1">
          <Label htmlFor="nu-code">Employee ID (for managers)</Label>
          <Input id="nu-code" value={v.employee_code} placeholder="Links their reporting line"
                 onChange={(e) => setV({ ...v, employee_code: e.target.value })} />
        </div>
        <div className="space-y-1 sm:col-span-2">
          <Label htmlFor="nu-pw">Temporary password (10+ characters)</Label>
          <Input id="nu-pw" type="password" autoComplete="new-password" minLength={10} required value={v.password}
                 onChange={(e) => setV({ ...v, password: e.target.value })} />
        </div>
      </div>
      <p className="text-xs text-muted-foreground">{ROLES.find((r) => r.value === v.role)?.hint}.
        {MFA_ROLES.has(v.role) && " This role must set up two-step sign-in on first login."}</p>
      <ErrorText error={error} />
      <div className="flex gap-2">
        <Button type="submit" disabled={busy}>{busy ? "Creating…" : "Create user"}</Button>
        <Button type="button" variant="outline" onClick={onCancel}>Cancel</Button>
      </div>
    </form>
  );
}

function OrgSettings() {
  const q = useQuery<Org>("/org");
  const [draft, setDraft] = useState<Record<string, string> | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const s = q.data?.settings;
  const values = draft ?? {
    legal_name: s?.legal_name ?? "", address: s?.address ?? "", hr_contact_email: s?.hr_contact_email ?? "",
    test_addresses: (s?.test_addresses ?? []).join(", "), establishment_size: String(s?.establishment_size ?? ""),
    escalation_days: String(s?.escalation_days ?? ""),
  };
  const set = (k: string, v: string) => setDraft({ ...values, [k]: v });

  async function save(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await patch("/org", {
        legal_name: values.legal_name || null, address: values.address || null,
        hr_contact_email: values.hr_contact_email || null,
        test_addresses: values.test_addresses.split(/[,\s]+/).filter(Boolean),
        establishment_size: values.establishment_size ? Number(values.establishment_size) : null,
        escalation_days: values.escalation_days ? Number(values.escalation_days) : null,
      });
      toast.success("Organisation settings saved");
      setDraft(null);
      q.reload();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  const field = (k: string, label: string, hint?: string, type = "text") => (
    <div className="space-y-1">
      <Label htmlFor={`org-${k}`}>{label}</Label>
      <Input id={`org-${k}`} type={type} value={values[k]} onChange={(e) => set(k, e.target.value)} />
      {hint && <p className="text-xs text-muted-foreground">{hint}</p>}
    </div>
  );

  return (
    <Panel title="Organisation" description={q.data ? `${q.data.name} · ${q.data.region} · ${q.data.timezone}` : undefined}>
      <ErrorText error={q.error} />
      <form onSubmit={save} className="space-y-4">
        <div className="grid gap-3 sm:grid-cols-2">
          {field("legal_name", "Legal entity name", "Used on letters and notices")}
          {field("hr_contact_email", "HR contact email", "Shown to employees in self-service", "email")}
          <div className="sm:col-span-2">{field("address", "Registered address")}</div>
          {field("test_addresses", "Test-send addresses", "Comma-separated. Test sends go only here")}
          {field("establishment_size", "Establishment headcount", "Used for threshold rules (e.g. government permission)", "number")}
          {field("escalation_days", "Escalate approvals after (days)", "1–30", "number")}
        </div>
        {q.data && (
          <p className="text-xs text-muted-foreground">
            Mail provider: <span className="font-mono">{q.data.mail.provider}</span>
            {q.data.mail.live ? " · live sending allowed" : " · capture only (nothing leaves the system)"}
          </p>
        )}
        <ErrorText error={error} />
        <Button type="submit" disabled={busy || !draft}>{busy ? "Saving…" : "Save settings"}</Button>
      </form>
    </Panel>
  );
}

export default function UsersPage() {
  const { me } = useAuth();
  const q = useQuery<User[]>("/users");
  const [adding, setAdding] = useState(false);

  async function update(u: User, body: Record<string, unknown>, done: string) {
    try {
      await patch(`/users/${u.id}`, body);
      toast.success(done);
      q.reload();
    } catch (e) {
      toast.error((e as Error).message);
    }
  }

  return (
    <div className="space-y-8">
      <PageHeader
        eyebrow="Govern"
        title="Team & access"
        description="Roles decide what each person can see and do. Changing a role or deactivating someone ends their sessions immediately."
        actions={<Button className="gap-2 rounded-xl" onClick={() => setAdding(true)}><UserPlus className="size-4" />Add user</Button>}
      />

      <Panel bodyClassName="p-0">
        <ErrorText error={q.error} />
        <table className={t.table}>
          <thead className={t.thead}>
            <tr className="border-b">
              <th className={t.th}>User</th>
              <th className={t.th}>Role</th>
              <th className={t.th}>Employee ID</th>
              <th className={t.th}>Two-step sign-in</th>
              <th className={t.th}>Status</th>
              <th className={t.th} />
            </tr>
          </thead>
          <tbody>
            {(q.data ?? []).map((u) => {
              const self = me?.id === u.id && me.kind === "staff";
              return (
                <tr key={u.id} className={t.tr}>
                  <td className={t.td}>
                    <div className="flex items-center gap-3">
                      <Avatar name={u.full_name} />
                      <div>
                        <div className="font-medium">{u.full_name}{self && <span className="ml-1 text-xs text-muted-foreground">(you)</span>}</div>
                        <div className="text-xs text-muted-foreground">{u.email} · added {relTime(u.created_at)}</div>
                      </div>
                    </div>
                  </td>
                  <td className={t.td}>
                    <select className="h-8 rounded-md border bg-background px-2 text-sm" value={u.role} disabled={self}
                            aria-label={`Role for ${u.email}`}
                            onChange={(e) => update(u, { role: e.target.value }, `Role changed to ${e.target.value}`)}>
                      {ROLES.map((r) => <option key={r.value} value={r.value}>{r.label}</option>)}
                    </select>
                  </td>
                  <td className={t.td}>
                    <Input className="h-8 w-28 font-mono text-xs" defaultValue={u.employee_code ?? ""} placeholder="–"
                           aria-label={`Employee ID for ${u.email}`}
                           onBlur={(e) => {
                             const v = e.target.value.trim() || null;
                             if (v !== u.employee_code) void update(u, { employee_code: v }, "Employee link saved");
                           }} />
                  </td>
                  <td className={t.td}>
                    {u.mfa_enabled ? <Pill spec={{ label: "Enrolled", icon: KeyRound, color: "var(--status-good)" }} />
                      : MFA_ROLES.has(u.role) ? <Pill spec={{ label: "Required · not set up", icon: KeyRound, color: "var(--status-warning)" }} />
                      : <span className="text-xs text-muted-foreground">Not required</span>}
                  </td>
                  <td className={t.td}>
                    <Pill spec={u.active ? { label: "Active", icon: CircleCheck, color: "var(--status-good)" }
                                         : { label: "Deactivated", icon: Ban, color: "var(--viz-muted)" }} />
                  </td>
                  <td className={`${t.td} text-right whitespace-nowrap`}>
                    {u.mfa_enabled && (
                      <Button size="sm" variant="ghost" className="gap-1.5" title="Reset two-step sign-in"
                              onClick={() => window.confirm(`Reset two-step sign-in for ${u.email}? They will enrol again on next sign-in.`)
                                && update(u, { reset_mfa: true }, "Two-step sign-in reset")}>
                        <ShieldOff className="size-3.5" />Reset MFA
                      </Button>
                    )}
                    {!self && (
                      <Button size="sm" variant="ghost"
                              onClick={() => update(u, { active: !u.active }, u.active ? "User deactivated" : "User reactivated")}>
                        {u.active ? "Deactivate" : "Reactivate"}
                      </Button>
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </Panel>

      <OrgSettings />

      <Dialog open={adding} onOpenChange={setAdding}>
        <DialogContent className="rounded-2xl sm:max-w-lg">
          <DialogHeader><DialogTitle>Add user</DialogTitle></DialogHeader>
          {adding && <NewUserForm onCancel={() => setAdding(false)} onDone={() => { setAdding(false); q.reload(); }} />}
        </DialogContent>
      </Dialog>
    </div>
  );
}
