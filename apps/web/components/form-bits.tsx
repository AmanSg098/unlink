"use client";

import { useCallback, useState } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Label } from "@/components/ui/label";
import { ErrorText } from "@/components/common";
import type { Pill } from "@/components/kit";
import { api, type Employee } from "@/lib/api";
import { cn } from "@/lib/utils";

export type PillSpec = React.ComponentProps<typeof Pill>["spec"];

/** Label + control, stacked. */
export function Field({ label, htmlFor, hint, className, children }: {
  label: string; htmlFor?: string; hint?: React.ReactNode; className?: string; children: React.ReactNode;
}) {
  return (
    <div className={cn("space-y-1.5", className)}>
      <Label htmlFor={htmlFor}>{label}</Label>
      {children}
      {hint && <p className="text-xs text-muted-foreground">{hint}</p>}
    </div>
  );
}

export const selectCls = "h-9 w-full rounded-xl border bg-background/50 px-3 text-sm";

export function Select({ value, onChange, options, className, ...rest }: {
  value: string; onChange: (v: string) => void; options: (string | [string, string])[]; className?: string;
} & Omit<React.SelectHTMLAttributes<HTMLSelectElement>, "value" | "onChange">) {
  return (
    <select className={cn(selectCls, className)} value={value} onChange={(e) => onChange(e.target.value)} {...rest}>
      {options.map((o) => {
        const [v, l] = typeof o === "string" ? [o, o] : o;
        return <option key={v} value={v}>{l}</option>;
      })}
    </select>
  );
}

/** Runs an async action with a busy flag; errors land in `error` (and optionally a toast). */
export function useAction() {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const run = useCallback(async (fn: () => Promise<unknown>, success?: string) => {
    setBusy(true);
    setError(null);
    try {
      await fn();
      if (success) toast.success(success);
      return true;
    } catch (e) {
      setError((e as Error).message);
      return false;
    } finally {
      setBusy(false);
    }
  }, []);
  return { busy, error, setError, run };
}

/** A controlled dialog wrapping a form; `onSubmit` returning true closes it. */
export function FormDialog({ open, onOpenChange, title, description, submitLabel = "Save", destructive, wide,
                             onSubmit, children }: {
  open: boolean; onOpenChange: (o: boolean) => void; title: string; description?: React.ReactNode;
  submitLabel?: string; destructive?: boolean; wide?: boolean;
  onSubmit: () => Promise<unknown>; children?: React.ReactNode;
}) {
  const { busy, error, setError, run } = useAction();
  return (
    <Dialog open={open} onOpenChange={(o) => { if (!o) setError(null); onOpenChange(o); }}>
      <DialogContent className={cn("max-h-[90vh] overflow-y-auto rounded-2xl", wide ? "sm:max-w-2xl" : "sm:max-w-lg")}>
        <DialogHeader>
          <DialogTitle>{title}</DialogTitle>
          {description && <DialogDescription>{description}</DialogDescription>}
        </DialogHeader>
        <form className="space-y-4" onSubmit={async (e) => {
          e.preventDefault();
          if (await run(onSubmit)) onOpenChange(false);
        }}>
          {children}
          <ErrorText error={error} />
          <div className="flex justify-end gap-2">
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>Cancel</Button>
            <Button type="submit" disabled={busy} variant={destructive ? "destructive" : "default"}>
              {busy ? "Working…" : submitLabel}
            </Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  );
}

/** Find one visible employee by exact employee ID. */
export async function findEmployee(code: string): Promise<Employee> {
  const c = code.trim();
  const list = await api<Employee[]>(`/employees?q=${encodeURIComponent(c)}`);
  const e = list.find((x) => x.employee_code.toLowerCase() === c.toLowerCase());
  if (!e) throw new Error(`No employee with ID ${c} that you can see`);
  return e;
}

/** Fetch a file through the session cookie and save it. */
export async function download(path: string, filename: string) {
  const res = await fetch(`/api${path}`, { credentials: "same-origin" });
  if (!res.ok) {
    const body = await res.json().catch(() => null);
    throw new Error((body as { detail?: string })?.detail ?? "Download failed");
  }
  const url = URL.createObjectURL(await res.blob());
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

export const today = () => new Date().toISOString().slice(0, 10);

/** "partially_met" -> "Partially met". */
export const humanize = (s: string | null | undefined) =>
  s ? s.charAt(0).toUpperCase() + s.slice(1).replace(/_/g, " ") : "–";

/** Definition list item. */
export function Detail({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="min-w-0">
      <dt className="text-xs text-muted-foreground">{label}</dt>
      <dd className="mt-0.5 truncate text-sm">{children}</dd>
    </div>
  );
}
