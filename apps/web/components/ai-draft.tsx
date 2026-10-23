"use client";

import { useState } from "react";
import { Sparkles } from "lucide-react";
import { Button } from "@/components/ui/button";
import { fmtDate } from "@/components/common";
import type { AiDraft } from "@/lib/api";

/** Shows an AI draft as plain text with a clear "draft" label and a copy button. */
export function AiDraftCard({ draft, title }: { draft: AiDraft; title: string }) {
  const [copied, setCopied] = useState(false);
  return (
    <div className="glass rounded-2xl p-5 animate-fade-up">
      <div className="mb-2 flex flex-wrap items-center gap-2">
        <Sparkles className="size-4 text-primary" aria-hidden="true" />
        <span className="text-sm font-medium">{title}</span>
        <span className="rounded-full border border-primary/30 bg-primary/10 px-2 py-0.5 text-[11px]">AI draft · review before use</span>
        <span className="text-xs text-muted-foreground">
          {draft.created_by} · {fmtDate(draft.created_at)} · {draft.model}
        </span>
        <Button size="sm" variant="ghost" className="ml-auto" onClick={async () => {
          await navigator.clipboard.writeText(draft.content);
          setCopied(true);
          setTimeout(() => setCopied(false), 1500);
        }}>
          {copied ? "Copied" : "Copy"}
        </Button>
      </div>
      <div className="whitespace-pre-wrap text-sm leading-relaxed">{draft.content}</div>
    </div>
  );
}
