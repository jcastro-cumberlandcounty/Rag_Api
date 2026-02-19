"""
compliance_api.py - Planning Department Compliance API
=======================================================
FastAPI router providing compliance-checking endpoints for:
  - Cumberland County Subdivision Ordinance
  - Town of Wade Subdivision Ordinance

Jurisdiction is determined by the 'jurisdiction' field in the request body:
  "county"  -> Cumberland County rules
  "wade"    -> Town of Wade rules

Endpoints:
  POST /compliance/check                -> auto-routes by jurisdiction
  POST /compliance/check/county         -> always runs County rules
  POST /compliance/check/wade           -> always runs Wade rules
  POST /compliance/check/failures-only  -> auto-routes, returns FAILs + WARNINGs only
  POST /compliance/check/compare        -> side-by-side County vs Wade comparison
  GET  /compliance/jurisdictions         -> lists available jurisdictions and rule counts
  GET  /compliance/submissions           -> lists saved test submissions on the VM

  -- Plat Image Vision Endpoints (NEW) --
  POST /compliance/check-plat-image              -> upload plat image, AI extracts fields,
                                                    runs full compliance report
  POST /compliance/check-plat-image/failures-only -> same but returns only FAILs + WARNINGs
                                                     + planner observations

Test Submission Saving:
  Completed compliance checks are saved as JSON to:
    /submissions/{jurisdiction}/{submission_type}/{timestamp}_{subdivision_name}.json
  Both the raw request data and the compliance report are saved together.
  Plat image results are saved under:
    /submissions/{jurisdiction}/{submission_type}/plat_images/{timestamp}_{filename}.json
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile

from .models import ComplianceRequest, SubmissionData
from .compliance_rules import (
    run_all_rules,
    run_county_rules,
    run_wade_rules,
    build_report,
    ALL_COUNTY_RULES,
    ALL_WADE_RULES,
)
from .plat_vision_extractor import extract_from_plat_image

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/compliance", tags=["Planning - Compliance Checking"])

# ------------------------------------------------------------------
# VM folder for test submissions
# Base path can be overridden via the COMPLIANCE_SUBMISSIONS_DIR
# environment variable (useful when running in a container).
# ------------------------------------------------------------------
_DEFAULT_SAVE_DIR = Path("/submissions")
SUBMISSIONS_DIR   = Path(os.getenv("COMPLIANCE_SUBMISSIONS_DIR", str(_DEFAULT_SAVE_DIR)))

# Allowed image types for plat image uploads
_ALLOWED_IMAGE_TYPES = {
    "image/jpeg",
    "image/jpg",
    "image/png",
    "image/tiff",
    "image/bmp",
    "image/webp",
}


# ==================================================================
# Dependencies
# ==================================================================

def get_ollama(request: Request):
    """
    FastAPI dependency that returns the shared OllamaClient from app.state.
    main.py must set app.state.ollama = OllamaClient(...) at startup.
    """
    return request.app.state.ollama


# ==================================================================
# Internal helpers
# ==================================================================

def _to_submission_data(req: ComplianceRequest) -> SubmissionData:
    """Convert a validated Pydantic request into a SubmissionData dataclass."""
    return SubmissionData(**req.model_dump())


def _save_submission(req: ComplianceRequest, report: dict) -> Optional[str]:
    """
    Persist the raw request and compliance report to the VM test folder.

    Folder structure:
      /submissions/{jurisdiction}/{submission_type}/
          {YYYY-MM-DD_HHMMSS}_{subdivision_name}.json

    Returns the saved file path string, or None if saving failed.
    """
    try:
        safe_name = (req.subdivision_name or "unnamed").replace(" ", "_").replace("/", "-")
        timestamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
        folder    = SUBMISSIONS_DIR / req.jurisdiction / req.submission_type
        folder.mkdir(parents=True, exist_ok=True)
        file_path = folder / f"{timestamp}_{safe_name}.json"

        payload = {
            "saved_at":    datetime.now().isoformat(),
            "jurisdiction": req.jurisdiction,
            "submission": req.model_dump(),
            "report":     report,
        }
        file_path.write_text(json.dumps(payload, indent=2, default=str))
        logger.info("Compliance submission saved: %s", file_path)
        return str(file_path)
    except Exception as exc:
        logger.warning("Could not save submission to disk: %s", exc)
        return None


def _save_plat_image_result(
    filename: str,
    jurisdiction: str,
    submission_type: str,
    report: dict,
) -> Optional[str]:
    """
    Persist a plat-image compliance result to the VM test folder.

    Folder structure:
      /submissions/{jurisdiction}/{submission_type}/plat_images/
          {YYYY-MM-DD_HHMMSS}_{filename}.json

    Returns the saved file path string, or None if saving failed.
    """
    try:
        safe_name = filename.replace(" ", "_").replace("/", "-")
        timestamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
        folder    = SUBMISSIONS_DIR / jurisdiction / submission_type / "plat_images"
        folder.mkdir(parents=True, exist_ok=True)
        file_path = folder / f"{timestamp}_{safe_name}.json"

        file_path.write_text(json.dumps(report, indent=2, default=str))
        logger.info("Plat image result saved: %s", file_path)
        return str(file_path)
    except Exception as exc:
        logger.warning("Could not save plat image result to disk: %s", exc)
        return None


def _build_response(report: dict, saved_path: Optional[str]) -> dict:
    """Attach metadata (save path) to a completed report."""
    report["_meta"] = {
        "saved_to": saved_path or "not saved",
        "checked_at": datetime.now().isoformat(),
    }
    return report


# ==================================================================
# Existing endpoints — unchanged
# ==================================================================

@router.post(
    "/check",
    summary="Run compliance rules – auto-routes by jurisdiction",
    response_description=(
        "Structured compliance report with PASS / FAIL / WARNING / N/A per rule. "
        "Jurisdiction is determined by the 'jurisdiction' field ('county' or 'wade')."
    ),
)
def check_compliance(
    req: ComplianceRequest,
    save: bool = Query(
        default=True,
        description="Save submission + report to VM test folder.",
    ),
) -> dict:
    """
    Evaluate a developer submission against the correct ordinance rule set.

    - **jurisdiction = 'county'** -> Cumberland County Subdivision Ordinance rules
    - **jurisdiction = 'wade'**   -> Town of Wade Subdivision Ordinance rules

    Returns a full compliance report including:
    - **overall_status**: PASS | WARNING | FAIL
    - **summary**: counts by status
    - **failures**: items requiring correction before approval
    - **warnings**: items requiring manual verification
    - **passed**: confirmed compliant items
    - **not_applicable**: rules skipped for this submission type / development type
    """
    data    = _to_submission_data(req)
    results = run_all_rules(data)
    report  = build_report(results)
    report["jurisdiction"] = req.jurisdiction

    saved_path = _save_submission(req, report) if save else None
    return _build_response(report, saved_path)


@router.post(
    "/check/county",
    summary="Run Cumberland County compliance rules (explicit)",
    response_description="Compliance report evaluated against Cumberland County Subdivision Ordinance.",
)
def check_compliance_county(
    req: ComplianceRequest,
    save: bool = Query(default=True, description="Save submission + report to VM test folder."),
) -> dict:
    """
    Always evaluates against **Cumberland County** rules regardless of the
    jurisdiction field in the request body.

    Use this endpoint when you want to explicitly test County rules, or to
    compare County vs. Wade results for the same submission data.
    """
    # Force county jurisdiction
    req_dict               = req.model_dump()
    req_dict["jurisdiction"] = "county"
    county_req             = ComplianceRequest(**req_dict)

    data    = _to_submission_data(county_req)
    results = run_county_rules(data)
    report  = build_report(results)
    report["jurisdiction"] = "county"

    saved_path = _save_submission(county_req, report) if save else None
    return _build_response(report, saved_path)


@router.post(
    "/check/wade",
    summary="Run Town of Wade compliance rules (explicit)",
    response_description="Compliance report evaluated against Town of Wade Subdivision Ordinance.",
)
def check_compliance_wade(
    req: ComplianceRequest,
    save: bool = Query(default=True, description="Save submission + report to VM test folder."),
) -> dict:
    """
    Always evaluates against **Town of Wade** rules regardless of the
    jurisdiction field in the request body.

    Use this endpoint when you want to explicitly test Wade rules, or to
    compare County vs. Wade results for the same submission data.
    """
    req_dict               = req.model_dump()
    req_dict["jurisdiction"] = "wade"
    wade_req               = ComplianceRequest(**req_dict)

    data    = _to_submission_data(wade_req)
    results = run_wade_rules(data)
    report  = build_report(results)
    report["jurisdiction"] = "wade"

    saved_path = _save_submission(wade_req, report) if save else None
    return _build_response(report, saved_path)


@router.post(
    "/check/failures-only",
    summary="Return only FAIL and WARNING items – auto-routes by jurisdiction",
    response_description="Deficiency list: only FAIL and WARNING results returned.",
)
def check_compliance_failures(
    req: ComplianceRequest,
    save: bool = Query(default=True, description="Save submission + report to VM test folder."),
) -> dict:
    """
    Same as **/check** but returns only the FAIL and WARNING items.
    Useful for generating a quick deficiency letter for the developer.

    Jurisdiction is auto-routed from the 'jurisdiction' field.
    """
    data    = _to_submission_data(req)
    results = run_all_rules(data)
    report  = build_report(results)

    deficiency_report = {
        "jurisdiction":   req.jurisdiction,
        "overall_status": report["overall_status"],
        "summary": {
            "total":           report["summary"]["total"],
            "fail":            report["summary"]["fail"],
            "warning":         report["summary"]["warning"],
            "not_applicable":  report["summary"]["not_applicable"],
        },
        "failures":  report["failures"],
        "warnings":  report["warnings"],
    }

    saved_path = _save_submission(req, deficiency_report) if save else None
    return _build_response(deficiency_report, saved_path)


@router.post(
    "/check/compare",
    summary="Compare County vs Wade results for the same submission",
    response_description=(
        "Side-by-side comparison of County and Wade compliance results "
        "for the same submission data."
    ),
)
def check_compliance_compare(
    req: ComplianceRequest,
    save: bool = Query(default=False, description="Save comparison report to VM test folder."),
) -> dict:
    """
    Run the same submission against **both** County and Wade rule sets and
    return a side-by-side comparison.

    Useful during testing to understand how a submission would be evaluated
    under each ordinance.
    """
    base = req.model_dump()

    county_req  = ComplianceRequest(**{**base, "jurisdiction": "county"})
    wade_req    = ComplianceRequest(**{**base, "jurisdiction": "wade"})

    county_data    = _to_submission_data(county_req)
    wade_data      = _to_submission_data(wade_req)

    county_results = run_county_rules(county_data)
    wade_results   = run_wade_rules(wade_data)

    county_report  = build_report(county_results)
    wade_report    = build_report(wade_results)

    county_report["jurisdiction"] = "county"
    wade_report["jurisdiction"]   = "wade"

    comparison = {
        "submission_type":  req.submission_type,
        "development_type": req.development_type,
        "county": {
            "overall_status": county_report["overall_status"],
            "summary":        county_report["summary"],
            "failures":       county_report["failures"],
            "warnings":       county_report["warnings"],
        },
        "wade": {
            "overall_status": wade_report["overall_status"],
            "summary":        wade_report["summary"],
            "failures":       wade_report["failures"],
            "warnings":       wade_report["warnings"],
        },
        "difference": {
            "county_only_failures": [
                f for f in county_report["failures"]
                if not any(w["rule_id"] == f["rule_id"] for w in wade_report["failures"])
            ],
            "wade_only_failures": [
                f for f in wade_report["failures"]
                if not any(c["rule_id"] == f["rule_id"] for c in county_report["failures"])
            ],
        },
    }

    if save:
        folder    = SUBMISSIONS_DIR / "comparisons"
        folder.mkdir(parents=True, exist_ok=True)
        safe_name = (req.subdivision_name or "unnamed").replace(" ", "_")
        timestamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
        file_path = folder / f"{timestamp}_{safe_name}_compare.json"
        try:
            file_path.write_text(json.dumps(comparison, indent=2, default=str))
            comparison["_meta"] = {
                "saved_to":   str(file_path),
                "checked_at": datetime.now().isoformat(),
            }
        except Exception as exc:
            logger.warning("Could not save comparison: %s", exc)
            comparison["_meta"] = {"saved_to": "not saved", "checked_at": datetime.now().isoformat()}
    else:
        comparison["_meta"] = {"saved_to": "not saved", "checked_at": datetime.now().isoformat()}

    return comparison


@router.get(
    "/jurisdictions",
    summary="List available jurisdictions and rule counts",
)
def list_jurisdictions() -> dict:
    """
    Returns metadata about supported jurisdictions including the number
    of active rules in each ordinance's rule set.
    """
    return {
        "jurisdictions": [
            {
                "id":          "county",
                "label":       "Cumberland County",
                "ordinance":   "Cumberland County Subdivision Ordinance (amended through August 21, 2023)",
                "rule_count":  len(ALL_COUNTY_RULES),
                "endpoint":    "/compliance/check/county",
            },
            {
                "id":          "wade",
                "label":       "Town of Wade",
                "ordinance":   "Town of Wade Subdivision Ordinance (amended through August 9, 2022)",
                "rule_count":  len(ALL_WADE_RULES),
                "endpoint":    "/compliance/check/wade",
            },
        ],
        "submission_types":  ["preliminary_plan", "final_plat"],
        "development_types": ["subdivision", "group_development", "mobile_home_park", "condominium"],
        "test_save_folder":  str(SUBMISSIONS_DIR),
    }


@router.get(
    "/submissions",
    summary="List saved test submissions on the VM",
)
def list_saved_submissions(
    jurisdiction: Optional[str] = Query(
        default=None,
        description="Filter by jurisdiction: 'county' or 'wade'",
    ),
    submission_type: Optional[str] = Query(
        default=None,
        description="Filter by type: 'preliminary_plan' or 'final_plat'",
    ),
) -> dict:
    """
    List all test submissions currently saved in the VM submissions folder.
    Optionally filter by jurisdiction and/or submission type.
    """
    if not SUBMISSIONS_DIR.exists():
        return {"submissions": [], "total": 0, "folder": str(SUBMISSIONS_DIR)}

    files = []
    search_root = SUBMISSIONS_DIR

    try:
        for jur_dir in sorted(search_root.iterdir()):
            if not jur_dir.is_dir():
                continue
            if jurisdiction and jur_dir.name != jurisdiction:
                continue
            for type_dir in sorted(jur_dir.iterdir()):
                if not type_dir.is_dir():
                    continue
                if submission_type and type_dir.name != submission_type:
                    continue
                for f in sorted(type_dir.glob("*.json"), reverse=True):
                    files.append({
                        "file":            f.name,
                        "path":            str(f),
                        "jurisdiction":    jur_dir.name,
                        "submission_type": type_dir.name,
                        "size_kb":         round(f.stat().st_size / 1024, 2),
                    })
    except Exception as exc:
        logger.warning("Error listing submissions: %s", exc)

    return {
        "submissions": files,
        "total":       len(files),
        "folder":      str(SUBMISSIONS_DIR),
    }


# ==================================================================
# NEW — Plat Image Vision Endpoints
# ==================================================================

@router.post(
    "/check-plat-image",
    summary="Upload a plat image → AI extracts fields → full compliance report",
    response_description=(
        "Full compliance report generated from vision AI extraction of the plat image, "
        "plus open-ended planner observations from the vision model."
    ),
)
async def check_plat_image(
    plat_image: UploadFile = File(
        ...,
        description="Scanned or exported plat image (PNG, JPEG, TIFF, BMP, WebP)",
    ),
    submission_type: str = Form(
        ...,
        description="'preliminary_plan' or 'final_plat'",
    ),
    jurisdiction: str = Form(
        default="county",
        description="'county' or 'wade' — determines which rule set is applied after extraction",
    ),
    vision_model: str = Form(
        default="llama3.2-vision:11b",
        description="Ollama vision model tag to use for extraction",
    ),
    save: bool = Query(
        default=True,
        description="Save the result to the VM submissions folder",
    ),
    ollama=Depends(get_ollama),
) -> dict:
    """
    Two-pass AI plat review workflow using the local Ollama vision model:

    **Pass 1 — Structured extraction**
    The vision model reads the plat image and extracts every observable
    field (subdivision name, lot count, scale, north arrow, flood zone
    indicators, easements, cul-de-sac dimensions, certificate blocks,
    etc.) into a structured JSON object that maps directly to SubmissionData.

    **Pass 2 — Planner observations**
    A second prompt asks the vision model to act as a senior planner and
    flag anything suspicious, missing, or unclear that the hard rules
    cannot capture on their own (e.g. lots that appear landlocked,
    unlabeled cul-de-sac diameters, tight intersection angles, etc.).

    After both passes the extracted SubmissionData is fed into the correct
    jurisdiction's compliance rule engine and a complete report is returned.

    **Returns**
    - All standard compliance report fields (overall_status, summary,
      failures, warnings, passed, not_applicable)
    - jurisdiction: which rule set was applied
    - planner_observations: list of open-ended narrative findings
    - extracted_fields: raw dict of what the vision model extracted (for audit)
    - vision_model: which Ollama model was used
    - source_file: original filename of the uploaded image
    """
    # Validate image type
    if plat_image.content_type not in _ALLOWED_IMAGE_TYPES:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Unsupported file type '{plat_image.content_type}'. "
                f"Upload a PNG, JPEG, TIFF, BMP, or WebP image."
            ),
        )

    # Validate submission type
    if submission_type not in ("preliminary_plan", "final_plat"):
        raise HTTPException(
            status_code=400,
            detail="submission_type must be 'preliminary_plan' or 'final_plat'.",
        )

    # Validate jurisdiction
    if jurisdiction not in ("county", "wade"):
        raise HTTPException(
            status_code=400,
            detail="jurisdiction must be 'county' or 'wade'.",
        )

    # Read image bytes
    image_bytes = await plat_image.read()
    if not image_bytes:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")

    logger.info(
        "Plat image received: filename=%s size=%d bytes submission_type=%s jurisdiction=%s",
        plat_image.filename,
        len(image_bytes),
        submission_type,
        jurisdiction,
    )

    # Run vision extraction (Pass 1 structured fields + Pass 2 narrative)
    try:
        vision_result = extract_from_plat_image(
            ollama_client=ollama,
            image_bytes=image_bytes,
            submission_type=submission_type,
            vision_model=vision_model,
        )
    except Exception as exc:
        logger.exception("Vision extraction failed")
        raise HTTPException(
            status_code=500,
            detail=f"Vision extraction failed: {exc}",
        )

    # Route to the correct jurisdiction rule set — same logic as manual endpoints
    submission_data = vision_result["submission_data"]
    if jurisdiction == "wade":
        results = run_wade_rules(submission_data)
    else:
        results = run_county_rules(submission_data)

    report = build_report(results)

    # Attach vision-specific outputs
    report["jurisdiction"]         = jurisdiction
    report["planner_observations"] = vision_result["planner_observations"]
    report["extracted_fields"]     = vision_result["extracted_fields"]
    report["vision_model"]         = vision_result["vision_model"]
    report["source_file"]          = plat_image.filename

    # Save to disk using the plat_images subfolder
    saved_path = None
    if save:
        saved_path = _save_plat_image_result(
            filename=plat_image.filename or "unknown",
            jurisdiction=jurisdiction,
            submission_type=submission_type,
            report=report,
        )

    return _build_response(report, saved_path)


@router.post(
    "/check-plat-image/failures-only",
    summary="Upload a plat image → return only FAIL + WARNING items + planner observations",
    response_description="Deficiency list generated from vision AI extraction of the plat image.",
)
async def check_plat_image_failures(
    plat_image: UploadFile = File(...),
    submission_type: str = Form(...),
    jurisdiction: str = Form(default="county"),
    vision_model: str = Form(default="llama3.2-vision:11b"),
    save: bool = Query(default=True),
    ollama=Depends(get_ollama),
) -> dict:
    """
    Same as **/check-plat-image** but strips out PASS and N/A items.

    Returns only failures, warnings, and planner observations — ideal
    for generating a deficiency letter or review comment list directly
    from a scanned plat with no manual data entry.
    """
    # Reuse the full endpoint — it handles all validation and vision logic
    full = await check_plat_image(
        plat_image=plat_image,
        submission_type=submission_type,
        jurisdiction=jurisdiction,
        vision_model=vision_model,
        save=save,
        ollama=ollama,
    )

    return {
        "jurisdiction":         full["jurisdiction"],
        "overall_status":       full["overall_status"],
        "summary": {
            "total":           full["summary"]["total"],
            "fail":            full["summary"]["fail"],
            "warning":         full["summary"]["warning"],
            "not_applicable":  full["summary"]["not_applicable"],
        },
        "failures":             full["failures"],
        "warnings":             full["warnings"],
        "planner_observations": full["planner_observations"],
        "extracted_fields":     full["extracted_fields"],
        "vision_model":         full["vision_model"],
        "source_file":          full["source_file"],
        "_meta":                full["_meta"],
    }
