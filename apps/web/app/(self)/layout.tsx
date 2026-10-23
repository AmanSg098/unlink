"use client";

import { LogOut } from "lucide-react";
import { Button } from "@/components/ui/button";
import { RequireEmployee, useAuth } from "@/components/auth";
import { Logo } from "@/components/logo";
import { ThemeToggle } from "@/components/theme";

/** Employee self-service: a deliberately small shell with no staff navigation. */
export default function SelfLayout({ children }: { children: React.ReactNode }) {
  const { me, logout } = useAuth();
  return (
    <div className="min-h-screen">
      <header className="sticky top-0 z-20 border-b border-border/60 bg-background/80 backdrop-blur">
        <div className="mx-auto flex h-14 max-w-4xl items-center gap-3 px-4 md:px-6">
          <Logo href="/me/case" />
          <span className="ml-auto hidden text-sm text-muted-foreground sm:block">{me?.full_name}</span>
          <ThemeToggle />
          <Button size="icon" variant="ghost" onClick={logout} aria-label="Sign out" title="Sign out">
            <LogOut className="size-4" />
          </Button>
        </div>
      </header>
      <main className="mx-auto w-full max-w-4xl px-4 py-8 md:px-6">
        <RequireEmployee>{children}</RequireEmployee>
      </main>
    </div>
  );
}
