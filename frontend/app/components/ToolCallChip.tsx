import type { ToolCall } from "../types";

export const VERDICT_STYLES: Record<string, string> = {
  likely_insurable: "bg-emerald-100 text-emerald-800 dark:bg-emerald-900/40 dark:text-emerald-300",
  harder_to_place: "bg-amber-100 text-amber-800 dark:bg-amber-900/40 dark:text-amber-300",
  likely_hard_to_place: "bg-red-100 text-red-800 dark:bg-red-900/40 dark:text-red-300",
  low_confidence: "bg-zinc-100 text-zinc-700 dark:bg-zinc-800 dark:text-zinc-300",
  out_of_scope: "bg-zinc-100 text-zinc-700 dark:bg-zinc-800 dark:text-zinc-300",
};

function verdictStyle(verdict?: string | null): string {
  return (verdict && VERDICT_STYLES[verdict]) || "bg-zinc-100 text-zinc-700 dark:bg-zinc-800 dark:text-zinc-300";
}

function overridesLabel(overrides?: Record<string, boolean> | null): string | null {
  if (!overrides) return null;
  const active = Object.entries(overrides)
    .filter(([, v]) => v)
    .map(([k]) => k.replace(/_/g, " "));
  return active.length ? `assuming: ${active.join(", ")}` : null;
}

function CheckInsurabilityChip({ call }: { call: ToolCall }) {
  const overridesText = overridesLabel(call.input.overrides);

  return (
    <div className="mb-2 flex flex-wrap items-center gap-2 text-xs">
      <span className="inline-flex items-center gap-1 rounded-full bg-zinc-100 px-2.5 py-1 font-mono text-zinc-600 dark:bg-zinc-800 dark:text-zinc-400">
        🔧 check_insurability({call.input.address})
      </span>
      {call.verdict && (
        <span className={`inline-flex items-center rounded-full px-2.5 py-1 font-medium ${verdictStyle(call.verdict)}`}>
          {call.verdict.replace(/_/g, " ")}
        </span>
      )}
      {overridesText && (
        <span className="inline-flex items-center rounded-full bg-blue-100 px-2.5 py-1 text-blue-800 dark:bg-blue-900/40 dark:text-blue-300">
          {overridesText}
        </span>
      )}
      {call.data_source_mode === "demo_cache" && (
        <span className="inline-flex items-center rounded-full bg-purple-100 px-2.5 py-1 text-purple-800 dark:bg-purple-900/40 dark:text-purple-300">
          cached fallback
        </span>
      )}
      {call.parcel_boundary_geojson && (
        <span className="inline-flex items-center rounded-full bg-blue-100 px-2.5 py-1 text-blue-800 dark:bg-blue-900/40 dark:text-blue-300">
          parcel boundary shown
        </span>
      )}
      {call.fire_station && call.fire_station.drive_minutes != null && (
        <span className="inline-flex items-center rounded-full bg-zinc-100 px-2.5 py-1 text-zinc-600 dark:bg-zinc-800 dark:text-zinc-400">
          🚒 {call.fire_station.drive_minutes.toFixed(0)} min to {call.fire_station.station_name}
        </span>
      )}
    </div>
  );
}

const HAZARD_TOOL_META: Record<string, { label: string; emoji: string }> = {
  check_flood_risk: { label: "check_flood_risk", emoji: "🌊" },
  check_earthquake_risk: { label: "check_earthquake_risk", emoji: "🌎" },
};

function HazardCheckChip({ call }: { call: ToolCall }) {
  const meta = HAZARD_TOOL_META[call.tool] ?? { label: call.tool, emoji: "🔧" };
  return (
    <div className="mb-2 flex flex-wrap items-center gap-2 text-xs">
      <span className="inline-flex items-center gap-1 rounded-full bg-zinc-100 px-2.5 py-1 font-mono text-zinc-600 dark:bg-zinc-800 dark:text-zinc-400">
        {meta.emoji} {meta.label}({call.input.address})
      </span>
      {call.verdict && (
        <span className={`inline-flex items-center rounded-full px-2.5 py-1 font-medium ${verdictStyle(call.verdict)}`}>
          {call.verdict.replace(/_/g, " ")}
        </span>
      )}
      {call.data_source_mode === "demo_cache" && (
        <span className="inline-flex items-center rounded-full bg-purple-100 px-2.5 py-1 text-purple-800 dark:bg-purple-900/40 dark:text-purple-300">
          cached fallback
        </span>
      )}
      {call.parcel_boundary_geojson && (
        <span className="inline-flex items-center rounded-full bg-blue-100 px-2.5 py-1 text-blue-800 dark:bg-blue-900/40 dark:text-blue-300">
          parcel boundary shown
        </span>
      )}
    </div>
  );
}

const HAZARD_LABELS: Record<string, string> = {
  wildfire: "🔥 wildfire",
  flood: "🌊 flood",
  earthquake: "🌎 earthquake",
};

function FullRiskReportChip({ call }: { call: ToolCall }) {
  const hazards = call.hazards || [];
  return (
    <div className="mb-2 flex flex-col gap-1.5 text-xs">
      <span className="inline-flex w-fit items-center gap-1 rounded-full bg-zinc-100 px-2.5 py-1 font-mono text-zinc-600 dark:bg-zinc-800 dark:text-zinc-400">
        🧭 full_risk_report({call.input.address})
      </span>
      {call.overall_verdict && (
        <span className={`inline-flex w-fit items-center rounded-full px-2.5 py-1 font-medium ${verdictStyle(call.overall_verdict)}`}>
          overall: {call.overall_verdict.replace(/_/g, " ")}
        </span>
      )}
      <div className="flex flex-col gap-1">
        {hazards.map((h, i) => (
          <div key={i} className="flex items-center gap-2">
            <span className="w-20 shrink-0 text-zinc-500 dark:text-zinc-400">
              {HAZARD_LABELS[h.hazard] ?? h.hazard}
            </span>
            <span className={`inline-flex shrink-0 items-center rounded-full px-2 py-0.5 font-medium ${verdictStyle(h.verdict)}`}>
              {h.verdict.replace(/_/g, " ")}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}

function AskAboutLocationChip({ call }: { call: ToolCall }) {
  return (
    <div className="mb-2 flex flex-wrap items-center gap-2 text-xs">
      <span className="inline-flex items-center gap-1 rounded-full bg-zinc-100 px-2.5 py-1 font-mono text-zinc-600 dark:bg-zinc-800 dark:text-zinc-400">
        🔧 ask_about_location({call.input.address})
      </span>
      <span className="inline-flex items-center rounded-full bg-indigo-100 px-2.5 py-1 text-indigo-800 dark:bg-indigo-900/40 dark:text-indigo-300">
        not a scoring factor
      </span>
      {call.confidence && (
        <span className="inline-flex items-center rounded-full bg-zinc-100 px-2.5 py-1 text-zinc-600 dark:bg-zinc-800 dark:text-zinc-400">
          confidence: {call.confidence}
        </span>
      )}
    </div>
  );
}

function CompareAddressesChip({ call }: { call: ToolCall }) {
  const results = call.results || [];
  return (
    <div className="mb-2 flex flex-col gap-1.5 text-xs">
      <span className="inline-flex w-fit items-center gap-1 rounded-full bg-zinc-100 px-2.5 py-1 font-mono text-zinc-600 dark:bg-zinc-800 dark:text-zinc-400">
        🔧 compare_addresses({results.length} addresses)
      </span>
      <div className="flex flex-col gap-1">
        {results.map((r, i) => (
          <div key={i} className="flex items-center gap-2">
            <span className={`inline-flex shrink-0 items-center rounded-full px-2 py-0.5 font-medium ${verdictStyle(r.verdict)}`}>
              {r.verdict.replace(/_/g, " ")}
            </span>
            <span className="truncate text-zinc-600 dark:text-zinc-400">{r.address}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

export default function ToolCallChip({ call }: { call: ToolCall }) {
  if (call.tool === "compare_addresses") {
    return <CompareAddressesChip call={call} />;
  }
  if (call.tool === "full_risk_report") {
    return <FullRiskReportChip call={call} />;
  }
  if (call.tool === "check_flood_risk" || call.tool === "check_earthquake_risk") {
    return <HazardCheckChip call={call} />;
  }
  if (call.tool === "ask_about_location") {
    return <AskAboutLocationChip call={call} />;
  }
  return <CheckInsurabilityChip call={call} />;
}
