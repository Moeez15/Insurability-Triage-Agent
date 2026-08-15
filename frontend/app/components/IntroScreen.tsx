"use client";

interface IntroScreenProps {
  onStart: () => void;
}

const CAPABILITIES = [
  {
    title: "Check wildfire, flood & earthquake risk",
    detail: "One report, three independent verdicts — CAL FIRE, FEMA, and USGS/ASCE data.",
  },
  {
    title: "Price the fix",
    detail: "See which mitigation would change a verdict, and what it costs.",
  },
  {
    title: "Compare a listing book",
    detail: "Rank a batch of properties by wildfire risk in one pass.",
  },
];

export default function IntroScreen({ onStart }: IntroScreenProps) {
  return (
    <div
      onClick={onStart}
      className="flex h-dvh cursor-pointer flex-col items-center justify-center bg-zinc-50 px-6 dark:bg-black"
    >
      <div className="flex w-full max-w-lg flex-col items-center text-center">
        <h1 className="text-3xl font-semibold tracking-tight text-balance text-zinc-900 sm:text-4xl md:text-5xl dark:text-zinc-50">
          Your AI agent for property risk triage
        </h1>
        <p className="mt-4 text-base text-balance text-zinc-500 dark:text-zinc-400">
          Tell me an address, and I&apos;ll tell you if it&apos;s insurable —
          before you&apos;re deep into escrow.
        </p>

        <div className="mt-10 flex w-full flex-col gap-3 text-left">
          {CAPABILITIES.map((c) => (
            <div
              key={c.title}
              className="rounded-xl border border-zinc-200 bg-white px-4 py-3 dark:border-zinc-800 dark:bg-zinc-900"
            >
              <p className="text-sm font-medium text-zinc-900 dark:text-zinc-50">
                {c.title}
              </p>
              <p className="mt-0.5 text-sm text-zinc-500 dark:text-zinc-400">
                {c.detail}
              </p>
            </div>
          ))}
        </div>

        <button
          type="button"
          onClick={(e) => {
            e.stopPropagation();
            onStart();
          }}
          className="mt-10 h-12 rounded-full bg-amber-700 px-8 text-sm font-medium text-white shadow-sm transition-colors hover:bg-amber-800 dark:hover:bg-amber-600"
        >
          Get Started
        </button>

        <p className="mt-6 text-xs text-zinc-400 dark:text-zinc-600">
          Powered by Mireye &middot; CAL FIRE, FEMA &amp; USGS data
        </p>
      </div>
    </div>
  );
}
