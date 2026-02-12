"""
accessibility_models.py

Data models for ADA/WCAG compliance checking.
These classes define the structure of our accessibility reports.

Think of these as blueprints that ensure every report has the same structure,
making them easy to save to JSON and display in a UI later.
"""

from __future__ import annotations

from typing import List, Optional
from enum import Enum
from pydantic import BaseModel, Field


# -----------------------------------------------------------------------------
# Enums (Fixed sets of allowed values)
# -----------------------------------------------------------------------------

class ComplianceLevel(str, Enum):
    """
    WCAG compliance levels - defines how strict the accessibility requirements are.
    
    Government sites typically require Level AA as a minimum.
    """
    A = "A"          # Basic accessibility (minimum)
    AA = "AA"        # Mid-range accessibility (government standard)
    AAA = "AAA"      # Highest accessibility (gold standard)


class FileType(str, Enum):
    """
    Supported file types for accessibility checking.
    """
    PDF = "pdf"
    DOCX = "docx"
    XLSX = "xlsx"


class IssueLevel(str, Enum):
    """
    How severe is this accessibility issue?
    """
    CRITICAL = "critical"    # Blocks users with disabilities completely
    ERROR = "error"          # Makes content very difficult to access
    WARNING = "warning"      # Could cause problems for some users
    INFO = "info"            # Best practice recommendation


# -----------------------------------------------------------------------------
# Individual Issue Model
# -----------------------------------------------------------------------------

class AccessibilityIssue(BaseModel):
    """
    Represents a single accessibility problem found in a document.
    
    Example:
        "Image on page 3 is missing alt text" would be one issue.
    """
    
    # What WCAG success criterion does this violate?
    # Example: "1.1.1" (Non-text Content), "1.3.1" (Info and Relationships)
    wcag_criterion: str = Field(
        ...,
        description="WCAG 2.1 success criterion number (e.g., '1.1.1', '2.4.2')"
    )
    
    # How bad is this issue?
    level: IssueLevel = Field(
        ...,
        description="Severity level of the issue"
    )
    
    # Human-readable description of what's wrong
    description: str = Field(
        ...,
        description="Clear explanation of the accessibility problem"
    )
    
    # Where in the document is this issue?
    # Could be a page number, sheet name, or element ID
    location: Optional[str] = Field(
        None,
        description="Location in document where issue was found (e.g., 'Page 5', 'Sheet1')"
    )
    
    # How to fix it
    remediation: str = Field(
        ...,
        description="Step-by-step guidance on how to fix this issue"
    )
    
    # Is this a blocker for WCAG AA compliance?
    blocks_compliance: bool = Field(
        default=True,
        description="Whether this issue prevents WCAG AA certification"
    )


# -----------------------------------------------------------------------------
# File-Specific Check Results
# -----------------------------------------------------------------------------

class PDFAccessibilityChecks(BaseModel):
    """
    Results of PDF-specific accessibility checks.
    """
    is_tagged: bool = Field(
        ...,
        description="Does the PDF have proper tags for structure (headings, lists, etc.)?"
    )
    
    has_document_language: bool = Field(
        ...,
        description="Is the document language specified (e.g., 'en-US')?"
    )
    
    images_with_alt_text: int = Field(
        default=0,
        description="Number of images that have alt text"
    )
    
    images_without_alt_text: int = Field(
        default=0,
        description="Number of images missing alt text"
    )
    
    has_logical_reading_order: bool = Field(
        ...,
        description="Is the reading order logical for screen readers?"
    )
    
    is_ocr_needed: bool = Field(
        ...,
        description="Is this a scanned image PDF that needs OCR?"
    )
    
    has_searchable_text: bool = Field(
        ...,
        description="Can you select and search text in the PDF?"
    )
    
    heading_structure_valid: bool = Field(
        default=True,
        description="Are headings properly nested (H1 → H2 → H3, not H1 → H3)?"
    )
    
    form_fields_labeled: Optional[bool] = Field(
        None,
        description="If PDF has forms, are all fields properly labeled?"
    )


class DocxAccessibilityChecks(BaseModel):
    """
    Results of Word document accessibility checks.
    """
    has_document_language: bool = Field(
        ...,
        description="Is the document language specified?"
    )
    
    images_with_alt_text: int = Field(
        default=0,
        description="Number of images with alt text"
    )
    
    images_without_alt_text: int = Field(
        default=0,
        description="Number of images missing alt text"
    )
    
    uses_heading_styles: bool = Field(
        ...,
        description="Does document use proper heading styles (not just bold text)?"
    )
    
    heading_structure_valid: bool = Field(
        default=True,
        description="Are headings properly nested?"
    )
    
    tables_have_headers: bool = Field(
        default=True,
        description="Do all tables have header rows defined?"
    )
    
    sufficient_color_contrast: bool = Field(
        default=True,
        description="Is color contrast ratio >= 4.5:1 for normal text?"
    )
    
    has_meaningful_hyperlinks: bool = Field(
        default=True,
        description="Are hyperlink text descriptive (not just 'click here')?"
    )


class XlsxAccessibilityChecks(BaseModel):
    """
    Results of Excel spreadsheet accessibility checks.
    """
    sheets_have_meaningful_names: bool = Field(
        ...,
        description="Are sheet names descriptive (not 'Sheet1', 'Sheet2')?"
    )
    
    has_cell_structure: bool = Field(
        ...,
        description="Is data organized with proper headers and structure?"
    )
    
    sufficient_color_contrast: bool = Field(
        default=True,
        description="Is color contrast sufficient for text?"
    )
    
    avoids_merged_cells: bool = Field(
        default=True,
        description="Are merged cells avoided? (They break screen readers)"
    )
    
    has_alt_text_for_charts: bool = Field(
        default=True,
        description="Do charts and graphs have descriptive alt text?"
    )


# -----------------------------------------------------------------------------
# Complete Accessibility Report
# -----------------------------------------------------------------------------

class AccessibilityReport(BaseModel):
    """
    Complete accessibility compliance report for a single document.
    
    This is what gets saved to data/accessibility_reports/ and
    returned from the /check-accessibility endpoint.
    """
    
    # Basic file information
    file_name: str = Field(
        ...,
        description="Original filename"
    )
    
    file_type: FileType = Field(
        ...,
        description="Type of file checked"
    )
    
    file_size_bytes: int = Field(
        ...,
        description="File size in bytes"
    )
    
    # When was this check performed?
    checked_at: str = Field(
        ...,
        description="ISO timestamp when accessibility check was performed"
    )
    
    # Overall compliance status
    is_compliant: bool = Field(
        ...,
        description="Does this file meet WCAG AA requirements?"
    )
    
    compliance_level_met: Optional[ComplianceLevel] = Field(
        None,
        description="Highest WCAG level achieved (if any)"
    )
    
    # Summary statistics
    total_issues: int = Field(
        default=0,
        description="Total number of accessibility issues found"
    )
    
    critical_issues: int = Field(
        default=0,
        description="Number of critical issues (must fix)"
    )
    
    error_issues: int = Field(
        default=0,
        description="Number of errors (should fix)"
    )
    
    warning_issues: int = Field(
        default=0,
        description="Number of warnings (recommended to fix)"
    )
    
    # Detailed list of all issues found
    issues: List[AccessibilityIssue] = Field(
        default_factory=list,
        description="Detailed list of all accessibility problems found"
    )
    
    # File-type-specific checks
    pdf_checks: Optional[PDFAccessibilityChecks] = Field(
        None,
        description="PDF-specific check results (only present for PDFs)"
    )
    
    docx_checks: Optional[DocxAccessibilityChecks] = Field(
        None,
        description="Word document check results (only present for .docx)"
    )
    
    xlsx_checks: Optional[XlsxAccessibilityChecks] = Field(
        None,
        description="Excel spreadsheet check results (only present for .xlsx)"
    )
    
    # Notes and recommendations
    summary: str = Field(
        default="",
        description="Human-readable summary of findings"
    )
    
    recommendations: List[str] = Field(
        default_factory=list,
        description="Top recommended actions to improve accessibility"
    )


# -----------------------------------------------------------------------------
# API Response Models
# -----------------------------------------------------------------------------

class AccessibilityCheckResponse(BaseModel):
    """
    Response returned by /check-accessibility endpoint.
    Contains the full detailed report.
    """
    report: AccessibilityReport = Field(
        ...,
        description="Complete accessibility report"
    )


class AccessibilityRejectionSummary(BaseModel):
    """
    Brief summary returned when /ingest rejects a file for non-compliance.
    User can call /check-accessibility to get the full report.
    """
    message: str = Field(
        ...,
        description="Why the file was rejected"
    )
    
    is_compliant: bool = Field(
        default=False,
        description="Always False for rejections"
    )
    
    total_issues: int = Field(
        ...,
        description="Total number of accessibility issues found"
    )
    
    critical_issues: int = Field(
        ...,
        description="Number of critical issues"
    )
    
    report_id: str = Field(
        ...,
        description="ID to retrieve full report via /check-accessibility"
    )
    
    top_issues: List[str] = Field(
        default_factory=list,
        description="Brief descriptions of the 3 most important issues"
    )
