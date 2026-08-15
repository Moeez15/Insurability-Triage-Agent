"""Real, live-verified Mireye response fixtures (captured during
/plan-eng-review 2026-08-14) — not synthetic data."""

PARADISE_CA_FETCH = {
    "lat": 39.749521,
    "lng": -121.63408,
    "fields": {
        "fire_hazard_severity_zone_class": {
            "value": "Very High",
            "source": "CALFIRE_FHSZ",
            "confidence": "high",
            "notes": "CAL FIRE LRA Fire Hazard Severity Zone at the point (FHSZ code 3).",
            "status": "ok",
        },
        "fire_hazard_responsibility_area": {
            "value": "LRA",
            "source": "CALFIRE_FHSZ",
            "confidence": "high",
            "notes": "responsibility area from the SRA attribute of the same CAL FIRE LRA polygon.",
            "status": "ok",
        },
        "tree_canopy_pct": {"value": 0.0, "unit": "percent", "source": "USFS_NLCD_TCC", "status": "ok"},
        "elevation": {"value": 492.8, "unit": "meters", "source": "USGS_3DEP_COG", "status": "ok"},
    },
    "partial_failures": [],
}

EVERGREEN_CO_FETCH = {
    "lat": 39.633634,
    "lng": -105.329915,
    "fields": {
        "fire_hazard_severity_zone_class": {
            "value": None,
            "source": "CALFIRE_FHSZ",
            "confidence": "high",
            "notes": (
                "the point is outside California — it falls outside the California "
                "bounding box entirely, so neither CAL FIRE layer was queried. "
                "CAL FIRE FHSZ is a California-only regulatory product and does not "
                "apply here. Not applicable, NOT a finding of no wildfire hazard."
            ),
            "status": "absent",
        },
        "fire_hazard_responsibility_area": {
            "value": None,
            "source": "CALFIRE_FHSZ",
            "confidence": "high",
            "notes": "the point is outside California — not applicable.",
            "status": "absent",
        },
        "tree_canopy_pct": {"value": 18.0, "unit": "percent", "source": "USFS_NLCD_TCC", "status": "ok"},
    },
    "partial_failures": [],
}

FRA_WITHIN_CA_FETCH = {
    "lat": 40.0,
    "lng": -121.0,
    "fields": {
        "fire_hazard_severity_zone_class": {
            "value": None,
            "source": "CALFIRE_FHSZ",
            "notes": "Federal Responsibility Area land — CAL FIRE has no statutory mandate to zone it.",
            "status": "absent",
        },
        "fire_hazard_responsibility_area": {
            "value": None,
            "source": "CALFIRE_FHSZ",
            "notes": "Federal Responsibility Area land.",
            "status": "absent",
        },
    },
    "partial_failures": [],
}

LOW_RISK_CA_FETCH = {
    "lat": 37.79,
    "lng": -122.39,
    "fields": {
        "fire_hazard_severity_zone_class": {
            "value": "Non-Wildland",
            "source": "CALFIRE_FHSZ",
            "confidence": "high",
            "notes": "Non-Wildland classification — urban core.",
            "status": "ok",
        },
        "fire_hazard_responsibility_area": {
            "value": "LRA",
            "source": "CALFIRE_FHSZ",
            "confidence": "high",
            "notes": "LRA.",
            "status": "ok",
        },
    },
    "partial_failures": [],
}

TRANSIENT_FAILURE_FETCH = {
    "lat": 39.7,
    "lng": -121.6,
    "fields": {
        "fire_hazard_severity_zone_class": {
            "value": None,
            "source": "CALFIRE_FHSZ",
            "status": "failed",
            "retryable": True,
            "error": "TimeoutError: ",
        },
        "fire_hazard_responsibility_area": {
            "value": None,
            "source": "CALFIRE_FHSZ",
            "status": "failed",
            "retryable": True,
            "error": "TimeoutError: ",
        },
    },
    "partial_failures": [
        {"field": "fire_hazard_severity_zone_class", "error": "TimeoutError: ", "retryable": True},
    ],
}

# --- flood_risk preset fixtures (live-verified 2026-08-15) ---

MIAMI_BEACH_FLOOD_FETCH = {
    "lat": 25.769783,
    "lng": -80.133277,
    "fields": {
        "within_floodplain_polygon": {
            "value": True,
            "source": "FEMA_NFHL",
            "confidence": "high",
            "notes": (
                "FEMA NFHL Flood Hazard Zones indicate Special Flood Hazard "
                "Area: Zone AE; SFHA_TF=T; FLD_AR_ID=12086C_1179; "
                "SOURCE_CIT=12086C_FIS1."
            ),
            "status": "ok",
        },
        "elevation": {"value": 2.1, "unit": "meters", "source": "USGS_3DEP_COG", "status": "ok"},
    },
    "partial_failures": [],
}

GUERNEVILLE_FLOOD_FETCH = {
    "lat": 38.502246,
    "lng": -122.997475,
    "fields": {
        "within_floodplain_polygon": {
            "value": False,
            "source": "FEMA_NFHL",
            "confidence": "high",
            "notes": (
                "FEMA NFHL Flood Hazard Zones intersect, but not an SFHA: "
                "Zone X; 0.2 PCT ANNUAL CHANCE FLOOD HAZARD; SFHA_TF=F; "
                "FLD_AR_ID=06097C_2550; SOURCE_CIT=06097C_STUDY18."
            ),
            "status": "ok",
        },
    },
    "partial_failures": [],
}

FLOOD_TRANSIENT_FAILURE_FETCH = {
    "lat": 25.77,
    "lng": -80.13,
    "fields": {
        "within_floodplain_polygon": {
            "value": None,
            "source": "FEMA_NFHL",
            "status": "failed",
            "retryable": True,
            "error": "TimeoutError: ",
        },
    },
    "partial_failures": [
        {"field": "within_floodplain_polygon", "error": "TimeoutError: ", "retryable": True},
    ],
}

# --- natural_hazard preset fixtures (live-verified 2026-08-15) ---

PARADISE_EARTHQUAKE_FETCH = {
    "lat": 39.749521,
    "lng": -121.63408,
    "fields": {
        "seismic_design_category": {
            "value": "D",
            "source": "USGS_DESIGNMAPS_ASCE7",
            "confidence": "high",
            "notes": "siteClass=D riskCategory=II (assumed defaults; Ss=0.88 S1=0.28 SDS=0.75)",
            "status": "ok",
        },
        "seismic_pga_2pct_50yr_g": {
            "value": 0.375,
            "unit": "g",
            "source": "USGS_NSHM",
            "status": "ok",
        },
    },
    "partial_failures": [],
}

MIAMI_BEACH_EARTHQUAKE_FETCH = {
    "lat": 25.769783,
    "lng": -80.133277,
    "fields": {
        "seismic_design_category": {
            "value": "A",
            "source": "USGS_DESIGNMAPS_ASCE7",
            "confidence": "high",
            "status": "ok",
        },
        "seismic_pga_2pct_50yr_g": {
            "value": 0.025,
            "unit": "g",
            "source": "USGS_NSHM",
            "status": "ok",
        },
    },
    "partial_failures": [],
}

EARTHQUAKE_TRANSIENT_FAILURE_FETCH = {
    "lat": 39.7,
    "lng": -121.6,
    "fields": {
        "seismic_design_category": {
            "value": None,
            "source": "USGS_DESIGNMAPS_ASCE7",
            "status": "failed",
            "retryable": True,
            "error": "TimeoutError: ",
        },
    },
    "partial_failures": [
        {"field": "seismic_design_category", "error": "TimeoutError: ", "retryable": True},
    ],
}
