import {
  Activity, FileText, Gauge, Handshake, LayoutDashboard, Mail, Plug, Scale, ScrollText, ShieldAlert, UserCog,
  UsersRound, Wallet, type LucideIcon,
} from "lucide-react";
import type { Role } from "@/lib/api";

export type NavItem = { href: string; label: string; icon: LucideIcon; roles: Role[] };

/** Signed-in staff navigation, grouped. Admin passes every role check. */
export const NAV_GROUPS: { label: string; items: NavItem[] }[] = [
  {
    label: "Workspace",
    items: [{ href: "/dashboard", label: "Home", icon: LayoutDashboard,
      roles: ["hr", "manager", "legal", "finance", "approver", "viewer"] }],
  },
  {
    label: "Decide",
    items: [
      { href: "/people", label: "People", icon: UsersRound, roles: ["hr", "manager", "legal", "finance", "approver", "viewer"] },
      { href: "/performance", label: "Performance", icon: Activity, roles: ["hr", "legal", "manager"] },
      { href: "/plans", label: "Reduction plans", icon: FileText, roles: ["hr", "legal", "finance", "approver", "viewer"] },
      { href: "/kpis", label: "KPI library", icon: Gauge, roles: ["hr", "legal", "finance", "approver", "viewer"] },
    ],
  },
  {
    label: "Act",
    items: [
      { href: "/notices", label: "Notices", icon: Mail, roles: ["hr", "legal", "approver"] },
      { href: "/cases", label: "Exit cases", icon: Handshake, roles: ["hr", "manager", "legal", "finance", "approver", "viewer"] },
      { href: "/fnf", label: "FNF", icon: Wallet, roles: ["hr", "finance", "legal"] },
      { href: "/grievances", label: "Grievances", icon: ShieldAlert, roles: ["hr", "legal"] },
    ],
  },
  {
    label: "Govern",
    items: [
      { href: "/rules", label: "Jurisdiction rules", icon: Scale, roles: ["legal", "hr", "finance", "approver"] },
      { href: "/audit", label: "Audit log", icon: ScrollText, roles: ["legal"] },
      { href: "/integrations", label: "Integrations", icon: Plug, roles: [] },
      { href: "/users", label: "Team & access", icon: UserCog, roles: [] },
    ],
  },
];

export const NAV: NavItem[] = NAV_GROUPS.flatMap((g) => g.items);
