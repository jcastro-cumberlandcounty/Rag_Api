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
  GET  /compliance/jurisdictions         -> lists available jurisdictions and rule counts

Test Submission Saving:
  Completed compliance checks are saved as JSON to:
    /submissions/{jurisdiction}/{submission_type}/{timestamp}_{subdivision_name}.json
  Both the raw request data and the compliance report are saved together.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Query

from .models import ComplianceRequest, SubmissionData
from .compliance_rules import (
    run_all_rules,
    run_county_rules,
    run_wade_rules,
    build_report,
    ALL_COUNTY_RULES,
    ALL_WADE_RULES,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/compliance", tags=["Planning - Compliance Checking"])

# ------------------------------------------------------------------
# VM folder for test submissions
# Base path can be overridden via the COMPLIANCE_SUBMISSIONS_DIR
# environment variable (useful when running in a container).
# ------------------------------------------------------------------
_DEFAULT_SAVE_DIR = Path("/submissions")
SUBMISSIONS_DIR   = Path(os.getenv("COMPLIANCE_SUBMISSIONS_DIR", str(_DEFAULT_SAVE_DIR)))


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


def _build_response(report: dict, saved_path: Optional[str]) -> dict:
    """Attach metadata (save path) to a completed report."""
    report["_meta"] = {
        "saved_to": saved_path or "not saved",
        "checked_at": datetime.now().isoformat(),
    }
    return report


# ==================================================================
# Endpoints
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