"use client";

import { useRouter } from "next/navigation";
import { toast } from "sonner";
import { PageHeader } from "@/components/kit";
import { PlanForm } from "@/components/plan-form";
import { post, type Plan } from "@/lib/api";

export default function NewPlanPage() {
  const router = useRouter();
  return (
    <div className="space-y-8">
      <PageHeader eyebrow="Reduction plans" title="New reduction plan"
                  description="Nothing is decided here. Saving creates a draft you can run, review and change before submitting it for approval." />
      <PlanForm submitLabel="Create draft" onCancel={() => router.push("/plans")}
                onSubmit={async (v) => {
                  const p = await post<Plan>("/plans", v);
                  toast.success("Draft plan created");
                  router.push(`/plans/${p.id}`);
                }} />
    </div>
  );
}
