from __future__ import annotations

from typing import Dict

import fitz  # PyMuPDF


def extract_pages(pdf_path: str) -> Dict[int, str]:
    """
    Extract text from a PDF, preserving page numbers.

    Returns:
        { page_number (1-based): text }
    """

    # Open the PDF file
    doc = fitz.open(pdf_path)

    pages: Dict[int, str] = {}

    # Iterate through pages (0-based internally)
    for page_index in range(doc.page_count):
        page = doc.load_page(page_index)

        # Extract plain text from the page
        # (layout is best-effort; PDFs are messy)
        text = page.get_text("text") or ""

        # Store using 1-based page numbers for human citation
        pages[page_index + 1] = text

    # Always close the document
    doc.close()

    return pages
