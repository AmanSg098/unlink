"use client";

import { Toaster as Sonner } from "sonner";
import { useTheme } from "@/components/theme";

export function Toaster() {
  const { theme } = useTheme();
  return <Sonner theme={theme} position="bottom-right" richColors closeButton
                 toastOptions={{ classNames: { toast: "!rounded-xl !border-border" } }} />;
}
