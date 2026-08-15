export type CompareResultEntry = {
  address: string;
  verdict: string;
  lat: number | null;
  lng: number | null;
  top_driving_factor?: string | null;
  cheapest_mitigation?: { action: string; est_cost_usd: [number, number] | null } | null;
  data_source_mode?: string | null;
};

export type FireStationInfo = {
  station_name: string;
  straight_line_distance_m: number | null;
  drive_minutes: number | null;
  drive_miles: number | null;
  destination_match_confidence: number | null;
};

export type ToolCall = {
  tool: string;
  input: {
    address?: string;
    overrides?: Record<string, boolean> | null;
    addresses?: string[];
    question?: string;
  };
  // check_insurability shape
  verdict?: string | null;
  data_source_mode?: string | null;
  lat?: number | null;
  lng?: number | null;
  parcel_boundary_geojson?: string | null;
  fire_station?: FireStationInfo | null;
  // compare_addresses shape
  results?: CompareResultEntry[];
  summary?: string | null;
  // ask_about_location shape
  confidence?: string | null;
};

export type ChatMessage = {
  role: "user" | "assistant";
  content: string;
  toolCalls?: ToolCall[];
};

export type ChatResponse = {
  session_id: string;
  reply: string;
  tool_calls: ToolCall[];
};
