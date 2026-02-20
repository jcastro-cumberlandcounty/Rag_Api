"""
plat_vision_extractor.py  -  AI Vision-Based Plat Analyzer
============================================================
Uses the local llama3.2-vision:11b model (via OllamaClient) to examine
a submitted plat image and produce two outputs:

  1. structured_fields  ->  a dict whose keys map 1-to-1 to SubmissionData
                           fields, so the existing compliance rule engine
                           can run with zero manual data entry.

  2. planner_observations -> a plain-English list of things the vision
                            model noticed that may not be captured by
                            hard rules (e.g. "Lot 7 appears to lack
                            street frontage based on its shape").

Architecture
------------
- Follows the exact same pattern as vision_processor.py:
    image_bytes -> base64 -> ollama_client.chat(vision_model, messages)
- Two separate prompts are sent so the model can focus cleanly on each
  task. Both use the same base64 blob (encoded once).
- JSON parsing is fault-tolerant; any field the model could not read
  stays None so the rule engine emits WARNINGS instead of crashing.
- The OllamaClient and vision_model name are passed in, not hard-coded,
  so callers can override them the same way the rest of the app does.

Usage (from compliance_api.py)
-------------------------------
    from plat_vision_extractor import extract_from_plat_image

    result = extract_from_plat_image(
        ollama_client=ollama,
        image_bytes=await file.read(),
        submission_type="preliminary_plan",   # or "final_plat"
        vision_model="llama3.2-vision:11b",
    )

    submission_data      = result["submission_data"]      # SubmissionData
    planner_observations = result["planner_observations"] # list[str]
    raw_extracted        = result["extracted_fields"]     # dict (for debug)
"""

from __future__ import annotations

import base64
import json
import logging
import re
from typing import Any

from ...ollama_client import OllamaClient   # app/rag/ollama_client.py
from .models import SubmissionData          # app/rag/departments/planning/models.py

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Default model name - matches what main.py and vision_processor.py use
# ---------------------------------------------------------------------------
DEFAULT_VISION_MODEL = "llama3.2-vision:11b"


# ===========================================================================
# PASS 1 - Structured field extraction
# ===========================================================================

_EXTRACTION_PROMPT = """\
You are an expert NC-licensed land surveyor reviewing a Cumberland County
subdivision plat or preliminary plan image.

Your ONLY job right now is to extract observable facts from the image and
return them as a single JSON object. Do NOT add any explanation, markdown,
or code fences - output ONLY the raw JSON.

For every field you cannot determine from the image, output null.
For boolean fields use true or false only when confident; otherwise null.
For numeric fields read labels and dimension callouts directly; estimate
from proportion only as a last resort.

Return this exact JSON structure (all keys required, values may be null):

{
  "submission_type": null,
  "subdivision_name": null,
  "owner_name": null,
  "designer_name": null,
  "scale_feet_per_inch": null,
  "has_date": null,
  "has_north_arrow": null,
  "sheet_width_inches": null,
  "sheet_height_inches": null,
  "has_vicinity_sketch": null,
  "total_acreage": null,
  "has_zoning_district_lines": null,
  "has_existing_easements": null,
  "has_adjoining_owner_names": null,
  "has_row_width_labeled": null,
  "total_proposed_lots": null,
  "min_lot_frontage_ft": null,
  "lots_under_one_acre": null,
  "lots_missing_sqft_label": null,
  "lots_missing_acreage_label": null,
  "lots_sequentially_numbered": null,
  "has_sfha_on_site": null,
  "sfha_boundary_shown": null,
  "sfha_disclosure_note_present": null,
  "has_riparian_watercourse": null,
  "riparian_buffer_shown": null,
  "riparian_buffer_width_ft": null,
  "has_watercourse_on_site": null,
  "drainage_easement_shown": null,
  "drainage_easement_min_width_ft": null,
  "utility_easement_width_ft": null,
  "utility_statement_on_plan": null,
  "water_sewer_type": null,
  "on_site_sewer_disclosure_present": null,
  "max_block_length_ft": null,
  "has_street_names": null,
  "has_street_cross_sections": null,
  "street_corner_radius_ft": null,
  "street_offset_ft": null,
  "has_cul_de_sac": null,
  "cul_de_sac_length_ft": null,
  "cul_de_sac_roadway_diameter_ft": null,
  "cul_de_sac_row_diameter_ft": null,
  "has_hammerhead": null,
  "hammerhead_outside_length_ft": null,
  "hammerhead_outside_width_ft": null,
  "hammerhead_roadway_length_ft": null,
  "hammerhead_roadway_width_ft": null,
  "has_private_streets": null,
  "private_street_class": null,
  "private_street_row_ft": null,
  "class_b_lots_served": null,
  "class_c_lots_served": null,
  "class_b_c_connect_to_paved": null,
  "private_street_disclosure_present": null,
  "class_c_disclosure_present": null,
  "class_b_c_no_further_divide_disclosure": null,
  "private_street_owners_assoc": null,
  "proposed_lots_or_units": null,
  "public_water_within_300ft": null,
  "public_sewer_within_300ft": null,
  "public_water_within_500ft": null,
  "public_sewer_within_500ft": null,
  "in_sewer_service_area": null,
  "density_units_per_acre": null,
  "fire_hydrant_max_spacing_ft": null,
  "fire_hydrant_max_from_lot_ft": null,
  "adjacent_to_school_or_park": null,
  "sidewalk_shown": null,
  "sidewalk_width_inches": null,
  "sidewalk_pedestrian_thickness_in": null,
  "sidewalk_vehicular_thickness_in": null,
  "recreation_area_sqft": null,
  "dwelling_units": null,
  "disturbed_area_acres": null,
  "stormwater_permit_addressed": null,
  "retention_basin_present": null,
  "retention_basin_fence_shown": null,
  "wetlands_shown_if_present": null,
  "topographic_contours_shown": null,
  "in_fort_liberty_special_interest_area": null,
  "in_voluntary_agricultural_district": null,
  "farmland_disclosure_present": null,
  "in_airport_overlay_district": null,
  "airport_disclosure_present": null,
  "in_mia": null,
  "mia_lots": null,
  "conforms_to_approved_prelim": null,
  "surveyor_certificate_present": null,
  "ownership_dedication_cert_present": null,
  "director_cert_present": null,
  "plat_review_officer_cert_present": null,
  "register_of_deeds_space_present": null,
  "nonconforming_structure_disclosure": null,
  "proposed_public_street_disclosure": null,
  "months_since_prelim_approval": null
}

Field guidance (only read values visible on the image):
- submission_type       : "preliminary_plan" or "final_plat" from title/notes
- subdivision_name      : exact text from the title block
- owner_name            : owner name + address from title block
- designer_name         : surveyor or engineer name/firm from title block
- scale_feet_per_inch   : numeric value only (e.g. 50 if scale reads '1"=50'')
- has_north_arrow       : look for compass rose or N-arrow symbol
- has_vicinity_sketch   : small inset location map
- total_proposed_lots   : count numbered parcels/lots shown
- lots_sequentially_numbered : do lot numbers run without gaps?
- lots_missing_sqft_label   : sub-acre lots with no square footage text
- lots_missing_acreage_label: lots >= 1 ac with no acreage text
- has_sfha_on_site      : FEMA flood zone line or 'Zone AE/X' label visible
- sfha_disclosure_note_present : note referencing FEMA/flood in text blocks
- has_riparian_watercourse: river, creek, or perennial stream on site
- topographic_contours_shown : contour lines drawn across the plan
- has_cul_de_sac        : circular bulb at end of a street
- has_hammerhead        : T- or L-shaped turnaround at street end
- has_private_streets   : streets labeled 'Private' or 'Pvt'
- surveyor_certificate_present  : signed/sealed certificate block on plat
- ownership_dedication_cert_present : notarized ownership block present
- director_cert_present : Planning Director signature block present
- water_sewer_type      : "public", "private", "on_site", or null
"""


# ==========================================================================
# PASS 2 - Open-ended planner narrative observations
# ==========================================================================

_NARRATIVE_PROMPT = """\
You are a Cumberland County, NC senior planner reviewing a preliminary
subdivision plat or final plat image for ordinance compliance.

Look carefully at the plat and list EVERY item that:
  * appears to be missing that would typically be required,
  * appears to violate a dimension or design standard,
  * is unclear or ambiguous and needs the planner to verify in the field,
  * raises a concern that the structured data fields cannot capture.

Focus on things a human planner would circle in red or write a comment
about during a standard completeness review. Examples of good observations:
  - "Lot 4 appears to have no street frontage - it may be a landlocked parcel."
  - "A cul-de-sac is visible but no diameter dimension is labeled."
  - "Contour lines appear to be present but the interval is not labeled."
  - "Street intersection at Oak Dr / Pine St shows a very tight angle -
     may not meet minimum corner radius requirements."
  - "No utility statement or note about water/sewer service was found."
  - "The north arrow is missing from the plan sheet."

Return your observations as a JSON array of plain-English strings.
Do NOT add markdown or any text outside the JSON array.
Example format:
["Observation one.", "Observation two.", "Observation three."]

If no significant concerns are visible, return an empty array: []
"""


# ==========================================================================
# JSON helpers
# ==========================================================================

def _strip_to_json(text: str) -> str:
    """
    Strip any markdown fences or leading/trailing prose that the vision
    model may have added around the JSON despite instructions not to.
    Finds the first '{' or '[' and the last '}' or ']'.
    """
    # Remove ```json ... ``` style fences
    text = re.sub(r"```[a-zA-Z]*", "", text).strip()

    # Find the outermost JSON object or array
    start_obj = text.find("{")
    start_arr = text.find("[")
    end_obj = text.rfind("}")
    end_arr = text.rfind("]")

    # Pick whichever valid container comes first
    starts = [(i, c) for i, c in [(start_obj, "}"), (start_arr, "]")] if i != -1]
    if not starts:
        return text  # nothing we can do; let the caller handle the parse error

    start_idx, closer = min(starts, key=lambda x: x[0])
    end_idx = text.rfind(closer)
    if end_idx == -1 or end_idx < start_idx:
        return text

    return text[start_idx : end_idx + 1]


def _parse_extracted_fields(raw: str) -> dict[str, Any]:
    """
    Parse the JSON from Pass 1. On failure, return an empty dict so
    the rule engine still runs (all fields -> None -> all WARNINGs).
    """
    try:
        cleaned = _strip_to_json(raw)
        return json.loads(cleaned)
    except (json.JSONDecodeError, ValueError) as exc:
        logger.warning("Could not parse extraction JSON: %s | raw=%s", exc, raw[:200])
        return {}


def _parse_observations(raw: str) -> list[str]:
    """
    Parse the JSON array from Pass 2. On failure, return a single
    warning string so the planner knows the narrative step failed.
    """
    try:
        cleaned = _strip_to_json(raw)
        result = json.loads(cleaned)
        if isinstance(result, list):
            return [str(s) for s in result if s]
        return []
    except (json.JSONDecodeError, ValueError) as exc:
        logger.warning("Could not parse observation JSON: %s | raw=%s", exc, raw[:200])
        return ["WARNING: Vision model narrative could not be parsed - manual review required."]


# ==========================================================================
# Field -> SubmissionData mapping
# ==========================================================================

# Fields that the extraction prompt returns but that need to be coerced to
# the correct Python type before hydrating SubmissionData.
_BOOL_FIELDS = {
    "has_date", "has_north_arrow", "has_vicinity_sketch", "has_zoning_district_lines",
    "has_existing_easements", "has_adjoining_owner_names", "has_row_width_labeled",
    "lots_sequentially_numbered", "has_sfha_on_site", "sfha_boundary_shown",
    "sfha_disclosure_note_present", "has_riparian_watercourse", "riparian_buffer_shown",
    "has_watercourse_on_site", "drainage_easement_shown", "utility_statement_on_plan",
    "on_site_sewer_disclosure_present", "has_street_names", "has_street_cross_sections",
    "has_cul_de_sac", "has_hammerhead", "has_private_streets",
    "class_b_c_connect_to_paved", "private_street_disclosure_present",
    "class_c_disclosure_present", "class_b_c_no_further_divide_disclosure",
    "private_street_owners_assoc", "public_water_within_300ft", "public_sewer_within_300ft",
    "public_water_within_500ft", "public_sewer_within_500ft", "in_sewer_service_area",
    "adjacent_to_school_or_park", "sidewalk_shown", "stormwater_permit_addressed",
    "retention_basin_present", "retention_basin_fence_shown", "wetlands_shown_if_present",
    "topographic_contours_shown", "in_fort_liberty_special_interest_area",
    "in_voluntary_agricultural_district", "farmland_disclosure_present",
    "in_airport_overlay_district", "airport_disclosure_present", "in_mia",
    "conforms_to_approved_prelim", "surveyor_certificate_present",
    "ownership_dedication_cert_present", "director_cert_present",
    "plat_review_officer_cert_present", "register_of_deeds_space_present",
    "nonconforming_structure_disclosure", "proposed_public_street_disclosure",
}

_INT_FIELDS = {
    "total_proposed_lots", "lots_under_one_acre", "lots_missing_sqft_label",
    "lots_missing_acreage_label", "class_b_lots_served", "class_c_lots_served",
    "proposed_lots_or_units", "dwelling_units", "mia_lots",
}

_FLOAT_FIELDS = {
    "scale_feet_per_inch", "sheet_width_inches", "sheet_height_inches",
    "total_acreage", "min_lot_frontage_ft", "riparian_buffer_width_ft",
    "drainage_easement_min_width_ft", "utility_easement_width_ft",
    "max_block_length_ft", "street_corner_radius_ft", "street_offset_ft",
    "cul_de_sac_length_ft", "cul_de_sac_roadway_diameter_ft",
    "cul_de_sac_row_diameter_ft", "hammerhead_outside_length_ft",
    "hammerhead_outside_width_ft", "hammerhead_roadway_length_ft",
    "hammerhead_roadway_width_ft", "private_street_row_ft",
    "density_units_per_acre", "fire_hydrant_max_spacing_ft",
    "fire_hydrant_max_from_lot_ft", "sidewalk_width_inches",
    "sidewalk_pedestrian_thickness_in", "sidewalk_vehicular_thickness_in",
    "recreation_area_sqft", "disturbed_area_acres", "months_since_prelim_approval",
}


def _coerce(key: str, value: Any) -> Any:
    """Safely coerce a raw JSON value to the type SubmissionData expects."""
    if value is None:
        return None
    try:
        if key in _BOOL_FIELDS:
            if isinstance(value, bool):
                return value
            return str(value).lower() in ("true", "yes", "1")
        if key in _INT_FIELDS:
            return int(float(value))
        if key in _FLOAT_FIELDS:
            return float(value)
    except (TypeError, ValueError):
        logger.debug("Coerce failed for field '%s' value '%s' - setting None", key, value)
        return None
    return value  # string fields pass through as-is


def _build_submission_data(
    extracted: dict[str, Any],
    caller_submission_type: str,
) -> SubmissionData:
    """
    Hydrate a SubmissionData dataclass from the vision model's extraction dict.

    The caller-supplied submission_type overrides whatever the model
    detected, so the API caller always has final say.
    """
    kwargs: dict[str, Any] = {}

    # Build the complete set of valid SubmissionData field names from the
    # dataclass definition so we never pass unexpected kwargs.
    import dataclasses

    valid_fields = {f.name for f in dataclasses.fields(SubmissionData)}

    for key, value in extracted.items():
        if key not in valid_fields:
            continue  # ignore any hallucinated keys from the model
        kwargs[key] = _coerce(key, value)

    # The API caller's submission_type always wins
    kwargs["submission_type"] = caller_submission_type

    return SubmissionData(**kwargs)


# ==========================================================================
# Public entry point
# ==========================================================================

def extract_from_plat_image(
    ollama_client: OllamaClient,
    image_bytes: bytes,
    submission_type: str,
    vision_model: str = DEFAULT_VISION_MODEL,
) -> dict[str, Any]:
    """
    Run the two-pass vision extraction on a plat image.

    Parameters
    ----------
    ollama_client   : Shared OllamaClient instance (same one used by main.py)
    image_bytes     : Raw bytes of the uploaded plat image (PNG / JPEG / TIFF)
    submission_type : "preliminary_plan" or "final_plat" - supplied by the API
                      caller so the rule engine knows which rules apply.
    vision_model    : Ollama model tag (default: llama3.2-vision:11b)

    Returns
    -------
    {
        "submission_data"      : SubmissionData  (hydrated dataclass)
        "planner_observations" : list[str]       (open-ended narrative findings)
        "extracted_fields"     : dict            (raw extraction for debug/audit)
        "vision_model"         : str             (model that was used)
    }
    """
    # Encode the image once; reuse for both passes
    image_b64 = base64.b64encode(image_bytes).decode("utf-8")

    # ------------------------------------------------------------------
    # Pass 1 - Structured JSON extraction
    # ------------------------------------------------------------------
    logger.info("Plat vision Pass 1: structured field extraction (%s)", vision_model)
    try:
        raw_extraction = ollama_client.chat(
            model=vision_model,
            messages=[
                {
                    "role": "user",
                    "content": _EXTRACTION_PROMPT,
                    "images": [image_b64],
                }
            ],
            format="json",
        )
    except Exception as exc:
        logger.error("Pass 1 vision call failed: %s", exc)
        raw_extraction = "{}"

    extracted_fields = _parse_extracted_fields(raw_extraction)
    logger.info(
        "Pass 1 extracted %d fields",
        sum(1 for v in extracted_fields.values() if v is not None),
    )

    # ------------------------------------------------------------------
    # Pass 2 - Open-ended planner observations
    # ------------------------------------------------------------------
    logger.info("Plat vision Pass 2: planner narrative observations (%s)", vision_model)
    try:
        raw_narrative = ollama_client.chat(
            model=vision_model,
            messages=[
                {
                    "role": "user",
                    "content": _NARRATIVE_PROMPT,
                    "images": [image_b64],
                }
            ],
            format="json",
        )
    except Exception as exc:
        logger.error("Pass 2 vision call failed: %s", exc)
        raw_narrative = "[]"

    planner_observations = _parse_observations(raw_narrative)
    logger.info("Pass 2 produced %d planner observations", len(planner_observations))

    # ------------------------------------------------------------------
    # Build SubmissionData from extracted fields
    # ------------------------------------------------------------------
    submission_data = _build_submission_data(extracted_fields, submission_type)

    return {
        "submission_data": submission_data,
        "planner_observations": planner_observations,
        "extracted_fields": extracted_fields,
        "vision_model": vision_model,
    }
