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
