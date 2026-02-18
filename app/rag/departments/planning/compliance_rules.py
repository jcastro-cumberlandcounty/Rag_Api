"""
compliance_rules.py - Compliance Rules Engine
==============================================
Hardcoded compliance rules for:
  - Cumberland County Subdivision Ordinance (amended through August 21, 2023)
  - Town of Wade Subdivision Ordinance (amended through August 9, 2022)

Rules are grouped into:
  ALL_COUNTY_RULES  -> run against submissions in unincorporated Cumberland County
  ALL_WADE_RULES    -> run against submissions in the Town of Wade planning jurisdiction

run_all_rules(data) dispatches automatically based on data.jurisdiction.

Rule ID prefixes:
  MAP  - Map format / scale / sheet size
  TTL  - Title block data
  PPL  - Preliminary plan data requirements
  LOT  - Lot standards
  STR  - Street design
  CDS  - Cul-de-sac / hammerhead
  PVT  - Private streets
  UTL  - Utilities (water / sewer)
  FIR  - Fire hydrants
  SWK  - Sidewalks
  REC  - Recreation area
  SWM  - Stormwater
  DRN  - Drainage easements
  UEZ  - Utility easements
  ENV  - Environmental / special overlays
  MIA  - Municipal Influence Area
  FPL  - Final plat certificates & disclosures
  WAD  - Wade-specific rules (street construction, town water, etc.)
  MHP  - Mobile home park rules (Wade)
  GRP  - Group development rules (Wade)
"""

from __future__ import annotations

from typing import Callable, List

from .models import SubmissionData, RuleResult, Status


RuleFunc = Callable[[SubmissionData], RuleResult]


# ==============================================================
# Helper factories
# ==============================================================

def _na(rule_id: str, rule_name: str, section: str) -> RuleResult:
    return RuleResult(
        rule_id=rule_id,
        status=Status.NOT_APPLICABLE,
        rule_name=rule_name,
        section=section,
        detail="Not applicable to this submission.",
    )


def _pass(rule_id: str, rule_name: str, section: str, detail: str, value=None) -> RuleResult:
    return RuleResult(
        rule_id=rule_id,
        status=Status.PASS,
        rule_name=rule_name,
        section=section,
        detail=detail,
        value_found=value,
    )


def _fail(rule_id: str, rule_name: str, section: str, detail: str, fix: str, value=None) -> RuleResult:
    return RuleResult(
        rule_id=rule_id,
        status=Status.FAIL,
        rule_name=rule_name,
        section=section,
        detail=detail,
        fix=fix,
        value_found=value,
    )


def _warn(rule_id: str, rule_name: str, section: str, detail: str, fix: str = "", value=None) -> RuleResult:
    return RuleResult(
        rule_id=rule_id,
        status=Status.WARNING,
        rule_name=rule_name,
        section=section,
        detail=detail,
        fix=fix,
        value_found=value,
    )


# ==============================================================
# MAP â Scale & Sheet Size
# ==============================================================

def rule_map_scale(d: SubmissionData) -> RuleResult:
    """
    Scale ranges (ft per inch):
      Preliminary plan:        50â200  (both County Sec 2203 and Wade Sec 5.1)
      County final plat:       20â200  (Sec 2503.B checklist)
      Wade final plat:         50â200  (Wade Sec 5.2)
    """
    rid, name = "MAP-001", "Map Scale"
    is_final = d.submission_type == "final_plat"
    is_wade  = d.jurisdiction == "wade"

    if is_final and not is_wade:
        sec = "Sec. 2503.B"
        lo, hi = 20, 200
    else:
        sec = "Sec. 2203" if not is_wade else ("Sec. 5.2" if is_final else "Sec. 5.1")
        lo, hi = 50, 200

    if d.scale_feet_per_inch is None:
        return _warn(rid, name, sec,
                     "Scale not extracted from submission.",
                     f"Confirm plan is drawn at {lo}â{hi} ft per inch.")
    if lo <= d.scale_feet_per_inch <= hi:
        return _pass(rid, name, sec,
                     f"Scale {d.scale_feet_per_inch} ft/in is within {lo}â{hi} ft/in.",
                     d.scale_feet_per_inch)
    return _fail(rid, name, sec,
                 f"Scale {d.scale_feet_per_inch} ft/in is outside the {lo}â{hi} ft/in range.",
                 f"Redraw plan at a scale between {lo} ft/in and {hi} ft/in.",
                 d.scale_feet_per_inch)


def rule_sheet_size(d: SubmissionData) -> RuleResult:
    rid, name, sec = "MAP-002", "Preliminary Plan Sheet Size", "Sec. 2203"
    if d.submission_type != "preliminary_plan":
        return _na(rid, name, sec)
    w, h = d.sheet_width_inches, d.sheet_height_inches
    if w is None or h is None:
        return _warn(rid, name, sec,
                     "Sheet dimensions not extracted.",
                     "Verify plan is submitted on 24 x 36 inch sheets.")
    if (w == 24 and h == 36) or (w == 36 and h == 24):
        return _pass(rid, name, sec, f"Sheet size {w}-{h} inches is correct.")
    return _fail(rid, name, sec,
                 f"Sheet size {w}-{h} inches does not meet required 24-36 inches.",
                 "Resubmit on 24-36 inch sheets.")


def rule_final_plat_sheet_size(d: SubmissionData) -> RuleResult:
    rid, name, sec = "MAP-003", "Final Plat Sheet Size", "Sec. 2503.B"
    if d.submission_type != "final_plat":
        return _na(rid, name, sec)
    w, h = d.sheet_width_inches, d.sheet_height_inches
    if w is None or h is None:
        return _warn(rid, name, sec,
                     "Sheet dimensions not extracted.",
                     "Verify sheet is 18-24 or 24-36 inches.")
    valid = {(18, 24), (24, 18), (24, 36), (36, 24)}
    if (w, h) in valid:
        return _pass(rid, name, sec, f"Sheet size {w}-{h} inches is acceptable.")
    return _fail(rid, name, sec,
                 f"Sheet size {w}-{h} inches. Final plats must be 18-24 or 24-36 inches.",
                 "Resubmit final plat on 18-24 or 24-36 inch sheets.")


def rule_topographic_contours(d: SubmissionData) -> RuleResult:
    rid, name, sec = "MAP-004", "Topographic Contours (1 or 2 ft intervals)", "Sec. 2203"
    if d.submission_type != "preliminary_plan":
        return _na(rid, name, sec)
    if d.topographic_contours_shown is True:
        return _pass(rid, name, sec, "Topographic contours at 1 or 2 ft intervals shown.")
    if d.topographic_contours_shown is False:
        return _fail(rid, name, sec,
                     "Topographic contours missing from preliminary plan.",
                     "Superimpose plan on topographic map with 1 or 2 ft interval contours.")
    return _warn(rid, name, sec,
                 "Topographic contours not verified.",
                 "Confirm 1 or 2 ft interval contours are shown on plan.")


def rule_final_plat_mylar(d: SubmissionData) -> RuleResult:
    rid, name, sec = "MAP-005", "Final Plat Material (Mylar/Archival Film)", "Sec. 2503.B"
    if d.submission_type != "final_plat":
        return _na(rid, name, sec)
    if d.final_plat_mylar_material is True:
        return _pass(rid, name, sec, "Final plat submitted on mylar or archival-quality film.")
    if d.final_plat_mylar_material is False:
        return _fail(rid, name, sec,
                     "Final plat material does not appear to be original ink on polyester film "
                     "(mylar) or equivalent archival-quality reproducible map.",
                     "Resubmit final plat on original ink on polyester film (mylar) or ANSI "
                     "archival-quality transparent drawing material per Sec. 2503.B.")
    return _warn(rid, name, sec,
                 "Final plat material not verified.",
                 "Confirm plat is on mylar or ANSI archival-quality reproducible material.")


# ==============================================================
# TTL â Title Block
# ==============================================================

def rule_subdivision_name(d: SubmissionData) -> RuleResult:
    rid, name, sec = "TTL-001", "Subdivision / Development Name", "Sec. 2203.A.1"
    if d.subdivision_name:
        return _pass(rid, name, sec, f"Subdivision name present: '{d.subdivision_name}'.")
    return _fail(rid, name, sec,
                 "Subdivision or development name missing.",
                 "Add subdivision/development name to title block. "
                 "Confirm no duplicate name exists in Cumberland County.")


def rule_owner_designer(d: SubmissionData) -> RuleResult:
    rid, name, sec = "TTL-002", "Owner and Designer Information", "Sec. 2203.A.2"
    missing = []
    if not d.owner_name:
        missing.append("owner name/address")
    if not d.designer_name:
        missing.append("designer (NC Surveyor or NC Civil Engineer) name/address")
    if not missing:
        return _pass(rid, name, sec, "Owner and designer information present.")
    return _fail(rid, name, sec,
                 f"Missing: {', '.join(missing)}.",
                 "Add owner and/or NC-licensed designer names and addresses to title block.")


def rule_date_and_north(d: SubmissionData) -> RuleResult:
    rid, name, sec = "TTL-003", "Date and North Arrow", "Sec. 2203.A.3-4"
    missing = []
    if d.has_date is False:
        missing.append("date (and revision block)")
    if d.has_north_arrow is False:
        missing.append("true north arrow")
    if not missing:
        return _pass(rid, name, sec, "Date and north arrow present.")
    return _fail(rid, name, sec,
                 f"Missing: {', '.join(missing)}.",
                 "Add preparation date, revision block, and true north arrow to plan.")


# ==============================================================
# PPL â Preliminary Plan Data Requirements
# ==============================================================

def rule_overlay_districts_shown(d: SubmissionData) -> RuleResult:
    rid, name, sec = "PPL-001", "Overlay Districts Shown (Airport, etc.)", "Sec. 2203.C.10"
    if d.submission_type != "preliminary_plan":
        return _na(rid, name, sec)
    if d.has_overlay_districts_shown is True:
        return _pass(rid, name, sec, "Overlay districts (Airport, etc.) shown on plan.")
    if d.has_overlay_districts_shown is False:
        return _fail(rid, name, sec,
                     "Applicable overlay districts are not shown on the preliminary plan.",
                     "Identify and label all applicable overlay districts (Airport Overlay, "
                     "Watershed, etc.) on the preliminary plan per Sec. 2203.C.10.")
    return _warn(rid, name, sec,
                 "Overlay district depiction not verified.",
                 "Confirm any applicable overlay districts are labeled on the plan.")


def rule_municipal_limits_shown(d: SubmissionData) -> RuleResult:
    rid, name, sec = "PPL-002", "Municipal Corporate Limits Shown", "Sec. 2203.C.17"
    if d.submission_type != "preliminary_plan":
        return _na(rid, name, sec)
    if d.has_municipal_limits_shown is True:
        return _pass(rid, name, sec, "Municipal corporate limits shown on plan.")
    if d.has_municipal_limits_shown is False:
        return _fail(rid, name, sec,
                     "Municipal corporate limits not shown on preliminary plan.",
                     "Add municipal corporate limit lines if the tract abuts or falls within "
                     "a municipality's boundary per Sec. 2203.C.17.")
    return _warn(rid, name, sec,
                 "Municipal limits not verified.",
                 "Confirm municipal corporate limits are labeled if applicable.")


def rule_jurisdictional_boundaries_shown(d: SubmissionData) -> RuleResult:
    rid, name, sec = "PPL-003", "County/Jurisdictional Boundaries on Tract", "Sec. 2203.C.18"
    if d.submission_type != "preliminary_plan":
        return _na(rid, name, sec)
    if d.has_jurisdictional_boundaries_shown is True:
        return _pass(rid, name, sec, "County or other jurisdictional boundaries shown.")
    if d.has_jurisdictional_boundaries_shown is False:
        return _fail(rid, name, sec,
                     "County or jurisdictional boundaries not shown on preliminary plan.",
                     "Depict county or other jurisdictional boundary lines on the plan "
                     "per Sec. 2203.C.18.")
    return _warn(rid, name, sec,
                 "Jurisdictional boundaries not verified.",
                 "Confirm county or jurisdictional boundary lines are shown if applicable.")


def rule_existing_structure_addresses(d: SubmissionData) -> RuleResult:
    rid, name, sec = "PPL-004", "Addresses of Existing Structures", "Sec. 2203.C.20"
    if d.submission_type != "preliminary_plan":
        return _na(rid, name, sec)
    if d.has_existing_structure_addresses is True:
        return _pass(rid, name, sec, "Addresses of existing structures shown.")
    if d.has_existing_structure_addresses is False:
        return _fail(rid, name, sec,
                     "Addresses of existing structures are missing from the preliminary plan.",
                     "Add addresses of all existing structures on the tract per Sec. 2203.C.20.")
    return _warn(rid, name, sec,
                 "Existing structure addresses not verified.",
                 "Confirm all existing structure addresses are labeled on the plan.")


def rule_common_elements_shown(d: SubmissionData) -> RuleResult:
    rid, name, sec = "PPL-005", "Common Elements / HOA Areas Shown", "Sec. 2203.C.21"
    if d.submission_type != "preliminary_plan":
        return _na(rid, name, sec)
    if d.has_common_elements_shown is True:
        return _pass(rid, name, sec, "Common elements and HOA-controlled areas shown.")
    if d.has_common_elements_shown is False:
        return _fail(rid, name, sec,
                     "Areas designated as common elements or HOA-controlled open space "
                     "are not shown on the preliminary plan.",
                     "Identify and label all HOA/common element areas with a note indicating "
                     "HOA ownership and maintenance responsibility per Sec. 2203.C.21.")
    return _warn(rid, name, sec,
                 "Common element areas not verified.",
                 "Confirm HOA/common areas are labeled with maintenance responsibility noted.")


def rule_public_dedication_areas_shown(d: SubmissionData) -> RuleResult:
    rid, name, sec = "PPL-006", "Areas to be Dedicated/Reserved for Public Use", "Sec. 2203.C.22"
    if d.submission_type != "preliminary_plan":
        return _na(rid, name, sec)
    if d.has_public_dedication_areas_shown is True:
        return _pass(rid, name, sec, "Areas to be dedicated or reserved for public use are shown.")
    if d.has_public_dedication_areas_shown is False:
        return _fail(rid, name, sec,
                     "Areas to be dedicated or reserved for public use are not shown.",
                     "Label all areas designated for public dedication (parks, open space, "
                     "rights-of-way) on the preliminary plan per Sec. 2203.C.22.")
    return _warn(rid, name, sec,
                 "Public dedication areas not verified.",
                 "Confirm all areas for public dedication are labeled on the plan.")


def rule_proposed_use_stated(d: SubmissionData) -> RuleResult:
    rid, name, sec = "PPL-007", "Proposed Use of Property Stated", "Sec. 2203.C.11"
    if d.submission_type != "preliminary_plan":
        return _na(rid, name, sec)
    if d.has_proposed_use_stated is True:
        return _pass(rid, name, sec, "Proposed use of property is stated on the plan.")
    if d.has_proposed_use_stated is False:
        return _fail(rid, name, sec,
                     "Proposed use of property is not stated on the preliminary plan.",
                     "Add a note stating the intended use (e.g., residential, commercial, "
                     "industrial) of all tracts per Sec. 2203.C.11.")
    return _warn(rid, name, sec,
                 "Proposed use statement not verified.",
                 "Confirm proposed use of property is labeled on the plan.")


def rule_watershed_designation_shown(d: SubmissionData) -> RuleResult:
    rid, name, sec = "PPL-008", "Watershed Designation Shown if Applicable", "Sec. 2203 / Watershed Ord."
    if d.submission_type != "preliminary_plan":
        return _na(rid, name, sec)
    if d.has_watershed_designation_shown is True:
        return _pass(rid, name, sec, "Watershed designation shown on plan.")
    if d.has_watershed_designation_shown is False:
        return _warn(rid, name, sec,
                     "Watershed designation not shown. If the property is within a watershed "
                     "critical area, a separate Watershed Protection Permit is required.",
                     "Check and label any applicable watershed critical area boundaries. "
                     "Contact Planning staff regarding Watershed Protection Ordinance requirements.")
    return _warn(rid, name, sec,
                 "Watershed designation not verified.",
                 "Confirm whether the property is within a watershed critical area and label accordingly.")


def rule_wells_septic_shown(d: SubmissionData) -> RuleResult:
    rid, name, sec = "PPL-009", "Existing Wells and Septic Locations Shown", "Sec. 2203.C (Env. Data)"
    if d.submission_type != "preliminary_plan":
        return _na(rid, name, sec)
    if d.water_sewer_type == "public":
        return _na(rid, name, sec)
    if d.has_existing_wells_septic_shown is True:
        return _pass(rid, name, sec, "Existing well and septic locations shown on plan.")
    if d.has_existing_wells_septic_shown is False:
        return _fail(rid, name, sec,
                     "Existing well and/or septic locations not shown on preliminary plan.",
                     "Show and label all existing well and septic locations on the plan "
                     "per Environmental Data requirements.")
    return _warn(rid, name, sec,
                 "Well/septic locations not verified.",
                 "Confirm all existing wells and septic systems are shown if on-site utilities exist.")


def rule_street_functional_class(d: SubmissionData) -> RuleResult:
    rid, name, sec = "PPL-010", "Street Functional Classification Labeled", "Sec. 2203 Street Data"
    if d.submission_type != "preliminary_plan":
        return _na(rid, name, sec)
    if d.street_functional_class_labeled is True:
        return _pass(rid, name, sec, "Street functional classification labeled on plan.")
    if d.street_functional_class_labeled is False:
        return _fail(rid, name, sec,
                     "Functional classification of adjacent state roadways is not labeled "
                     "on the preliminary plan.",
                     "Label the NCDOT functional classification of all adjacent/abutting "
                     "state roads on the plan. Reference the NCDOT Functional Class Road "
                     "network map.")
    return _warn(rid, name, sec,
                 "Street functional classification not verified.",
                 "Confirm NCDOT functional classification is labeled for all adjacent state roads.")


def rule_acreage_new_row(d: SubmissionData) -> RuleResult:
    rid, name, sec = "PPL-011", "Acreage in Newly Dedicated ROW Shown", "Sec. 2203.C.16"
    if d.submission_type != "preliminary_plan":
        return _na(rid, name, sec)
    if d.acreage_new_row_shown is True:
        return _pass(rid, name, sec, "Acreage in newly dedicated right-of-way is shown.")
    if d.acreage_new_row_shown is False:
        return _fail(rid, name, sec,
                     "Acreage in newly dedicated right-of-way is not shown on the plan.",
                     "Label the acreage of all newly dedicated right-of-way on the "
                     "preliminary plan per Sec. 2203.C.16.")
    return _warn(rid, name, sec,
                 "New ROW acreage not verified.",
                 "Confirm newly dedicated ROW acreage is labeled on the plan.")


def rule_retention_basin_fence_note(d: SubmissionData) -> RuleResult:
    rid, name, sec = "PPL-012", "Retention/Detention Basin Fence Note and Detail", "Sec. 1102.O (Zoning Ord.)"
    if d.submission_type != "preliminary_plan":
        return _na(rid, name, sec)
    if d.retention_basin_present is False or d.retention_basin_present is None:
        return _na(rid, name, sec)
    if d.retention_basin_fence_detail_note is True:
        return _pass(rid, name, sec,
                     "Retention/detention basin fence detail and note present on plan.")
    if d.retention_basin_fence_detail_note is False:
        return _fail(rid, name, sec,
                     "Retention/detention basin present but fence detail and/or plan note missing.",
                     "Add fence detail showing minimum 4 ft high fence with lockable gate. "
                     "Include a note: 'A fence permit shall be obtained from Code Enforcement "
                     "prior to Final Plat approval.' per Sec. 1102.O.")
    return _warn(rid, name, sec,
                 "Retention basin fence note/detail not verified.",
                 "Confirm fence detail (4 ft min, lockable gate) and permit note are on the plan.")


def rule_underground_utilities_note(d: SubmissionData) -> RuleResult:
    rid, name, sec = "PPL-013", "Underground Utilities Note on Plan", "Sec. 2306.C"
    if d.submission_type != "preliminary_plan":
        return _na(rid, name, sec)
    if d.underground_utilities_note_on_plan is True:
        return _pass(rid, name, sec, "Underground utilities note present on plan.")
    if d.underground_utilities_note_on_plan is False:
        return _fail(rid, name, sec,
                     "Underground utilities statement missing from preliminary plan.",
                     "Add a note stating: 'All utilities will be placed underground where "
                     "practical. High voltage electrical lines (25kv or greater) are exempt.' "
                     "per Sec. 2306.C.")
    return _warn(rid, name, sec,
                 "Underground utilities note not verified.",
                 "Confirm plan includes underground utilities statement per Sec. 2306.C.")


def rule_hoa_recreation_note(d: SubmissionData) -> RuleResult:
    rid, name, sec = "PPL-014", "HOA Recreation Area Note on Plan", "Sec. 2308.C.4"
    if d.submission_type != "preliminary_plan":
        return _na(rid, name, sec)
    units = d.dwelling_units or d.group_dev_units or d.mhp_units or 0
    if units == 0:
        return _na(rid, name, sec)
    if d.hoa_recreation_note_on_plan is True:
        return _pass(rid, name, sec, "HOA recreation area ownership/maintenance note present.")
    if d.hoa_recreation_note_on_plan is False:
        return _fail(rid, name, sec,
                     "HOA recreation area maintenance note missing from preliminary plan.",
                     "Add a note on the plan stating the recreation area will be maintained "
                     "and owned by the HOA per Sec. 2308.C.4. County Attorney review of HOA "
                     "documents will be required at Final Plat.")
    return _warn(rid, name, sec,
                 "HOA recreation note not verified.",
                 "Confirm HOA ownership and maintenance note is present for recreation areas.")


def rule_soil_scientist_cert(d: SubmissionData) -> RuleResult:
    rid, name, sec = "PPL-015", "Soil Scientist Certification (On-Site Sewer)", "Sec. 2303.B / Sec. 2306.A.2"
    if d.water_sewer_type != "on_site":
        return _na(rid, name, sec)
    if d.soil_scientist_cert_provided is True:
        return _pass(rid, name, sec,
                     "Certified soil scientist analysis provided with preliminary plan package.")
    if d.soil_scientist_cert_provided is False:
        return _fail(rid, name, sec,
                     "Soil scientist certification missing. Required for all lots proposed "
                     "to use on-site water and/or sewer systems.",
                     "Provide a certified soil scientist analysis confirming each lot meets "
                     "Environmental Health minimum standards for on-site water/sewer per "
                     "Sec. 2303.B. Required with the preliminary plan submittal package.")
    return _warn(rid, name, sec,
                 "Soil scientist certification not verified.",
                 "Confirm certified soil analysis is included in preliminary plan submittal "
                 "package for all lots using on-site utilities.")


# ==============================================================
# LOT â Lot Standards
# ==============================================================

def rule_lot_frontage(d: SubmissionData) -> RuleResult:
    rid, name, sec = "LOT-001", "Minimum Lot Frontage", "Sec. 2303.C"
    if d.min_lot_frontage_ft is None:
        return _warn(rid, name, sec,
                     "Minimum lot frontage not extracted.",
                     "Verify every lot abuts a street for at least 20 continuous feet.")
    if d.min_lot_frontage_ft >= 20:
        return _pass(rid, name, sec,
                     f"Minimum lot frontage {d.min_lot_frontage_ft} ft >= 20 ft required.",
                     d.min_lot_frontage_ft)
    return _fail(rid, name, sec,
                 f"Minimum lot frontage {d.min_lot_frontage_ft} ft is below the 20 ft minimum.",
                 "Redesign lots so every lot has >= 20 ft continuous street frontage.",
                 d.min_lot_frontage_ft)


def rule_lot_size_labels(d: SubmissionData) -> RuleResult:
    rid, name, sec = "LOT-002", "Lot Size Labels", "Sec. 2203.D.11"
    issues = []
    if d.lots_missing_sqft_label and d.lots_missing_sqft_label > 0:
        issues.append(f"{d.lots_missing_sqft_label} sub-acre lot(s) missing square footage label")
    if d.lots_missing_acreage_label and d.lots_missing_acreage_label > 0:
        issues.append(f"{d.lots_missing_acreage_label} lot(s) >=1 acre missing acreage label")
    if not issues:
        return _pass(rid, name, sec, "All lots have required size labels.")
    return _fail(rid, name, sec,
                 "; ".join(issues) + ".",
                 "Label sub-acre lots with square footage and lots >=1 acre with acreage.")


def rule_lot_numbering(d: SubmissionData) -> RuleResult:
    rid, name, sec = "LOT-003", "Consecutive Lot Numbering", "Sec. 2203.D.6"
    if d.lots_sequentially_numbered is None:
        return _warn(rid, name, sec,
                     "Lot numbering not verified.",
                     "Confirm lots are numbered/sequenced consecutively.")
    if d.lots_sequentially_numbered:
        return _pass(rid, name, sec, "Lots are consecutively numbered.")
    return _fail(rid, name, sec,
                 "Lots are not consecutively numbered.",
                 "Renumber lots sequentially (e.g., Lot 1, Lot 2, Lot 3...).")


# ==============================================================
# STR â Street Design (shared thresholds, both jurisdictions)
# ==============================================================

def rule_block_length(d: SubmissionData) -> RuleResult:
    rid, name = "STR-001", "Maximum Block Length"
    sec = "Sec. 2304.A.10.f" if d.jurisdiction == "county" else "Sec. 3.18"
    if d.max_block_length_ft is None:
        return _warn(rid, name, sec,
                     "Block length not extracted.",
                     "Verify block lengths do not exceed 1,800 ft.")
    if d.max_block_length_ft <= 1800:
        return _pass(rid, name, sec,
                     f"Maximum block length {d.max_block_length_ft} ft <= 1,800 ft.",
                     d.max_block_length_ft)
    return _fail(rid, name, sec,
                 f"Block length {d.max_block_length_ft} ft exceeds 1,800 ft maximum.",
                 "Redesign street layout to keep block lengths <= 1,800 ft.",
                 d.max_block_length_ft)


def rule_street_offset(d: SubmissionData) -> RuleResult:
    rid, name = "STR-002", "Street Centerline Offset at Intersections"
    sec = "Sec. 2304.A.10.e" if d.jurisdiction == "county" else "Sec. 3.17.f"
    if d.street_offset_ft is None:
        return _warn(rid, name, sec,
                     "Street offset not extracted.",
                     "Verify offset of centerlines across intersections is >= 125 ft.")
    if d.street_offset_ft >= 125:
        return _pass(rid, name, sec,
                     f"Street centerline offset {d.street_offset_ft} ft >= 125 ft.",
                     d.street_offset_ft)
    return _fail(rid, name, sec,
                 f"Street centerline offset {d.street_offset_ft} ft is below 125 ft minimum.",
                 "Adjust intersection alignment so centerline offset >= 125 ft.",
                 d.street_offset_ft)


def rule_corner_radius(d: SubmissionData) -> RuleResult:
    rid, name = "STR-003", "Street Intersection Corner Radius"
    sec = "Sec. 2304.A.10.c" if d.jurisdiction == "county" else "Sec. 3.17.d"
    if d.street_corner_radius_ft is None:
        return _warn(rid, name, sec,
                     "Corner radius not extracted.",
                     "Verify property-line corner radii at intersections are >= 25 ft.")
    if d.street_corner_radius_ft >= 25:
        return _pass(rid, name, sec,
                     f"Corner radius {d.street_corner_radius_ft} ft >= 25 ft.",
                     d.street_corner_radius_ft)
    return _fail(rid, name, sec,
                 f"Corner radius {d.street_corner_radius_ft} ft is below 25 ft minimum.",
                 "Round property-line intersections to a minimum 25 ft radius.",
                 d.street_corner_radius_ft)


# ==============================================================
# CDS â Cul-de-Sac / Hammerhead (County thresholds)
# ==============================================================

def rule_cul_de_sac_length(d: SubmissionData) -> RuleResult:
    rid, name, sec = "CDS-001", "Cul-de-Sac Maximum Length", "Sec. 2304.A.10.g"
    if d.has_cul_de_sac is False:
        return _na(rid, name, sec)
    if d.cul_de_sac_length_ft is None:
        return _warn(rid, name, sec,
                     "Cul-de-sac length not extracted.",
                     "Verify cul-de-sac street length does not exceed 1,400 ft.")
    if d.cul_de_sac_length_ft <= 1400:
        return _pass(rid, name, sec,
                     f"Cul-de-sac length {d.cul_de_sac_length_ft} ft <= 1,400 ft.",
                     d.cul_de_sac_length_ft)
    return _fail(rid, name, sec,
                 f"Cul-de-sac length {d.cul_de_sac_length_ft} ft exceeds 1,400 ft maximum.",
                 "Shorten cul-de-sac to <= 1,400 ft or stub to adjacent property.",
                 d.cul_de_sac_length_ft)


def rule_cul_de_sac_dimensions(d: SubmissionData) -> RuleResult:
    rid, name, sec = "CDS-002", "Cul-de-Sac Turnaround Dimensions", "Sec. 2304.A.10.g"
    if d.has_cul_de_sac is False:
        return _na(rid, name, sec)
    issues = []
    if d.cul_de_sac_roadway_diameter_ft is not None and d.cul_de_sac_roadway_diameter_ft < 70:
        issues.append(f"roadway diameter {d.cul_de_sac_roadway_diameter_ft} ft < 70 ft required")
    if d.cul_de_sac_row_diameter_ft is not None and d.cul_de_sac_row_diameter_ft < 100:
        issues.append(f"ROW diameter {d.cul_de_sac_row_diameter_ft} ft < 100 ft required")
    if not issues:
        if d.cul_de_sac_roadway_diameter_ft is None and d.cul_de_sac_row_diameter_ft is None:
            return _warn(rid, name, sec,
                         "Cul-de-sac dimensions not extracted.",
                         "Verify: roadway diameter >= 70 ft and ROW diameter >= 100 ft.")
        return _pass(rid, name, sec,
                     "Cul-de-sac turnaround dimensions meet requirements (roadway >= 70 ft, ROW >= 100 ft).")
    return _fail(rid, name, sec,
                 "Cul-de-sac turnaround does not meet dimensions: " + "; ".join(issues) + ".",
                 "Redesign: roadway outside diameter >= 70 ft, ROW diameter >= 100 ft.")


def rule_hammerhead_dimensions(d: SubmissionData) -> RuleResult:
    rid, name, sec = "CDS-003", "Hammerhead Turnaround Dimensions", "Sec. 2304.A.10.g"
    if d.has_hammerhead is False or d.has_hammerhead is None:
        return _na(rid, name, sec)
    issues = []
    checks = [
        (d.hammerhead_outside_length_ft, 100, "outside length"),
        (d.hammerhead_outside_width_ft,   50, "outside width"),
        (d.hammerhead_roadway_length_ft,   70, "roadway length"),
        (d.hammerhead_roadway_width_ft,    20, "roadway width"),
    ]
    for val, req, label in checks:
        if val is not None and val < req:
            issues.append(f"{label} {val} ft < {req} ft required")
    if not issues:
        if all(v is None for v, *_ in checks):
            return _warn(rid, name, sec,
                         "Hammerhead dimensions not extracted.",
                         "Verify: outside 50-100 ft min, roadway 20-70 ft min, 15 ft radius at T.")
        return _pass(rid, name, sec, "Hammerhead dimensions meet requirements.")
    return _fail(rid, name, sec,
                 "Hammerhead does not meet dimensions: " + "; ".join(issues) + ".",
                 "Redesign hammerhead: outside min 50-100 ft, roadway min 20-70 ft, "
                 "15 ft radius at T-intersections.")


# ==============================================================
# PVT â Private Streets (County thresholds)
# ==============================================================

def rule_private_street_class_b_max_lots(d: SubmissionData) -> RuleResult:
    rid, name, sec = "PVT-001", "Class B Private Street â Max Lots Served", "Sec. 2304.C.4.b"
    if not d.has_private_streets or d.private_street_class != "B":
        return _na(rid, name, sec)
    if d.class_b_lots_served is None:
        return _warn(rid, name, sec,
                     "Lots served by Class B street not extracted.",
                     "Verify Class B private street serves <= 8 lots.")
    if d.class_b_lots_served <= 8:
        return _pass(rid, name, sec,
                     f"Class B street serves {d.class_b_lots_served} lots <= 8 maximum.",
                     d.class_b_lots_served)
    return _fail(rid, name, sec,
                 f"Class B street serves {d.class_b_lots_served} lots, exceeding maximum of 8.",
                 "Reduce lots served by Class B street to <= 8, or upgrade to Class A.",
                 d.class_b_lots_served)


def rule_private_street_class_c_max_lots(d: SubmissionData) -> RuleResult:
    rid, name, sec = "PVT-002", "Class C Private Street â Max Lots Served", "Sec. 2304.C.4.c.4"
    if not d.has_private_streets or d.private_street_class != "C":
        return _na(rid, name, sec)
    if d.class_c_lots_served is None:
        return _warn(rid, name, sec,
                     "Lots served by Class C street not extracted.",
                     "Verify Class C private street serves <= 4 lots.")
    if d.class_c_lots_served <= 4:
        return _pass(rid, name, sec,
                     f"Class C street serves {d.class_c_lots_served} lots <= 4 maximum.",
                     d.class_c_lots_served)
    return _fail(rid, name, sec,
                 f"Class C street serves {d.class_c_lots_served} lots, exceeding maximum of 4.",
                 "Reduce lots served by Class C street to <= 4, or upgrade street class.",
                 d.class_c_lots_served)


def rule_private_street_class_a_row(d: SubmissionData) -> RuleResult:
    rid, name, sec = "PVT-003", "Class A Private Street â ROW Width (no curb/gutter)", "Sec. 2304.C.4.a.6"
    if not d.has_private_streets or d.private_street_class != "A":
        return _na(rid, name, sec)
    if d.private_street_row_ft is None:
        return _warn(rid, name, sec,
                     "Class A ROW width not extracted.",
                     "If no curb/gutter, verify ROW >= 45 ft.")
    if d.private_street_row_ft >= 45:
        return _pass(rid, name, sec,
                     f"Class A ROW {d.private_street_row_ft} ft >= 45 ft.",
                     d.private_street_row_ft)
    return _fail(rid, name, sec,
                 f"Class A ROW {d.private_street_row_ft} ft < 45 ft (required when no curb/gutter).",
                 "Increase Class A private street ROW to >= 45 ft where curb/gutter is omitted.",
                 d.private_street_row_ft)


def rule_private_street_owners_assoc(d: SubmissionData) -> RuleResult:
    rid, name = "PVT-004", "Private Street Owners' Association Required"
    sec = "Sec. 2304.C.4.a.3 / b.2" if d.jurisdiction == "county" else "Sec. 4.2.a"
    if not d.has_private_streets:
        return _na(rid, name, sec)
    if d.private_street_class not in ("A", "B"):
        return _na(rid, name, sec)
    if d.private_street_owners_assoc is True:
        return _pass(rid, name, sec, "Owners' association established for private street maintenance.")
    if d.private_street_owners_assoc is False:
        return _fail(rid, name, sec,
                     "No owners' association documented for Class A/B private street.",
                     "Establish owners' association with County Attorney-approved legal documents "
                     "addressing street maintenance liability.")
    return _warn(rid, name, sec,
                 "Owners' association status not confirmed.",
                 "Verify County Attorney-approved owners' association documents are on file.")


def rule_private_street_disclosure(d: SubmissionData) -> RuleResult:
    rid, name = "PVT-005", "Private Street Disclosure on Plat"
    sec = "Sec. 2304.C.8 / 2504.A" if d.jurisdiction == "county" else "Sec. 4.2 / Wade Sec. 5.2.f"
    if not d.has_private_streets:
        return _na(rid, name, sec)
    if d.private_street_disclosure_present is True:
        return _pass(rid, name, sec, "General private street disclosure is present on plat.")
    if d.private_street_disclosure_present is False:
        return _fail(rid, name, sec,
                     "General private street disclosure missing from plat.",
                     "Add the required private street disclosure language to the plat.")
    return _warn(rid, name, sec,
                 "Private street disclosure not verified.",
                 "Confirm required private street disclosure language appears on the plat.")


# ==============================================================
# UTL â Utilities: Water & Sewer
# ==============================================================

def rule_public_water_sewer_2_to_10_lots(d: SubmissionData) -> RuleResult:
    rid, name = "UTL-001", "Public W/S Connection â 2-10 Lots within 300 ft"
    sec = "Sec. 2306.A.1.b" if d.jurisdiction == "county" else "Sec. 4.3.d.2"
    lots = d.proposed_lots_or_units or 0
    if not (2 <= lots <= 10):
        return _na(rid, name, sec)
    within = d.public_water_within_300ft or d.public_sewer_within_300ft
    if within is None:
        return _warn(rid, name, sec,
                     f"{lots} lots proposed. Proximity to public W/S not stated.",
                     "Determine whether public water or sewer is within 300 ft. "
                     "If yes, connection is required.")
    if within:
        if d.water_sewer_type == "public":
            return _pass(rid, name, sec,
                         f"{lots} lots within 300 ft of public W/S â connection confirmed.")
        return _fail(rid, name, sec,
                     f"{lots} lots proposed and public W/S is within 300 ft, but plan "
                     "shows on-site/private utilities.",
                     "Extend and connect to public water/sewer.")
    return _pass(rid, name, sec,
                 f"Public W/S is not within 300 ft; connection not required for {lots} lots.")


def rule_public_water_sewer_11_to_20_lots(d: SubmissionData) -> RuleResult:
    rid, name = "UTL-002", "Public W/S Connection â 11-20 Lots within 500 ft"
    sec = "Sec. 2306.A.1.b" if d.jurisdiction == "county" else "Sec. 4.3.d.2"
    lots = d.proposed_lots_or_units or 0
    if not (11 <= lots <= 20):
        return _na(rid, name, sec)
    within = d.public_water_within_500ft or d.public_sewer_within_500ft
    if within is None:
        return _warn(rid, name, sec,
                     f"{lots} lots proposed. Proximity to public W/S (500 ft) not stated.",
                     "Determine whether public water or sewer is within 500 ft. "
                     "If yes, connection is required.")
    if within:
        if d.water_sewer_type == "public":
            return _pass(rid, name, sec,
                         f"{lots} lots within 500 ft of public W/S â connection confirmed.")
        return _fail(rid, name, sec,
                     f"{lots} lots proposed and public W/S is within 500 ft, but plan "
                     "shows on-site/private utilities.",
                     "Extend and connect to public water/sewer.")
    return _pass(rid, name, sec,
                 f"Public W/S is not within 500 ft; connection not required for {lots} lots.")


def rule_public_water_sewer_over_20_lots(d: SubmissionData) -> RuleResult:
    rid, name = "UTL-003", "Public W/S Connection â >20 Lots in SSA / >2 units/acre"
    sec = "Sec. 2306.A.1.b" if d.jurisdiction == "county" else "Sec. 4.3.d.2"
    lots    = d.proposed_lots_or_units or 0
    density = d.density_units_per_acre
    in_ssa  = d.in_sewer_service_area
    trigger = (lots > 20 and in_ssa) or (density is not None and density > 2)
    if not trigger:
        return _na(rid, name, sec)
    if d.water_sewer_type == "public":
        return _pass(rid, name, sec,
                     "Public water and sewer connection confirmed for high-density/SSA development.")
    return _fail(rid, name, sec,
                 f"{lots} lots or density {density} units/acre in SSA requires public W/S, "
                 "but plan shows on-site/private utilities.",
                 "Extend and connect to public water and sewer.")


def rule_on_site_sewer_disclosure(d: SubmissionData) -> RuleResult:
    rid, name = "UTL-004", "On-Site Sewer/Water Disclosure on Plat"
    sec = "Sec. 2504.C / 2306.A.2" if d.jurisdiction == "county" else "Sec. 5.2 / Sec. 3.15"
    if d.water_sewer_type != "on_site":
        return _na(rid, name, sec)
    if d.on_site_sewer_disclosure_present is True:
        return _pass(rid, name, sec, "On-site W/S disclosure present on plat.")
    if d.on_site_sewer_disclosure_present is False:
        return _fail(rid, name, sec,
                     "On-site W/S disclosure missing from plat.",
                     "Add required disclosure: 'Individual lots shown on this plat do not have "
                     "public sewer and/or water services available, and no lots have been "
                     "approved by the Health Department for on-site sewer services or been "
                     "deemed acceptable for private water wells as of the date of this recording.'")
    return _warn(rid, name, sec,
                 "On-site W/S disclosure status not verified.",
                 "Confirm required on-site sewer/water disclosure appears on plat.")


def rule_utility_statement_on_plan(d: SubmissionData) -> RuleResult:
    rid, name = "UTL-005", "Utility Statement on Preliminary Plan"
    sec = "Sec. 2203.F" if d.jurisdiction == "county" else "Sec. 5.1.f"
    if d.submission_type != "preliminary_plan":
        return _na(rid, name, sec)
    if d.utility_statement_on_plan is True:
        return _pass(rid, name, sec, "Utility statement present on preliminary plan.")
    if d.utility_statement_on_plan is False:
        return _fail(rid, name, sec,
                     "Utility statement missing from preliminary plan.",
                     "Add statement describing intended water/sewer service type, or proposed "
                     "on-site method if public utilities are not available.")
    return _warn(rid, name, sec,
                 "Utility statement not verified.",
                 "Confirm plan includes statement on water/sewer service type.")


def rule_utility_easement(d: SubmissionData) -> RuleResult:
    rid, name = "UEZ-001", "Utility Easement Width"
    sec = "Sec. 2303.E.1" if d.jurisdiction == "county" else "Sec. 3.11"
    if d.utility_easement_width_ft is None:
        return _warn(rid, name, sec,
                     "Utility easement width not extracted.",
                     "Verify utility easements are >= 10 ft wide (5 ft each side of rear lot line).")
    if d.utility_easement_width_ft >= 10:
        return _pass(rid, name, sec,
                     f"Utility easement {d.utility_easement_width_ft} ft >= 10 ft.",
                     d.utility_easement_width_ft)
    return _fail(rid, name, sec,
                 f"Utility easement {d.utility_easement_width_ft} ft < 10 ft minimum.",
                 "Increase utility easement to >= 10 ft (5 ft on each side of rear lot line).",
                 d.utility_easement_width_ft)


# ==============================================================
# FIR â Fire Hydrants
# ==============================================================

def rule_fire_hydrant_spacing(d: SubmissionData) -> RuleResult:
    rid, name = "FIR-001", "Fire Hydrant Maximum Spacing"
    sec = "Sec. 2306.B.1" if d.jurisdiction == "county" else "Sec. 4.3.f.1"
    lots = d.proposed_lots_or_units or 0
    if lots < 4 or d.water_sewer_type != "public":
        return _na(rid, name, sec)
    if d.fire_hydrant_max_spacing_ft is None:
        return _warn(rid, name, sec,
                     "Fire hydrant spacing not extracted.",
                     "Verify hydrants are no more than 1,000 ft apart.")
    if d.fire_hydrant_max_spacing_ft <= 1000:
        return _pass(rid, name, sec,
                     f"Hydrant spacing {d.fire_hydrant_max_spacing_ft} ft <= 1,000 ft.",
                     d.fire_hydrant_max_spacing_ft)
    return _fail(rid, name, sec,
                 f"Hydrant spacing {d.fire_hydrant_max_spacing_ft} ft exceeds 1,000 ft maximum.",
                 "Relocate or add hydrants so spacing <= 1,000 ft.",
                 d.fire_hydrant_max_spacing_ft)


def rule_fire_hydrant_distance_to_lot(d: SubmissionData) -> RuleResult:
    rid, name = "FIR-002", "Fire Hydrant Distance to Any Lot"
    sec = "Sec. 2306.B.1" if d.jurisdiction == "county" else "Sec. 4.3.f.1"
    lots = d.proposed_lots_or_units or 0
    if lots < 4 or d.water_sewer_type != "public":
        return _na(rid, name, sec)
    if d.fire_hydrant_max_from_lot_ft is None:
        return _warn(rid, name, sec,
                     "Max hydrant distance to lots not extracted.",
                     "Verify no lot is more than 500 ft from a fire hydrant.")
    if d.fire_hydrant_max_from_lot_ft <= 500:
        return _pass(rid, name, sec,
                     f"All lots within {d.fire_hydrant_max_from_lot_ft} ft of a hydrant <= 500 ft.",
                     d.fire_hydrant_max_from_lot_ft)
    return _fail(rid, name, sec,
                 f"A lot is {d.fire_hydrant_max_from_lot_ft} ft from a hydrant, exceeding 500 ft.",
                 "Add or relocate hydrants so every lot is within 500 ft.",
                 d.fire_hydrant_max_from_lot_ft)


def rule_fire_marshal_acceptance(d: SubmissionData) -> RuleResult:
    rid, name, sec = "FIR-003", "Fire Marshal Acceptance Letter Before Final Plat", "Sec. 2306.B / NC Fire Code"
    if d.submission_type != "final_plat":
        return _na(rid, name, sec)
    lots = d.proposed_lots_or_units or 0
    if lots < 4 or d.water_sewer_type != "public":
        return _na(rid, name, sec)
    if d.fire_marshal_acceptance_letter is True:
        return _pass(rid, name, sec, "Fire Marshal acceptance letter on file.")
    if d.fire_marshal_acceptance_letter is False:
        return _fail(rid, name, sec,
                     "Fire Marshal acceptance letter not provided. Required before Final Plat approval.",
                     "Submit fire protection plans to the Fire Marshal's Office. Obtain written "
                     "acceptance letter and include with Final Plat submittal package.")
    return _warn(rid, name, sec,
                 "Fire Marshal acceptance letter status not verified.",
                 "Confirm Fire Marshal acceptance letter is on file before Final Plat approval.")


# ==============================================================
# SWK â Sidewalks (County thresholds)
# ==============================================================

def rule_sidewalk_required(d: SubmissionData) -> RuleResult:
    rid, name, sec = "SWK-001", "Sidewalk Required Near School or Park", "Sec. 2305.A"
    if d.adjacent_to_school_or_park is False:
        return _na(rid, name, sec)
    if d.adjacent_to_school_or_park is None:
        return _warn(rid, name, sec,
                     "Adjacency to school/park not determined.",
                     "Check whether development is adjacent to a public school or park. "
                     "If yes, a 10 ft minimum sidewalk is required.")
    if d.sidewalk_shown is True:
        return _pass(rid, name, sec, "Sidewalk shown on plan adjacent to school/park.")
    return _fail(rid, name, sec,
                 "Development is adjacent to school/park but no sidewalk is shown.",
                 "Design and dedicate a sidewalk >= 10 ft wide providing direct convenient "
                 "access to the adjacent school or park per Sec. 2305.A.")


def rule_sidewalk_dimensions(d: SubmissionData) -> RuleResult:
    """County sidewalk dimensions: 36 in wide, 4 in ped., 7 in vehicular."""
    rid, name, sec = "SWK-002", "Sidewalk Construction Dimensions (County)", "Sec. 2305.B"
    if d.adjacent_to_school_or_park is False or d.sidewalk_shown is False:
        return _na(rid, name, sec)
    issues = []
    if d.sidewalk_width_inches is not None and d.sidewalk_width_inches < 36:
        issues.append(f"width {d.sidewalk_width_inches} in < 36 in minimum")
    if d.sidewalk_pedestrian_thickness_in is not None and d.sidewalk_pedestrian_thickness_in < 4:
        issues.append(f"pedestrian thickness {d.sidewalk_pedestrian_thickness_in} in < 4 in")
    if d.sidewalk_vehicular_thickness_in is not None and d.sidewalk_vehicular_thickness_in < 7:
        issues.append(f"vehicular thickness {d.sidewalk_vehicular_thickness_in} in < 7 in")
    if not issues:
        return _pass(rid, name, sec, "Sidewalk dimensions meet Sec. 2305.B requirements.")
    return _fail(rid, name, sec,
                 "Sidewalk dimensions do not comply: " + "; ".join(issues) + ".",
                 "Revise: min width 36 in, >= 4 in thick (pedestrian), >= 7 in thick (vehicular), "
                 "joints every 3 ft, 3,000 PSI concrete, ADA compliant.")


# ==============================================================
# REC â Recreation Area (County: 800 sq ft per dwelling unit)
# ==============================================================

def rule_recreation_area(d: SubmissionData) -> RuleResult:
    rid, name, sec = "REC-001", "Recreation Area â Min 800 sq ft per Dwelling Unit (County)", "Sec. 2308.A"
    units = d.dwelling_units
    if units is None or units == 0:
        return _na(rid, name, sec)
    required = units * 800
    if d.recreation_area_sqft is None:
        return _warn(rid, name, sec,
                     f"{units} units require >= {required:,} sq ft of recreation area.",
                     "Confirm recreation area is labeled and dimensioned on the plan, "
                     "or document fee-in-lieu per Sec. 2308.A if < 25,000 sq ft threshold.")
    if d.recreation_area_sqft >= required:
        return _pass(rid, name, sec,
                     f"Recreation area {d.recreation_area_sqft:,} sq ft >= "
                     f"{required:,} sq ft required ({units} units - 800 sq ft).",
                     d.recreation_area_sqft)
    return _fail(rid, name, sec,
                 f"Recreation area {d.recreation_area_sqft:,} sq ft < {required:,} sq ft required.",
                 f"Add {required - d.recreation_area_sqft:,.0f} sq ft of recreation area "
                 f"or pay fee-in-lieu if eligible per Sec. 2308.A.",
                 d.recreation_area_sqft)


# ==============================================================
# SWM â Stormwater
# ==============================================================

def rule_stormwater_permit(d: SubmissionData) -> RuleResult:
    rid, name = "SWM-001", "Post-Construction Stormwater Permit (>= 1 Acre)"
    sec = "Sec. 2306.D" if d.jurisdiction == "county" else "Sec. 4.3 / NCDEQ"
    if d.disturbed_area_acres is None:
        return _warn(rid, name, sec,
                     "Disturbed area acreage not extracted.",
                     "If >= 1 acre of land will be disturbed, a NCDEQ Post-Construction "
                     "Stormwater Management Permit is required.")
    if d.disturbed_area_acres < 1.0:
        return _pass(rid, name, sec,
                     f"Disturbed area {d.disturbed_area_acres} acres < 1 acre; "
                     "NCDEQ stormwater permit not triggered.",
                     d.disturbed_area_acres)
    if d.stormwater_permit_addressed is True:
        return _pass(rid, name, sec,
                     f"Disturbed area {d.disturbed_area_acres} acres >= 1 acre; "
                     "NCDEQ stormwater permitting addressed.",
                     d.disturbed_area_acres)
    return _fail(rid, name, sec,
                 f"Disturbed area {d.disturbed_area_acres} acres >= 1 acre but stormwater "
                 "permit compliance not addressed on plan.",
                 "Obtain or reference NCDEQ Post-Construction Stormwater Management Permit. "
                 "Note permit requirements on plan.",
                 d.disturbed_area_acres)


def rule_retention_basin_fence(d: SubmissionData) -> RuleResult:
    rid, name, sec = "SWM-002", "Retention/Detention Basin Fencing", "Sec. 1102.O (Zoning Ord.)"
    if d.retention_basin_present is False or d.retention_basin_present is None:
        return _na(rid, name, sec)
    if d.retention_basin_fence_shown is True:
        return _pass(rid, name, sec,
                     "Retention/detention basin fencing (>= 4 ft with lockable gate) shown.")
    if d.retention_basin_fence_shown is False:
        return _fail(rid, name, sec,
                     "Retention/detention basin present but required fencing not shown.",
                     "Show minimum 4 ft fence with lockable gate around retention/detention basin. "
                     "Include fence detail and note that fence permit is required from Code Enforcement.")
    return _warn(rid, name, sec,
                 "Basin fencing not verified.",
                 "Confirm >= 4 ft fence with lockable gate is shown around any retention/detention basin.")


def rule_stormwater_hoa_access(d: SubmissionData) -> RuleResult:
    rid, name, sec = "SWM-003", "Stormwater Facility Internal HOA Access", "Sec. 2308 / Checklist"
    if d.submission_type != "final_plat":
        return _na(rid, name, sec)
    if d.retention_basin_present is False or d.retention_basin_present is None:
        return _na(rid, name, sec)
    if d.stormwater_hoa_access_shown is True:
        return _pass(rid, name, sec,
                     "Internal access to stormwater facility for HOA maintenance is shown.")
    if d.stormwater_hoa_access_shown is False:
        return _fail(rid, name, sec,
                     "Internal access to the stormwater facility is not shown on the plat.",
                     "Provide internal access route to stormwater facility so HOA can access "
                     "and maintain it. Show and label on final plat.")
    return _warn(rid, name, sec,
                 "Stormwater HOA access not verified.",
                 "Confirm internal access to stormwater facility is shown for HOA maintenance.")


# ==============================================================
# DRN â Drainage Easement
# ==============================================================

def rule_drainage_easement(d: SubmissionData) -> RuleResult:
    rid, name = "DRN-001", "Watercourse Drainage Easement Width"
    sec = "Sec. 2303.E.2" if d.jurisdiction == "county" else "Sec. 3.11"
    if d.has_watercourse_on_site is False:
        return _na(rid, name, sec)
    if d.has_watercourse_on_site is None:
        return _warn(rid, name, sec,
                     "Watercourse presence not determined.",
                     "Check whether site contains a watercourse. If yes, a >= 20 ft drainage easement is required.")
    if not d.drainage_easement_shown:
        return _fail(rid, name, sec,
                     "Watercourse on site but drainage easement not shown on plan.",
                     "Show drainage easement >= 20 ft wide conforming to watercourse centerline. "
                     "Include required note for man-made lakes if applicable.")
    if d.drainage_easement_min_width_ft is not None and d.drainage_easement_min_width_ft < 20:
        return _fail(rid, name, sec,
                     f"Drainage easement {d.drainage_easement_min_width_ft} ft < 20 ft minimum.",
                     "Widen drainage easement to minimum 20 ft (not to exceed 20 ft from top of bank).",
                     d.drainage_easement_min_width_ft)
    return _pass(rid, name, sec,
                 "Drainage easement shown and >= 20 ft wide.",
                 d.drainage_easement_min_width_ft)


# ==============================================================
# ENV â Environmental / Special Overlays
# ==============================================================

def rule_sfha_boundary(d: SubmissionData) -> RuleResult:
    rid, name = "ENV-001", "SFHA Boundary Delineation"
    sec = "Sec. 2303.G" if d.jurisdiction == "county" else "Sec. 3.16.a"
    if d.has_sfha_on_site is False:
        return _na(rid, name, sec)
    if d.has_sfha_on_site is None:
        return _warn(rid, name, sec,
                     "SFHA presence not determined.",
                     "Check FIRM maps. If SFHA present, delineate boundary on plan.")
    if d.sfha_boundary_shown is True:
        return _pass(rid, name, sec, "SFHA boundary delineated on plan.")
    return _fail(rid, name, sec,
                 "SFHA on site but boundary not shown on plan.",
                 "Delineate SFHA boundary per Cumberland County FIRM maps on the plan.")


def rule_sfha_disclosure(d: SubmissionData) -> RuleResult:
    rid, name = "ENV-002", "SFHA Notice / Disclosure Note"
    sec = "Sec. 2303.G" if d.jurisdiction == "county" else "Sec. 3.16.c"
    if d.has_sfha_on_site is False:
        return _na(rid, name, sec)
    if d.sfha_disclosure_note_present is True:
        return _pass(rid, name, sec, "SFHA disclosure note present on plan.")
    if d.sfha_disclosure_note_present is False:
        return _fail(rid, name, sec,
                     "SFHA disclosure note missing.",
                     "Add required note: 'Notice: Any improvement within the Special Flood "
                     "Hazard Area, or any subsequent revision thereof, is subject to the "
                     "provisions of the Cumberland County Flood Damage Prevention Ordinance "
                     "and may be limited or precluded thereby.'")
    return _warn(rid, name, sec,
                 "SFHA disclosure note not verified.",
                 "Confirm SFHA notice note appears on the plan/plat.")


def rule_riparian_buffer(d: SubmissionData) -> RuleResult:
    rid, name, sec = "ENV-003", "Riparian Buffer (50 ft Combined)", "Sec. 1102.H (Zoning Ord.)"
    if d.has_riparian_watercourse is False:
        return _na(rid, name, sec)
    if d.has_riparian_watercourse is None:
        return _warn(rid, name, sec,
                     "Riparian watercourse presence not determined.",
                     "Check if site abuts Cape Fear River, Little River, Lower Little River, "
                     "Rockfish Creek, Little Rockfish Creek, or South River. "
                     "If yes, 50 ft combined riparian buffer is required.")
    if not d.riparian_buffer_shown:
        return _fail(rid, name, sec,
                     "Riparian watercourse on site but buffer not shown.",
                     "Show and label the 50 ft combined riparian buffer (two zones) on the plan.")
    if d.riparian_buffer_width_ft is not None and d.riparian_buffer_width_ft < 50:
        return _fail(rid, name, sec,
                     f"Riparian buffer shown as {d.riparian_buffer_width_ft} ft < 50 ft required.",
                     "Increase riparian buffer to >= 50 ft combined width.",
                     d.riparian_buffer_width_ft)
    return _pass(rid, name, sec, "Riparian buffer shown and >= 50 ft.", d.riparian_buffer_width_ft)


def rule_fort_liberty_notification(d: SubmissionData) -> RuleResult:
    rid, name, sec = "ENV-004", "Fort Liberty Special Interest Area Notification", "Sec. 2302.C"
    if d.in_fort_liberty_special_interest_area is False:
        return _na(rid, name, sec)
    if d.in_fort_liberty_special_interest_area is True:
        return _warn(rid, name, sec,
                     "Development is within the Fort Liberty Special Interest Area.",
                     "Planning & Inspections Staff must forward plan copy to military planner "
                     "at Fort Liberty AND the local U.S. Fish & Wildlife Service office. "
                     "Consider clustering per Sec. 2302.C to protect Red-Cockaded Woodpecker habitat.")
    return _na(rid, name, sec)


def rule_farmland_disclosure(d: SubmissionData) -> RuleResult:
    rid, name = "ENV-005", "Farmland Protection Area Disclosure"
    sec = "Sec. 2302.G / 2504.B" if d.jurisdiction == "county" else "Sec. 5.2.g"
    if d.in_voluntary_agricultural_district is False:
        return _na(rid, name, sec)
    if d.in_voluntary_agricultural_district is None:
        return _warn(rid, name, sec,
                     "VAD/rural area status not determined.",
                     "Check if property is in a Voluntary Agricultural District or Rural Area. "
                     "If yes, farmland disclosure is required on final plat.")
    if d.farmland_disclosure_present is True:
        return _pass(rid, name, sec, "Farmland Protection Area disclosure present.")
    return _fail(rid, name, sec,
                 "Property in VAD/rural area but farmland disclosure missing.",
                 "Add required farmland disclosure note to the final plat.")


def rule_airport_overlay_disclosure(d: SubmissionData) -> RuleResult:
    rid, name, sec = "ENV-006", "Airport Overlay District Disclosure", "Sec. 8.101.E (Zoning Ord.)"
    if d.in_airport_overlay_district is False:
        return _na(rid, name, sec)
    if d.in_airport_overlay_district is None:
        return _warn(rid, name, sec,
                     "Airport Overlay District status not determined.",
                     "Check official zoning map for AOD. If within AOD, disclosure note is required.")
    if d.airport_disclosure_present is True:
        return _pass(rid, name, sec, "Airport Overlay District disclosure present.")
    return _fail(rid, name, sec,
                 "Property in Airport Overlay District but disclosure missing.",
                 "Add required AOD noise impact disclosure note to plan/plat per Sec. 8.101.E.")


def rule_mia_applicability(d: SubmissionData) -> RuleResult:
    rid, name, sec = "MIA-001", "Municipal Influence Area Standards Apply", "Sec. 2302.A"
    if d.in_mia is False:
        return _na(rid, name, sec)
    lots = d.mia_lots or 0
    if d.in_mia is True and lots >= 4:
        return _warn(rid, name, sec,
                     f"Development is in an MIA with {lots} lots/units (>= 4 trigger).",
                     "Apply the applicable MIA municipality's subdivision design standards "
                     "from Exhibit 5. Confirm street widths, recreation area, utilities, "
                     "and sidewalk requirements match the applicable municipal standards.")
    return _na(rid, name, sec)


# ==============================================================
# FPL â Final Plat Certificates & Disclosures (County)
# ==============================================================

def rule_final_plat_conforms_to_prelim(d: SubmissionData) -> RuleResult:
    rid, name = "FPL-001", "Final Plat Conforms to Approved Preliminary Plan"
    sec = "Sec. 2503.A / 2501.B" if d.jurisdiction == "county" else "Sec. 2.4 / Sec. 5.2.a"
    if d.submission_type != "final_plat":
        return _na(rid, name, sec)
    if d.conforms_to_approved_prelim is True:
        return _pass(rid, name, sec, "Final plat conforms to approved preliminary plan.")
    if d.conforms_to_approved_prelim is False:
        return _fail(rid, name, sec,
                     "Final plat does not conform to approved preliminary plan.",
                     "Submit revised preliminary plan with transmittal letter explaining changes, "
                     "and obtain new preliminary approval before final plat is processed.")
    return _warn(rid, name, sec,
                 "Conformance with approved preliminary plan not confirmed.",
                 "Verify final plat matches the approved preliminary plan. Provide approval "
                 "letter and stamped preliminary plan with submission.")


def rule_final_plat_conditional_zoning(d: SubmissionData) -> RuleResult:
    rid, name, sec = "FPL-002", "Conformance with Conditional Zoning Site Plan (if applicable)", "Sec. 506"
    if d.submission_type != "final_plat":
        return _na(rid, name, sec)
    if d.conditional_zoning_conformance is None:
        return _warn(rid, name, sec,
                     "Conditional Zoning approval status not determined.",
                     "Verify whether the project was approved with a Board of Commissioners "
                     "Conditional Zoning request. If yes, final plat must conform to the "
                     "approved site plan and all conditions of approval per Sec. 506.")
    if d.conditional_zoning_conformance is True:
        return _pass(rid, name, sec,
                     "Final plat conforms to approved Conditional Zoning site plan and conditions.")
    return _fail(rid, name, sec,
                 "Final plat does not conform to the Conditional Zoning site plan or "
                 "conditions of approval.",
                 "Submit revised preliminary plan with narrative addressing Section 506 "
                 "requirements. Include previous approval letter, condition sheet, and site plan.")


def rule_final_plat_surveyor_cert(d: SubmissionData) -> RuleResult:
    rid, name = "FPL-003", "Surveyor's Certificate on Final Plat"
    sec = "Sec. 2503.C" if d.jurisdiction == "county" else "Sec. 5.2.b"
    if d.submission_type != "final_plat":
        return _na(rid, name, sec)
    if d.surveyor_certificate_present is True:
        return _pass(rid, name, sec, "Surveyor's certificate present on final plat.")
    if d.surveyor_certificate_present is False:
        return _fail(rid, name, sec,
                     "Surveyor's certificate missing from final plat.",
                     "Add NC licensed surveyor's certificate per N.C. GEN. STAT. 47-30, "
                     "with ratio of precision, signature, seal, and registration number.")
    return _warn(rid, name, sec,
                 "Surveyor's certificate not verified.",
                 "Confirm surveyor certificate is present, signed, and sealed.")


def rule_final_plat_ownership_cert(d: SubmissionData) -> RuleResult:
    rid, name = "FPL-004", "Certificate of Ownership and Dedication"
    sec = "Sec. 2503.D" if d.jurisdiction == "county" else "Sec. 5.2.c"
    if d.submission_type != "final_plat":
        return _na(rid, name, sec)
    if d.ownership_dedication_cert_present is True:
        return _pass(rid, name, sec, "Certificate of ownership and dedication present.")
    if d.ownership_dedication_cert_present is False:
        jurisdiction_note = (
            "jurisdiction of the County of Cumberland"
            if d.jurisdiction == "county"
            else "Planning and Development Regulation Jurisdiction of the Town of Wade"
        )
        return _fail(rid, name, sec,
                     "Ownership/dedication certificate missing.",
                     f"Add notarized ownership and dedication certificate. The certificate "
                     f"must reference the '{jurisdiction_note}' and include owner signature(s).")
    return _warn(rid, name, sec,
                 "Ownership/dedication certificate not verified.",
                 "Confirm notarized certificate with owner signatures is present.")


def rule_final_plat_director_cert(d: SubmissionData) -> RuleResult:
    rid, name = "FPL-005", "Director's Certificate of Approval"
    sec = "Sec. 2503.E" if d.jurisdiction == "county" else "Sec. 5.2.e"
    if d.submission_type != "final_plat":
        return _na(rid, name, sec)
    if d.director_cert_present is True:
        return _pass(rid, name, sec, "Director's certificate space present on final plat.")
    if d.director_cert_present is False:
        return _fail(rid, name, sec,
                     "Director's certificate space missing from final plat.",
                     "Add space for Cumberland County Planning & Inspections Director "
                     "approval signature per Sec. 2503.E.")
    return _warn(rid, name, sec,
                 "Director's certificate space not verified.",
                 "Confirm Director's certificate block is on the final plat.")


def rule_final_plat_plat_review_officer(d: SubmissionData) -> RuleResult:
    rid, name, sec = "FPL-006", "Plat Review Officer Certification", "Sec. 2503.F"
    if d.submission_type != "final_plat":
        return _na(rid, name, sec)
    if d.plat_review_officer_cert_present is True:
        return _pass(rid, name, sec, "Plat Review Officer certification space present.")
    if d.plat_review_officer_cert_present is False:
        return _fail(rid, name, sec,
                     "Plat Review Officer certification space missing from final plat.",
                     "Add Plat Review Officer certification block: 'STATE OF NORTH CAROLINA "
                     "COUNTY OF CUMBERLAND â I, [name], Plat Review Officer of Cumberland "
                     "County, certify that the plat to which this certificate is affixed meets "
                     "all statutory requirements for recording.' per Sec. 2503.F.")
    return _warn(rid, name, sec,
                 "Plat Review Officer certification not verified.",
                 "Confirm Sec. 2503.F Plat Review Officer certification block is present.")


def rule_final_plat_recording_deadline(d: SubmissionData) -> RuleResult:
    """County: final plat must be recorded within 1 year of Director approval."""
    rid, name, sec = "FPL-007", "Final Plat Recording Within 1 Year of Approval (County)", "Sec. 2506"
    if d.submission_type != "final_plat":
        return _na(rid, name, sec)
    if d.months_since_prelim_approval is None:
        return _warn(rid, name, sec,
                     "Months since preliminary plan approval not provided.",
                     "Verify the final plat will be recorded within 1 year of Director approval.")
    if d.months_since_prelim_approval <= 12:
        return _pass(rid, name, sec,
                     f"{d.months_since_prelim_approval:.1f} months since approval; "
                     "within 12-month window.")
    return _fail(rid, name, sec,
                 f"{d.months_since_prelim_approval:.1f} months have passed since preliminary "
                 "plan approval, exceeding the 12-month recording deadline.",
                 "Record the final plat immediately or reapply for preliminary approval.",
                 d.months_since_prelim_approval)


def rule_nonconforming_structure_disclosure(d: SubmissionData) -> RuleResult:
    rid, name = "FPL-008", "Nonconforming Structure Disclosure"
    sec = "Sec. 2504.D" if d.jurisdiction == "county" else "Sec. 5.2"
    if d.submission_type != "final_plat":
        return _na(rid, name, sec)
    if d.nonconforming_structure_disclosure is True:
        return _pass(rid, name, sec, "Nonconforming structure disclosure/certification present.")
    if d.nonconforming_structure_disclosure is False:
        return _fail(rid, name, sec,
                     "Nonconforming structure disclosure missing.",
                     "Show all existing structures on final plat, or add signed owner "
                     "certification: 'Nonconforming structures have not been created by "
                     "this subdivision/development/recombination plat.'")
    return _warn(rid, name, sec,
                 "Nonconforming structure disclosure not verified.",
                 "Confirm existing structures are shown on plat or certification is present.")


def rule_proposed_public_street_disclosure(d: SubmissionData) -> RuleResult:
    rid, name = "FPL-009", "Proposed Public Street Disclosure"
    sec = "Sec. 2504.E" if d.jurisdiction == "county" else "Sec. 5.2"
    if d.submission_type != "final_plat":
        return _na(rid, name, sec)
    if d.proposed_public_street_disclosure is True:
        return _pass(rid, name, sec, "Proposed public street disclosure present.")
    if d.proposed_public_street_disclosure is False:
        return _fail(rid, name, sec,
                     "Proposed public street disclosure missing.",
                     "Add required disclosure noting streets not yet accepted by NCDOT.")
    return _warn(rid, name, sec,
                 "Proposed public street disclosure not verified.",
                 "Confirm public street disclosure is present if streets are not yet NCDOT-accepted.")


def rule_final_plat_ccr_docs(d: SubmissionData) -> RuleResult:
    rid, name, sec = "FPL-010", "CCR/HOA Documents for County Attorney Review", "Sec. 2304 / Checklist"
    if d.submission_type != "final_plat":
        return _na(rid, name, sec)
    if d.ccr_hoa_docs_provided is True:
        return _pass(rid, name, sec,
                     "CCR/HOA legal documents provided for County Attorney review.")
    if d.ccr_hoa_docs_provided is False:
        return _fail(rid, name, sec,
                     "CCR/HOA legal documents not provided for County Attorney review.",
                     "Submit CCR/HOA legal documents with a transmittal letter indicating "
                     "the page references for required regulatory language. County Attorney "
                     "review and approval is required before Final Plat approval.")
    return _warn(rid, name, sec,
                 "CCR/HOA document status not verified.",
                 "Confirm whether CCR/HOA documents are required. If yes, submit with "
                 "transmittal letter for County Attorney review.")


# ==============================================================
# WADE-SPECIFIC RULES  (WAD / MHP / GRP prefix)
# ==============================================================

# --- WAD-001: Town Water Required for All Development ---

def rule_wade_town_water_required(d: SubmissionData) -> RuleResult:
    rid, name, sec = "WAD-001", "Town Water Required â All Wade Development", "Sec. 3.14"
    if d.water_sewer_type == "public":
        return _pass(rid, name, sec,
                     "Town water connection indicated. Meets Wade Sec. 3.14 requirement.")
    if d.water_sewer_type in ("on_site", "community", "private"):
        return _fail(rid, name, sec,
                     "All development within the Town of Wade planning jurisdiction must "
                     f"connect to Town water. Plan shows '{d.water_sewer_type}' utilities.",
                     "Connect to Town of Wade public water system as required by Sec. 3.14. "
                     "On-site or private water supply is not permitted.")
    return _warn(rid, name, sec,
                 "Water supply type not determined.",
                 "Confirm connection to Town of Wade public water system is shown. "
                 "All Wade development must have Town water per Sec. 3.14.")


# --- WAD-002: Asphalt Curb & Gutter Within Town Limits ---

def rule_wade_curb_gutter(d: SubmissionData) -> RuleResult:
    rid, name, sec = "WAD-002", "Asphalt Curb & Gutter Required (Within Town Limits)", "Sec. 4.1.e"
    if d.within_town_limits is False:
        return _na(rid, name, sec)
    if d.within_town_limits is None:
        return _warn(rid, name, sec,
                     "Whether development is within Town of Wade limits not determined.",
                     "Confirm whether within Town limits. If yes, asphalt curb & gutter "
                     "is required per Sec. 4.1.e.")
    if d.curb_gutter_shown is True:
        return _pass(rid, name, sec,
                     "Asphalt curb & gutter shown on plan. Meets Sec. 4.1.e requirement.")
    if d.curb_gutter_shown is False:
        return _fail(rid, name, sec,
                     "Asphalt curb & gutter is required within Town of Wade limits "
                     "but is not shown on the plan.",
                     "Design and show asphalt curb & gutter to NCDOT standards on all "
                     "streets within the Town limits per Sec. 4.1.e.")
    return _warn(rid, name, sec,
                 "Curb & gutter not verified on plan.",
                 "Confirm asphalt curb & gutter is shown for all streets within Town limits.")


# --- WAD-003: Street Base Course ---

def rule_wade_street_base(d: SubmissionData) -> RuleResult:
    rid, name, sec = "WAD-003", "Street Base Course â 4 inch ABC Stone Min", "Sec. 4.1.b"
    if d.submission_type == "final_plat":
        return _na(rid, name, sec)
    if d.street_base_depth_in is None:
        return _warn(rid, name, sec,
                     "Street base course depth not extracted.",
                     "Verify base course is minimum 4 inches of ABC stone (crusher run) "
                     "to a minimum 20 ft width per Sec. 4.1.b.")
    if d.street_base_depth_in >= 4:
        return _pass(rid, name, sec,
                     f"Street base {d.street_base_depth_in} inches >= 4 inch minimum.",
                     d.street_base_depth_in)
    return _fail(rid, name, sec,
                 f"Street base {d.street_base_depth_in} inches < 4 inch minimum required.",
                 "Increase street base to minimum 4 inches of ABC stone (crusher run) "
                 "at minimum 20 ft width per Sec. 4.1.b.",
                 d.street_base_depth_in)


# --- WAD-004: Street Surface Course ---

def rule_wade_street_surface(d: SubmissionData) -> RuleResult:
    rid, name, sec = "WAD-004", "Street Surface Course â 2 inch I-2 Asphalt Min", "Sec. 4.1.c"
    if d.submission_type == "final_plat":
        return _na(rid, name, sec)
    if d.street_surface_depth_in is None:
        return _warn(rid, name, sec,
                     "Street surface depth not extracted.",
                     "Verify surface course is minimum 2 inches of I-2 asphalt "
                     "to a minimum 20 ft width per Sec. 4.1.c.")
    if d.street_surface_depth_in >= 2:
        return _pass(rid, name, sec,
                     f"Street surface {d.street_surface_depth_in} inches >= 2 inch minimum.",
                     d.street_surface_depth_in)
    return _fail(rid, name, sec,
                 f"Street surface {d.street_surface_depth_in} inches < 2 inch minimum required.",
                 "Increase street surface to minimum 2 inches of I-2 asphalt "
                 "at minimum 20 ft width per Sec. 4.1.c.",
                 d.street_surface_depth_in)


# --- WAD-005: Street ROW Minimum ---

def rule_wade_street_row(d: SubmissionData) -> RuleResult:
    rid, name, sec = "WAD-005", "Street ROW â Min 50 ft (80 ft if Divided)", "Sec. 3.17.b"
    if d.street_row_ft is None:
        return _warn(rid, name, sec,
                     "Street ROW width not extracted.",
                     "Verify street ROW is >= 50 ft minimum (>= 80 ft if divided with median).")
    divided = d.street_divided_median is True
    required = 80 if divided else 50
    label    = "80 ft (divided street)" if divided else "50 ft"
    if d.street_row_ft >= required:
        return _pass(rid, name, sec,
                     f"Street ROW {d.street_row_ft} ft >= {required} ft required ({label}).",
                     d.street_row_ft)
    return _fail(rid, name, sec,
                 f"Street ROW {d.street_row_ft} ft < {required} ft minimum required ({label}).",
                 f"Increase street ROW to >= {required} ft. Divided streets require >= 80 ft "
                 f"with no median less than 20 ft wide per Sec. 3.17.b.",
                 d.street_row_ft)


# --- WAD-006: Wade Cul-de-Sac Max Length (800 ft) ---

def rule_wade_cul_de_sac_length(d: SubmissionData) -> RuleResult:
    rid, name, sec = "WAD-006", "Cul-de-Sac Maximum Length (Wade â 800 ft)", "Sec. 3.17.c"
    if d.has_cul_de_sac is False:
        return _na(rid, name, sec)
    if d.cul_de_sac_length_ft is None:
        return _warn(rid, name, sec,
                     "Cul-de-sac length not extracted.",
                     "Verify cul-de-sac street length does not exceed 800 ft (Wade Sec. 3.17.c).")
    if d.cul_de_sac_length_ft <= 800:
        return _pass(rid, name, sec,
                     f"Cul-de-sac length {d.cul_de_sac_length_ft} ft <= 800 ft Wade maximum.",
                     d.cul_de_sac_length_ft)
    return _fail(rid, name, sec,
                 f"Cul-de-sac length {d.cul_de_sac_length_ft} ft exceeds 800 ft Wade maximum.",
                 "Shorten cul-de-sac to <= 800 ft or stub to adjacent property. "
                 "Note: Wade limit is 800 ft, stricter than County's 1,400 ft.",
                 d.cul_de_sac_length_ft)


# --- WAD-007: Wade Cul-de-Sac Turnaround Dimensions (roadway 80 ft) ---

def rule_wade_cul_de_sac_dimensions(d: SubmissionData) -> RuleResult:
    rid, name, sec = "WAD-007", "Cul-de-Sac Turnaround Dimensions (Wade â 80 ft roadway)", "Sec. 3.17.c"
    if d.has_cul_de_sac is False:
        return _na(rid, name, sec)
    issues = []
    if d.cul_de_sac_roadway_diameter_ft is not None and d.cul_de_sac_roadway_diameter_ft < 80:
        issues.append(
            f"roadway diameter {d.cul_de_sac_roadway_diameter_ft} ft < 80 ft required (Wade)"
        )
    if d.cul_de_sac_row_diameter_ft is not None and d.cul_de_sac_row_diameter_ft < 100:
        issues.append(
            f"ROW diameter {d.cul_de_sac_row_diameter_ft} ft < 100 ft required"
        )
    if not issues:
        if d.cul_de_sac_roadway_diameter_ft is None and d.cul_de_sac_row_diameter_ft is None:
            return _warn(rid, name, sec,
                         "Cul-de-sac dimensions not extracted.",
                         "Verify: roadway diameter >= 80 ft (Wade) and ROW diameter >= 100 ft.")
        return _pass(rid, name, sec,
                     "Cul-de-sac dimensions meet Wade requirements (roadway >= 80 ft, ROW >= 100 ft).")
    return _fail(rid, name, sec,
                 "Cul-de-sac turnaround does not meet Wade dimensions: " + "; ".join(issues) + ".",
                 "Redesign: roadway outside diameter >= 80 ft, ROW diameter >= 100 ft per Sec. 3.17.c.")


# --- WAD-008: Private Street ROW 60 ft ---

def rule_wade_private_street_row(d: SubmissionData) -> RuleResult:
    rid, name, sec = "WAD-008", "Private Street â 60 ft ROW / 20 ft Pavement (Wade)", "Sec. 4.2.c"
    if not d.has_private_streets:
        return _na(rid, name, sec)
    if d.private_street_row_ft is None:
        return _warn(rid, name, sec,
                     "Private street ROW width not extracted.",
                     "Verify private street ROW is >= 60 ft with >= 20 ft pavement face-to-face "
                     "or gutter-to-gutter per Sec. 4.2.c (NCDOT residential street standard).")
    if d.private_street_row_ft >= 60:
        return _pass(rid, name, sec,
                     f"Private street ROW {d.private_street_row_ft} ft >= 60 ft Wade minimum.",
                     d.private_street_row_ft)
    return _fail(rid, name, sec,
                 f"Private street ROW {d.private_street_row_ft} ft < 60 ft Wade minimum.",
                 "Increase private street ROW to >= 60 ft with >= 20 ft pavement "
                 "per Sec. 4.2.c (NCDOT residential with asphalt curb & gutter).",
                 d.private_street_row_ft)


# --- WAD-009: Private Street Engineer Certification ---

def rule_wade_private_street_engineer_cert(d: SubmissionData) -> RuleResult:
    rid, name, sec = "WAD-009", "Private Street â Registered Engineer Certification", "Sec. 4.2.d"
    if not d.has_private_streets:
        return _na(rid, name, sec)
    if d.submission_type != "final_plat":
        return _na(rid, name, sec)
    if d.engineer_cert_private_street is True:
        return _pass(rid, name, sec,
                     "Registered engineer certification for private street construction on file.")
    if d.engineer_cert_private_street is False:
        return _fail(rid, name, sec,
                     "Registered engineer certification for private street construction is missing. "
                     "Required before recording the final plat.",
                     "Obtain written statement from a registered engineer with engineer's seal "
                     "confirming all private streets and drainage are constructed per "
                     "Sec. 4.2.c requirements. Submit to Town of Wade for approval prior to "
                     "recording final plat per Sec. 4.2.d.")
    return _warn(rid, name, sec,
                 "Private street engineer certification not verified.",
                 "Confirm registered engineer certification with seal is on file before "
                 "recording final plat per Sec. 4.2.d.")


# --- WAD-010: Sidewalk on All New Streets (5 ft wide) ---

def rule_wade_sidewalk_all_streets(d: SubmissionData) -> RuleResult:
    rid, name, sec = "WAD-010", "Sidewalk Required â All New Streets, One Side (Wade)", "Sec. 4.1.h"
    if d.submission_type != "preliminary_plan":
        return _na(rid, name, sec)
    if d.sidewalk_all_new_streets_shown is True:
        return _pass(rid, name, sec,
                     "Sidewalks shown on one side of all new streets per Sec. 4.1.h.")
    if d.sidewalk_all_new_streets_shown is False:
        return _fail(rid, name, sec,
                     "Asphalt sidewalks are required on one side of all new streets "
                     "within Wade jurisdiction but are not shown on the plan.",
                     "Design and show asphalt sidewalks on one side of all new streets. "
                     "Minimum width 5 ft adjacent to asphalt curb & gutter per Sec. 4.1.h.")
    return _warn(rid, name, sec,
                 "Sidewalk coverage on all new streets not verified.",
                 "Confirm asphalt sidewalks (min 5 ft wide) are shown on one side of "
                 "every new street per Sec. 4.1.h.")


# --- WAD-011: Sidewalk Dimensions (Wade: 5 ft = 60 in) ---

def rule_wade_sidewalk_dimensions(d: SubmissionData) -> RuleResult:
    rid, name, sec = "WAD-011", "Sidewalk Dimensions â 5 ft Min Width (Wade)", "Sec. 4.1.h"
    if d.sidewalk_shown is False:
        return _na(rid, name, sec)
    issues = []
    if d.sidewalk_width_inches is not None and d.sidewalk_width_inches < 60:
        issues.append(f"width {d.sidewalk_width_inches} in < 60 in (5 ft) Wade minimum")
    if d.sidewalk_pedestrian_thickness_in is not None and d.sidewalk_pedestrian_thickness_in < 4:
        issues.append(f"pedestrian thickness {d.sidewalk_pedestrian_thickness_in} in < 4 in")
    if d.sidewalk_vehicular_thickness_in is not None and d.sidewalk_vehicular_thickness_in < 7:
        issues.append(f"vehicular thickness {d.sidewalk_vehicular_thickness_in} in < 7 in")
    if not issues:
        return _pass(rid, name, sec, "Sidewalk dimensions meet Wade Sec. 4.1.h requirements.")
    return _fail(rid, name, sec,
                 "Sidewalk dimensions do not comply: " + "; ".join(issues) + ".",
                 "Revise: min width 5 ft (60 in) adjacent to curb & gutter, >= 4 in thick "
                 "(pedestrian), >= 7 in thick (vehicular), ADA compliant per Sec. 4.1.h.")


# --- WAD-012: Wade Recreation Area (standard subdivision, floodplain tiers) ---

def rule_wade_recreation_area(d: SubmissionData) -> RuleResult:
    rid, name, sec = "WAD-012", "Recreation Area â Wade Standard Subdivision (Sec. 3.13.1)", "Sec. 3.13.1"
    if d.development_type != "subdivision":
        return _na(rid, name, sec)

    above_fp  = d.lots_above_floodplain or 0
    in_fp     = d.lots_in_floodplain    or 0
    water_bod = d.lots_on_water_body    or 0
    total_lots = (d.total_proposed_lots or 0)

    if total_lots == 0:
        return _na(rid, name, sec)

    # If no breakdown given, warn
    if above_fp == 0 and in_fp == 0 and water_bod == 0:
        return _warn(rid, name, sec,
                     f"{total_lots} lots proposed. Floodplain lot breakdown not provided.",
                     "Provide lot counts by floodplain status to calculate required recreation "
                     "area: 500 sq ft/lot (above floodplain), 1,000 sq ft/lot (in floodplain), "
                     "2,000 sq ft/lot (water body) per Sec. 3.13.1.")

    required = (above_fp * 500) + (in_fp * 1000) + (water_bod * 2000)

    if d.recreation_area_sqft is None:
        return _warn(rid, name, sec,
                     f"Required recreation area is {required:,} sq ft "
                     f"({above_fp} lots above FP - 500 + {in_fp} lots in FP - 1,000 + "
                     f"{water_bod} on water - 2,000). Recreation area not labeled on plan.",
                     "Label and dimension recreation area on plan to demonstrate compliance.")

    if d.recreation_area_sqft >= required:
        return _pass(rid, name, sec,
                     f"Recreation area {d.recreation_area_sqft:,} sq ft >= "
                     f"{required:,} sq ft required.",
                     d.recreation_area_sqft)
    return _fail(rid, name, sec,
                 f"Recreation area {d.recreation_area_sqft:,} sq ft < {required:,} sq ft required "
                 f"(500/1,000/2,000 sq ft per lot by floodplain status).",
                 f"Add {required - d.recreation_area_sqft:,.0f} sq ft of recreation area or "
                 f"pay fee-in-lieu if applicable per Sec. 3.13.1.",
                 d.recreation_area_sqft)


# --- WAD-013: Final Plat Recording Within 30 Days (Wade) ---

def rule_wade_final_plat_recording_deadline(d: SubmissionData) -> RuleResult:
    rid, name, sec = "WAD-013", "Final Plat Recording Within 30 Days of Approval (Wade)", "Sec. 2.7"
    if d.submission_type != "final_plat":
        return _na(rid, name, sec)
    if d.months_since_prelim_approval is None:
        return _warn(rid, name, sec,
                     "Days/months since Town approval not provided.",
                     "Verify the final plat will be recorded in the Cumberland County Register "
                     "of Deeds within 30 days of Town of Wade approval per Sec. 2.7. "
                     "Failure to record within 30 days voids final approval.")
    days_approx = d.months_since_prelim_approval * 30
    if days_approx <= 30:
        return _pass(rid, name, sec,
                     f"Approximately {days_approx:.0f} days since approval; within 30-day window.")
    return _fail(rid, name, sec,
                 f"Approximately {days_approx:.0f} days have passed since approval, "
                 "exceeding the 30-day recording deadline.",
                 "Record the final plat with the Register of Deeds immediately. "
                 "Final approval is void if not recorded within 30 days per Sec. 2.7.",
                 days_approx)


# ==============================================================
# MHP â Mobile Home Park Rules (Wade Sec. 3.23)
# ==============================================================

def rule_wade_mhp_lot_area(d: SubmissionData) -> RuleResult:
    rid, name, sec = "MHP-001", "Mobile Home Park â Minimum Lot Area 1 Acre", "Sec. 3.23.a"
    if d.development_type != "mobile_home_park":
        return _na(rid, name, sec)
    if d.mhp_min_lot_area_acres is None:
        return _warn(rid, name, sec,
                     "Mobile home park lot area not extracted.",
                     "Verify the mobile home park site is minimum 1 acre (excluding "
                     "dedicated ROW, floodplain, and well/septic areas) per Sec. 3.23.a.")
    if d.mhp_min_lot_area_acres >= 1.0:
        return _pass(rid, name, sec,
                     f"MHP lot area {d.mhp_min_lot_area_acres} acres >= 1 acre minimum.",
                     d.mhp_min_lot_area_acres)
    return _fail(rid, name, sec,
                 f"MHP lot area {d.mhp_min_lot_area_acres} acres < 1 acre minimum.",
                 "Increase mobile home park site to minimum 1 acre (net of ROW, "
                 "floodplain, and utility areas) per Sec. 3.23.a.",
                 d.mhp_min_lot_area_acres)


def rule_wade_mhp_density(d: SubmissionData) -> RuleResult:
    rid, name, sec = "MHP-002", "Mobile Home Park â Max Density 8 Units/Acre", "Sec. 3.23.a"
    if d.development_type != "mobile_home_park":
        return _na(rid, name, sec)
    if d.mhp_density_per_acre is None:
        return _warn(rid, name, sec,
                     "Mobile home park density not extracted.",
                     "Verify density does not exceed 8 mobile homes per acre "
                     "(net of ROW, floodplain, and utility areas) per Sec. 3.23.a.")
    if d.mhp_density_per_acre <= 8:
        return _pass(rid, name, sec,
                     f"MHP density {d.mhp_density_per_acre} units/acre <= 8 maximum.",
                     d.mhp_density_per_acre)
    return _fail(rid, name, sec,
                 f"MHP density {d.mhp_density_per_acre} units/acre exceeds 8 unit/acre maximum.",
                 "Reduce number of mobile home spaces to stay at or below 8 per net acre "
                 "per Sec. 3.23.a.",
                 d.mhp_density_per_acre)


def rule_wade_mhp_unit_separation(d: SubmissionData) -> RuleResult:
    rid, name, sec = "MHP-003", "Mobile Home Unit Separation Distances", "Sec. 3.23.c"
    if d.development_type != "mobile_home_park":
        return _na(rid, name, sec)
    issues = []
    if (d.mhp_unit_separation_longitudinal_ft is not None
            and d.mhp_unit_separation_longitudinal_ft < 25):
        issues.append(
            f"longitudinal separation {d.mhp_unit_separation_longitudinal_ft} ft < 25 ft required"
        )
    if (d.mhp_unit_separation_end_ft is not None
            and d.mhp_unit_separation_end_ft < 15):
        issues.append(
            f"end-to-end separation {d.mhp_unit_separation_end_ft} ft < 15 ft required"
        )
    if not issues:
        if (d.mhp_unit_separation_longitudinal_ft is None
                and d.mhp_unit_separation_end_ft is None):
            return _warn(rid, name, sec,
                         "Mobile home unit separation distances not extracted.",
                         "Verify: units >= 25 ft apart longitudinally, >= 15 ft end-to-end, "
                         "and >= 25 ft from any permanent building per Sec. 3.23.c.")
        return _pass(rid, name, sec,
                     "Mobile home unit separation distances meet Sec. 3.23.c requirements.")
    return _fail(rid, name, sec,
                 "Mobile home unit separations do not comply: " + "; ".join(issues) + ".",
                 "Redesign layout: >= 25 ft between units longitudinally, "
                 ">= 15 ft end-to-end or corner-to-corner, >= 25 ft from any "
                 "permanent building per Sec. 3.23.c.")


def rule_wade_mhp_recreation(d: SubmissionData) -> RuleResult:
    rid, name, sec = "MHP-004", "Mobile Home Park â Recreation Area", "Sec. 3.23.d.5"
    if d.development_type != "mobile_home_park":
        return _na(rid, name, sec)
    units = d.mhp_units or 0
    if units == 0:
        return _na(rid, name, sec)

    required_per_unit = units * 500
    min_site = 5000 if units <= 10 else 10000

    if d.mhp_recreation_area_sqft is None:
        return _warn(rid, name, sec,
                     f"{units} MHP units require >= {required_per_unit:,} sq ft recreation area "
                     f"(minimum site >= {min_site:,} sq ft).",
                     "Label and dimension all recreation areas on the site plan.")

    site_ok  = d.mhp_recreation_area_sqft >= min_site
    total_ok = d.mhp_recreation_area_sqft >= required_per_unit

    if site_ok and total_ok:
        return _pass(rid, name, sec,
                     f"MHP recreation area {d.mhp_recreation_area_sqft:,} sq ft meets "
                     f"both per-unit ({required_per_unit:,} sq ft) and "
                     f"minimum site ({min_site:,} sq ft) requirements.",
                     d.mhp_recreation_area_sqft)

    issues = []
    if not total_ok:
        issues.append(f"{d.mhp_recreation_area_sqft:,} sq ft < {required_per_unit:,} sq ft "
                      f"(500 sq ft - {units} units) required")
    if not site_ok:
        issues.append(f"{d.mhp_recreation_area_sqft:,} sq ft < {min_site:,} sq ft "
                      f"minimum single-site requirement")
    return _fail(rid, name, sec,
                 "MHP recreation area insufficient: " + "; ".join(issues) + ".",
                 f"Provide >= 500 sq ft per unit ({required_per_unit:,} sq ft total) in "
                 f"area(s) each >= {min_site:,} sq ft per Sec. 3.23.d.5.",
                 d.mhp_recreation_area_sqft)


def rule_wade_mhp_perimeter_buffer(d: SubmissionData) -> RuleResult:
    rid, name, sec = "MHP-005", "Mobile Home Park â Perimeter Buffer 15 ft", "Sec. 3.23.d.6"
    if d.development_type != "mobile_home_park":
        return _na(rid, name, sec)
    if d.mhp_perimeter_buffer_ft is None:
        return _warn(rid, name, sec,
                     "Mobile home park perimeter buffer width not extracted.",
                     "Verify a minimum 15 ft natural or landscaped buffer with physical "
                     "barrier (fence/hedge) is provided around the park perimeter, "
                     "excluding entrance drives, per Sec. 3.23.d.6.")
    if d.mhp_perimeter_buffer_ft >= 15:
        return _pass(rid, name, sec,
                     f"Perimeter buffer {d.mhp_perimeter_buffer_ft} ft >= 15 ft minimum.",
                     d.mhp_perimeter_buffer_ft)
    return _fail(rid, name, sec,
                 f"Perimeter buffer {d.mhp_perimeter_buffer_ft} ft < 15 ft minimum.",
                 "Increase perimeter buffer to >= 15 ft with physical barrier (fence or hedge) "
                 "defining park boundaries per Sec. 3.23.d.6.",
                 d.mhp_perimeter_buffer_ft)


def rule_wade_mhp_pedestrian_paths(d: SubmissionData) -> RuleResult:
    rid, name, sec = "MHP-006", "Mobile Home Park â Internal Pedestrian Paths 3 ft Min", "Sec. 3.23.d.8"
    if d.development_type != "mobile_home_park":
        return _na(rid, name, sec)
    if d.mhp_pedestrian_path_width_ft is None:
        return _warn(rid, name, sec,
                     "Internal pedestrian path width not extracted.",
                     "Verify minimum 3 ft wide internal pedestrian paths to central "
                     "facilities (pool, office, laundry, recreation, bus stops) are "
                     "shown on the site plan per Sec. 3.23.d.8.")
    if d.mhp_pedestrian_path_width_ft >= 3:
        return _pass(rid, name, sec,
                     f"Internal pedestrian path {d.mhp_pedestrian_path_width_ft} ft >= 3 ft minimum.",
                     d.mhp_pedestrian_path_width_ft)
    return _fail(rid, name, sec,
                 f"Internal pedestrian path {d.mhp_pedestrian_path_width_ft} ft < 3 ft minimum.",
                 "Increase internal pedestrian path width to >= 3 ft. "
                 "Paths must connect to central facilities and be shown on site plan. "
                 "No occupancy permit issued until paths are installed per Sec. 3.23.d.8.",
                 d.mhp_pedestrian_path_width_ft)


# ==============================================================
# GRP â Group Development Recreation (Wade Sec. 3.21.k)
# ==============================================================

def rule_wade_group_dev_recreation(d: SubmissionData) -> RuleResult:
    rid, name, sec = "GRP-001", "Group Development â Recreation Area (Wade Sec. 3.21.k)", "Sec. 3.21.k"
    if d.development_type != "group_development":
        return _na(rid, name, sec)
    units = d.group_dev_units or 0
    if units == 0:
        return _na(rid, name, sec)

    # Min 500 sq ft/unit; if > 10 units, each recreation site >= 10,000 sq ft
    required_total = units * 500
    min_site       = 10000 if units > 10 else 0

    if d.group_dev_recreation_sqft is None:
        return _warn(rid, name, sec,
                     f"{units} group dev units require >= {required_total:,} sq ft recreation area"
                     + (f"; each site >= 10,000 sq ft" if min_site else "") + ".",
                     "Label and dimension recreation area(s) on the plan to demonstrate "
                     "compliance with Sec. 3.21.k.")

    if d.group_dev_recreation_sqft >= required_total:
        return _pass(rid, name, sec,
                     f"Group dev recreation {d.group_dev_recreation_sqft:,} sq ft >= "
                     f"{required_total:,} sq ft required ({units} units - 500 sq ft).",
                     d.group_dev_recreation_sqft)
    return _fail(rid, name, sec,
                 f"Group dev recreation {d.group_dev_recreation_sqft:,} sq ft < "
                 f"{required_total:,} sq ft required.",
                 f"Add {required_total - d.group_dev_recreation_sqft:,.0f} sq ft of recreation area. "
                 + (f"Each individual site must be >= 10,000 sq ft. " if min_site else "")
                 + "Per Sec. 3.21.k.",
                 d.group_dev_recreation_sqft)


# ==============================================================
# Rule Registries
# ==============================================================

ALL_COUNTY_RULES: List[RuleFunc] = [
    # Map / format
    rule_map_scale,
    rule_sheet_size,
    rule_final_plat_sheet_size,
    rule_topographic_contours,
    rule_final_plat_mylar,
    # Title
    rule_subdivision_name,
    rule_owner_designer,
    rule_date_and_north,
    # Preliminary plan data
    rule_overlay_districts_shown,
    rule_municipal_limits_shown,
    rule_jurisdictional_boundaries_shown,
    rule_existing_structure_addresses,
    rule_common_elements_shown,
    rule_public_dedication_areas_shown,
    rule_proposed_use_stated,
    rule_watershed_designation_shown,
    rule_wells_septic_shown,
    rule_street_functional_class,
    rule_acreage_new_row,
    rule_retention_basin_fence_note,
    rule_underground_utilities_note,
    rule_hoa_recreation_note,
    rule_soil_scientist_cert,
    # Lots
    rule_lot_frontage,
    rule_lot_size_labels,
    rule_lot_numbering,
    # Streets
    rule_block_length,
    rule_street_offset,
    rule_corner_radius,
    # Cul-de-sac
    rule_cul_de_sac_length,
    rule_cul_de_sac_dimensions,
    rule_hammerhead_dimensions,
    # Private streets
    rule_private_street_class_b_max_lots,
    rule_private_street_class_c_max_lots,
    rule_private_street_class_a_row,
    rule_private_street_owners_assoc,
    rule_private_street_disclosure,
    # Utilities
    rule_utility_statement_on_plan,
    rule_public_water_sewer_2_to_10_lots,
    rule_public_water_sewer_11_to_20_lots,
    rule_public_water_sewer_over_20_lots,
    rule_on_site_sewer_disclosure,
    rule_utility_easement,
    # Fire
    rule_fire_hydrant_spacing,
    rule_fire_hydrant_distance_to_lot,
    rule_fire_marshal_acceptance,
    # Sidewalks (county thresholds)
    rule_sidewalk_required,
    rule_sidewalk_dimensions,
    # Recreation (county: 800 sq ft/unit)
    rule_recreation_area,
    # Stormwater
    rule_stormwater_permit,
    rule_retention_basin_fence,
    rule_stormwater_hoa_access,
    # Drainage
    rule_drainage_easement,
    # Environmental
    rule_sfha_boundary,
    rule_sfha_disclosure,
    rule_riparian_buffer,
    rule_fort_liberty_notification,
    rule_farmland_disclosure,
    rule_airport_overlay_disclosure,
    rule_mia_applicability,
    # Final plat
    rule_final_plat_conforms_to_prelim,
    rule_final_plat_conditional_zoning,
    rule_final_plat_surveyor_cert,
    rule_final_plat_ownership_cert,
    rule_final_plat_director_cert,
    rule_final_plat_plat_review_officer,
    rule_final_plat_recording_deadline,
    rule_nonconforming_structure_disclosure,
    rule_proposed_public_street_disclosure,
    rule_final_plat_ccr_docs,
]

ALL_WADE_RULES: List[RuleFunc] = [
    # Map / format (same ranges except final plat scale handled in rule_map_scale)
    rule_map_scale,
    rule_sheet_size,
    rule_final_plat_sheet_size,
    rule_topographic_contours,
    # Title (same)
    rule_subdivision_name,
    rule_owner_designer,
    rule_date_and_north,
    # Lots (same)
    rule_lot_frontage,
    rule_lot_size_labels,
    rule_lot_numbering,
    # Streets (shared thresholds)
    rule_block_length,
    rule_street_offset,
    rule_corner_radius,
    # Wade-specific street rules
    rule_wade_street_row,
    rule_wade_curb_gutter,
    rule_wade_street_base,
    rule_wade_street_surface,
    # Cul-de-sac (Wade overrides â stricter limits)
    rule_wade_cul_de_sac_length,
    rule_wade_cul_de_sac_dimensions,
    rule_hammerhead_dimensions,          # same dimensions
    # Private streets (Wade overrides)
    rule_private_street_class_b_max_lots,
    rule_private_street_class_c_max_lots,
    rule_wade_private_street_row,        # Wade: 60 ft ROW
    rule_private_street_owners_assoc,
    rule_private_street_disclosure,
    rule_wade_private_street_engineer_cert,
    # Utilities
    rule_utility_statement_on_plan,
    rule_wade_town_water_required,       # Wade: town water mandatory
    rule_public_water_sewer_2_to_10_lots,
    rule_public_water_sewer_11_to_20_lots,
    rule_public_water_sewer_over_20_lots,
    rule_on_site_sewer_disclosure,
    rule_utility_easement,
    # Fire (same standards)
    rule_fire_hydrant_spacing,
    rule_fire_hydrant_distance_to_lot,
    rule_fire_marshal_acceptance,
    # Sidewalks (Wade overrides)
    rule_sidewalk_required,              # near school/park still applies
    rule_wade_sidewalk_all_streets,      # Wade: all new streets
    rule_wade_sidewalk_dimensions,       # Wade: 5 ft min
    # Recreation (Wade overrides by development type)
    rule_wade_recreation_area,           # standard subdivision
    rule_wade_group_dev_recreation,      # group development
    rule_wade_mhp_recreation,            # mobile home park
    # Mobile home park (Wade-only)
    rule_wade_mhp_lot_area,
    rule_wade_mhp_density,
    rule_wade_mhp_unit_separation,
    rule_wade_mhp_perimeter_buffer,
    rule_wade_mhp_pedestrian_paths,
    # Stormwater (same)
    rule_stormwater_permit,
    rule_retention_basin_fence,
    # Drainage (same)
    rule_drainage_easement,
    # Environmental (same â all in Cumberland County)
    rule_sfha_boundary,
    rule_sfha_disclosure,
    rule_riparian_buffer,
    rule_fort_liberty_notification,
    rule_farmland_disclosure,
    rule_airport_overlay_disclosure,
    rule_mia_applicability,
    # Final plat (Wade overrides)
    rule_final_plat_conforms_to_prelim,
    rule_final_plat_surveyor_cert,
    rule_final_plat_ownership_cert,
    rule_final_plat_director_cert,
    rule_wade_final_plat_recording_deadline,   # Wade: 30 days (not 12 months)
    rule_nonconforming_structure_disclosure,
    rule_proposed_public_street_disclosure,
    rule_final_plat_ccr_docs,
]


# ==============================================================
# Run Functions
# ==============================================================

def run_county_rules(data: SubmissionData) -> list:
    """Run all Cumberland County compliance rules."""
    return [rule(data) for rule in ALL_COUNTY_RULES]


def run_wade_rules(data: SubmissionData) -> list:
    """Run all Town of Wade compliance rules."""
    return [rule(data) for rule in ALL_WADE_RULES]


def run_all_rules(data: SubmissionData) -> list:
    """
    Dispatch to the correct rule set based on data.jurisdiction.
    Defaults to county rules if jurisdiction is unrecognised.
    """
    if data.jurisdiction == "wade":
        return run_wade_rules(data)
    return run_county_rules(data)


def run_rules_by_category(data: SubmissionData, prefix: str) -> list:
    """Run only rules whose rule_id starts with a given prefix (e.g. 'STR', 'WAD')."""
    all_rules = ALL_WADE_RULES if data.jurisdiction == "wade" else ALL_COUNTY_RULES
    results   = [rule(data) for rule in all_rules]
    return [r for r in results if r.rule_id.startswith(prefix)]


# ==============================================================
# Report Builder
# ==============================================================

def build_report(results: list) -> dict:
    """
    Summarize rule results into a structured compliance report.

    Returns:
        {
          "jurisdiction": "county" | "wade",
          "summary":  { "total", "pass", "fail", "warning", "not_applicable" },
          "overall_status": "PASS" | "FAIL" | "WARNING",
          "failures":      [...],
          "warnings":      [...],
          "passed":        [...],
          "not_applicable":[...],
        }
    """
    from .models import Status  # local import to avoid circular at module level

    failures = [r for r in results if r.status == Status.FAIL]
    warnings = [r for r in results if r.status == Status.WARNING]
    passed   = [r for r in results if r.status == Status.PASS]
    na       = [r for r in results if r.status == Status.NOT_APPLICABLE]

    if failures:
        overall = "FAIL"
    elif warnings:
        overall = "WARNING"
    else:
        overall = "PASS"

    def _fmt(r: RuleResult) -> dict:
        return {
            "rule_id":     r.rule_id,
            "rule_name":   r.rule_name,
            "section":     r.section,
            "status":      r.status.value,
            "detail":      r.detail,
            "fix":         r.fix,
            "value_found": r.value_found,
        }

    return {
        "summary": {
            "total":          len(results),
            "pass":           len(passed),
            "fail":           len(failures),
            "warning":        len(warnings),
            "not_applicable": len(na),
        },
        "overall_status": overall,
        "failures":        [_fmt(r) for r in failures],
        "warnings":        [_fmt(r) for r in warnings],
        "passed":          [_fmt(r) for r in passed],
        "not_applicable":  [_fmt(r) for r in na],
    }