import Image from "next/image";
import Link from "next/link";
import { cn } from "@/lib/utils";

// Brand assets live in public/brand (generated from brand/source by brand/process.py).
// The wordmark's lettering is near-black, so dark mode uses a lightened copy.

/** The emblem on its own: compact spots where the wordmark won't fit. */
export function LogoMark({ className, size = 32 }: { className?: string; size?: number }) {
  return (
    <Image src="/brand/emblem.png" alt="Unlink" width={size} height={Math.round(size * 0.916)}
           className={className} priority />
  );
}

/** Horizontal site logo: the "Unlink" wordmark, light/dark variants swapped by theme. */
export function Logo({ href = "/", className, height = 26 }: { href?: string; className?: string; height?: number }) {
  const width = Math.round(height * (800 / 181));
  return (
    <Link href={href} className={cn("inline-flex shrink-0 items-center", className)} aria-label="Unlink home">
      <Image src="/brand/wordmark-text.png" alt="Unlink" width={width} height={height} className="dark:hidden" priority />
      <Image src="/brand/wordmark-text-dark.png" alt="Unlink" width={width} height={height} className="hidden dark:block" priority />
    </Link>
  );
}

/** Stacked emblem-over-wordmark logo for hero moments (login, landing). */
export function StackedLogo({ className, height = 120 }: { className?: string; height?: number }) {
  const width = Math.round(height * (945 / 775));
  return (
    <span className={cn("inline-block", className)}>
      <Image src="/brand/wordmark.png" alt="Unlink" width={width} height={height} className="dark:hidden" priority />
      <Image src="/brand/wordmark-dark.png" alt="Unlink" width={width} height={height} className="hidden dark:block" priority />
    </span>
  );
}
