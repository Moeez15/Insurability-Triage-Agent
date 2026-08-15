"use client";

import { useState, type FormEvent } from "react";
import { useCrossfade } from "../hooks/useCrossfade";

interface HomepageProps {
  onSubmitAddress: (address: string) => void;
}

type Phase = "hero" | "address";

const FEATURES = [
  {
    icon: "🔥🌊🌎",
    title: "Multi-hazard risk check",
    detail: "One report, three independent verdicts — CAL FIRE, FEMA, and USGS/ASCE data.",
  },
  {
    icon: "💰",
    title: "Price the fix",
    detail: "See which mitigation would change a verdict, and what it costs.",
  },
  {
    icon: "📊",
    title: "Compare a listing book",
    detail: "Rank a batch of properties by wildfire risk in one pass.",
  },
];

const EXAMPLE_ADDRESS = "5555 Skyway, Paradise, CA 95969";

export default function Homepage({ onSubmitAddress }: HomepageProps) {
  const { stage: phase, visible, transitionTo } = useCrossfade<Phase>("hero");
  const [address, setAddress] = useState("");
  const [submitting, setSubmitting] = useState(false);

  function activate() {
    if (phase === "hero") transitionTo("address");
  }

  function handleSubmit(e: FormEvent) {
    e.preventDefault();
    const trimmed = address.trim();
    if (!trimmed || submitting) return;
    setSubmitting(true);
    onSubmitAddress(trimmed);
  }

  return (
    <div
      onClick={phase === "hero" ? activate : undefined}
      className={`relative flex h-dvh flex-col items-center justify-center bg-zinc-50 px-6 transition-all duration-300 ease-out dark:bg-black ${
        phase === "hero" ? "cursor-pointer" : ""
      } ${visible ? "opacity-100 translate-y-0" : "opacity-0 translate-y-2"}`}
    >
      {phase === "address" && (
        <button
          type="button"
          onClick={() => transitionTo("hero")}
          className="absolute left-3 top-3 rounded-lg p-3 text-sm text-zinc-400 transition-colors hover:text-zinc-600 dark:text-zinc-600 dark:hover:text-zinc-400"
        >
          &larr; Back
        </button>
      )}

      {phase === "hero" ? (
        <div className="flex w-full max-w-lg flex-col items-center text-center">
          <h1 className="text-3xl font-semibold tracking-tight text-balance text-zinc-900 sm:text-4xl md:text-5xl dark:text-zinc-50">
            Your AI agent for property risk triage
          </h1>
          <p className="mt-4 text-base text-balance text-zinc-500 dark:text-zinc-400">
            Tell me an address, and I&apos;ll tell you if it&apos;s insurable —
            before you&apos;re deep into escrow.
          </p>

          <div className="mt-10 flex w-full flex-col gap-3 text-left">
            {FEATURES.map((f) => (
              <div
                key={f.title}
                className="flex items-start gap-3 rounded-xl border border-zinc-200 bg-white px-4 py-3 dark:border-zinc-800 dark:bg-zinc-900"
              >
                <span className="shrink-0 whitespace-nowrap text-lg leading-none">{f.icon}</span>
                <div>
                  <p className="text-sm font-medium text-zinc-900 dark:text-zinc-50">
                    {f.title}
                  </p>
                  <p className="mt-0.5 text-sm text-zinc-500 dark:text-zinc-400">
                    {f.detail}
                  </p>
                </div>
              </div>
            ))}
          </div>

          <button
            type="button"
            onClick={(e) => {
              e.stopPropagation();
              activate();
            }}
            className="mt-10 h-12 rounded-full bg-amber-700 px-8 text-sm font-medium text-white shadow-sm transition-colors hover:bg-amber-800 dark:hover:bg-amber-600"
          >
            Get Started
          </button>

          <p className="mt-6 text-xs text-zinc-400 dark:text-zinc-600">
            Powered by Mireye &middot; CAL FIRE, FEMA &amp; USGS data
          </p>
        </div>
      ) : (
        <div className="flex w-full max-w-md flex-col items-center text-center">
          <p className="text-sm font-medium text-amber-700 dark:text-amber-500">
            Let&apos;s get started.
          </p>
          <h2 className="mt-1 text-2xl font-semibold tracking-tight text-zinc-900 sm:text-3xl dark:text-zinc-50">
            What address should I work with?
          </h2>
          <p className="mt-2 text-sm text-zinc-500 dark:text-zinc-400">
            Any US property address — I&apos;ll geocode it and check
            wildfire, flood, and earthquake risk.
          </p>

          <form onSubmit={handleSubmit} className="mt-8 flex w-full flex-col items-center">
            <input
              autoFocus
              value={address}
              onChange={(e) => setAddress(e.target.value)}
              disabled={submitting}
              placeholder="Enter a property address…"
              className="h-14 w-full rounded-2xl border border-zinc-300 bg-white px-5 text-base text-zinc-900 outline-none focus:border-amber-600 disabled:opacity-60 dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-100 dark:focus:border-amber-500"
            />

            <button
              type="button"
              onClick={() => setAddress(EXAMPLE_ADDRESS)}
              disabled={submitting}
              className="mt-3 rounded p-1 text-xs text-zinc-400 underline-offset-2 transition-colors hover:text-zinc-600 hover:underline disabled:opacity-60 dark:text-zinc-600 dark:hover:text-zinc-400"
            >
              Try: {EXAMPLE_ADDRESS}
            </button>

            <button
              type="submit"
              disabled={!address.trim() || submitting}
              className="mt-8 flex h-12 w-full items-center justify-center gap-2 rounded-full bg-amber-700 text-sm font-medium text-white shadow-sm transition-colors hover:bg-amber-800 disabled:bg-zinc-300 disabled:text-zinc-500 dark:disabled:bg-zinc-800 dark:disabled:text-zinc-500 dark:hover:bg-amber-600"
            >
              {submitting ? (
                <>
                  <span className="h-3.5 w-3.5 animate-spin rounded-full border-2 border-white/40 border-t-white" />
                  Starting agent…
                </>
              ) : (
                "Start Agent"
              )}
            </button>
          </form>
        </div>
      )}
    </div>
  );
}
