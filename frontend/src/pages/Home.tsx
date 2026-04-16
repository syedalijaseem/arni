import { useState, useEffect } from "react";
import { Link } from "react-router-dom";
import { useAuth } from "@/context/AuthContext";
import { buttonVariants } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import ThemeToggle from "@/components/ThemeToggle";

interface HealthData {
  status: string;
  app: string;
  version: string;
  database: string;
}

const FEATURES = [
  {
    icon: "\uD83C\uDF99\uFE0F",
    title: "Real-Time Voice AI",
    desc: "Arni listens and responds when you call its name \u2014 no clicking, no typing.",
  },
  {
    icon: "\uD83D\uDCC4",
    title: "Document Intelligence",
    desc: "Upload reports, specs, or financials. Ask questions during the meeting and get instant cited answers.",
  },
  {
    icon: "\uD83E\uDDE0",
    title: "Persistent Memory",
    desc: "Arni remembers every meeting. Reconvene and pick up exactly where you left off.",
  },
  {
    icon: "\uD83D\uDD0D",
    title: "Semantic Search",
    desc: "Search across all your meetings and documents with natural language \u2014 not just keywords.",
  },
  {
    icon: "\u2705",
    title: "Auto Summaries",
    desc: "Every meeting ends with a structured summary, key decisions, and action items \u2014 automatically.",
  },
  {
    icon: "\uD83D\uDD12",
    title: "Private & Secure",
    desc: "Your meetings stay yours. Participant-only access, JWT auth, encrypted at rest.",
  },
];

const STEPS = [
  {
    num: "1",
    title: "Create & Invite",
    desc: "Start a meeting, invite your team, upload reference documents.",
  },
  {
    num: "2",
    title: "Talk Naturally",
    desc: "Say \u2018Hey Arni\u2019 to ask questions, get summaries, or pull data from your documents \u2014 all by voice.",
  },
  {
    num: "3",
    title: "Access Forever",
    desc: "After the meeting, chat with Arni about anything discussed. Reconvene with full memory intact.",
  },
];

const PRICING = [
  {
    name: "Starter",
    tagline: "For individuals and small teams",
    features: [
      "Up to 5 meetings/month",
      "Document uploads (10 per meeting)",
      "90-day meeting history",
      "Post-meeting chat",
    ],
    cta: "Coming Soon",
    highlight: false,
  },
  {
    name: "Pro",
    tagline: "For growing teams",
    badge: "Best Value",
    features: [
      "Unlimited meetings",
      "Unlimited document uploads",
      "Full meeting history",
      "Cross-meeting memory",
      "Priority support",
    ],
    cta: "Coming Soon",
    highlight: true,
  },
  {
    name: "Enterprise",
    tagline: "For organizations",
    features: [
      "Everything in Pro",
      "Custom integrations",
      "SSO & admin controls",
      "Dedicated support",
      "Custom data retention",
    ],
    cta: "Contact Us",
    highlight: false,
  },
];

function Home() {
  const { isAuthenticated } = useAuth();
  const [health, setHealth] = useState<HealthData | null>(null);

  useEffect(() => {
    fetch("/api/health")
      .then((r) => r.json())
      .then(setHealth)
      .catch(() => setHealth(null));
  }, []);

  return (
    <div className="min-h-screen flex flex-col bg-background text-foreground">
      {/* Nav */}
      <header className="sticky top-0 z-50 w-full flex items-center justify-between px-6 md:px-12 py-4 border-b border-border/50 bg-background/80 backdrop-blur-md">
        <span className="text-xl font-bold tracking-tight">
          <span className="text-primary">Arni</span>
        </span>
        <div className="flex items-center gap-2">
          <ThemeToggle />
          {isAuthenticated ? (
            <Link to="/dashboard" className={buttonVariants()}>Dashboard</Link>
          ) : (
            <>
              <Link to="/login" className={buttonVariants({ variant: "ghost" })}>Sign in</Link>
              <Link to="/register" className={buttonVariants()}>Get started</Link>
            </>
          )}
        </div>
      </header>

      {/* Hero */}
      <section className="relative flex-1 flex flex-col items-center justify-center px-6 py-24 md:py-32 overflow-hidden">
        <div className="inline-flex items-center border border-primary/30 bg-primary/10 text-primary text-sm rounded-full px-4 py-1.5 mb-8">
          <span className="flex h-2 w-2 rounded-full bg-primary mr-2 animate-pulse" />
          AI Meeting Participant
        </div>

        <h1 className="text-5xl md:text-7xl font-extrabold tracking-tight text-center leading-[1.1]">
          Your AI teammate
          <br />
          <span className="bg-clip-text text-transparent bg-gradient-to-r from-primary to-blue-400">that never forgets.</span>
        </h1>

        <p className="mt-6 text-lg md:text-xl text-muted-foreground text-center max-w-2xl leading-relaxed">
          Arni joins your meetings, answers questions in real time,
          and builds a searchable knowledge base your whole team
          can access &mdash; meeting after meeting.
        </p>

        <div className="flex flex-col sm:flex-row items-center justify-center gap-4 mt-12 relative z-10">
          {isAuthenticated ? (
            <Link to="/dashboard" className={buttonVariants({ size: "lg", className: "rounded-full px-8" })}>Go to Dashboard</Link>
          ) : (
            <>
              <Link
                to="/register"
                className="inline-flex items-center justify-center rounded-full px-8 py-3.5 text-base font-semibold bg-primary hover:bg-primary/90 text-primary-foreground transition-all shadow-[0_0_20px_rgba(37,99,235,0.3)] hover:shadow-[0_0_30px_rgba(37,99,235,0.5)] hover:-translate-y-0.5"
              >
                Get started free
                <svg className="ml-2 w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M14 5l7 7m0 0l-7 7m7-7H3"/></svg>
              </Link>
              <a
                href="#how-it-works"
                className="inline-flex items-center justify-center rounded-full px-8 py-3.5 text-base font-medium border border-border bg-background/50 hover:bg-accent text-foreground transition-all hover:-translate-y-0.5 backdrop-blur-sm"
              >
                See how it works
              </a>
            </>
          )}
        </div>

        {/* Hero Image with Glow */}
        <div className="relative mt-16 md:mt-24 w-full max-w-5xl mx-auto">
          {/* Ambient Glow */}
          <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[120%] h-[120%] max-w-4xl bg-primary/20 blur-[100px] rounded-[100%] -z-10 pointer-events-none" />
          
          <div className="rounded-xl overflow-hidden border border-border/60 bg-background/50 backdrop-blur-sm shadow-2xl shadow-primary/10 relative z-10">
            <img 
              src="/screenshots/meeting-room-light.png" 
              alt="Arni Meeting Room Interface" 
              className="w-full h-auto object-cover dark:hidden" 
            />
            <img 
              src="/screenshots/meeting-room-dark.png" 
              alt="Arni Meeting Room Interface" 
              className="w-full h-auto object-cover hidden dark:block" 
            />
          </div>
        </div>
      </section>

      {/* Features */}
      <section className="px-6 md:px-12 py-24 border-t border-border">
        <div className="max-w-5xl mx-auto">
          <h2 className="text-3xl md:text-4xl font-bold text-center mb-4">
            Everything your team needs
          </h2>
          <p className="text-muted-foreground text-center mb-14 max-w-xl mx-auto">
            From live voice AI to persistent cross-meeting memory.
          </p>
          <div className="grid gap-8 md:grid-cols-2 lg:grid-cols-3 mt-16">
            {FEATURES.map((f) => (
              <div
                key={f.title}
                className="group relative bg-background/50 backdrop-blur-sm border border-border rounded-2xl p-8 hover:bg-card/50 transition-colors"
              >
                <div className="absolute inset-0 bg-gradient-to-b from-primary/5 to-transparent opacity-0 group-hover:opacity-100 transition-opacity rounded-2xl" />
                <div className="relative z-10">
                  <div className="text-3xl mb-4 p-2 w-14 h-14 flex items-center justify-center rounded-xl bg-primary/10 border border-primary/20 text-primary">{f.icon}</div>
                  <h3 className="text-foreground font-semibold text-lg mb-2">{f.title}</h3>
                  <p className="text-muted-foreground leading-relaxed">{f.desc}</p>
                </div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Deep Dives */}
      <section className="px-6 md:px-12 py-24 border-t border-border overflow-hidden">
        <div className="max-w-6xl mx-auto flex flex-col gap-32">
          
          {/* Feature 1 */}
          <div className="flex flex-col lg:flex-row items-center gap-12 lg:gap-20">
            <div className="flex-1 space-y-6">
              <h2 className="text-3xl md:text-4xl font-bold">Automated Meeting Reports</h2>
              <p className="text-lg text-muted-foreground leading-relaxed">
                Get an accurate, detailed report as soon as your call ends. Arni automatically compiles key decisions, timelines, and generates editable action items.
              </p>
              <ul className="space-y-4 text-base text-foreground/80 mt-6">
                <li className="flex items-center gap-3"><span className="text-primary text-xl">✔</span> High-quality AI summaries</li>
                <li className="flex items-center gap-3"><span className="text-primary text-xl">✔</span> Editable action lists</li>
                <li className="flex items-center gap-3"><span className="text-primary text-xl">✔</span> Chat with past meetings</li>
              </ul>
            </div>
            
            <div className="flex-1 w-full relative group">
              <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[110%] h-[110%] max-w-lg bg-primary/10 blur-[80px] rounded-[100%] -z-10 transition-all duration-700 group-hover:bg-primary/20" />
              <div className="rounded-xl overflow-hidden border border-border/60 bg-background/50 backdrop-blur-sm shadow-2xl shadow-primary/5 transform translate-x-4 lg:translate-x-8 transition-transform duration-1000 ease-out group-hover:translate-x-0 relative z-10">
                <img src="/screenshots/report-qna-light.png" alt="Smart Search" className="w-full h-auto object-cover dark:hidden" />
                <img src="/screenshots/report-qna-dark.png" alt="Smart Search" className="w-full h-auto object-cover hidden dark:block" />
              </div>
            </div>
          </div>

          {/* Feature 2 */}
          <div className="flex flex-col lg:flex-row-reverse items-center gap-12 lg:gap-20">
            <div className="flex-1 space-y-6">
              <h2 className="text-3xl md:text-4xl font-bold">Real-Time AI Participant</h2>
              <p className="text-lg text-muted-foreground leading-relaxed">
                Invite Arni to your meetings as an active voice participant. Use wake words to talk to Arni without typing, fetching data from your documents instantly.
              </p>
              <ul className="space-y-4 text-base text-foreground/80 mt-6">
                <li className="flex items-center gap-3"><span className="text-primary text-xl">✔</span> Voice-activated assistant</li>
                <li className="flex items-center gap-3"><span className="text-primary text-xl">✔</span> Real-time live transcript</li>
                <li className="flex items-center gap-3"><span className="text-primary text-xl">✔</span> Document-aware Q&A</li>
              </ul>
            </div>
            
            <div className="flex-1 w-full relative group">
              <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[110%] h-[110%] max-w-lg bg-primary/10 blur-[80px] rounded-[100%] -z-10 transition-all duration-700 group-hover:bg-primary/20" />
              <div className="rounded-xl overflow-hidden border border-border/60 bg-background/50 backdrop-blur-sm shadow-2xl shadow-primary/5 transform -translate-x-4 lg:-translate-x-8 transition-transform duration-1000 ease-out group-hover:translate-x-0 relative z-10">
                <img src="/screenshots/meeting-room-light.png" alt="Persistent Projects" className="w-full h-auto object-cover dark:hidden" />
                <img src="/screenshots/meeting-room-dark.png" alt="Persistent Projects" className="w-full h-auto object-cover hidden dark:block" />
              </div>
            </div>
          </div>

        </div>
      </section>

      {/* How It Works */}
      <section id="how-it-works" className="px-6 md:px-12 py-24 border-t border-border">
        <div className="max-w-4xl mx-auto">
          <h2 className="text-3xl md:text-4xl font-bold text-center mb-4">
            From conversation to knowledge in 3 steps
          </h2>
          <p className="text-muted-foreground text-center mb-14 max-w-xl mx-auto">
            No setup, no plugins, no learning curve.
          </p>
          <div className="flex flex-col md:flex-row items-start gap-8 md:gap-0">
            {STEPS.map((s, i) => (
              <div key={s.num} className="flex-1 flex flex-col items-center text-center relative">
                {/* Connector line */}
                {i < STEPS.length - 1 && (
                  <div className="hidden md:block absolute top-5 left-[calc(50%+28px)] right-[calc(-50%+28px)] h-px bg-border" />
                )}
                <div className="w-10 h-10 rounded-full bg-primary flex items-center justify-center text-primary-foreground font-bold text-sm mb-4 relative z-10">
                  {s.num}
                </div>
                <h3 className="text-foreground font-semibold mb-2">{s.title}</h3>
                <p className="text-muted-foreground text-sm leading-relaxed max-w-xs">{s.desc}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Pricing */}
      <section className="px-6 md:px-12 py-24 border-t border-border">
        <div className="max-w-5xl mx-auto">
          <h2 className="text-3xl md:text-4xl font-bold text-center mb-4">
            Simple, transparent pricing
          </h2>
          <p className="text-muted-foreground text-center mb-14">
            Coming soon &mdash; join the waitlist to get early access.
          </p>
          <div className="grid gap-6 md:grid-cols-3">
            {PRICING.map((p) => (
              <div
                key={p.name}
                className={`relative rounded-xl p-6 border ${
                  p.highlight
                    ? "border-primary bg-card/80"
                    : "border-border bg-card/50"
                }`}
              >
                {p.badge && (
                  <span className="absolute -top-3 left-1/2 -translate-x-1/2 bg-orange-500 text-white text-xs font-semibold px-3 py-0.5 rounded-full">
                    {p.badge}
                  </span>
                )}
                <h3 className="text-foreground font-semibold text-lg mb-1">{p.name}</h3>
                <p className="text-muted-foreground text-sm mb-5">{p.tagline}</p>
                <ul className="space-y-2 mb-6">
                  {p.features.map((feat) => (
                    <li key={feat} className="flex items-start gap-2 text-sm text-foreground/80">
                      <span className="text-primary mt-0.5">&#10003;</span>
                      {feat}
                    </li>
                  ))}
                </ul>
                {p.name === "Enterprise" ? (
                  <a
                    href="mailto:syedalijaseem@gmail.com"
                    className="block w-full text-center rounded-md px-4 py-2 text-sm font-medium border border-border text-foreground hover:bg-accent transition-colors"
                  >
                    Contact Us
                  </a>
                ) : (
                  <button
                    disabled
                    className="w-full rounded-md px-4 py-2 text-sm font-medium bg-muted text-muted-foreground cursor-not-allowed"
                  >
                    {p.cta}
                  </button>
                )}
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Footer */}
      <footer className="px-6 md:px-12 py-10 border-t border-border">
        <div className="max-w-5xl mx-auto flex flex-col md:flex-row items-center justify-between gap-6">
          <div className="text-center md:text-left">
            <span className="text-lg font-bold text-primary">Arni</span>
            <p className="text-muted-foreground text-sm mt-1">Your AI teammate</p>
          </div>
          <nav className="flex gap-6 text-sm text-muted-foreground">
            <a href="#how-it-works" className="hover:text-foreground transition-colors">Features</a>
            <a href="#" className="hover:text-foreground transition-colors">Privacy</a>
            <a href="#" className="hover:text-foreground transition-colors">Terms</a>
          </nav>
          <div className="flex items-center gap-3 text-sm text-muted-foreground">
            <span>Built by Syed Ali Jaseem</span>
            <a href="https://github.com/syedalijaseem" target="_blank" rel="noopener noreferrer" className="hover:text-foreground transition-colors">
              <svg className="w-4 h-4" fill="currentColor" viewBox="0 0 24 24"><path d="M12 0C5.37 0 0 5.37 0 12c0 5.3 3.438 9.8 8.205 11.387.6.113.82-.258.82-.577 0-.285-.01-1.04-.015-2.04-3.338.724-4.042-1.61-4.042-1.61-.546-1.387-1.333-1.756-1.333-1.756-1.09-.745.083-.73.083-.73 1.205.085 1.84 1.237 1.84 1.237 1.07 1.834 2.807 1.304 3.492.997.108-.775.418-1.305.762-1.605-2.665-.3-5.466-1.332-5.466-5.93 0-1.31.468-2.382 1.235-3.222-.124-.303-.535-1.524.117-3.176 0 0 1.008-.322 3.3 1.23A11.51 11.51 0 0112 5.803c1.02.005 2.047.138 3.006.404 2.29-1.552 3.297-1.23 3.297-1.23.653 1.653.242 2.874.118 3.176.77.84 1.233 1.911 1.233 3.222 0 4.61-2.805 5.625-5.475 5.921.43.372.823 1.102.823 2.222 0 1.606-.015 2.896-.015 3.286 0 .322.216.694.825.576C20.565 21.795 24 17.298 24 12c0-6.63-5.37-12-12-12z"/></svg>
            </a>
            <a href="https://linkedin.com/in/syedalijaseem" target="_blank" rel="noopener noreferrer" className="hover:text-foreground transition-colors">
              <svg className="w-4 h-4" fill="currentColor" viewBox="0 0 24 24"><path d="M20.447 20.452h-3.554v-5.569c0-1.328-.027-3.037-1.852-3.037-1.853 0-2.136 1.445-2.136 2.939v5.667H9.351V9h3.414v1.561h.046c.477-.9 1.637-1.85 3.37-1.85 3.601 0 4.267 2.37 4.267 5.455v6.286zM5.337 7.433a2.062 2.062 0 01-2.063-2.065 2.064 2.064 0 112.063 2.065zm1.782 13.019H3.555V9h3.564v11.452zM22.225 0H1.771C.792 0 0 .774 0 1.729v20.542C0 23.227.792 24 1.771 24h20.451C23.2 24 24 23.227 24 22.271V1.729C24 .774 23.2 0 22.222 0h.003z"/></svg>
            </a>
          </div>
        </div>
        <p className="text-center text-muted-foreground/60 text-xs mt-6">
          &copy; 2025 Arni. All rights reserved.
        </p>
      </footer>
    </div>
  );
}

export default Home;
