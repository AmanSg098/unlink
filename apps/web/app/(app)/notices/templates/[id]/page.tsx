"use client";

import { ArrowLeft, Braces, Pencil, ShieldCheck } from "lucide-react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { Suspense, useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { ErrorText, fmtDate } from "@/components/common";
import { useAct } from "@/components/case-ui";
import { TemplateStatusPill } from "@/components/notice-ui";
import { PageHeader, Panel } from "@/components/kit";
import { useAuth } from "@/components/auth";
import { useQuery } from "@/lib/use-query";
import { patch, post, type Template } from "@/lib/api";

type Detail = { template: Template; versions: Template[]; preview: { subject: string; body: string } };
type Edit = Pick<Template, "subject" | "body" | "send_to_personal" | "attach_pdf" | "encrypt_attachment">;

function TemplateDetail() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const { me, can } = useAuth();
  const q = useQuery<Detail>(`/notice-templates/${id}`);
  const [edit, setEdit] = useState<Edit | null>(null);
  const { busy, run } = useAct();

  if (!q.data) return <ErrorText error={q.error} />;
  const { template: tpl, versions, preview } = q.data;
  const ownVersion = tpl.created_by === me?.email;

  async function save() {
    const nt = await run(() => patch<Template>(`/notice-templates/${tpl.id}`, edit), "Saved as a new version for Legal to approve");
    if (nt) {
      setEdit(null);
      router.replace(`/notices/templates/${nt.id}`);
    }
  }

  const flag = (k: "send_to_personal" | "attach_pdf" | "encrypt_attachment", label: string) => (
    <label className="flex items-center gap-2 text-sm">
      <input type="checkbox" checked={edit![k]} onChange={(e) => setEdit({ ...edit!, [k]: e.target.checked })} />{label}
    </label>
  );

  return (
    <div className="space-y-8">
      <Link href="/notices" className="inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground">
        <ArrowLeft className="size-4" />Notices
      </Link>
      <PageHeader
        eyebrow={<span className="font-mono">{tpl.key}</span>}
        title={`${tpl.title} · v${tpl.version}`}
        description={<span className="inline-flex flex-wrap items-center gap-2">
          <TemplateStatusPill status={tpl.status} /><span className="capitalize">{tpl.type}</span>
          <span>Written by {tpl.created_by}</span>
          {tpl.approved_by && <span>· approved by {tpl.approved_by} on {fmtDate(tpl.approved_at)}</span>}
        </span>}
        actions={
          <div className="flex gap-2">
            {can("hr", "legal") && tpl.status !== "retired" && !edit && (
              <Button variant="outline" onClick={() => setEdit({
                subject: tpl.subject, body: tpl.body, send_to_personal: tpl.send_to_personal, attach_pdf: tpl.attach_pdf,
                encrypt_attachment: tpl.encrypt_attachment,
              })}>
                <Pencil className="size-4" />Edit as new version
              </Button>
            )}
            {can("legal") && tpl.status === "draft" && (
              <Button disabled={busy || ownVersion} title={ownVersion ? "Whoever wrote a version can't approve it" : undefined}
                      onClick={async () => {
                        if (await run(() => post(`/notice-templates/${tpl.id}/approve`), "Template approved; the previous version is retired")) q.reload();
                      }}>
                <ShieldCheck className="size-4" />Approve for use
              </Button>
            )}
          </div>
        }
      />

      {tpl.status === "draft" && (
        <p className="rounded-xl border border-dashed p-3 text-sm text-muted-foreground">
          Notices made from this version can&apos;t be approved for sending until Legal approves the template.
          The person who wrote a version can&apos;t approve it.
        </p>
      )}

      <div className="grid gap-6 xl:grid-cols-[1.4fr_1fr]">
        {edit ? (
          <Panel title="Edit">
            <div className="space-y-3">
              <div className="space-y-1.5">
                <Label htmlFor="subject">Subject</Label>
                <Input id="subject" value={edit.subject} onChange={(e) => setEdit({ ...edit, subject: e.target.value })} />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="body">Body (Jinja merge fields, e.g. {"{{ employee_name }}"})</Label>
                <Textarea id="body" rows={20} className="font-mono text-sm" value={edit.body}
                          onChange={(e) => setEdit({ ...edit, body: e.target.value })} />
              </div>
              <div className="flex flex-wrap gap-5">
                {flag("send_to_personal", "Send to personal email")}
                {flag("attach_pdf", "Attach as PDF")}
                {flag("encrypt_attachment", "Password-protect the PDF")}
              </div>
              <div className="flex gap-2">
                <Button disabled={busy} onClick={save}>Save new version</Button>
                <Button variant="outline" onClick={() => setEdit(null)}>Cancel</Button>
              </div>
            </div>
          </Panel>
        ) : (
          <Panel title="Preview" description="Merge fields shown as [field].">
            <div className="mb-3 font-medium">{preview.subject}</div>
            <pre className="rounded-xl border bg-background/50 p-4 font-sans text-sm leading-relaxed whitespace-pre-wrap">{preview.body}</pre>
          </Panel>
        )}

        <div className="space-y-6">
          <Panel title={<span className="flex items-center gap-2"><Braces className="size-4" />Merge fields</span>}>
            <div className="flex flex-wrap gap-1.5">
              {tpl.merge_fields.map((f) => <code key={f} className="rounded-md bg-muted px-1.5 py-0.5 text-xs">{f}</code>)}
            </div>
            <p className="mt-3 text-xs text-muted-foreground">
              Values come from the case, the employee and organisation settings. Anything that can&apos;t be filled shows
              as [MISSING: field] and blocks sending.
            </p>
          </Panel>
          <Panel title="Delivery">
            <ul className="space-y-1 text-sm">
              <li>{tpl.send_to_personal ? "Sent to the personal email (falls back to work email)" : "Sent to the work email"}</li>
              <li>{tpl.attach_pdf ? "Letter attached as PDF" : "No PDF attachment"}</li>
              {tpl.attach_pdf && <li>{tpl.encrypt_attachment ? "PDF password-protected; password sent in a separate email" : "PDF not password-protected"}</li>}
            </ul>
          </Panel>
          <Panel title="Versions">
            <ul className="divide-y text-sm">
              {versions.map((v) => (
                <li key={v.id} className="flex items-center gap-3 py-2">
                  <Link href={`/notices/templates/${v.id}`} className={v.id === tpl.id ? "font-medium" : "hover:text-primary"}>v{v.version}</Link>
                  <span className="text-xs text-muted-foreground">{v.created_by}</span>
                  <span className="ml-auto"><TemplateStatusPill status={v.status} /></span>
                </li>
              ))}
            </ul>
          </Panel>
        </div>
      </div>
    </div>
  );
}

export default function TemplatePage() {
  return <Suspense><TemplateDetail /></Suspense>;
}
