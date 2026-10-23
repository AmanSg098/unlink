"use client";

import { CornerDownLeft, FileText, LogOut, Moon, Plus, Search, type LucideIcon } from "lucide-react";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import { Dialog, DialogContent, DialogTitle } from "@/components/ui/dialog";
import { StatusPill } from "@/components/kit";
import { useTheme } from "@/components/theme";
import { useAuth } from "@/components/auth";
import { NAV } from "@/lib/nav";
import { useQuery } from "@/lib/use-query";
import { cn } from "@/lib/utils";
import type { Plan } from "@/lib/api";

type Item = { id: string; group: string; label: string; icon: LucideIcon; hint?: React.ReactNode; run: () => void };

export function useCommandPalette() {
  const [open, setOpen] = useState(false);
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setOpen((o) => !o);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);
  return { open, setOpen };
}

export function CommandPalette({ open, setOpen }: { open: boolean; setOpen: (o: boolean) => void }) {
  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogContent className="top-[18%] translate-y-0 gap-0 overflow-hidden p-0 sm:max-w-xl" showCloseButton={false}>
        <DialogTitle className="sr-only">Command palette</DialogTitle>
        {open && <PaletteBody close={() => setOpen(false)} />}
      </DialogContent>
    </Dialog>
  );
}

function PaletteBody({ close }: { close: () => void }) {
  const router = useRouter();
  const { can, logout } = useAuth();
  const { toggle } = useTheme();
  const plans = useQuery<Plan[]>(can("hr", "legal", "finance", "approver", "viewer") ? "/plans" : null);
  const [q, setQ] = useState("");
  const [active, setActive] = useState(0);

  const items = useMemo<Item[]>(() => {
    const go = (href: string) => () => { close(); router.push(href); };
    const all: Item[] = [
      ...(can("hr") ? [{ id: "new", group: "Actions", label: "New reduction plan", icon: Plus, run: go("/plans/new") }] : []),
      ...NAV.filter((n) => can(...n.roles))
        .map((n) => ({ id: n.href, group: "Go to", label: n.label, icon: n.icon, run: go(n.href) })),
      ...(plans.data ?? []).map((p) => ({
        id: `p${p.id}`, group: "Plans", label: p.name, icon: FileText, hint: <StatusPill status={p.status} />,
        run: go(`/plans/${p.id}`),
      })),
      { id: "theme", group: "Actions", label: "Toggle light / dark", icon: Moon, run: () => { toggle(); close(); } },
      { id: "logout", group: "Actions", label: "Sign out", icon: LogOut, run: () => { close(); void logout(); } },
    ];
    const needle = q.trim().toLowerCase();
    return needle ? all.filter((i) => i.label.toLowerCase().includes(needle)) : all;
  }, [q, plans.data, can, close, router, toggle, logout]);

  const sel = Math.min(active, Math.max(items.length - 1, 0));
  let lastGroup = "";

  return (
    <div onKeyDown={(e) => {
      if (e.key === "ArrowDown") { e.preventDefault(); setActive((sel + 1) % Math.max(items.length, 1)); }
      if (e.key === "ArrowUp") { e.preventDefault(); setActive((sel - 1 + items.length) % Math.max(items.length, 1)); }
      if (e.key === "Enter") { e.preventDefault(); items[sel]?.run(); }
    }}>
      <div className="flex items-center gap-2 border-b px-4">
        <Search className="size-4 text-muted-foreground" />
        <input autoFocus value={q} onChange={(e) => { setQ(e.target.value); setActive(0); }}
               placeholder="Search plans, pages, actions…"
               className="h-12 flex-1 bg-transparent text-sm outline-none placeholder:text-muted-foreground" />
        <kbd className="rounded-md border bg-muted px-1.5 font-mono text-[10px] text-muted-foreground">esc</kbd>
      </div>
      <div className="max-h-80 overflow-y-auto p-2" role="listbox">
        {items.length === 0 && <p className="py-8 text-center text-sm text-muted-foreground">Nothing matches.</p>}
        {items.map((it, i) => {
          const header = it.group !== lastGroup ? it.group : null;
          lastGroup = it.group;
          return (
            <div key={it.id}>
              {header && <div className="px-2 pt-2 pb-1 text-[11px] font-medium tracking-wide text-muted-foreground uppercase">{header}</div>}
              <button role="option" aria-selected={i === sel} onMouseEnter={() => setActive(i)} onClick={it.run}
                      className={cn("flex w-full items-center gap-3 rounded-lg px-2 py-2 text-left text-sm",
                                    i === sel ? "bg-accent text-accent-foreground" : "text-foreground/90")}>
                <it.icon className="size-4 text-muted-foreground" />
                <span className="flex-1 truncate">{it.label}</span>
                {it.hint}
                {i === sel && <CornerDownLeft className="size-3.5 text-muted-foreground" />}
              </button>
            </div>
          );
        })}
      </div>
    </div>
  );
}
