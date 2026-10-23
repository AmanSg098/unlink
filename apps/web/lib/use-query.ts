"use client";

import { useCallback, useEffect, useState } from "react";
import { api } from "@/lib/api";
import { useAuth } from "@/components/auth";

type State<T> = { key: string; data?: T; error: string | null };

/** Minimal fetch-on-mount hook; re-runs when the path or signed-in user changes. */
export function useQuery<T>(path: string | null) {
  const { me } = useAuth();
  // Fetch only once fully signed in (an unfinished MFA step would 401 and sign the user out).
  const signedIn = !!me && (me.kind === "employee" || !me.mfa_required || me.mfa_verified);
  const [tick, setTick] = useState(0);
  const key = `${me?.id}|${path}|${tick}`;
  const [state, setState] = useState<State<T>>({ key: "", error: null });

  useEffect(() => {
    if (!signedIn || path === null) return;
    let cancelled = false;
    api<T>(path)
      .then((data) => !cancelled && setState({ key, data, error: null }))
      .catch((e: Error) => !cancelled && setState((p) => ({ key, data: p.data, error: e.message })));
    return () => {
      cancelled = true;
    };
  }, [key, path, signedIn]);

  const reload = useCallback(() => setTick((t) => t + 1), []);
  return { data: state.data, error: state.error, loading: state.key !== key, reload };
}
