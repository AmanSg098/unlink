"use client";

import { Bell } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { relTime } from "@/components/kit";
import { useQuery } from "@/lib/use-query";
import { post, type Notification } from "@/lib/api";
import { cn } from "@/lib/utils";

export function NotificationBell() {
  const q = useQuery<{ unread: number; items: Notification[] }>("/notifications");
  const [open, setOpen] = useState(false);
  const unread = q.data?.unread ?? 0;

  return (
    <div className="relative">
      <Button variant="ghost" size="icon" aria-label={`Notifications${unread ? ` (${unread} unread)` : ""}`}
              onClick={() => { setOpen((o) => !o); q.reload(); }}>
        <Bell className="size-4" />
        {unread > 0 && (
          <span className="absolute top-1 right-1 grid min-w-4 place-items-center rounded-full bg-primary px-1 text-[10px] font-semibold text-primary-foreground">
            {unread}
          </span>
        )}
      </Button>
      {open && (
        <>
          <button className="fixed inset-0 z-30 cursor-default" aria-label="Close notifications" onClick={() => setOpen(false)} />
          <div className="absolute right-0 z-40 mt-2 w-80 overflow-hidden rounded-xl border bg-popover shadow-xl">
            <div className="flex items-center justify-between border-b px-3 py-2 text-sm font-medium">
              Notifications
              {unread > 0 && (
                <button className="text-xs text-muted-foreground hover:text-foreground"
                        onClick={async () => { await post("/notifications/read-all"); q.reload(); }}>
                  Mark all read
                </button>
              )}
            </div>
            <ul className="max-h-96 overflow-y-auto">
              {(q.data?.items ?? []).map((n) => (
                <li key={n.id}>
                  <Link href={n.link ?? "/dashboard"} onClick={async () => { setOpen(false); await post(`/notifications/${n.id}/read`); q.reload(); }}
                        className={cn("block px-3 py-2.5 text-sm hover:bg-muted/50", !n.read_at && "bg-primary/5")}>
                    <div className={cn(!n.read_at && "font-medium")}>{n.title}</div>
                    <div className="text-xs text-muted-foreground">{relTime(n.created_at)}</div>
                  </Link>
                </li>
              ))}
              {q.data?.items.length === 0 && <li className="px-3 py-6 text-center text-sm text-muted-foreground">Nothing yet</li>}
            </ul>
          </div>
        </>
      )}
    </div>
  );
}
