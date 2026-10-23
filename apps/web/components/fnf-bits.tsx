import { Ban, CircleCheck, CircleDashed, CircleX, Hourglass, Wallet } from "lucide-react";
import type { PillSpec } from "@/components/form-bits";

export const FNF_STATUS: Record<string, PillSpec> = {
  draft: { label: "Draft", icon: CircleDashed, color: "var(--viz-muted)" },
  submitted: { label: "In approval", icon: Hourglass, color: "var(--status-warning)" },
  approved: { label: "Approved", icon: CircleCheck, color: "var(--status-good)" },
  rejected: { label: "Rejected", icon: CircleX, color: "var(--status-critical)" },
  superseded: { label: "Superseded", icon: Ban, color: "var(--viz-muted)" },
  paid: { label: "Paid", icon: Wallet, color: "var(--status-good)" },
};
