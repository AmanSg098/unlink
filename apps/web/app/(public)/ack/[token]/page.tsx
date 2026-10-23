"use client";

import { CircleCheck, LoaderCircle } from "lucide-react";
import { useParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { ErrorText, fmtDate } from "@/components/common";
import { StackedLogo } from "@/components/logo";
import { api, post } from "@/lib/api";

type Info = { subject: string; company: string; acknowledged_at: string | null };

function Acknowledge() {
  const { token } = useParams<{ token: string }>();
  const [info, setInfo] = useState<Info | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    let cancelled = false;
    api<Info>(`/acknowledge/${encodeURIComponent(token)}`)
      .then((r) => !cancelled && setInfo(r))
      .catch((e: Error) => !cancelled && setError(e.message));
    return () => {
      cancelled = true;
    };
  }, [token]);

  async function confirm() {
    setBusy(true);
    setError(null);
    try {
      const r = await post<{ acknowledged_at: string }>(`/acknowledge/${encodeURIComponent(token)}`);
      setInfo((p) => (p ? { ...p, acknowledged_at: r.acknowledged_at } : p));
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  if (error && !info) return <ErrorText error={error} />;
  if (!info) return <LoaderCircle className="mx-auto size-6 animate-spin text-muted-foreground" />;

  return (
    <div className="space-y-4">
      <div className="text-xs text-muted-foreground">{info.company}</div>
      <h1 className="text-xl font-semibold tracking-tight">{info.subject}</h1>
      {info.acknowledged_at ? (
        <div className="flex items-start gap-3 rounded-xl border p-3 text-sm"
             style={{ borderColor: "color-mix(in oklab, var(--status-good) 45%, transparent)" }}>
          <CircleCheck className="mt-0.5 size-4 shrink-0 text-[var(--status-good)]" aria-hidden="true" />
          <span>Receipt confirmed on {fmtDate(info.acknowledged_at)}. You can close this page.</span>
        </div>
      ) : (
        <>
          <p className="text-sm text-muted-foreground">
            Please confirm that you have received this letter. Confirming receipt does not mean you agree with its
            contents, and it does not affect your right to raise a concern.
          </p>
          <ErrorText error={error} />
          <Button className="h-10 w-full rounded-xl" disabled={busy} onClick={confirm}>
            {busy ? <LoaderCircle className="size-4 animate-spin" /> : "I confirm I received this letter"}
          </Button>
        </>
      )}
    </div>
  );
}

export default function AckPage() {
  return (
    <div className="grid min-h-screen place-items-center p-6">
      <div className="glass w-full max-w-md rounded-3xl p-8">
        <StackedLogo height={72} className="mx-auto mb-6 block w-fit" />
        <Suspense>
          <Acknowledge />
        </Suspense>
      </div>
    </div>
  );
}
