"use client";

import { CircleCheck, LoaderCircle } from "lucide-react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";
import { Button, buttonVariants } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { ErrorText } from "@/components/common";
import { StackedLogo } from "@/components/logo";
import { post } from "@/lib/api";
import { cn } from "@/lib/utils";

function ActivateForm() {
  const token = useSearchParams().get("token") ?? "";
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [done, setDone] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (password !== confirm) return setError("The two passwords don't match");
    setBusy(true);
    setError(null);
    try {
      const r = await post<{ email: string }>("/auth/activate", { token, password });
      setDone(r.email);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  if (done) {
    return (
      <div className="space-y-4 text-center">
        <CircleCheck className="mx-auto size-8 text-[var(--status-good)]" />
        <h1 className="text-xl font-semibold">Your account is ready</h1>
        <p className="text-sm text-muted-foreground">Sign in with <span className="font-medium text-foreground">{done}</span> and the password you just set.</p>
        <Link href="/login" className={cn(buttonVariants(), "w-full rounded-xl")}>Sign in</Link>
      </div>
    );
  }

  if (!token) {
    return <ErrorText error="This link is missing its invitation code. Open the link from your email again, or ask HR for a new one." />;
  }

  return (
    <>
      <h1 className="text-2xl font-semibold tracking-tight">Set your password</h1>
      <p className="mt-1 text-sm text-muted-foreground">
        This gives you private access to your letters, documents and settlement, and lets you raise a concern.
      </p>
      <form onSubmit={submit} className="mt-6 space-y-4">
        <div className="space-y-1.5">
          <Label htmlFor="pw">New password (10+ characters)</Label>
          <Input id="pw" type="password" autoComplete="new-password" minLength={10} required value={password}
                 className="h-10 rounded-xl" onChange={(e) => setPassword(e.target.value)} />
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="pw2">Confirm password</Label>
          <Input id="pw2" type="password" autoComplete="new-password" minLength={10} required value={confirm}
                 className="h-10 rounded-xl" onChange={(e) => setConfirm(e.target.value)} />
        </div>
        <ErrorText error={error} />
        <Button type="submit" disabled={busy} className="h-10 w-full rounded-xl">
          {busy ? <LoaderCircle className="size-4 animate-spin" /> : "Activate account"}
        </Button>
      </form>
    </>
  );
}

export default function ActivatePage() {
  return (
    <div className="grid min-h-screen place-items-center p-6">
      <div className="glass w-full max-w-sm rounded-3xl p-8">
        <StackedLogo height={80} className="mx-auto mb-6 block w-fit" />
        <Suspense>
          <ActivateForm />
        </Suspense>
      </div>
    </div>
  );
}
