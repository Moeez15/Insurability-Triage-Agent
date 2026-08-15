"use client";

import { useState, type FormEvent } from "react";

interface AddressScreenProps {
  onSubmit: (address: string) => void;
  onBack: () => void;
}

const EXAMPLE_ADDRESS = "5555 Skyway, Paradise, CA 95969";

export default function AddressScreen({ onSubmit, onBack }: AddressScreenProps) {
  const [address, setAddress] = useState("");

  function handleSubmit(e: FormEvent) {
    e.preventDefault();
    const trimmed = address.trim();
    if (!trimmed) return;
    onSubmit(trimmed);
  }

  return (
    <div className="relative flex h-dvh flex-col items-center justify-center bg-zinc-50 px-6 dark:bg-black">
      <button
        type="button"
        onClick={onBack}
        className="absolute left-3 top-3 rounded-lg p-3 text-sm text-zinc-400 transition-colors hover:text-zinc-600 dark:text-zinc-600 dark:hover:text-zinc-400"
      >
        &larr; Back
      </button>

      <form
        onSubmit={handleSubmit}
        className="flex w-full max-w-md flex-col items-center text-center"
      >
        <h2 className="text-2xl font-semibold tracking-tight text-zinc-900 sm:text-3xl dark:text-zinc-50">
          What address should I work with?
        </h2>
        <p className="mt-2 text-sm text-zinc-500 dark:text-zinc-400">
          Any US property address — I&apos;ll geocode it and check wildfire,
          flood, and earthquake risk.
        </p>

        <input
          autoFocus
          value={address}
          onChange={(e) => setAddress(e.target.value)}
          placeholder="Enter a property address…"
          className="mt-8 h-14 w-full rounded-2xl border border-zinc-300 bg-white px-5 text-base text-zinc-900 outline-none focus:border-amber-600 dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-100 dark:focus:border-amber-500"
        />

        <button
          type="button"
          onClick={() => setAddress(EXAMPLE_ADDRESS)}
          className="mt-3 rounded p-1 text-xs text-zinc-400 underline-offset-2 transition-colors hover:text-zinc-600 hover:underline dark:text-zinc-600 dark:hover:text-zinc-400"
        >
          Try: {EXAMPLE_ADDRESS}
        </button>

        <button
          type="submit"
          disabled={!address.trim()}
          className="mt-8 h-12 w-full rounded-full bg-amber-700 text-sm font-medium text-white shadow-sm transition-colors hover:bg-amber-800 disabled:bg-zinc-300 disabled:text-zinc-500 dark:disabled:bg-zinc-800 dark:disabled:text-zinc-500 dark:hover:bg-amber-600"
        >
          Start Agent
        </button>
      </form>
    </div>
  );
}
