import { TriangleAlert } from "lucide-react";

export function ErrorText({ error }: { error: string | null | undefined }) {
  if (!error) return null;
  return (
    <p role="alert" className="flex items-start gap-2 rounded-xl border px-3 py-2 text-sm"
       style={{ borderColor: "color-mix(in oklab, var(--status-critical) 40%, transparent)",
                background: "color-mix(in oklab, var(--status-critical) 10%, transparent)" }}>
      <TriangleAlert className="mt-0.5 size-4 shrink-0 text-[var(--status-critical)]" aria-hidden="true" />
      <span>{error}</span>
    </p>
  );
}

export function fmtDate(iso: string | null | undefined) {
  if (!iso) return "-";
  return new Date(iso).toLocaleString("en-IN", { dateStyle: "medium", timeStyle: "short" });
}

/** Shared table styles so every list in the app reads the same. */
export const tableCls = {
  table: "w-full text-sm",
  thead: "text-left text-xs text-muted-foreground",
  th: "px-4 py-3 font-medium",
  tr: "border-b border-border/60 transition-colors last:border-0 hover:bg-muted/30",
  td: "px-4 py-3",
};
