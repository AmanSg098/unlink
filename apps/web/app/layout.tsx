import type { Metadata } from "next";
import { Suspense } from "react";
import { Geist, Geist_Mono } from "next/font/google";
import { AuthProvider } from "@/components/auth";
import { THEME_SCRIPT } from "@/components/theme";
import { Toaster } from "@/components/toaster";
import "./globals.css";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: { default: "Unlink", template: "%s · Unlink" },
  description: "Explainable, auditable workforce reduction planning. Unlink plans; people decide.",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en" className={`${geistSans.variable} ${geistMono.variable} dark h-full`} suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: THEME_SCRIPT }} />
      </head>
      <body className="min-h-full">
        <Suspense>
          <AuthProvider>
            {children}
            <Toaster />
          </AuthProvider>
        </Suspense>
      </body>
    </html>
  );
}
