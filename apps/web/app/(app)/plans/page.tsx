"use client";

import { FileText, Plus } from "lucide-react";
import Link from "next/link";
import { buttonVariants } from "@/components/ui/button";
import { ErrorText, tableCls as t } from "@/components/common";
import { EmptyState, PageHeader, Panel, StatusPill, relTime } from "@/components/kit";
import { useAuth } from "@/components/auth";
import { useQuery } from "@/lib/use-query";
import { fmtPaise, type Plan } from "@/lib/api";
import { cn } from "@/lib/utils";

const METHOD_LABEL: Record<Plan["selection_method"], string> = {
  score_ranked: "Score-ranked", role_redundancy: "Role redundancy", manual_list: "Manual list",
};

function target(p: Plan) {
  if (p.selection_method === "role_redundancy") return `${p.eliminated_roles.length} role${p.eliminated_roles.length === 1 ? "" : "s"}`;
  if (p.selection_method === "manual_list") return `${p.manual_codes.length} listed`;
  return [p.target_count && `${p.target_count} people`, p.target_cost_paise && fmtPaise(p.target_cost_paise)]
    .filter(Boolean).join(" · ") || "–";
}

export default function PlansPage() {
  const { can } = useAuth();
  const q = useQuery<Plan[]>("/plans");
  const plans = q.data ?? [];

  return (
    <div className="space-y-8">
      <PageHeader
        eyebrow="Decide"
        title="Reduction plans"
        description="Each plan scores or lists a pool, proposes who is affected, and goes through legal, finance and final approval before any exit case opens."
        actions={can("hr") && (
          <Link href="/plans/new" className={cn(buttonVariants(), "gap-2 rounded-xl")}>
            <Plus className="size-4" />New plan
          </Link>
        )}
      />
      <Panel bodyClassName="p-0">
        <ErrorText error={q.error} />
        {!q.loading && plans.length === 0 ? (
          <EmptyState icon={FileText} title="No plans yet">
            {can("hr") ? "Create a plan to score a pool and see who would be proposed." : "HR hasn't created any plans."}
          </EmptyState>
        ) : (
          <div className="overflow-x-auto">
            <table className={t.table}>
              <thead className={t.thead}>
                <tr className="border-b">
                  <th className={t.th}>Plan</th>
                  <th className={t.th}>Method</th>
                  <th className={t.th}>Target</th>
                  <th className={t.th}>Status</th>
                  <th className={t.th}>Waiting on</th>
                  <th className={t.th}>Last run</th>
                </tr>
              </thead>
              <tbody>
                {plans.map((p) => (
                  <tr key={p.id} className={t.tr}>
                    <td className={t.td}>
                      <Link href={`/plans/${p.id}`} className="font-medium hover:text-primary">{p.name}</Link>
                      <div className="text-xs text-muted-foreground">
                        v{p.version} · by {p.created_by}{p.cases && " · exit cases open"}
                      </div>
                    </td>
                    <td className={t.td}>{METHOD_LABEL[p.selection_method]}</td>
                    <td className={`${t.td} tabular-nums`}>{target(p)}</td>
                    <td className={t.td}><StatusPill status={p.status} /></td>
                    <td className={`${t.td} text-xs text-muted-foreground`}>
                      {p.current_step ? `${p.current_step.step.replace(/_/g, " ")} (${p.current_step.roles.join(" or ")})` : "–"}
                    </td>
                    <td className={`${t.td} text-xs text-muted-foreground`}>{relTime(p.last_run_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Panel>
    </div>
  );
}
