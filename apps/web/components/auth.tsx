"use client";

import { usePathname, useRouter } from "next/navigation";
import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { UNAUTHORIZED_EVENT, api, post, type Me, type Role } from "@/lib/api";

type AuthCtx = {
  me: Me | null;
  /** True once the first /auth/me check has finished (signed in or not). */
  ready: boolean;
  refresh: () => Promise<Me | null>;
  logout: () => Promise<void>;
  /** Staff with one of these roles (admin always passes). */
  can: (...roles: Role[]) => boolean;
};

const AuthContext = createContext<AuthCtx | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [me, setMe] = useState<Me | null>(null);
  const [ready, setReady] = useState(false);
  const router = useRouter();

  const refresh = useCallback(async () => {
    try {
      const m = await api<Me>("/auth/me");
      setMe(m);
      return m;
    } catch {
      setMe(null);
      return null;
    } finally {
      setReady(true);
    }
  }, []);

  useEffect(() => {
    let cancelled = false;
    api<Me>("/auth/me")
      .then((m) => !cancelled && setMe(m))
      .catch(() => !cancelled && setMe(null))
      .finally(() => !cancelled && setReady(true));
    // Any 401 from the API means the session ended (or MFA is pending); guards then redirect.
    const onUnauthorized = () => setMe(null);
    window.addEventListener(UNAUTHORIZED_EVENT, onUnauthorized);
    return () => {
      cancelled = true;
      window.removeEventListener(UNAUTHORIZED_EVENT, onUnauthorized);
    };
  }, []);

  const logout = useCallback(async () => {
    await post("/auth/logout").catch(() => {});
    setMe(null);
    router.push("/login");
  }, [router]);

  const can = useCallback(
    (...roles: Role[]) => !!me && me.kind === "staff" && (me.role === "admin" || roles.includes(me.role as Role)),
    [me],
  );

  const value = useMemo(() => ({ me, ready, refresh, logout, can }), [me, ready, refresh, logout, can]);
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth outside AuthProvider");
  return ctx;
}

function Spinner() {
  return (
    <div className="grid min-h-[60vh] place-items-center">
      <span className="size-6 animate-spin rounded-full border-2 border-muted border-t-primary" />
    </div>
  );
}

/** Staff-only pages. Signed-out users go to /login; MFA-pending staff finish MFA there; employees go to /me/case.
 *  The page is always rendered (just hidden) so Next.js can still prerender and validate the segment. */
export function RequireAuth({ children }: { children: React.ReactNode }) {
  const { me, ready } = useAuth();
  const pathname = usePathname();
  const router = useRouter();
  const ok = !!me && me.kind === "staff" && (!me.mfa_required || me.mfa_verified);

  useEffect(() => {
    if (!ready) return;
    if (!me) router.replace(`/login?next=${encodeURIComponent(pathname)}`);
    else if (me.kind === "employee") router.replace("/me/case");
    else if (me.mfa_required && !me.mfa_verified) router.replace(`/login?mfa=1&next=${encodeURIComponent(pathname)}`);
  }, [ready, me, pathname, router]);

  return (
    <>
      {!ok && <Spinner />}
      <div hidden={!ok}>{children}</div>
    </>
  );
}

/** Employee self-service pages. */
export function RequireEmployee({ children }: { children: React.ReactNode }) {
  const { me, ready } = useAuth();
  const router = useRouter();
  const ok = !!me && me.kind === "employee";

  useEffect(() => {
    if (!ready) return;
    if (!me) router.replace("/login?next=/me/case");
    else if (me.kind === "staff") router.replace("/dashboard");
  }, [ready, me, router]);

  return (
    <>
      {!ok && <Spinner />}
      <div hidden={!ok}>{children}</div>
    </>
  );
}
