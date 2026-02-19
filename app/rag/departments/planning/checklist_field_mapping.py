"""
checklist_field_mapping.py   -  Phase B: /fill-checklist PDF Field Maps
========================================================================
Maps compliance rule results and extracted SubmissionData fields to the
AcroForm field names in both fillable checklist PDFs.

PDF Field Structure
-------------------
Preliminary Plan (274 AcroForm fields):
  - Header text fields: "Applicant/Owner", "CASE#", "REIDs"
  - 90 checkbox triplets numbered sequentially:
      Item 1  -> Y,   N,   NA
      Item 2  -> Y_2, N_2, NA_2
      Item n  -> Y_n, N_n, NA_n
  - One body text field: "incorporated into the preliminary plan" (Section H note)

Final Plat (57 AcroForm fields):
  - Checkbox (Btn) fields with long descriptive names
  - Each paired with a text (Tx) companion field for notes/initials

Fill Logic
----------
For each checklist item:
  PASS    -> check the Y field (set to "Yes" or "/Yes")
  FAIL    -> check the N field
  WARNING -> check the N field and flag for human review
  N/A     -> check the NA field
  None    -> leave blank (no rule covers this item, human must complete)

Usage (Phase B)
---------------
from checklist_field_mapping import (
    PRELIM_ITEMS,
    FINAL_PLAT_ITEMS,
    fill_preliminary_plan,
    fill_final_plat,
)
"""

from __future__ import annotations
from typing import Optional


# =============================================================================
# Helper: generate field name tuple for Preliminary Plan sequential items
# =============================================================================

def _prelim_fields(n: int) -> dict[str, str]:
    """Return the Y/N/NA field names for Preliminary Plan item n (1-based)."""
    suffix = "" if n == 1 else f"_{n}"
    return {"y": f"Y{suffix}", "n": f"N{suffix}", "na": f"NA{suffix}"}


# =============================================================================
# PRELIMINARY PLAN  -- 90-item sequential mapping
#
# Each entry maps a logical checklist item to:
#   - field_triplet : AcroForm field names {"y", "n", "na"}
#   - rule_ids      : list of compliance rule_ids whose result drives this item
#                     (empty list = no automated rule; planner fills manually)
#   - section       : ordinance section reference (for reference)
#   - label         : short description matching the PDF checklist text
#   - extracted_key : if not None, also check this SubmissionData field for
#                     N/A determination (e.g. "has_riparian_watercourse")
# =============================================================================

PRELIM_ITEMS: list[dict] = [
    # -----------------------------------------------------------------------
    # A. Title Data
    # -----------------------------------------------------------------------
    {
        "item": 1, "section": "A.1",
        "label": "Subdivision or Development Name",
        "rule_ids": ["TTL-001"],
        "fields": _prelim_fields(1),
        "extracted_key": "subdivision_name",
    },
    {
        "item": 2, "section": "A.2",
        "label": "Names & Addresses of owner(s) or designer",
        "rule_ids": ["TTL-002"],
        "fields": _prelim_fields(2),
        "extracted_key": None,
    },
    {
        "item": 3, "section": "A.3",
        "label": "Scale & Date(s) map was prepared or revised",
        "rule_ids": ["TTL-003"],
        "fields": _prelim_fields(3),
        "extracted_key": "scale_feet_per_inch",
    },
    {
        "item": 4, "section": "A.4",
        "label": "True North Arrow",
        "rule_ids": ["MAP-001"],
        "fields": _prelim_fields(4),
        "extracted_key": None,
    },
    # -----------------------------------------------------------------------
    # B. Vicinity Sketch
    # -----------------------------------------------------------------------
    {
        "item": 5, "section": "B.1",
        "label": "Key map or vicinity sketch",
        "rule_ids": ["MAP-002"],
        "fields": _prelim_fields(5),
        "extracted_key": None,
    },
    # -----------------------------------------------------------------------
    # C. Existing Data (22 items)
    # -----------------------------------------------------------------------
    {
        "item": 6, "section": "C.1",
        "label": "Location of existing & platted property (township, county, state)",
        "rule_ids": ["MAP-003"],
        "fields": _prelim_fields(6),
        "extracted_key": None,
    },
    {
        "item": 7, "section": "C.2",
        "label": "Total acreage of proposed development",
        "rule_ids": ["MAP-004"],
        "fields": _prelim_fields(7),
        "extracted_key": "total_acreage",
    },
    {
        "item": 8,  "section": "C.3",  "label": "Dimension(s), location(s), and use of all existing building(s)",
        "rule_ids": [],   "fields": _prelim_fields(8),  "extracted_key": None,
    },
    {
        "item": 9,  "section": "C.4",  "label": "Culverts",
        "rule_ids": [],   "fields": _prelim_fields(9),  "extracted_key": None,
    },
    {
        "item": 10, "section": "C.5",  "label": "Bridges",
        "rule_ids": [],   "fields": _prelim_fields(10), "extracted_key": None,
    },
    {
        "item": 11, "section": "C.6",  "label": "Watercourses",
        "rule_ids": ["ENV-001"],       "fields": _prelim_fields(11), "extracted_key": "has_riparian_watercourse",
    },
    {
        "item": 12, "section": "C.7",  "label": "Railroad lines or right(s)-of-way",
        "rule_ids": [],   "fields": _prelim_fields(12), "extracted_key": None,
    },
    {
        "item": 13, "section": "C.8",  "label": "Political Boundary Lines",
        "rule_ids": [],   "fields": _prelim_fields(13), "extracted_key": None,
    },
    {
        "item": 14, "section": "C.9",  "label": "Zoning District Lines",
        "rule_ids": [],   "fields": _prelim_fields(14), "extracted_key": None,
    },
    {
        "item": 15, "section": "C.10", "label": "Any Overlay Districts (Airport, etc.)",
        "rule_ids": [],   "fields": _prelim_fields(15), "extracted_key": None,
    },
    {
        "item": 16, "section": "C.11", "label": "Proposed use of property",
        "rule_ids": [],   "fields": _prelim_fields(16), "extracted_key": None,
    },
    {
        "item": 17, "section": "C.12", "label": "Location of Easements & Name of Easement Holder",
        "rule_ids": [],   "fields": _prelim_fields(17), "extracted_key": None,
    },
    {
        "item": 18, "section": "C.13", "label": "Right(s)-of-way name & width",
        "rule_ids": ["STR-001"],       "fields": _prelim_fields(18), "extracted_key": None,
    },
    {
        "item": 19, "section": "C.14", "label": "Names of adjoining property owners or subdivisions",
        "rule_ids": [],   "fields": _prelim_fields(19), "extracted_key": None,
    },
    {
        "item": 20, "section": "C.15", "label": "Type of Preliminary Plan",
        "rule_ids": [],   "fields": _prelim_fields(20), "extracted_key": None,
    },
    {
        "item": 21, "section": "C.16", "label": "Acreage in a newly dedicated right-of-way",
        "rule_ids": [],   "fields": _prelim_fields(21), "extracted_key": None,
    },
    {
        "item": 22, "section": "C.17", "label": "Municipal Corporate limits",
        "rule_ids": [],   "fields": _prelim_fields(22), "extracted_key": None,
    },
    {
        "item": 23, "section": "C.18", "label": "County or other jurisdictional boundaries on the tract",
        "rule_ids": [],   "fields": _prelim_fields(23), "extracted_key": "has_jurisdictional_boundaries_shown",
    },
    {
        "item": 24, "section": "C.19", "label": "Existing property lines on the tract",
        "rule_ids": [],   "fields": _prelim_fields(24), "extracted_key": None,
    },
    {
        "item": 25, "section": "C.20", "label": "Address of existing structures",
        "rule_ids": [],   "fields": _prelim_fields(25), "extracted_key": None,
    },
    {
        "item": 26, "section": "C.21", "label": "Areas designated as common elements or open space (HOA)",
        "rule_ids": ["REC-001"],       "fields": _prelim_fields(26), "extracted_key": None,
    },
    {
        "item": 27, "section": "C.22", "label": "Areas to be dedicated or reserved for the public",
        "rule_ids": [],   "fields": _prelim_fields(27), "extracted_key": "has_public_dedication_areas_shown",
    },
    # -----------------------------------------------------------------------
    # D. Data Relating to Proposed Subdivision (16 items)
    # -----------------------------------------------------------------------
    {
        "item": 28, "section": "D.1",  "label": "Proposed Streets",
        "rule_ids": ["STR-002"],       "fields": _prelim_fields(28), "extracted_key": None,
    },
    {
        "item": 29, "section": "D.2",  "label": "Alleys",
        "rule_ids": [],   "fields": _prelim_fields(29), "extracted_key": None,
    },
    {
        "item": 30, "section": "D.3",  "label": "Crosswalks",
        "rule_ids": [],   "fields": _prelim_fields(30), "extracted_key": None,
    },
    {
        "item": 31, "section": "D.4",  "label": "Total number of proposed lots",
        "rule_ids": ["LOT-001"],       "fields": _prelim_fields(31), "extracted_key": "total_lots",
    },
    {
        "item": 32, "section": "D.5",  "label": "Proposed lot lines and dimensions including bearings",
        "rule_ids": ["LOT-002", "LOT-003"], "fields": _prelim_fields(32), "extracted_key": None,
    },
    {
        "item": 33, "section": "D.6",  "label": "Lots sequenced or numbered consecutively",
        "rule_ids": [],   "fields": _prelim_fields(33), "extracted_key": "lots_sequentially_numbered",
    },
    {
        "item": 34, "section": "D.7",  "label": "Location, dimension(s), and type of proposed common recreation facilities",
        "rule_ids": ["REC-001"],       "fields": _prelim_fields(34), "extracted_key": None,
    },
    {
        "item": 35, "section": "D.8",  "label": "Location, dimension(s), and type of existing & proposed easements",
        "rule_ids": [],   "fields": _prelim_fields(35), "extracted_key": None,
    },
    {
        "item": 36, "section": "D.9",  "label": "Building Setback lines (Sec. 1104)",
        "rule_ids": ["CDS-001"],       "fields": _prelim_fields(36), "extracted_key": None,
    },
    {
        "item": 37, "section": "D.10", "label": "Special Flood Hazard Areas",
        "rule_ids": ["FPL-001"],       "fields": _prelim_fields(37), "extracted_key": None,
    },
    {
        "item": 38, "section": "D.11", "label": "Square footage / acreage for all proposed lots",
        "rule_ids": ["LOT-002"],       "fields": _prelim_fields(38), "extracted_key": "lots_missing_acreage_label",
    },
    {
        "item": 39, "section": "D.12", "label": "Areas to be dedicated or reserved for the public",
        "rule_ids": [],   "fields": _prelim_fields(39), "extracted_key": None,
    },
    {
        "item": 40, "section": "D.13", "label": "Common elements or open space (HOA maintenance)",
        "rule_ids": [],   "fields": _prelim_fields(40), "extracted_key": None,
    },
    {
        "item": 41, "section": "D.14", "label": "Parks",
        "rule_ids": [],   "fields": _prelim_fields(41), "extracted_key": None,
    },
    {
        "item": 42, "section": "D.15", "label": "Playgrounds",
        "rule_ids": [],   "fields": _prelim_fields(42), "extracted_key": None,
    },
    {
        "item": 43, "section": "D.16", "label": "Other Open Spaces",
        "rule_ids": [],   "fields": _prelim_fields(43), "extracted_key": None,
    },
    # -----------------------------------------------------------------------
    # E. Data Relating to Surrounding Area
    # -----------------------------------------------------------------------
    {
        "item": 44, "section": "E.1",
        "label": "Overall development sketch showing prospective future street system",
        "rule_ids": [],   "fields": _prelim_fields(44), "extracted_key": None,
    },
    # -----------------------------------------------------------------------
    # F. Utility Plans
    # -----------------------------------------------------------------------
    {
        "item": 45, "section": "F.1",
        "label": "Statement as to type of intended water and sewer service",
        "rule_ids": ["UTL-001"],       "fields": _prelim_fields(45), "extracted_key": None,
    },
    # -----------------------------------------------------------------------
    # G. Street Cross Sections
    # -----------------------------------------------------------------------
    {
        "item": 46, "section": "G.1",
        "label": "Typical cross sections of proposed streets (Sec. 2304)",
        "rule_ids": ["STR-003"],       "fields": _prelim_fields(46), "extracted_key": None,
    },
    # -----------------------------------------------------------------------
    # H. Other Improvements
    # -----------------------------------------------------------------------
    {
        "item": 47, "section": "H.1",
        "label": "Other improvements at discretion of Director",
        "rule_ids": [],   "fields": _prelim_fields(47), "extracted_key": None,
    },
    # -----------------------------------------------------------------------
    # I. Environmental Data (9 items)
    # -----------------------------------------------------------------------
    {
        "item": 48, "section": "I.1",
        "label": "Wetlands, Watercourses, Ponds, Lakes, Streams, or Cemeteries",
        "rule_ids": ["ENV-001"],       "fields": _prelim_fields(48), "extracted_key": None,
    },
    {
        "item": 49, "section": "I.2",
        "label": "Riparian Buffer (Sec. 1102 S.H)",
        "rule_ids": ["ENV-002"],       "fields": _prelim_fields(49), "extracted_key": "has_riparian_watercourse",
    },
    {
        "item": 50, "section": "I.3",
        "label": "Floodway & 100-year floodplain delineation",
        "rule_ids": ["FPL-001", "FPL-002"], "fields": _prelim_fields(50), "extracted_key": None,
    },
    {
        "item": 51, "section": "I.4",
        "label": "Special Flood Hazard Area disclosure note",
        "rule_ids": ["FPL-003"],       "fields": _prelim_fields(51), "extracted_key": "sfha_disclosure_note_present",
    },
    {
        "item": 52, "section": "I.5",
        "label": "Existing & proposed topography (contour lines 1-2 ft intervals)",
        "rule_ids": [],   "fields": _prelim_fields(52), "extracted_key": None,
    },
    {
        "item": 53, "section": "I.6",
        "label": "Watershed designation with critical areas",
        "rule_ids": ["ENV-003"],       "fields": _prelim_fields(53), "extracted_key": None,
    },
    {
        "item": 54, "section": "I.7",
        "label": "Existing well & septic locations",
        "rule_ids": [],   "fields": _prelim_fields(54), "extracted_key": None,
    },
    {
        "item": 55, "section": "I.8",
        "label": "Marshes, swamps, other wetlands, including streams",
        "rule_ids": ["ENV-004"],       "fields": _prelim_fields(55), "extracted_key": None,
    },
    {
        "item": 56, "section": "I.9",
        "label": "Drainage easement (min 20 ft wide)  -- Sec. 2307",
        "rule_ids": ["DRN-001"],       "fields": _prelim_fields(56), "extracted_key": "drainage_easement_min_width_ft",
    },
    # -----------------------------------------------------------------------
    # J. Street Data (7 items)
    # -----------------------------------------------------------------------
    {
        "item": 57, "section": "J.1",
        "label": "ROW lines and dimensions (Sec. 2304)",
        "rule_ids": ["STR-001"],       "fields": _prelim_fields(57), "extracted_key": None,
    },
    {
        "item": 58, "section": "J.2",
        "label": "Cul-de-sac pavement radius and street length (Sec. 2304 S.A(10)(g))",
        "rule_ids": ["CDS-002", "CDS-003"], "fields": _prelim_fields(58), "extracted_key": "cul_de_sac_roadway_diameter_ft",
    },
    {
        "item": 59, "section": "J.3",
        "label": "Existing street names & state road numbers with functional classification",
        "rule_ids": ["STR-002"],       "fields": _prelim_fields(59), "extracted_key": "street_functional_class_labeled",
    },
    {
        "item": 60, "section": "J.4",
        "label": "Proposed street names",
        "rule_ids": [],   "fields": _prelim_fields(60), "extracted_key": None,
    },
    {
        "item": 61, "section": "J.5",
        "label": "Block length (Sec. 2304 S.A(10))",
        "rule_ids": [],   "fields": _prelim_fields(61), "extracted_key": None,
    },
    {
        "item": 62, "section": "J.6",
        "label": "Streets designed per criteria Sec. 2304 S.A(1-10)",
        "rule_ids": ["STR-003"],       "fields": _prelim_fields(62), "extracted_key": None,
    },
    {
        "item": 63, "section": "J.7",
        "label": "Direct access restriction from lots on classified streets (Sec. 2303 S.D)",
        "rule_ids": [],   "fields": _prelim_fields(63), "extracted_key": None,
    },
    # -----------------------------------------------------------------------
    # K. Street Names
    # -----------------------------------------------------------------------
    {
        "item": 64, "section": "K.1",
        "label": "Street names and block range labeled on plan",
        "rule_ids": [],   "fields": _prelim_fields(64), "extracted_key": None,
    },
    # -----------------------------------------------------------------------
    # L. Sidewalks
    # -----------------------------------------------------------------------
    {
        "item": 65, "section": "L.1",
        "label": "Sidewalks (Sec. 2305 S.A)  -- adjacent to school/park",
        "rule_ids": ["SWK-001", "SWK-002"], "fields": _prelim_fields(65), "extracted_key": None,
    },
    # -----------------------------------------------------------------------
    # M. Utilities (Sec. 2306)
    # -----------------------------------------------------------------------
    {
        "item": 66, "section": "M.A",
        "label": "Water & sewer  -- public system connection requirements",
        "rule_ids": ["UTL-002", "UTL-003"], "fields": _prelim_fields(66), "extracted_key": None,
    },
    {
        "item": 67, "section": "M.B",
        "label": "Water & sewer  -- installed per County Health Dept standards",
        "rule_ids": ["UTL-004"],       "fields": _prelim_fields(67), "extracted_key": None,
    },
    # -----------------------------------------------------------------------
    # N. On-Site Water & Sewer Systems
    # -----------------------------------------------------------------------
    {
        "item": 68, "section": "N.1",
        "label": "On-site sewer disclosure (Sec. 2306 S.A-(2), Sec. 2504)",
        "rule_ids": ["UTL-005"],       "fields": _prelim_fields(68), "extracted_key": "on_site_sewer_disclosure_present",
    },
    # -----------------------------------------------------------------------
    # O. Environmental Health Comments
    # -----------------------------------------------------------------------
    {
        "item": 69, "section": "O.1",
        "label": "EH: public utilities afforded  -- no comment required",
        "rule_ids": [],   "fields": _prelim_fields(69), "extracted_key": None,
    },
    {
        "item": 70, "section": "O.2",
        "label": "EH: public utilities NOT afforded  -- EH permit applications required",
        "rule_ids": [],   "fields": _prelim_fields(70), "extracted_key": None,
    },
    # -----------------------------------------------------------------------
    # P. Preliminary Soil Analysis
    # -----------------------------------------------------------------------
    {
        "item": 71, "section": "P.1",
        "label": "Certified soil analysis from certified soil scientist",
        "rule_ids": [],   "fields": _prelim_fields(71), "extracted_key": None,
    },
    # -----------------------------------------------------------------------
    # Q. Subdivision Signage
    # -----------------------------------------------------------------------
    {
        "item": 72, "section": "Q.1",
        "label": "Subdivision name & signage shown (Article 13)",
        "rule_ids": [],   "fields": _prelim_fields(72), "extracted_key": None,
    },
    # -----------------------------------------------------------------------
    # R. Fire Marshal & Fire Inspection (NC Fire Code)
    # -----------------------------------------------------------------------
    {
        "item": 73, "section": "R.1",
        "label": "Fire protection water supply requirements (Sec. 507, NC Fire Code)",
        "rule_ids": ["FIR-001", "FIR-002"], "fields": _prelim_fields(73), "extracted_key": None,
    },
    # -----------------------------------------------------------------------
    # S. Commercial & Industrial Uses
    # -----------------------------------------------------------------------
    {
        "item": 74, "section": "S.1",
        "label": "Commercial & industrial lot arrangements per minimum requirements",
        "rule_ids": [],   "fields": _prelim_fields(74), "extracted_key": None,
    },
    # -----------------------------------------------------------------------
    # T. Retention/Detention Basins (Ponds)
    # -----------------------------------------------------------------------
    {
        "item": 75, "section": "T.1",
        "label": "Retention/detention basins with 4-ft fence & lockable gate (Sec. 1102 S.O)",
        "rule_ids": ["ENV-005"],       "fields": _prelim_fields(75), "extracted_key": "retention_basin_fence_detail_note",
    },
    # -----------------------------------------------------------------------
    # U. Required Drainage
    # -----------------------------------------------------------------------
    {
        "item": 76, "section": "U.1",
        "label": "Drainage systems per NCDOT/NCDEQ BMP standards (Sec. 2307 S.A)",
        "rule_ids": ["DRN-001"],       "fields": _prelim_fields(76), "extracted_key": None,
    },
    # -----------------------------------------------------------------------
    # V. Stormwater
    # -----------------------------------------------------------------------
    {
        "item": 77, "section": "V.1",
        "label": "Post-Construction Stormwater Mgmt (Sec. 2306 S.D, NCDEQ)",
        "rule_ids": ["SWM-001"],       "fields": _prelim_fields(77), "extracted_key": None,
    },
    # -----------------------------------------------------------------------
    # W. Recreation Area
    # -----------------------------------------------------------------------
    {
        "item": 78, "section": "W.1",
        "label": "Recreation area labeled with calculation; HOA note on plan (Sec. 2308)",
        "rule_ids": ["REC-001"],       "fields": _prelim_fields(78), "extracted_key": "hoa_recreation_note_on_plan",
    },
    # -----------------------------------------------------------------------
    # X. Underground Utilities
    # -----------------------------------------------------------------------
    {
        "item": 79, "section": "X.1",
        "label": "Underground utilities note on plan (Sec. 2306 S.C)",
        "rule_ids": ["UTL-001"],       "fields": _prelim_fields(79), "extracted_key": "underground_utilities_note_on_plan",
    },
    # -----------------------------------------------------------------------
    # Y. Municipal Influence Area (MIA)
    # -----------------------------------------------------------------------
    {
        "item": 80, "section": "Y.1",
        "label": "MIA design standards (Sec. 2302 S.1, Exhibit #5)",
        "rule_ids": ["MIA-001"],       "fields": _prelim_fields(80), "extracted_key": None,
    },
    # -----------------------------------------------------------------------
    # Z. Other Improvements
    # -----------------------------------------------------------------------
    {
        "item": 81, "section": "Z.1",
        "label": "Other improvements at Director's discretion (Sec. S.H)",
        "rule_ids": [],   "fields": _prelim_fields(81), "extracted_key": None,
    },
    # -----------------------------------------------------------------------
    # AA. Required Disclosures
    # -----------------------------------------------------------------------
    {
        "item": 82, "section": "AA.A.1",
        "label": "Private street disclosure  -- All Private Streets (Sec. 2304)",
        "rule_ids": ["PVT-001"],       "fields": _prelim_fields(82), "extracted_key": None,
    },
    {
        "item": 83, "section": "AA.A.2",
        "label": "Private street disclosure  -- Class C maintenance",
        "rule_ids": ["PVT-002"],       "fields": _prelim_fields(83), "extracted_key": "class_c_disclosure_present",
    },
    {
        "item": 84, "section": "AA.A.3",
        "label": "Private street disclosure  -- Class B or C no-further-divide",
        "rule_ids": ["PVT-003"],       "fields": _prelim_fields(84), "extracted_key": "class_b_c_no_further_divide_disclosure",
    },
    {
        "item": 85, "section": "AA.B",
        "label": "Farmland Protection Area disclosure (Rural Area, Land Use Plan)",
        "rule_ids": [],   "fields": _prelim_fields(85), "extracted_key": None,
    },
    {
        "item": 86, "section": "AA.C",
        "label": "On-site water and/or sewer disclosure (Sec. 2504)",
        "rule_ids": [],   "fields": _prelim_fields(86), "extracted_key": "on_site_sewer_disclosure_present",
    },
    {
        "item": 87, "section": "AA.D",
        "label": "Nonconforming structure disclosure",
        "rule_ids": [],   "fields": _prelim_fields(87), "extracted_key": "nonconforming_structure_disclosure",
    },
    {
        "item": 88, "section": "AA.E",
        "label": "Proposed public street disclosure (streets not yet NCDOT accepted)",
        "rule_ids": ["PPL-001"],       "fields": _prelim_fields(88), "extracted_key": None,
    },
    {
        "item": 89, "section": "AA.F.a",
        "label": "Airport Overlay District disclosure (Sec. 8.101.E)",
        "rule_ids": [],   "fields": _prelim_fields(89), "extracted_key": None,
    },
    {
        "item": 90, "section": "AA.F.b",
        "label": "Special Flood Hazard Area disclosure",
        "rule_ids": ["FPL-004"],       "fields": _prelim_fields(90), "extracted_key": "sfha_disclosure_note_present",
    },
]


# =============================================================================
# FINAL PLAT  -- Direct field name mapping
# Each item maps a checkbox field name to the rule_ids that drive it.
# =============================================================================

FINAL_PLAT_ITEMS: list[dict] = [
    {
        "label": "Application Form completed and signed",
        "checkbox_field": "1 Application Form completed and signed and uploaded into the case folder or emailed",
        "text_field":     "1 Application Form completed and signed and uploaded into the case folder or emailed to Intake planner",
        "rule_ids": [],
    },
    {
        "label": "Application fee ($100 Final Plat Fee)",
        "checkbox_field": "Application fee per fee Schedule 100 Final Plat Fee",
        "text_field":     "Application fee per fee Schedule 100 Final Plat Fee_2",
        "rule_ids": [],
    },
    {
        "label": "Copy of HOA by-laws and restrictive covenants",
        "checkbox_field": "Copy of homeowners association bylaws and restrictive covenants to be recorded or",
        "text_field":     "Copy of homeowners association bylaws and restrictive covenants to be recorded or incorporation documents for phased developments",
        "rule_ids": [],
    },
    {
        "label": "Separate transmittal letter to county attorney",
        "checkbox_field": "Separate transmittal letter to the county attorney referencing the applicable information",
        "text_field":     None,
        "rule_ids": [],
    },
    {
        "label": "Sec. 2304 A.10.h  -- Alley owner association documents",
        "checkbox_field": "A10h Alleys shall be approved and maintained the same as common areas within a",
        "text_field":     None,
        "rule_ids": [],
    },
    {
        "label": "Sec. 2304 C.4.a  -- Class A private street maintenance agreement",
        "checkbox_field": "C4 a Class A private street specification",
        "text_field":     None,
        "rule_ids": ["PVT-004"],
    },
    {
        "label": "Sec. 2304 C.4.b  -- Class B private street maintenance agreement",
        "checkbox_field": "C4b Class B private street specifications",
        "text_field":     None,
        "rule_ids": ["PVT-005"],
    },
    {
        "label": "Sec. 2308 C.4  -- Owner association conditions (recreation areas)",
        "checkbox_field": "C4 required conditions of owner associations Owners association or comparable legal",
        "text_field":     None,
        "rule_ids": ["REC-001"],
    },
    {
        "label": "Sec. 2402 F  -- Common areas deeded to HOA",
        "checkbox_field": "F Common Areas All areas of the site plan other than individual for sale lotsunits and",
        "text_field":     None,
        "rule_ids": [],
    },
    {
        "label": "Sec. 2402 G  -- Declaration of covenants and restrictions",
        "checkbox_field": "G Declaration of covenants and restrictions The developer shall file prior to submission for",
        "text_field":     None,
        "rule_ids": [],
    },
    {
        "label": "Line-item cost estimate of improvements (bonded, Sec. 2502B)",
        "checkbox_field": "Lineitem cost estimate of improvements intended to be bonded sealed by a professional",
        "text_field":     "Lineitem cost estimate of improvements intended to be bonded sealed by a professional engineer in accordance with Section 2502B",
        "rule_ids": [],
    },
    {
        "label": "Built to Standards Letter from NCDOT",
        "checkbox_field": "Built to Standards Letter from NCDOT for developments dedicating public streets",
        "text_field":     "Built to Standards Letter from NCDOT for developments dedicating public streets_2",
        "rule_ids": [],
    },
    {
        "label": "Transmittal letter from surveyor/engineer with approved Preliminary Plan",
        "checkbox_field": "Transmittal letter prepared by the surveyor or engineer with attached approved Preliminary",
        "text_field":     "Transmittal letter prepared by the surveyor or engineer with attached approved Preliminary Plan and condition sheet identifying status of conditions and satisfying applicable requirements whether noted on the Final Plat or shown",
        "rule_ids": [],
    },
    {
        "label": "Misc. payment (Recreation area fee-in-lieu)",
        "checkbox_field": "Mis Payment if applicable Recreation area feeinin lieu",
        "text_field":     "Mis Payment if applicable Recreation area feeinin lieu_2",
        "rule_ids": [],
    },
    {
        "label": "Final Plat including all required elements",
        "checkbox_field": "Final Plat including elements on the attached checklist filled out by surveyor or engineer",
        "text_field":     "Final Plat including elements on the attached checklist filled out by surveyor or engineer of record",
        "rule_ids": [],
    },
    # Certificates
    {
        "label": "A. General  -- conforms to approved Preliminary Plan and GS 47-30",
        "checkbox_field": "Yes_5",
        "text_field":     None,
        "rule_ids": [],
        "note": "Yes/No pair  -- Yes_5 / No A General..."
    },
    {
        "label": "B. Map form  -- scale and size requirements",
        "checkbox_field": "Yes_6",
        "text_field":     None,
        "rule_ids": ["MAP-005"],
    },
    {
        "label": "C. Surveyor's certificate",
        "checkbox_field": "C Surveyors certificate There shall appear on each final plat a certificate by the person under whose supervision the",
        "text_field":     "certify that this plat was drawn under my",
        "rule_ids": [],
    },
    {
        "label": "D. Certificate of ownership and dedication",
        "checkbox_field": "D Certificate of ownership and dedication The following notarized owner certificate shall appear on the final plat along",
        "text_field":     None,
        "rule_ids": [],
    },
    {
        "label": "E. Director's certificate of approval",
        "checkbox_field": "E Directors certificate of approval The following certificate shall appear on the final plat with the signature of the",
        "text_field":     None,
        "rule_ids": [],
    },
    {
        "label": "F. Plat Review Officer certification",
        "checkbox_field": "F Plat Review Officer certification The Plat Review Officer shall certify the final plat if it complies with all statutory",
        "text_field":     "OF CUMBERLAND I",
        "rule_ids": [],
    },
    # Section 2504 Disclosures
    {
        "label": "2504.A  -- Disclosure of private street status (All Private Streets)",
        "checkbox_field": "1 All Private Streets Cumberland County and other public agencies have no enforcement responsibility regarding",
        "text_field":     None,
        "rule_ids": ["PVT-001"],
    },
    {
        "label": "2504.A.2  -- Class C private street maintenance disclosure",
        "checkbox_field": "2 Class C private streets All current and future owners of the tracts served by and having access to the Class C",
        "text_field":     None,
        "rule_ids": ["PVT-002"],
    },
    {
        "label": "2504.B  -- Farmland Protection Area disclosure",
        "checkbox_field": "B Farmland Protection Area disclosure All final plats for subdivision or other development located within a designated",
        "text_field":     None,
        "rule_ids": [],
    },
    {
        "label": "2504.C  -- On-site water and/or sewer disclosure",
        "checkbox_field": "C Onsite water andor sewer disclosure The following statement shall be on any final plat for property not served by",
        "text_field":     None,
        "rule_ids": ["UTL-005"],
    },
    {
        "label": "2504.D  -- Nonconforming structure disclosure",
        "checkbox_field": "D Nonconforming structure disclosure All structures existing on the subject property at the time of the recording shall be",
        "text_field":     None,
        "rule_ids": [],
    },
    {
        "label": "2504.E  -- Proposed public street disclosure (NCDOT not yet accepted)",
        "checkbox_field": "E Proposed public street disclosure When the streets proposed within a subdivision or development do not qualify for",
        "text_field":     None,
        "rule_ids": ["PPL-001"],
    },
    {
        "label": "Stormwater facility internal access for HOA",
        "checkbox_field": "The subdivision plan must provide an internal access of any of the stormwater facility serving the site to allow the HOA",
        "text_field":     None,
        "rule_ids": ["SWM-002"],
    },
    {
        "label": "On-site sewer deed disclosure for lots without public sewer",
        "checkbox_field": "Applicant is not connecting to sewer or sewer The ownerdeveloper must be aware that every deed created for a lot",
        "text_field":     None,
        "rule_ids": ["UTL-005"],
    },
    {
        "label": "Sec. 2306 water/sewer installation certification",
        "checkbox_field": "Pursuant to SECTION 2306 UTILITIES A Water and sewer Where water andor sewer systems are to be installed as part",
        "text_field":     None,
        "rule_ids": ["UTL-002"],
    },
    {
        "label": "Fire hydrant satisfaction certification (Sec. 2306 S.B)",
        "checkbox_field": "Your certification should include that the subsection B Fire hydrants have been satisfied for this project Fire hydrants are",
        "text_field":     None,
        "rule_ids": ["FIR-003"],
    },
]


# =============================================================================
# Header field mapping (same for both PDFs)
# =============================================================================

PRELIM_HEADER_FIELDS = {
    "Applicant/Owner": "owner_name",    # -> extracted_fields["owner_name"] or SubmissionData
    "CASE#":           "case_number",   # -> extracted_fields["case_number"]
    "REIDs":           "reid_numbers",  # -> extracted_fields["reid_numbers"]
}