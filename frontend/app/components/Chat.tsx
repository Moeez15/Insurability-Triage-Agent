"use client";

import dynamic from "next/dynamic";
import { useRef, useState, type FormEvent } from "react";
import type { ChatMessage, ChatResponse, ToolCall } from "../types";
import ToolCallChip from "./ToolCallChip";
import MarkdownMessage from "./MarkdownMessage";
import type { MapPoint } from "./AddressMap";

// Leaflet touches window/document at import time — must not run during SSR.
const AddressMap = dynamic(() => import("./AddressMap"), { ssr: false });

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

const SUGGESTIONS = [
  "Is 5555 Skyway, Paradise, CA 95969 hard to insure?",
  "What if the defensible space is already cleared?",
  "Can you check my listing book and rank them by risk?",
];

function mapPointsFor(toolCalls?: ToolCall[]): MapPoint[] {
  if (!toolCalls) return [];
  const points: MapPoint[] = [];
  for (const call of toolCalls) {
    if (call.tool === "check_insurability" && call.lat != null && call.lng != null) {
      points.push({ address: call.input.address || "", lat: call.lat, lng: call.lng, verdict: call.verdict });
    } else if (call.tool === "compare_addresses") {
      for (const r of call.results || []) {
        if (r.lat != null && r.lng != null) {
          points.push({ address: r.address, lat: r.lat, lng: r.lng, verdict: r.verdict });
        }
      }
    }
  }
  return points;
}

function parcelBoundaryFor(toolCalls?: ToolCall[]): string | null {
  const check = toolCalls?.find((c) => c.tool === "check_insurability");
  return check?.parcel_boundary_geojson ?? null;
}

export default function Chat() {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const sessionId = useRef<string | undefined>(undefined);

  async function send(text: string) {
    const trimmed = text.trim();
    if (!trimmed || loading) return;

    setError(null);
    setMessages((prev) => [...prev, { role: "user", content: trimmed }]);
    setInput("");
    setLoading(true);

    try {
      const res = await fetch(`${API_URL}/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          message: trimmed,
          session_id: sessionId.current,
        }),
      });

      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        throw new Error(body.detail || `Request failed with ${res.status}`);
      }

      const data: ChatResponse = await res.json();
      sessionId.current = data.session_id;
      setMessages((prev) => [
        ...prev,
        { role: "assistant", content: data.reply, toolCalls: data.tool_calls },
      ]);
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : "Something went wrong talking to the agent."
      );
    } finally {
      setLoading(false);
    }
  }

  function handleSubmit(e: FormEvent) {
    e.preventDefault();
    send(input);
  }

  return (
    <div className="flex h-dvh flex-col bg-zinc-50 dark:bg-black">
      <header className="border-b border-zinc-200 bg-white px-6 py-4 dark:border-zinc-800 dark:bg-black">
        <h1 className="text-lg font-semibold text-zinc-900 dark:text-zinc-50">
          Insurability Triage Agent
        </h1>
        <p className="text-sm text-zinc-500 dark:text-zinc-400">
          Wildfire insurability triage for California addresses — built on
          Mireye + California&apos;s Safer From Wildfires regulation.
        </p>
      </header>

      <div className="flex-1 overflow-y-auto px-6 py-6">
        {messages.length === 0 ? (
          <div className="mx-auto flex h-full max-w-md flex-col items-center justify-center gap-4 text-center">
            <div>
              <h2 className="text-base font-medium text-zinc-900 dark:text-zinc-50">
                Check a California address
              </h2>
              <p className="mt-1 text-sm text-zinc-500 dark:text-zinc-400">
                Ask about wildfire insurability risk, mitigation costs, or
                compare a few listings at once.
              </p>
            </div>
            <div className="flex w-full flex-col gap-2">
              {SUGGESTIONS.map((s) => (
                <button
                  key={s}
                  onClick={() => send(s)}
                  className="flex min-h-11 w-full items-center rounded-lg border border-zinc-200 bg-white px-3 py-2 text-left text-sm text-zinc-700 transition-colors hover:border-zinc-300 hover:bg-zinc-50 dark:border-zinc-800 dark:bg-zinc-900 dark:text-zinc-300 dark:hover:border-zinc-700"
                >
                  {s}
                </button>
              ))}
            </div>
          </div>
        ) : (
        <div className="mx-auto flex max-w-2xl flex-col gap-4">
          {messages.map((m, i) => {
            const points = m.role === "assistant" ? mapPointsFor(m.toolCalls) : [];
            const parcelBoundary = m.role === "assistant" ? parcelBoundaryFor(m.toolCalls) : null;
            return (
              <div
                key={i}
                className={`flex ${m.role === "user" ? "justify-end" : "justify-start"}`}
              >
                <div
                  className={`max-w-[85%] rounded-2xl px-4 py-3 text-sm leading-relaxed whitespace-pre-wrap ${
                    m.role === "user"
                      ? "bg-zinc-900 text-zinc-50 dark:bg-zinc-50 dark:text-zinc-900"
                      : "bg-white text-zinc-900 shadow-sm ring-1 ring-zinc-200 dark:bg-zinc-900 dark:text-zinc-100 dark:ring-zinc-800"
                  }`}
                >
                  {m.role === "assistant" && m.toolCalls?.map((call, j) => (
                    <ToolCallChip key={j} call={call} />
                  ))}
                  {points.length > 0 && (
                    <AddressMap points={points} parcelBoundaryGeojson={parcelBoundary} />
                  )}
                  {m.role === "assistant" ? (
                    <MarkdownMessage content={m.content} />
                  ) : (
                    m.content
                  )}
                </div>
              </div>
            );
          })}

          {loading && (
            <div className="flex justify-start">
              <div className="flex max-w-[85%] items-center gap-1.5 rounded-2xl bg-white px-4 py-3 shadow-sm ring-1 ring-zinc-200 dark:bg-zinc-900 dark:ring-zinc-800">
                <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-zinc-400 [animation-delay:-0.3s]" />
                <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-zinc-400 [animation-delay:-0.15s]" />
                <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-zinc-400" />
              </div>
            </div>
          )}

          {error && (
            <div className="rounded-lg bg-red-50 px-4 py-3 text-sm text-red-700 dark:bg-red-900/30 dark:text-red-300">
              {error}
            </div>
          )}
        </div>
        )}
      </div>

      <form
        onSubmit={handleSubmit}
        className="border-t border-zinc-200 bg-white px-6 py-4 dark:border-zinc-800 dark:bg-black"
      >
        <div className="mx-auto flex max-w-2xl gap-2">
          <input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="Ask about a California address…"
            className="h-11 flex-1 rounded-full border border-zinc-300 bg-white px-4 text-sm text-zinc-900 outline-none focus:border-amber-600 dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-100 dark:focus:border-amber-500"
          />
          <button
            type="submit"
            disabled={loading || !input.trim()}
            className="h-11 rounded-full bg-amber-700 px-5 text-sm font-medium text-white transition-colors hover:bg-amber-800 disabled:bg-zinc-300 disabled:text-zinc-500 dark:disabled:bg-zinc-800 dark:disabled:text-zinc-500"
          >
            Send
          </button>
        </div>
      </form>
    </div>
  );
}
