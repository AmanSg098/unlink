"use client";

import { ArrowLeft, Pencil, Sparkles, TriangleAlert } from "lucide-react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { Suspense, useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { ErrorText, fmtDate } from "@/components/common";
import { AiDraftCard } from "@/components/ai-draft";
import { Hash, useAct } from "@/components/case-ui";
import { DraftStatusPill } from "@/components/notice-ui";
import { PageHeader, Panel } from "@/components/kit";
import { useAuth } from "@/components/auth";
import { useQuery } from "@/lib/use-query";
import { api, patch, post, type AiDraft, type Draft } from "@/lib/api";

function DraftDetail() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const { can } = useAuth();
  const q = useQuery<Draft>(`/notice-drafts/${id}`);
  const d = q.data;
  const aiDrafts = useQuery<AiDraft[]>(d && can("hr", "legal") ? `/exit-cases/${d.exit_case_id}/ai/drafts` : null);
  const [editing, setEditing] = useState<{ subject: string; body: string } | null>(null);
  const { busy, run } = useAct();

  if (!d) return <ErrorText error={q.error} />;
  const editable = can("hr") && (d.status === "draft" || d.status === "in_batch");
  const suggestions = (aiDrafts.data ?? []).filter((a) => a.kind === "notice");

  async function save() {
    const nd = await run(() => patch<Draft>(`/notice-drafts/${d!.id}`, editing), "Saved as a new version");
    if (nd) {
      setEditing(null);
      router.replace(`/notices/drafts/${nd.id}`);
    }
  }

  async function suggest() {
    const r = await run(() => api<AiDraft>(`/exit-cases/${d!.exit_case_id}/ai/notice-draft?template_id=${d!.template_id}`,
                                           { method: "POST" }), "Suggestion ready below");
    if (r) aiDrafts.reload();
  }

  async function applySuggestion(a: AiDraft) {
    const nd = await run(() => post<Draft>(`/exit-cases/${d!.exit_case_id}/ai/drafts/${a.id}/use`),
                         "Suggestion merged into a new draft version. Review it before batching.");
    if (nd) router.replace(`/notices/drafts/${nd.id}`);
  }

  return (
    <div className="space-y-8">
      <Link href="/notices" className="inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground">
        <ArrowLeft className="size-4" />Notices
      </Link>
      <PageHeader
        eyebrow={`${d.template.title} · v${d.template.version}`}
        title={<>Notice for {d.full_name}</>}
        description={<span className="inline-flex flex-wrap items-center gap-2">
          <DraftStatusPill status={d.status} />
          <span>Draft v{d.version} by {d.created_by} · {fmtDate(d.created_at)}</span>
          <Link href={`/cases/${d.exit_case_id}`} className="underline-offset-4 hover:underline">Exit case #{d.exit_case_id}</Link>
        </span>}
        actions={editable && !editing && (
          <Button variant="outline" onClick={() => setEditing({ subject: d.subject, body: d.body ?? "" })}>
            <Pencil className="size-4" />Edit
          </Button>
        )}
      />

      {(d.missing_fields.length > 0 || d.flagged_terms.length > 0) && (
        <Panel title={<span className="flex items-center gap-2"><TriangleAlert className="size-4 text-[var(--status-critical)]" />This draft can&apos;t be sent yet</span>}>
          <ul className="list-disc space-y-1 pl-5 text-sm">
            {d.missing_fields.map((f) => <li key={f}>Missing {f}</li>)}
            {d.flagged_terms.length > 0 && (
              <li>Protected terms in the text: {d.flagged_terms.join(", ")}. Remove them; a notice can&apos;t refer to protected characteristics.</li>
            )}
          </ul>
          <p className="mt-3 text-xs text-muted-foreground">
            Fix missing values at their source (case dates, reason, organisation settings) and prepare the draft again,
            or edit the text directly.
          </p>
        </Panel>
      )}

      <div className="grid gap-6 xl:grid-cols-[1.4fr_1fr]">
        <Panel title="Message" actions={<Hash value={d.content_hash} />}>
          {editing ? (
            <div className="space-y-3">
              <div className="space-y-1.5">
                <Label htmlFor="subject">Subject</Label>
                <Input id="subject" value={editing.subject} onChange={(e) => setEditing({ ...editing, subject: e.target.value })} />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="body">Body</Label>
                <Textarea id="body" rows={18} className="font-mono text-sm" value={editing.body}
                          onChange={(e) => setEditing({ ...editing, body: e.target.value })} />
              </div>
              {d.status === "in_batch" && (
                <p className="text-xs text-muted-foreground">This draft is in a batch. Saving updates the batch and any approval must be given again.</p>
              )}
              <div className="flex gap-2">
                <Button disabled={busy || !editing.subject.trim() || !editing.body.trim()} onClick={save}>Save new version</Button>
                <Button variant="outline" onClick={() => setEditing(null)}>Cancel</Button>
              </div>
            </div>
          ) : (
            <>
              <div className="mb-3 font-medium">{d.subject}</div>
              <pre className="rounded-xl border bg-background/50 p-4 font-sans text-sm leading-relaxed whitespace-pre-wrap">{d.body}</pre>
            </>
          )}
        </Panel>

        <div className="space-y-6">
          {can("hr", "legal") && (
            <Panel title={<span className="flex items-center gap-2"><Sparkles className="size-4 text-primary" />AI wording suggestion</span>}
                   description="Optional. The AI rewrites the template text for readability; it gets no names or pay data, and it never decides anything. Its text only becomes a new draft version when you choose to use it, and it still needs approval like any other draft.">
              <Button variant="outline" disabled={busy || !can("hr", "legal")} onClick={suggest}>
                <Sparkles className="size-4" />Suggest wording
              </Button>
            </Panel>
          )}
          {suggestions.map((a) => (
            <div key={a.id} className="space-y-2">
              <AiDraftCard draft={a} title="Suggested wording" />
              {a.flagged_terms.length > 0 ? (
                <p className="text-xs text-[var(--status-critical)]">Contains protected terms ({a.flagged_terms.join(", ")}); it can&apos;t be used as is.</p>
              ) : editable && (
                <Button size="sm" variant="outline" disabled={busy} onClick={() => applySuggestion(a)}>Use as a new draft version</Button>
              )}
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

export default function DraftPage() {
  return <Suspense><DraftDetail /></Suspense>;
}
