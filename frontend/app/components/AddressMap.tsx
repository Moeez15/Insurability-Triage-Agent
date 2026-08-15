"use client";

import "leaflet/dist/leaflet.css";
import L from "leaflet";
import { GeoJSON, MapContainer, Marker, Popup, TileLayer } from "react-leaflet";

// Leaflet's default marker icon references image paths that break under
// Next.js bundling — the standard workaround is pointing them at a CDN
// instead of fighting the bundler over static asset resolution.
const defaultIcon = L.icon({
  iconUrl: "https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon.png",
  iconRetinaUrl: "https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon-2x.png",
  shadowUrl: "https://unpkg.com/leaflet@1.9.4/dist/images/marker-shadow.png",
  iconSize: [25, 41],
  iconAnchor: [12, 41],
  popupAnchor: [1, -34],
  shadowSize: [41, 41],
});

const VERDICT_COLORS: Record<string, string> = {
  likely_insurable: "#059669",
  harder_to_place: "#d97706",
  likely_hard_to_place: "#dc2626",
  low_confidence: "#71717a",
  out_of_scope: "#71717a",
};

export type MapPoint = {
  address: string;
  lat: number;
  lng: number;
  verdict?: string | null;
};

function verdictIcon(verdict?: string | null): L.DivIcon {
  const color = (verdict && VERDICT_COLORS[verdict]) || "#3b82f6";
  return L.divIcon({
    className: "",
    html: `<div style="background:${color};width:16px;height:16px;border-radius:50%;border:2px solid white;box-shadow:0 1px 4px rgba(0,0,0,0.4)"></div>`,
    iconSize: [16, 16],
    iconAnchor: [8, 8],
    popupAnchor: [0, -8],
  });
}

export default function AddressMap({
  points,
  parcelBoundaryGeojson,
}: {
  points: MapPoint[];
  parcelBoundaryGeojson?: string | null;
}) {
  if (points.length === 0) return null;

  let parcelGeometry: GeoJSON.Geometry | null = null;
  if (parcelBoundaryGeojson) {
    try {
      parcelGeometry = JSON.parse(parcelBoundaryGeojson);
    } catch {
      parcelGeometry = null; // malformed geometry shouldn't break the map
    }
  }

  // Single point: center + fixed zoom (bounds fitting degenerates to a
  // near-infinite zoom on one coordinate). Zoom in further when a parcel
  // boundary is available — a parcel-sized polygon is invisible at the
  // "show the neighborhood" zoom level used otherwise. Multiple points:
  // fit bounds so every marker is actually visible, rather than a fixed
  // zoom that can leave far-apart markers off-screen.
  const single = points.length === 1;
  const mapProps = single
    ? {
        center: [points[0].lat, points[0].lng] as [number, number],
        zoom: parcelGeometry ? 18 : 13,
      }
    : {
        bounds: points.map((p) => [p.lat, p.lng] as [number, number]),
        boundsOptions: { padding: [24, 24] as [number, number] },
      };

  return (
    <div className="mb-2 h-56 w-full overflow-hidden rounded-lg ring-1 ring-zinc-200 dark:ring-zinc-800">
      <MapContainer
        {...mapProps}
        scrollWheelZoom={false}
        style={{ height: "100%", width: "100%" }}
      >
        <TileLayer
          attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
          url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
        />
        {parcelGeometry && (
          <GeoJSON
            data={parcelGeometry}
            style={{ color: "#3b82f6", weight: 2, fillOpacity: 0.15 }}
          />
        )}
        {points.map((p, i) => (
          <Marker key={i} position={[p.lat, p.lng]} icon={points.length > 1 ? verdictIcon(p.verdict) : defaultIcon}>
            <Popup>
              <strong>{p.address}</strong>
              {p.verdict && (
                <>
                  <br />
                  {p.verdict.replace(/_/g, " ")}
                </>
              )}
            </Popup>
          </Marker>
        ))}
      </MapContainer>
    </div>
  );
}
