"""
accessibility_checker.py

Main orchestrator for ADA/WCAG accessibility checking.

This module coordinates the entire accessibility validation process:
1. Identifies file type
2. Runs appropriate checks
3. Generates comprehensive report
4. Determines if file meets WCAG AA compliance
"""

from __future__ import annotations

import hashlib
from datetime import datetime
from pathlib import Path
from typing import Tuple

from app.accessibility_models import (
    AccessibilityReport,
    AccessibilityIssue,
    FileType,
    ComplianceLevel,
    IssueLevel,
)
from app.accessibility_utils import (
    check_pdf_accessibility,
    check_docx_accessibility,
    check_xlsx_accessibility,
)


class AccessibilityChecker:
    """
    Main class for checking document accessibility.
    
    Usage:
        checker = AccessibilityChecker()
        report = checker.check_file("/path/to/document.pdf")
        
        if report.is_compliant:
            print("Document is ADA compliant!")
        else:
            print(f"Found {report.total_issues} issues")
    """
    
    def __init__(self):
        """Initialize the accessibility checker."""
        pass
    
    def check_file(self, file_path: str, original_filename: str = None) -> AccessibilityReport:
        """
        Check a file for accessibility compliance.
        
        Args:
            file_path: Path to the file to check
            original_filename: Original filename (if different from file_path)
        
        Returns:
            AccessibilityReport with complete analysis
        
        Raises:
            ValueError: If file type is not supported
            FileNotFoundError: If file doesn't exist
        """
        # Convert to Path object for easier handling
        path = Path(file_path)
        
        # Check if file exists
        if not path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")
        
        # Determine file type from extension
        file_ext = path.suffix.lower()
        file_type = self._get_file_type(file_ext)
        
        if file_type is None:
            raise ValueError(
                f"Unsupported file type: {file_ext}. "
                f"Supported types: .pdf, .docx, .xlsx"
            )
        
        # Get file size
        file_size = path.stat().st_size
        
        # Use original filename if provided, otherwise use path name
        filename = original_filename or path.name
        
        # Run the appropriate checks based on file type
        issues = []
        pdf_checks = None
        docx_checks = None
        xlsx_checks = None
        
        if file_type == FileType.PDF:
            pdf_checks, issues = check_pdf_accessibility(str(path))
        
        elif file_type == FileType.DOCX:
            docx_checks, issues = check_docx_accessibility(str(path))
        
        elif file_type == FileType.XLSX:
            xlsx_checks, issues = check_xlsx_accessibility(str(path))
        
        # Build the complete report
        report = self._build_report(
            filename=filename,
            file_type=file_type,
            file_size=file_size,
            issues=issues,
            pdf_checks=pdf_checks,
            docx_checks=docx_checks,
            xlsx_checks=xlsx_checks,
        )
        
        return report
    
    def _get_file_type(self, extension: str) -> FileType | None:
        """
        Map file extension to FileType enum.
        
        Args:
            extension: File extension (e.g., '.pdf', '.docx')
        
        Returns:
            FileType enum or None if not supported
        """
        extension = extension.lower().lstrip('.')
        
        mapping = {
            'pdf': FileType.PDF,
            'docx': FileType.DOCX,
            'xlsx': FileType.XLSX,
        }
        
        return mapping.get(extension)
    
    def _build_report(
        self,
        filename: str,
        file_type: FileType,
        file_size: int,
        issues: list[AccessibilityIssue],
        pdf_checks=None,
        docx_checks=None,
        xlsx_checks=None,
    ) -> AccessibilityReport:
        """
        Build a complete accessibility report from check results.
        
        This method:
        1. Counts issue severity levels
        2. Determines overall compliance status
        3. Generates summary and recommendations
        4. Assembles the final report
        """
        # =====================================================================
        # STEP 1: Count issues by severity
        # =====================================================================
        critical_count = 0
        error_count = 0
        warning_count = 0
        
        for issue in issues:
            if issue.level == IssueLevel.CRITICAL:
                critical_count += 1
            elif issue.level == IssueLevel.ERROR:
                error_count += 1
            elif issue.level == IssueLevel.WARNING:
                warning_count += 1
        
        total_issues = len(issues)
        
        # =====================================================================
        # STEP 2: Determine compliance status
        # =====================================================================
        # For WCAG AA compliance, we need:
        # - Zero CRITICAL issues (these completely block access)
        # - Zero ERROR issues (these make content very difficult to access)
        # WARNINGS are recommendations but don't block AA compliance
        
        blocking_issues = critical_count + error_count
        is_compliant = (blocking_issues == 0)
        
        # Determine which compliance level was achieved
        compliance_level_met = None
        if is_compliant:
            # If no warnings either, we might meet AAA
            if warning_count == 0:
                compliance_level_met = ComplianceLevel.AAA
            else:
                compliance_level_met = ComplianceLevel.AA
        
        # =====================================================================
        # STEP 3: Generate human-readable summary
        # =====================================================================
        if is_compliant:
            summary = (
                f"✓ Document meets WCAG {compliance_level_met.value} accessibility standards. "
                f"Great job!"
            )
            if warning_count > 0:
                summary += (
                    f" Found {warning_count} recommendation(s) for further improvement."
                )
        else:
            summary = (
                f"✗ Document does NOT meet WCAG AA accessibility standards. "
                f"Found {blocking_issues} blocking issue(s) that must be fixed."
            )
        
        # =====================================================================
        # STEP 4: Generate top recommendations
        # =====================================================================
        recommendations = []
        
        # Add recommendations based on most common/critical issues
        if critical_count > 0:
            recommendations.append(
                f"PRIORITY: Fix {critical_count} critical issue(s) - "
                f"these completely block access for users with disabilities."
            )
        
        if error_count > 0:
            recommendations.append(
                f"Fix {error_count} error(s) that make content difficult to access."
            )
        
        # Add specific recommendations based on file type
        if file_type == FileType.PDF:
            if pdf_checks and not pdf_checks.is_tagged:
                recommendations.append(
                    "Tag the PDF using Adobe Acrobat Pro's auto-tag feature, "
                    "then manually verify the structure."
                )
            if pdf_checks and pdf_checks.is_ocr_needed:
                recommendations.append(
                    "Run OCR (Optical Character Recognition) to add a text layer "
                    "to this scanned PDF."
                )
            if pdf_checks and pdf_checks.images_without_alt_text > 0:
                recommendations.append(
                    f"Add alternative text to {pdf_checks.images_without_alt_text} image(s)."
                )
        
        elif file_type == FileType.DOCX:
            if docx_checks and not docx_checks.uses_heading_styles:
                recommendations.append(
                    "Replace bold text with proper Heading styles (Heading 1, 2, 3, etc.)."
                )
            if docx_checks and docx_checks.images_without_alt_text > 0:
                recommendations.append(
                    f"Add alt text to {docx_checks.images_without_alt_text} image(s)."
                )
        
        elif file_type == FileType.XLSX:
            if xlsx_checks and not xlsx_checks.avoids_merged_cells:
                recommendations.append(
                    "Unmerge cells - they break screen reader navigation."
                )
            if xlsx_checks and not xlsx_checks.has_cell_structure:
                recommendations.append(
                    "Add clear header rows to all data tables."
                )
        
        # Add general recommendation
        if not is_compliant:
            recommendations.append(
                "Review detailed issues below and use the remediation steps provided. "
                "Test with a screen reader after making changes."
            )
        
        # =====================================================================
        # STEP 5: Assemble the final report
        # =====================================================================
        report = AccessibilityReport(
            file_name=filename,
            file_type=file_type,
            file_size_bytes=file_size,
            checked_at=datetime.utcnow().isoformat() + "Z",  # ISO 8601 format
            is_compliant=is_compliant,
            compliance_level_met=compliance_level_met,
            total_issues=total_issues,
            critical_issues=critical_count,
            error_issues=error_count,
            warning_issues=warning_count,
            issues=issues,
            pdf_checks=pdf_checks,
            docx_checks=docx_checks,
            xlsx_checks=xlsx_checks,
            summary=summary,
            recommendations=recommendations,
        )
        
        return report
    
    @staticmethod
    def generate_report_id(filename: str) -> str:
        """
        Generate a unique ID for an accessibility report.
        
        This ID can be used to retrieve the report later.
        Uses a hash of filename + timestamp for uniqueness.
        
        Args:
            filename: Original filename
        
        Returns:
            Unique report ID (e.g., "ada_abc123def456")
        """
        # Create a unique identifier based on filename and current time
        content = f"{filename}_{datetime.utcnow().isoformat()}"
        hash_obj = hashlib.sha256(content.encode())
        hash_hex = hash_obj.hexdigest()[:12]  # Take first 12 characters
        
        return f"ada_{hash_hex}"


# =============================================================================
# Convenience function for one-off checks
# =============================================================================

def check_file_accessibility(file_path: str, original_filename: str = None) -> AccessibilityReport:
    """
    Convenience function to check a file's accessibility.
    
    Args:
        file_path: Path to file to check
        original_filename: Optional original filename
    
    Returns:
        AccessibilityReport
    
    Example:
        report = check_file_accessibility("/tmp/policy.pdf")
        if report.is_compliant:
            print("Document is accessible!")
        else:
            print(f"Found {report.total_issues} issues:")
            for issue in report.issues:
                print(f"  - {issue.description}")
    """
    checker = AccessibilityChecker()
    return checker.check_file(file_path, original_filename)
