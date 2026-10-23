"use client";

import { ArrowRight, Calculator, History, KeyRound, LoaderCircle, ShieldCheck } from "lucide-react";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { ErrorText } from "@/components/common";
import { Logo, StackedLogo } from "@/components/logo";
import { ThemeToggle } from "@/components/theme";
import { useAuth } from "@/components/auth";
import { api, post, type LoginResult, type Me } from "@/lib/api";

// Seeded development accounts (apps/api/app/cli.py). Shown only in development builds.
const DEMO = [
  { email: "hr@democorp.in", role: "HR" },
  { email: "manager@democorp.in", role: "Manager" },
  { email: "legal@democorp.in", role: "Legal" },
  { email: "finance@democorp.in", role: "Finance" },
  { email: "approver@democorp.in", role: "Approver" },
  { email: "admin@democorp.in", role: "Admin" },
  { email: "viewer@democorp.in", role: "Viewer" },
];
const IS_DEV = process.env.NODE_ENV === "development";

function LoginForm() {
  const router = useRouter();
  const params = useSearchParams();
  const { refresh, me } = useAuth();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [code, setCode] = useState("");
  const [step, setStep] = useState<"credentials" | "mfa">(params.get("mfa") ? "mfa" : "credentials");
  const [enrol, setEnrol] = useState<LoginResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  function go(m: Me | null) {
    if (!m) return;
    if (m.kind === "employee") return router.replace("/me/case");
    const next = params.get("next");
    router.replace(next && next.startsWith("/") && !next.startsWith("/login") && next !== "/" ? next : "/dashboard");
  }

  async function verify(value: string) {
    setBusy(true);
    setError(null);
    try {
      await post("/auth/mfa/verify", { code: value });
      go(await refresh());
    } catch (err) {
      setError((err as Error).message);
      setBusy(false);
    }
  }

  async function devCode(forEmail: string) {
    const r = await api<{ code: string }>(`/dev/totp?email=${encodeURIComponent(forEmail)}`);
    return r.code;
  }

  async function signIn(e: string, p: string, autoMfa = false) {
    setBusy(true);
    setError(null);
    try {
      const r = await post<LoginResult>("/auth/login", { email: e, password: p });
      if (r.mfa_required) {
        setEnrol(r.mfa_enrolled ? null : r);
        setStep("mfa");
        setBusy(false);
        if (autoMfa) await verify(await devCode(e));
        return;
      }
      go(await refresh());
    } catch (err) {
      setError((err as Error).message);
      setBusy(false);
    }
  }

  return (
    <div className="glass w-full max-w-sm rounded-3xl p-8 animate-fade-up">
      <StackedLogo height={92} className="mx-auto mb-6 block w-fit" />
      {step === "credentials" ? (
        <>
          <h1 className="text-2xl font-semibold tracking-tight">Welcome back</h1>
          <p className="mt-1 text-sm text-muted-foreground">Sign in to your organisation&apos;s workspace.</p>
          <form onSubmit={(e) => { e.preventDefault(); void signIn(email, password); }} className="mt-6 space-y-4">
            <div className="space-y-1.5">
              <Label htmlFor="email">Email</Label>
              <Input id="email" type="email" autoComplete="username" required value={email} className="h-10 rounded-xl"
                     onChange={(e) => setEmail(e.target.value)} />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="password">Password</Label>
              <Input id="password" type="password" autoComplete="current-password" required value={password}
                     className="h-10 rounded-xl" onChange={(e) => setPassword(e.target.value)} />
            </div>
            <ErrorText error={error} />
            <Button type="submit" disabled={busy} className="group h-10 w-full gap-2 rounded-xl">
              {busy ? <LoaderCircle className="size-4 animate-spin" /> : <>Sign in <ArrowRight className="size-4 transition-transform group-hover:translate-x-0.5" /></>}
            </Button>
          </form>
          {IS_DEV && (
            <div className="mt-6 border-t pt-5">
              <div className="mb-2 text-xs text-muted-foreground">Demo accounts (development only)</div>
              <div className="flex flex-wrap gap-2">
                {DEMO.map((d) => (
                  <button key={d.email} type="button" disabled={busy} onClick={() => void signIn(d.email, "unlink-demo", true)}
                          className="rounded-full border bg-background/50 px-3 py-1 text-xs transition-colors hover:border-primary hover:text-primary">
                    {d.role}
                  </button>
                ))}
              </div>
            </div>
          )}
        </>
      ) : (
        <>
          <h1 className="flex items-center gap-2 text-2xl font-semibold tracking-tight"><KeyRound className="size-5 text-primary" />Verify it&apos;s you</h1>
          {enrol?.qr_svg ? (
            <div className="mt-3 space-y-3 text-sm text-muted-foreground">
              <p>Your role requires two-step sign-in. Scan this code with an authenticator app, then enter the 6-digit code.</p>
              <div className="mx-auto w-44 rounded-xl bg-white p-2" dangerouslySetInnerHTML={{ __html: enrol.qr_svg }} />
              <p className="text-center font-mono text-xs break-all">{enrol.secret}</p>
            </div>
          ) : (
            <p className="mt-1 text-sm text-muted-foreground">Enter the 6-digit code from your authenticator app.</p>
          )}
          <form onSubmit={(e) => { e.preventDefault(); void verify(code); }} className="mt-5 space-y-4">
            <div className="space-y-1.5">
              <Label htmlFor="code">Authentication code</Label>
              <Input id="code" inputMode="numeric" autoComplete="one-time-code" maxLength={8} required value={code}
                     className="h-11 rounded-xl text-center font-mono text-lg tracking-[0.4em]"
                     onChange={(e) => setCode(e.target.value.replace(/\D/g, ""))} />
            </div>
            <ErrorText error={error} />
            <Button type="submit" disabled={busy || code.length < 6} className="h-10 w-full rounded-xl">
              {busy ? <LoaderCircle className="size-4 animate-spin" /> : "Verify"}
            </Button>
            {IS_DEV && (me?.email || email) && (
              <button type="button" className="w-full text-xs text-muted-foreground underline-offset-4 hover:underline"
                      onClick={async () => setCode(await devCode(me?.email || email))}>
                Fill the current code (development only)
              </button>
            )}
          </form>
        </>
      )}
    </div>
  );
}

export default function LoginPage() {
  return (
    <div className="relative grid min-h-screen lg:grid-cols-2">
      <section className="relative hidden flex-col justify-between overflow-hidden border-r bg-muted/30 p-10 lg:flex">
        <Logo />
        <div className="max-w-md space-y-6">
          <h2 className="text-4xl leading-tight font-semibold tracking-tight text-balance">
            Every decision explained. Every step approved. Every change on record.
          </h2>
          {[
            { icon: Calculator, t: "Deterministic, explainable selection" },
            { icon: ShieldCheck, t: "Protected people can never be selected or exited" },
            { icon: History, t: "Hash-chained audit trail with reasons" },
          ].map(({ icon: Icon, t }) => (
            <div key={t} className="flex items-center gap-3 text-sm text-muted-foreground">
              <span className="grid size-8 place-items-center rounded-lg border bg-background"><Icon className="size-4" /></span>
              {t}
            </div>
          ))}
        </div>
        <p className="text-xs text-muted-foreground">Nothing reaches an employee without a person approving it first.</p>
      </section>
      <section className="relative flex flex-col items-center justify-center gap-8 p-6">
        <div className="absolute top-4 right-4"><ThemeToggle /></div>
        <Suspense>
          <LoginForm />
        </Suspense>
      </section>
    </div>
  );
}
