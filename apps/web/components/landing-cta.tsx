"use client";

import { ArrowRight } from "lucide-react";
import Link from "next/link";
import { buttonVariants } from "@/components/ui/button";
import { useAuth } from "@/components/auth";
import { cn } from "@/lib/utils";

/** Primary call to action: "Open dashboard" when signed in, otherwise "Sign in". */
export function LandingCta({ size = "lg", className }: { size?: "default" | "lg"; className?: string }) {
  const { me } = useAuth();
  return (
    <Link href={me ? "/dashboard" : "/login"}
          className={cn(buttonVariants({ size }), "group gap-2 rounded-xl px-5", className)}>
      {me ? "Open dashboard" : "Sign in"}
      <ArrowRight className="size-4 transition-transform group-hover:translate-x-0.5" />
    </Link>
  );
}
