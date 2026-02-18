"""
models.py - Planning Department Data Models
===========================================
Pydantic models and data structures for Cumberland County and Town of Wade
subdivision compliance checking.

Jurisdictions:
  "county" -> Unincorporated Cumberland County (Cumberland County Subdivision Ordinance)
  "wade"   -> Town of Wade planning jurisdiction (Wade Subdivision Ordinance)

Contains:
  - Status:            PASS / FAIL / WARNING / N/A enum
  - Jurisdiction:      "county" | "wade" enum
  - DevelopmentType:   subdivision / group_development / mobile_home_park / condominium
  - RuleResult:        Single rule evaluation result dataclass
  - SubmissionData:    All extractable fields from a developer submission
  - ComplianceRequest: Pydantic API request model (mirrors SubmissionData)
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field


# =============================================================
# Enums
# =============================================================

class Status(str, Enum):
    """Rule evaluation status."""
    PASS = "PASS"
    FAIL = "FAIL"
    WARNING = "WARNING"
    NOT_APPLICABLE = "N/A"


class Jurisdiction(str, Enum):
    """Identifies which ordinance governs the submission."""
    COUNTY = "county"   # Unincorporated Cumberland County
    WADE   = "wade"     # Town of Wade planning jurisdiction


class DevelopmentType(str, Enum):
    """Type of development being reviewed."""
    SUBDIVISION      = "subdivision"
    GROUP_DEVELOPMENT = "group_development"
    MOBILE_HOME_PARK = "mobile_home_park"
    CONDOMINIUM      = "condominium"


# =============================================================
# Rule Result
# =============================================================

@dataclass
class RuleResult:
    """Result of evaluating a single compliance rule."""
    rule_id:     str
    status:      Status
    rule_name:   str
    section:     str
    detail:      str
    fix:         str    = ""
    value_found: object = None


# =============================================================
# Submission Data
# =============================================================

@dataclass
class SubmissionData:
    """
    All fields that can be extracted from a developer submission
    (plat PDF, plan image, or filled checklist).

    None = field was not found / not determinable from the submission.
         -> Rules will return WARNING (manual verification required).
    """

    # ----------------------------------------------------------
    # Jurisdiction & submission classification
    # ----------------------------------------------------------
    jurisdiction:     str = "county"       # Jurisdiction enum value
    submission_type:  str = ""             # "preliminary_plan" | "final_plat"
    development_type: str = "subdivision"  # DevelopmentType enum value

    # ----------------------------------------------------------
    # Title / general data   (Sec 2203 / Wade Sec 5.1)
    # ----------------------------------------------------------
    subdivision_name:    Optional[str]   = None
    owner_name:          Optional[str]   = None
    designer_name:       Optional[str]   = None
    scale_feet_per_inch: Optional[float] = None
    has_date:            Optional[bool]  = None
    has_north_arrow:     Optional[bool]  = None
    sheet_width_inches:  Optional[float] = None
    sheet_height_inches: Optional[float] = None

    # ----------------------------------------------------------
    # Vicinity & existing data
    # ----------------------------------------------------------
    has_vicinity_sketch:               Optional[bool]  = None
    total_acreage:                     Optional[float] = None
    has_zoning_district_lines:         Optional[bool]  = None
    has_existing_easements:            Optional[bool]  = None
    has_adjoining_owner_names:         Optional[bool]  = None
    has_row_width_labeled:             Optional[bool]  = None
    # --- New from checklist ---
    has_overlay_districts_shown:       Optional[bool]  = None  # Airport, etc.
    has_municipal_limits_shown:        Optional[bool]  = None
    has_jurisdictional_boundaries_shown: Optional[bool] = None
    has_existing_structure_addresses:  Optional[bool]  = None
    has_common_elements_shown:         Optional[bool]  = None  # HOA/common areas
    has_public_dedication_areas_shown: Optional[bool]  = None
    has_proposed_use_stated:           Optional[bool]  = None
    has_railroad_row_shown:            Optional[bool]  = None
    has_watershed_designation_shown:   Optional[bool]  = None
    has_existing_wells_septic_shown:   Optional[bool]  = None
    acreage_new_row_shown:             Optional[bool]  = None

    # ----------------------------------------------------------
    # Lot data   (Sec 2303 / Wade Sec 3.20)
    # ----------------------------------------------------------
    total_proposed_lots:        Optional[int]   = None
    min_lot_frontage_ft:        Optional[float] = None
    lots_under_one_acre:        Optional[int]   = None
    lots_missing_sqft_label:    Optional[int]   = None
    lots_missing_acreage_label: Optional[int]   = None
    lots_sequentially_numbered: Optional[bool]  = None

    # ----------------------------------------------------------
    # Special Flood Hazard Area   (Sec 2303.G / Wade Sec 3.16)
    # ----------------------------------------------------------
    has_sfha_on_site:             Optional[bool] = None
    sfha_boundary_shown:          Optional[bool] = None
    sfha_disclosure_note_present: Optional[bool] = None

    # ----------------------------------------------------------
    # Riparian buffer   (Zoning Sec 1102.H)
    # ----------------------------------------------------------
    has_riparian_watercourse: Optional[bool]  = None
    riparian_buffer_shown:    Optional[bool]  = None
    riparian_buffer_width_ft: Optional[float] = None

    # ----------------------------------------------------------
    # Drainage easement   (Sec 2303.E.2 / Wade Sec 3.11)
    # ----------------------------------------------------------
    has_watercourse_on_site:          Optional[bool]  = None
    drainage_easement_shown:          Optional[bool]  = None
    drainage_easement_min_width_ft:   Optional[float] = None

    # ----------------------------------------------------------
    # Utility easements   (Sec 2303.E.1 / Wade Sec 3.11)
    # ----------------------------------------------------------
    utility_easement_width_ft: Optional[float] = None

    # ----------------------------------------------------------
    # Streets   (Sec 2304 / Wade Sec 3.17)
    # ----------------------------------------------------------
    max_block_length_ft:            Optional[float] = None
    has_street_names:               Optional[bool]  = None
    has_street_cross_sections:      Optional[bool]  = None
    street_corner_radius_ft:        Optional[float] = None
    street_offset_ft:               Optional[float] = None
    # --- New ---
    street_functional_class_labeled: Optional[bool]  = None
    street_row_ft:                   Optional[float] = None   # Measured ROW width
    street_divided_median:           Optional[bool]  = None   # Has divided median?
    street_base_depth_in:            Optional[float] = None   # Wade: 4" ABC stone min
    street_surface_depth_in:         Optional[float] = None   # Wade: 2" I-2 asphalt min
    curb_gutter_shown:               Optional[bool]  = None   # Wade: required in town limits

    # ----------------------------------------------------------
    # Cul-de-sac / hammerhead   (Sec 2304.A.10.g / Wade Sec 3.17.c)
    # ----------------------------------------------------------
    has_cul_de_sac:                Optional[bool]  = None
    cul_de_sac_length_ft:          Optional[float] = None
    cul_de_sac_roadway_diameter_ft: Optional[float] = None
    cul_de_sac_row_diameter_ft:    Optional[float] = None
    has_hammerhead:                Optional[bool]  = None
    hammerhead_outside_length_ft:  Optional[float] = None
    hammerhead_outside_width_ft:   Optional[float] = None
    hammerhead_roadway_length_ft:  Optional[float] = None
    hammerhead_roadway_width_ft:   Optional[float] = None

    # ----------------------------------------------------------
    # Private streets   (Sec 2304.C / Wade Sec 4.2)
    # ----------------------------------------------------------
    has_private_streets:                     Optional[bool]  = None
    private_street_class:                    Optional[str]   = None
    private_street_row_ft:                   Optional[float] = None
    class_b_lots_served:                     Optional[int]   = None
    class_c_lots_served:                     Optional[int]   = None
    class_b_c_connect_to_paved:              Optional[bool]  = None
    private_street_disclosure_present:       Optional[bool]  = None
    class_c_disclosure_present:              Optional[bool]  = None
    class_b_c_no_further_divide_disclosure:  Optional[bool]  = None
    private_street_owners_assoc:             Optional[bool]  = None
    engineer_cert_private_street:            Optional[bool]  = None  # Wade Sec 4.2.d

    # ----------------------------------------------------------
    # Public water & sewer   (Sec 2306.A / Wade Sec 3.14, 4.3.d)
    # ----------------------------------------------------------
    proposed_lots_or_units:          Optional[int]   = None
    water_sewer_type:                Optional[str]   = None   # "public" | "on_site" | "community"
    public_water_within_300ft:       Optional[bool]  = None
    public_sewer_within_300ft:       Optional[bool]  = None
    public_water_within_500ft:       Optional[bool]  = None
    public_sewer_within_500ft:       Optional[bool]  = None
    public_water_within_2000ft:      Optional[bool]  = None   # Wade Table I tap-on threshold
    public_sewer_within_2000ft:      Optional[bool]  = None   # Wade Table I tap-on threshold
    in_sewer_service_area:           Optional[bool]  = None
    density_units_per_acre:          Optional[float] = None
    on_site_sewer_disclosure_present: Optional[bool] = None
    utility_statement_on_plan:       Optional[bool]  = None
    # --- New from checklist ---
    underground_utilities_note_on_plan: Optional[bool] = None  # Sec 2306.C
    soil_scientist_cert_provided:       Optional[bool] = None  # Required when on-site sewer
    # --- Wade location fields ---
    within_town_limits: Optional[bool] = None   # Inside Wade town limits
    within_usa:         Optional[bool] = None   # Within Urban Services Area

    # ----------------------------------------------------------
    # Fire hydrants   (Sec 2306.B / Wade Sec 4.3.f)
    # ----------------------------------------------------------
    fire_hydrant_max_spacing_ft:   Optional[float] = None
    fire_hydrant_max_from_lot_ft:  Optional[float] = None
    fire_marshal_acceptance_letter: Optional[bool] = None   # Required before final plat

    # ----------------------------------------------------------
    # Sidewalks   (Sec 2305 / Wade Sec 4.1.h)
    # ----------------------------------------------------------
    adjacent_to_school_or_park:          Optional[bool]  = None
    sidewalk_shown:                      Optional[bool]  = None
    sidewalk_width_inches:               Optional[float] = None
    sidewalk_pedestrian_thickness_in:    Optional[float] = None
    sidewalk_vehicular_thickness_in:     Optional[float] = None
    sidewalk_all_new_streets_shown:      Optional[bool]  = None  # Wade: required on all new streets

    # ----------------------------------------------------------
    # Recreation area
    # County: Sec 2308 (800 sq ft/unit)
    # Wade standard subdivision: Sec 3.13.1 (500/1000/2000 by floodplain status)
    # Wade group development: Sec 3.21.k (500 sq ft/unit; 10,000 sq ft if >10 units)
    # Wade mobile home park: Sec 3.23.d.5 (500 sq ft/unit; 5,000/10,000 min)
    # ----------------------------------------------------------
    recreation_area_sqft:             Optional[float] = None
    dwelling_units:                   Optional[int]   = None
    hoa_recreation_note_on_plan:      Optional[bool]  = None
    # Wade floodplain tiers
    lots_above_floodplain:            Optional[int]   = None
    lots_in_floodplain:               Optional[int]   = None
    lots_on_water_body:               Optional[int]   = None
    # Group development (Wade Sec 3.21.k)
    group_dev_units:                  Optional[int]   = None
    group_dev_recreation_sqft:        Optional[float] = None
    # Mobile home park (Wade Sec 3.23.d.5)
    mhp_units:                        Optional[int]   = None
    mhp_recreation_area_sqft:         Optional[float] = None

    # ----------------------------------------------------------
    # Mobile home park specifics   (Wade Sec 3.23)
    # ----------------------------------------------------------
    mhp_min_lot_area_acres:                Optional[float] = None
    mhp_density_per_acre:                  Optional[float] = None
    mhp_unit_separation_longitudinal_ft:   Optional[float] = None
    mhp_unit_separation_end_ft:            Optional[float] = None
    mhp_perimeter_buffer_ft:               Optional[float] = None
    mhp_pedestrian_path_width_ft:          Optional[float] = None

    # ----------------------------------------------------------
    # Stormwater   (Sec 2306.D / Wade Table I)
    # ----------------------------------------------------------
    disturbed_area_acres:          Optional[float] = None
    stormwater_permit_addressed:   Optional[bool]  = None
    retention_basin_present:       Optional[bool]  = None
    retention_basin_fence_shown:   Optional[bool]  = None
    retention_basin_fence_detail_note: Optional[bool] = None  # Note on plan required
    stormwater_hoa_access_shown:   Optional[bool]  = None     # Internal HOA access to facility

    # ----------------------------------------------------------
    # Environmental / special overlays
    # ----------------------------------------------------------
    wetlands_shown_if_present:              Optional[bool] = None
    topographic_contours_shown:             Optional[bool] = None
    in_fort_liberty_special_interest_area:  Optional[bool] = None
    in_voluntary_agricultural_district:     Optional[bool] = None
    farmland_disclosure_present:            Optional[bool] = None
    in_airport_overlay_district:            Optional[bool] = None
    airport_disclosure_present:             Optional[bool] = None
    in_mia:                                 Optional[bool] = None
    mia_lots:                               Optional[int]  = None
    has_subdivision_sign_shown:             Optional[bool] = None

    # ----------------------------------------------------------
    # Final plat certificates & disclosures
    # (Sec 2503-2504 / Wade Sec 5.2)
    # ----------------------------------------------------------
    conforms_to_approved_prelim:          Optional[bool]  = None
    conditional_zoning_conformance:       Optional[bool]  = None  # BOC site plan conformance
    ccr_hoa_docs_provided:                Optional[bool]  = None  # For County Attorney review
    surveyor_certificate_present:         Optional[bool]  = None
    ownership_dedication_cert_present:    Optional[bool]  = None
    director_cert_present:                Optional[bool]  = None
    plat_review_officer_cert_present:     Optional[bool]  = None  # Sec 2503.F
    register_of_deeds_space_present:      Optional[bool]  = None
    nonconforming_structure_disclosure:   Optional[bool]  = None
    proposed_public_street_disclosure:    Optional[bool]  = None
    final_plat_mylar_material:            Optional[bool]  = None  # Mylar/archival film required
    months_since_prelim_approval:         Optional[float] = None


# =============================================================
# Pydantic API Request Model
# =============================================================

class ComplianceRequest(BaseModel):
    """
    API request body. Mirrors SubmissionData.
    Fields extracted from the submitted plat PDF / plan image / checklist.
    """

    # Jurisdiction & classification
    jurisdiction: str = Field(
        default="county",
        description="'county' (Cumberland County) or 'wade' (Town of Wade)",
        examples=["county", "wade"],
    )
    submission_type: str = Field(
        ...,
        description="'preliminary_plan' or 'final_plat'",
        examples=["preliminary_plan"],
    )
    development_type: str = Field(
        default="subdivision",
        description="'subdivision' | 'group_development' | 'mobile_home_park' | 'condominium'",
        examples=["subdivision"],
    )

    # Title / general
    subdivision_name:    Optional[str]   = None
    owner_name:          Optional[str]   = None
    designer_name:       Optional[str]   = None
    scale_feet_per_inch: Optional[float] = None
    has_date:            Optional[bool]  = None
    has_north_arrow:     Optional[bool]  = None
    sheet_width_inches:  Optional[float] = None
    sheet_height_inches: Optional[float] = None

    # Vicinity & existing
    has_vicinity_sketch:                 Optional[bool]  = None
    total_acreage:                       Optional[float] = None
    has_zoning_district_lines:           Optional[bool]  = None
    has_existing_easements:              Optional[bool]  = None
    has_adjoining_owner_names:           Optional[bool]  = None
    has_row_width_labeled:               Optional[bool]  = None
    has_overlay_districts_shown:         Optional[bool]  = None
    has_municipal_limits_shown:          Optional[bool]  = None
    has_jurisdictional_boundaries_shown: Optional[bool]  = None
    has_existing_structure_addresses:    Optional[bool]  = None
    has_common_elements_shown:           Optional[bool]  = None
    has_public_dedication_areas_shown:   Optional[bool]  = None
    has_proposed_use_stated:             Optional[bool]  = None
    has_railroad_row_shown:              Optional[bool]  = None
    has_watershed_designation_shown:     Optional[bool]  = None
    has_existing_wells_septic_shown:     Optional[bool]  = None
    acreage_new_row_shown:               Optional[bool]  = None

    # Lots
    total_proposed_lots:        Optional[int]   = None
    proposed_lots_or_units:     Optional[int]   = None
    min_lot_frontage_ft:        Optional[float] = None
    lots_under_one_acre:        Optional[int]   = None
    lots_missing_sqft_label:    Optional[int]   = None
    lots_missing_acreage_label: Optional[int]   = None
    lots_sequentially_numbered: Optional[bool]  = None

    # SFHA
    has_sfha_on_site:             Optional[bool] = None
    sfha_boundary_shown:          Optional[bool] = None
    sfha_disclosure_note_present: Optional[bool] = None

    # Riparian
    has_riparian_watercourse: Optional[bool]  = None
    riparian_buffer_shown:    Optional[bool]  = None
    riparian_buffer_width_ft: Optional[float] = None

    # Drainage
    has_watercourse_on_site:        Optional[bool]  = None
    drainage_easement_shown:        Optional[bool]  = None
    drainage_easement_min_width_ft: Optional[float] = None

    # Utility easement
    utility_easement_width_ft: Optional[float] = None

    # Streets
    max_block_length_ft:             Optional[float] = None
    has_street_names:                Optional[bool]  = None
    has_street_cross_sections:       Optional[bool]  = None
    street_corner_radius_ft:         Optional[float] = None
    street_offset_ft:                Optional[float] = None
    street_functional_class_labeled: Optional[bool]  = None
    street_row_ft:                   Optional[float] = None
    street_divided_median:           Optional[bool]  = None
    street_base_depth_in:            Optional[float] = None
    street_surface_depth_in:         Optional[float] = None
    curb_gutter_shown:               Optional[bool]  = None

    # Cul-de-sac / hammerhead
    has_cul_de_sac:                 Optional[bool]  = None
    cul_de_sac_length_ft:           Optional[float] = None
    cul_de_sac_roadway_diameter_ft: Optional[float] = None
    cul_de_sac_row_diameter_ft:     Optional[float] = None
    has_hammerhead:                 Optional[bool]  = None
    hammerhead_outside_length_ft:   Optional[float] = None
    hammerhead_outside_width_ft:    Optional[float] = None
    hammerhead_roadway_length_ft:   Optional[float] = None
    hammerhead_roadway_width_ft:    Optional[float] = None

    # Private streets
    has_private_streets:                    Optional[bool]  = None
    private_street_class:                   Optional[str]   = None
    private_street_row_ft:                  Optional[float] = None
    class_b_lots_served:                    Optional[int]   = None
    class_c_lots_served:                    Optional[int]   = None
    class_b_c_connect_to_paved:             Optional[bool]  = None
    private_street_disclosure_present:      Optional[bool]  = None
    class_c_disclosure_present:             Optional[bool]  = None
    class_b_c_no_further_divide_disclosure: Optional[bool]  = None
    private_street_owners_assoc:            Optional[bool]  = None
    engineer_cert_private_street:           Optional[bool]  = None

    # Water & sewer
    water_sewer_type:                Optional[str]   = None
    public_water_within_300ft:       Optional[bool]  = None
    public_sewer_within_300ft:       Optional[bool]  = None
    public_water_within_500ft:       Optional[bool]  = None
    public_sewer_within_500ft:       Optional[bool]  = None
    public_water_within_2000ft:      Optional[bool]  = None
    public_sewer_within_2000ft:      Optional[bool]  = None
    in_sewer_service_area:           Optional[bool]  = None
    density_units_per_acre:          Optional[float] = None
    on_site_sewer_disclosure_present: Optional[bool] = None
    utility_statement_on_plan:       Optional[bool]  = None
    underground_utilities_note_on_plan: Optional[bool] = None
    soil_scientist_cert_provided:    Optional[bool]  = None
    within_town_limits:              Optional[bool]  = None
    within_usa:                      Optional[bool]  = None

    # Fire
    fire_hydrant_max_spacing_ft:    Optional[float] = None
    fire_hydrant_max_from_lot_ft:   Optional[float] = None
    fire_marshal_acceptance_letter: Optional[bool]  = None

    # Sidewalks
    adjacent_to_school_or_park:       Optional[bool]  = None
    sidewalk_shown:                   Optional[bool]  = None
    sidewalk_width_inches:            Optional[float] = None
    sidewalk_pedestrian_thickness_in: Optional[float] = None
    sidewalk_vehicular_thickness_in:  Optional[float] = None
    sidewalk_all_new_streets_shown:   Optional[bool]  = None

    # Recreation
    recreation_area_sqft:      Optional[float] = None
    dwelling_units:            Optional[int]   = None
    hoa_recreation_note_on_plan: Optional[bool] = None
    lots_above_floodplain:     Optional[int]   = None
    lots_in_floodplain:        Optional[int]   = None
    lots_on_water_body:        Optional[int]   = None
    group_dev_units:           Optional[int]   = None
    group_dev_recreation_sqft: Optional[float] = None
    mhp_units:                 Optional[int]   = None
    mhp_recreation_area_sqft:  Optional[float] = None

    # Mobile home park
    mhp_min_lot_area_acres:              Optional[float] = None
    mhp_density_per_acre:                Optional[float] = None
    mhp_unit_separation_longitudinal_ft: Optional[float] = None
    mhp_unit_separation_end_ft:          Optional[float] = None
    mhp_perimeter_buffer_ft:             Optional[float] = None
    mhp_pedestrian_path_width_ft:        Optional[float] = None

    # Stormwater
    disturbed_area_acres:              Optional[float] = None
    stormwater_permit_addressed:       Optional[bool]  = None
    retention_basin_present:           Optional[bool]  = None
    retention_basin_fence_shown:       Optional[bool]  = None
    retention_basin_fence_detail_note: Optional[bool]  = None
    stormwater_hoa_access_shown:       Optional[bool]  = None

    # Environmental
    wetlands_shown_if_present:             Optional[bool] = None
    topographic_contours_shown:            Optional[bool] = None
    in_fort_liberty_special_interest_area: Optional[bool] = None
    in_voluntary_agricultural_district:    Optional[bool] = None
    farmland_disclosure_present:           Optional[bool] = None
    in_airport_overlay_district:           Optional[bool] = None
    airport_disclosure_present:            Optional[bool] = None
    in_mia:                                Optional[bool] = None
    mia_lots:                              Optional[int]  = None
    has_subdivision_sign_shown:            Optional[bool] = None

    # Final plat
    conforms_to_approved_prelim:        Optional[bool]  = None
    conditional_zoning_conformance:     Optional[bool]  = None
    ccr_hoa_docs_provided:              Optional[bool]  = None
    surveyor_certificate_present:       Optional[bool]  = None
    ownership_dedication_cert_present:  Optional[bool]  = None
    director_cert_present:              Optional[bool]  = None
    plat_review_officer_cert_present:   Optional[bool]  = None
    register_of_deeds_space_present:    Optional[bool]  = None
    nonconforming_structure_disclosure: Optional[bool]  = None
    proposed_public_street_disclosure:  Optional[bool]  = None
    final_plat_mylar_material:          Optional[bool]  = None
    months_since_prelim_approval:       Optional[float] = None