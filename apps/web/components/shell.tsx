"use client";

import { LogOut, Menu, Plus, Search, ShieldCheck, UserRound } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState } from "react";
import { Button, buttonVariants } from "@/components/ui/button";
import { Dialog, DialogContent, DialogTitle } from "@/components/ui/dialog";
import { Avatar } from "@/components/kit";
import { CommandPalette, useCommandPalette } from "@/components/command-palette";
import { NotificationBell } from "@/components/notifications";
import { Logo } from "@/components/logo";
import { ThemeToggle } from "@/components/theme";
import { useAuth } from "@/components/auth";
import { NAV_GROUPS } from "@/lib/nav";
import { cn } from "@/lib/utils";

function isActive(pathname: string, href: string) {
  return pathname === href || pathname.startsWith(`${href}/`);
}

function NavLinks({ onNavigate }: { onNavigate?: () => void }) {
  const pathname = usePathname();
  const { can } = useAuth();
  return (
    <nav className="space-y-5">
      {NAV_GROUPS.map((g) => {
        const items = g.items.filter((n) => can(...n.roles));
        if (!items.length) return null;
        return (
          <div key={g.label}>
            <div className="mb-1 px-3 text-[11px] font-medium tracking-wide text-muted-foreground/80 uppercase">{g.label}</div>
            <div className="space-y-0.5">
              {items.map((n) => {
                const active = isActive(pathname, n.href);
                return (
                  <Link key={n.href} href={n.href} onClick={onNavigate}
                        className={cn("relative flex items-center gap-3 rounded-lg px-3 py-1.5 text-sm transition-colors",
                                      active ? "bg-sidebar-accent font-medium text-foreground"
                                             : "text-muted-foreground hover:bg-sidebar-accent/60 hover:text-foreground")}>
                    {active && <span className="absolute inset-y-1.5 left-0 w-0.5 rounded-full bg-primary" />}
                    <n.icon className={cn("size-4", active && "text-primary")} />
                    {n.label}
                  </Link>
                );
              })}
            </div>
          </div>
        );
      })}
    </nav>
  );
}

function UserCard({ onNavigate }: { onNavigate?: () => void }) {
  const { me, logout } = useAuth();
  if (!me) return null;
  return (
    <div className="flex items-center gap-3 rounded-xl border bg-background/40 p-2.5">
      <Avatar name={me.full_name} />
      <Link href="/account" onClick={onNavigate} className="min-w-0 flex-1">
        <div className="truncate text-sm font-medium">{me.full_name}</div>
        <div className="truncate text-xs text-muted-foreground capitalize">{me.role} · {me.org_name}</div>
      </Link>
      <Button size="icon" variant="ghost" onClick={logout} aria-label="Sign out" title="Sign out">
        <LogOut className="size-4" />
      </Button>
    </div>
  );
}

function SidebarBody({ onNavigate }: { onNavigate?: () => void }) {
  const { can } = useAuth();
  return (
    <div className="flex h-full flex-col gap-5 overflow-y-auto p-4">
      <Logo href="/dashboard" className="px-1" />
      {can("hr") && (
        <Link href="/plans/new" onClick={onNavigate} className={cn(buttonVariants(), "h-9 justify-start gap-2 rounded-xl")}>
          <Plus className="size-4" /> New reduction plan
        </Link>
      )}
      <NavLinks onNavigate={onNavigate} />
      <div className="mt-auto space-y-3">
        <div className="flex items-start gap-2 rounded-xl border border-dashed p-3 text-xs text-muted-foreground">
          <ShieldCheck className="mt-0.5 size-4 shrink-0 text-[var(--status-good)]" />
          <span>Nothing reaches an employee without a person approving it first.</span>
        </div>
        <UserCard onNavigate={onNavigate} />
      </div>
    </div>
  );
}

export function AppShell({ children }: { children: React.ReactNode }) {
  const palette = useCommandPalette();
  const [mobileOpen, setMobileOpen] = useState(false);

  return (
    <div className="relative min-h-screen">
      <aside className="fixed inset-y-0 left-0 z-30 hidden w-64 border-r border-sidebar-border bg-sidebar lg:block">
        <SidebarBody />
      </aside>

      <div className="min-w-0 lg:pl-64">
        <header className="sticky top-0 z-20 border-b border-border/60 bg-background/80 backdrop-blur">
          <div className="flex h-14 items-center gap-2 px-4 md:px-8">
            <Button variant="ghost" size="icon" className="lg:hidden" onClick={() => setMobileOpen(true)} aria-label="Open menu">
              <Menu className="size-5" />
            </Button>
            <Logo href="/dashboard" className="lg:hidden" />
            <button onClick={() => palette.setOpen(true)}
                    className="ml-auto flex h-9 w-full max-w-xs items-center gap-2 rounded-xl border bg-background/50 px-3 text-sm text-muted-foreground transition-colors hover:bg-background/80 lg:ml-0">
              <Search className="size-4" />
              <span className="flex-1 text-left">Jump to…</span>
              <kbd className="hidden rounded-md border bg-muted px-1.5 font-mono text-[10px] sm:inline">⌘K</kbd>
            </button>
            <div className="ml-auto hidden lg:block" />
            <NotificationBell />
            <Link href="/account" className={buttonVariants({ variant: "ghost", size: "icon" })} aria-label="My account">
              <UserRound className="size-4" />
            </Link>
            <ThemeToggle />
          </div>
        </header>
        <main className="mx-auto w-full max-w-7xl px-4 py-8 md:px-8">{children}</main>
      </div>

      <Dialog open={mobileOpen} onOpenChange={setMobileOpen}>
        <DialogContent className="top-0 left-0 h-full max-w-72 translate-x-0 translate-y-0 rounded-none p-0 sm:max-w-72"
                       showCloseButton={false}>
          <DialogTitle className="sr-only">Menu</DialogTitle>
          <SidebarBody onNavigate={() => setMobileOpen(false)} />
        </DialogContent>
      </Dialog>
      <CommandPalette open={palette.open} setOpen={palette.setOpen} />
    </div>
  );
}
