import {
  Activity, Ban, Bot, Calculator, CircleCheck, ClipboardCheck, FileCheck2, Gauge, Handshake, History, Lock,
  Mail, MessageSquareWarning, Scale, ShieldCheck, Sparkles, UsersRound, Wallet,
} from "lucide-react";
import Link from "next/link";
import { buttonVariants } from "@/components/ui/button";
import { LandingCta } from "@/components/landing-cta";
import { Logo, LogoMark } from "@/components/logo";
import { ThemeToggle } from "@/components/theme";
import { cn } from "@/lib/utils";

const PRINCIPLES = [
  { icon: Mail, title: "A person approves every message", body: "Nothing reaches an employee until someone signs off that exact text. Change a word and it needs approval again." },
  { icon: UsersRound, title: "Preparer can't approve", body: "Whoever drafts a plan, a notice or a settlement can never be the one who approves it." },
  { icon: ShieldCheck, title: "Protected by rule", body: "People on protected leave, under legal hold, or with an open grievance can't be selected or exited." },
  { icon: History, title: "Every step on record", body: "A hash-chained audit log: who, when, before, after, and the written reason." },
];

const STEPS = [
  { icon: Activity, title: "Performance", body: "Reviews, goals, check-ins and PIPs with dated evidence, so decisions rest on a real record." },
  { icon: Calculator, title: "Reduction plan", body: "Score-ranked, role redundancy or a named list, with every score broken into its factors." },
  { icon: Scale, title: "Fairness gate", body: "Impact ratios by group and intersection. A flagged plan needs a written justification to proceed." },
  { icon: Mail, title: "Notices", body: "Legal-approved templates, a test send, approval bound to the content, then a throttled release." },
  { icon: Handshake, title: "Exit cases", body: "A tracked case per person: reason and evidence, notice period, last day, tasks and holds." },
  { icon: Wallet, title: "Final settlement", body: "FNF computed line by line in paise with the rule behind each line, reviewed by finance." },
  { icon: ClipboardCheck, title: "Clearance", body: "Access removal, asset return and handover, each with an owner and a ticket." },
  { icon: MessageSquareWarning, title: "Grievances", body: "Logged from either side, acknowledged on time, decided independently, appealable once." },
];

const SAFEGUARDS = [
  "AI drafts text for review. It never ranks, selects, scores or sends, and its prompts carry no personal data.",
  "Hard exclusions can't be bypassed by weights, filters or manual overrides.",
  "Demographics are never scoring inputs. They're used only to check fairness.",
  "Jurisdiction rules ship unverified and say so until a lawyer signs them off.",
  "No names, salaries, ratings or health data in application logs.",
  "Each organisation's data is isolated on every table and every query.",
];

function MockWindow() {
  // Stylised product illustration (decorative).
  const bars = [3, 5, 8, 11, 9, 13, 10, 7, 9, 6, 4, 3];
  return (
    <div className="glass relative overflow-hidden rounded-2xl p-0 shadow-2xl" aria-hidden="true">
      <div className="flex items-center gap-1.5 border-b px-4 py-3">
        <span className="size-2.5 rounded-full bg-[#ff5f57]" />
        <span className="size-2.5 rounded-full bg-[#febc2e]" />
        <span className="size-2.5 rounded-full bg-[#28c840]" />
        <span className="ml-3 rounded-md bg-muted px-2 py-0.5 font-mono text-[10px] text-muted-foreground">unlink / plans / q4-support</span>
      </div>
      <div className="grid gap-3 p-4 sm:grid-cols-3">
        {[["In scope", "58"], ["Protected", "8"], ["Proposed", "8 / 8"]].map(([l, v]) => (
          <div key={l} className="rounded-xl border bg-background/40 p-3">
            <div className="text-[10px] text-muted-foreground">{l}</div>
            <div className="text-xl font-semibold">{v}</div>
          </div>
        ))}
        <div className="rounded-xl border bg-background/40 p-3 sm:col-span-2">
          <div className="mb-2 flex items-center gap-3 text-[10px] text-muted-foreground">
            <span className="flex items-center gap-1"><span className="size-2 rounded-sm bg-[var(--series-2)]" />Proposed</span>
            <span className="flex items-center gap-1"><span className="size-2 rounded-sm bg-[var(--series-1)]" />Retained</span>
          </div>
          <div className="flex h-24 items-end gap-[3px]">
            {bars.map((b, i) => (
              <div key={i} className="flex-1 origin-bottom animate-grow-y rounded-t-[3px]"
                   style={{ height: `${b * 7}%`, animationDelay: `${300 + i * 60}ms`,
                            background: i < 3 ? "var(--series-2)" : "var(--series-1)" }} />
            ))}
          </div>
        </div>
        <div className="space-y-2 rounded-xl border bg-background/40 p-3">
          <div className="text-[10px] text-muted-foreground">Fairness · impact ratio</div>
          {[["Female", 0.97], ["Male", 1], ["50+", 0.86]].map(([g, r]) => (
            <div key={g as string}>
              <div className="flex justify-between text-[10px]"><span>{g}</span><span>{(r as number).toFixed(2)}</span></div>
              <div className="relative mt-0.5 h-1.5 rounded-full bg-muted">
                <div className="h-full origin-left animate-grow-x rounded-full bg-[var(--series-1)]" style={{ width: `${(r as number) * 100}%` }} />
                <div className="absolute inset-y-[-2px] left-[80%] w-px bg-foreground/70" />
              </div>
            </div>
          ))}
        </div>
        <div className="rounded-xl border bg-background/40 p-3 sm:col-span-3">
          {[["E0206", "Support Specialist", 26, true], ["E0144", "Support Lead", 31, true], ["E0019", "Support Specialist", 58, false]].map(([c, r, s, p]) => (
            <div key={c as string} className="flex items-center gap-3 border-b py-1.5 text-[11px] last:border-0">
              <span className="w-12 font-mono text-muted-foreground">{c}</span>
              <span className="w-32 truncate">{r}</span>
              <div className="flex h-1.5 flex-1 gap-[2px] overflow-hidden rounded-full">
                <div style={{ width: `${(s as number) * 0.45}%`, background: "var(--series-1)" }} />
                <div style={{ width: `${(s as number) * 0.3}%`, background: "var(--series-2)" }} />
                <div style={{ width: `${(s as number) * 0.25}%`, background: "var(--series-3)" }} />
              </div>
              <span className={cn("rounded-full px-2 py-0.5 text-[10px]", p ? "bg-[var(--series-2)]/15" : "bg-muted")}>
                {p ? "Proposed" : "Retained"}
              </span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

export default function LandingPage() {
  return (
    <div className="relative min-h-screen overflow-x-clip">
      <header className="sticky top-0 z-30 border-b border-transparent backdrop-blur-xl">
        <div className="mx-auto flex h-16 max-w-6xl items-center gap-6 px-4 md:px-6">
          <Logo />
          <nav className="hidden gap-6 text-sm text-muted-foreground md:flex">
            <a href="#how" className="hover:text-foreground">How it works</a>
            <a href="#features" className="hover:text-foreground">Product</a>
            <a href="#safeguards" className="hover:text-foreground">Safeguards</a>
          </nav>
          <div className="ml-auto flex items-center gap-2">
            <ThemeToggle />
            <LandingCta size="default" />
          </div>
        </div>
      </header>

      <main>
        {/* Hero */}
        <section className="mx-auto grid max-w-6xl items-center gap-12 px-4 pt-16 pb-24 md:px-6 lg:grid-cols-[1.05fr_1fr] lg:pt-24">
          <div className="stagger space-y-7">
            <span className="inline-flex items-center gap-2 rounded-full border bg-background/40 px-3 py-1 text-xs text-muted-foreground backdrop-blur">
              <Sparkles className="size-3.5 text-primary" />
              Exit operations, from first review to final settlement
            </span>
            <h1 className="text-4xl leading-[1.08] font-semibold tracking-tight text-balance md:text-5xl lg:text-6xl">
              Hard decisions,
              <br />
              handled <span>properly.</span>
            </h1>
            <p className="max-w-xl text-lg text-muted-foreground text-pretty">
              Unlink runs the whole exit process: performance evidence, explainable reduction plans, fairness checks,
              approved notices, exit cases, settlements, clearance and grievances, with a complete record of every
              step. Software prepares. People decide.
            </p>
            <div className="flex flex-wrap items-center gap-3">
              <LandingCta />
              <a href="#how" className={cn(buttonVariants({ variant: "outline", size: "lg" }), "rounded-xl bg-background/40 backdrop-blur")}>
                See how it works
              </a>
            </div>
            <div className="flex flex-wrap gap-x-6 gap-y-2 text-sm text-muted-foreground">
              {["Explainable selection", "Approval on every message", "Defensibility pack on demand"].map((t) => (
                <span key={t} className="flex items-center gap-1.5">
                  <CircleCheck className="size-4 text-[var(--status-good)]" /> {t}
                </span>
              ))}
            </div>
          </div>
          <div className="relative animate-fade-up [animation-delay:200ms]">
            <MockWindow />
          </div>
        </section>

        {/* Principles */}
        <section className="mx-auto max-w-6xl px-4 pb-24 md:px-6">
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            {PRINCIPLES.map((p) => (
              <div key={p.title} className="glass group rounded-2xl p-5 transition-transform">
                <span className="grid size-10 place-items-center rounded-xl bg-primary/10 text-primary">
                  <p.icon className="size-5" />
                </span>
                <h3 className="mt-4 font-semibold">{p.title}</h3>
                <p className="mt-1 text-sm text-muted-foreground">{p.body}</p>
              </div>
            ))}
          </div>
        </section>

        {/* How it works */}
        <section id="how" className="mx-auto max-w-6xl scroll-mt-24 px-4 pb-28 md:px-6">
          <div className="mb-12 max-w-2xl">
            <div className="text-xs font-medium tracking-[0.2em] text-muted-foreground uppercase">How it works</div>
            <h2 className="mt-3 text-4xl font-semibold tracking-tight text-balance">From the first review to the last payslip, with nothing hidden.</h2>
          </div>
          <ol className="relative grid gap-x-6 gap-y-10 sm:grid-cols-2 md:grid-cols-4">
            {STEPS.map((s, i) => (
              <li key={s.title} className="relative">
                <span className="relative grid size-12 place-items-center rounded-2xl border bg-card">
                  <s.icon className="size-5" />
                  <span className="absolute -top-2 -right-2 grid size-5 place-items-center rounded-full bg-primary text-[10px] font-semibold text-primary-foreground">{i + 1}</span>
                </span>
                <h3 className="mt-4 font-semibold">{s.title}</h3>
                <p className="mt-1 text-sm text-muted-foreground">{s.body}</p>
              </li>
            ))}
          </ol>
        </section>

        {/* Bento features */}
        <section id="features" className="mx-auto max-w-6xl scroll-mt-24 px-4 pb-28 md:px-6">
          <div className="mb-12 max-w-2xl">
            <div className="text-xs font-medium tracking-[0.2em] text-muted-foreground uppercase">Product</div>
            <h2 className="mt-3 text-4xl font-semibold tracking-tight text-balance">Everything a careful process needs. Nothing it doesn&apos;t.</h2>
          </div>
          <div className="grid auto-rows-[minmax(180px,auto)] gap-4 md:grid-cols-6">
            <div className="glass rounded-2xl p-6 md:col-span-4">
              <Gauge className="size-5 text-primary" />
              <h3 className="mt-3 text-lg font-semibold">Explainable ranking</h3>
              <p className="mt-1 max-w-md text-sm text-muted-foreground">
                Every score splits into the factors that produced it, including your own KPIs. Overrides need a written
                reason, and plans route through legal, finance and a final approver.
              </p>
              <div className="mt-5 space-y-2">
                {[[40, 22, 18, 8], [30, 25, 20, 12], [18, 12, 10, 6]].map((row, i) => (
                  <div key={i} className="flex h-2 gap-[2px] overflow-hidden rounded-full">
                    {row.map((v, j) => <div key={j} className="origin-left animate-grow-x" style={{ width: `${v}%`, background: `var(--series-${j + 1})`, animationDelay: `${i * 120}ms` }} />)}
                  </div>
                ))}
              </div>
            </div>
            <div className="glass rounded-2xl p-6 md:col-span-2">
              <Scale className="size-5 text-primary" />
              <h3 className="mt-3 text-lg font-semibold">Fairness that blocks</h3>
              <p className="mt-1 text-sm text-muted-foreground">
                Impact ratios by gender, age band, tenure, department and location, plus gender × age. A flag stops
                approval until someone writes down why the plan should still go ahead.
              </p>
            </div>
            <div className="glass rounded-2xl p-6 md:col-span-2">
              <Mail className="size-5 text-primary" />
              <h3 className="mt-3 text-lg font-semibold">Notices you can stand behind</h3>
              <p className="mt-1 text-sm text-muted-foreground">
                Merge-checked drafts, a test send to yourself, approval tied to a content hash, a throttled release,
                bounce handling and tracked acknowledgements.
              </p>
            </div>
            <div className="glass rounded-2xl p-6 md:col-span-2">
              <Wallet className="size-5 text-primary" />
              <h3 className="mt-3 text-lg font-semibold">Settlements, line by line</h3>
              <p className="mt-1 text-sm text-muted-foreground">
                Notice pay, leave encashment, gratuity, bonus and recoveries, each with its formula and rule, plus a
                what-if comparison. Payroll gets a CSV.
              </p>
            </div>
            <div className="glass rounded-2xl p-6 md:col-span-2">
              <FileCheck2 className="size-5 text-primary" />
              <h3 className="mt-3 text-lg font-semibold">Defensibility pack</h3>
              <p className="mt-1 text-sm text-muted-foreground">
                One PDF with method, weights, fairness, overrides, approvals, rules used and the audit trail, with
                an external version that hides names.
              </p>
            </div>
            <div className="glass relative overflow-hidden rounded-2xl p-6 md:col-span-6">
              <div className="flex flex-wrap items-start gap-6">
                <span className="grid size-12 place-items-center rounded-2xl bg-primary/10 text-primary"><Bot className="size-6" /></span>
                <div className="max-w-2xl">
                  <h3 className="text-lg font-semibold">AI that drafts, never decides</h3>
                  <p className="mt-1 text-sm text-muted-foreground">
                    Unlink can draft a committee summary, a plain-language explanation of a ranking, a notice, a reply
                    or a grievance summary. Drafts are labelled and stored for a person to edit and use. The model sees
                    employee codes and scoring data only, never names, salaries, demographics or leave details, and it
                    sits completely outside scoring, selection, settlement and sending.
                  </p>
                </div>
              </div>
            </div>
          </div>
        </section>

        {/* Safeguards */}
        <section id="safeguards" className="mx-auto max-w-6xl scroll-mt-24 px-4 pb-28 md:px-6">
          <div className="glass relative overflow-hidden rounded-3xl p-8 md:p-12">
            <div className="grid gap-10 lg:grid-cols-[1fr_1.3fr]">
              <div>
                <Lock className="size-6 text-primary" />
                <h2 className="mt-4 text-4xl font-semibold tracking-tight text-balance">The lines Unlink won&apos;t cross.</h2>
                <p className="mt-3 text-muted-foreground">
                  These aren&apos;t settings. They&apos;re built into how the product works, and the test suite checks them.
                </p>
              </div>
              <ul className="grid gap-3 sm:grid-cols-2">
                {SAFEGUARDS.map((s) => (
                  <li key={s} className="flex gap-3 rounded-xl border bg-background/40 p-4 text-sm">
                    <Ban className="mt-0.5 size-4 shrink-0 text-[var(--status-critical)]" aria-hidden="true" />
                    <span>{s}</span>
                  </li>
                ))}
              </ul>
            </div>
          </div>
        </section>

        {/* Final CTA */}
        <section className="mx-auto max-w-6xl px-4 pb-24 text-center md:px-6">
          <LogoMark size={72} className="mx-auto mb-8" />
          <h2 className="text-4xl font-semibold tracking-tight text-balance md:text-5xl">
            Every exit, <span>done right.</span>
          </h2>
          <p className="mx-auto mt-4 max-w-xl text-muted-foreground">
            Clear decisions, approved communication, correct settlements, and a record you can stand behind.
          </p>
          <div className="mt-8 flex justify-center"><LandingCta /></div>
        </section>
      </main>

      <footer className="border-t">
        <div className="mx-auto flex max-w-6xl flex-wrap items-center justify-between gap-4 px-4 py-8 text-sm text-muted-foreground md:px-6">
          <Logo />
          <p>Nothing reaches an employee without a person approving it first.</p>
          <Link href="/login" className="hover:text-foreground">Sign in</Link>
        </div>
      </footer>
    </div>
  );
}
