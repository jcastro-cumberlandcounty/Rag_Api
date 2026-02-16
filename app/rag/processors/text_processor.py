"""
Text Processor Module

Purpose: Extract and chunk text from PDF documents for RAG (Retrieval Augmented Generation)

What this does:
1. Opens PDF files using PyMuPDF (fitz)
2. Extracts text from each page
3. Splits text into overlapping chunks (for better retrieval)
4. Returns structured chunk data ready for embedding

Python concepts used here:
- Type hints (the ": str" and "-> List[Chunk]" syntax tells what types we expect)
- List comprehensions (compact way to build lists)
- f-strings (f"text {variable}" for string formatting)
"""

from __future__ import annotations  # Allows us to use modern type hints

from typing import List  # For type hints - says "this returns a list of X"
import fitz  # PyMuPDF - library for reading PDF files

# Import our data models from types.py
from app.rag.types import Page, Chunk


# =============================================================================
# TEXT EXTRACTION FUNCTIONS
# =============================================================================

def extract_pdf_pages(pdf_path: str) -> List[Page]:
    """
    Extract text from a PDF file, one page at a time.
    
    Args:
        pdf_path: Full path to the PDF file (example: "/data/policy.pdf")
    
    Returns:
        List of Page objects, each containing:
        - page_num: The page number (1-based, so humans can read it)
        - text: All the text content from that page
    
    Example:
        pages = extract_pdf_pages("/data/policy.pdf")
        # pages[0].page_num = 1
        # pages[0].text = "Policy Document\nSection 1..."
    """
    # Open the PDF file - fitz.open() gives us a document object
    doc = fitz.open(pdf_path)
    
    # Create an empty list to store our Page objects
    pages: List[Page] = []
    
    # Loop through each page in the PDF
    # enumerate() gives us both the index (i) and the page object
    # enumerate() starts counting at 0, but we want page numbers starting at 1
    for i, page in enumerate(doc):
        # Extract all text from this page
        # If there's no text, we get empty string instead of None
        text = page.get_text() or ""
        
        # Create a Page object and add it to our list
        # i+1 because Python counts from 0, but humans count pages from 1
        pages.append(Page(page_num=i + 1, text=text))
    
    # Always close the document when done (frees up memory)
    doc.close()
    
    return pages


# =============================================================================
# TEXT CHUNKING FUNCTIONS
# =============================================================================

def sanitize_text_for_embedding(text: str, max_chars: int = 4000) -> str:
    """
    Clean up text so it's safe to send to embedding models.
    
    Why we need this:
    - PDFs often have weird characters (NULL bytes, control characters)
    - Embedding models can crash on bad characters
    - We need to limit size so we don't exceed model limits
    
    Args:
        text: Raw text from PDF (might have junk characters)
        max_chars: Maximum length (default 4000 chars)
    
    Returns:
        Clean text that's safe for embedding models
    
    Example:
        dirty = "Hello\x00World\x01"  # Has NULL and control chars
        clean = sanitize_text_for_embedding(dirty)
        # Result: "Hello World"
    """
    # If text is empty or None, just return empty string
    if not text:
        return ""
    
    # Step 1: Remove NULL bytes (the \x00 character)
    # NULL bytes crash many text processors
    safe = text.replace("\x00", " ")
    
    # Step 2: Remove other control characters (ASCII values below 32)
    # BUT keep newline (\n) and tab (\t) because those are useful
    # 
    # This is a "generator expression" - it's like a for loop inside a function
    # For each character: if it's safe, keep it; otherwise replace with space
    safe = "".join(
        ch if (ch == "\n" or ch == "\t" or ord(ch) >= 32) else " "
        for ch in safe
    )
    
    # Step 3: Normalize whitespace (collapse multiple spaces into one)
    # split() with no arguments splits on any whitespace
    # join() puts them back together with single spaces
    safe = " ".join(safe.split())
    
    # Step 4: Enforce maximum length (truncate if too long)
    if len(safe) > max_chars:
        safe = safe[:max_chars]  # Slice notation: take first max_chars characters
    
    # Step 5: Remove leading/trailing whitespace
    return safe.strip()


def chunk_pages(
    pages: List[Page],
    chunk_size: int = 900,
    overlap: int = 150,
) -> List[Chunk]:
    """
    Split pages into overlapping text chunks.
    
    Why overlapping chunks?
    - Important information might span chunk boundaries
    - Overlap ensures we don't "split" a key sentence in half
    - Example: If chunk 1 ends with "The policy requires", 
      chunk 2 might start 150 chars earlier to include that context
    
    Args:
        pages: List of Page objects (from extract_pdf_pages)
        chunk_size: Target size of each chunk in characters (default 900)
        overlap: How many characters to overlap between chunks (default 150)
    
    Returns:
        List of Chunk objects, each containing:
        - chunk_id: Unique identifier like "p1_c0" (page 1, chunk 0)
        - page: Page number this chunk came from
        - text: The actual chunk text
    
    Example:
        Input: pages with 2000 characters
        Output: ~3 chunks of 900 chars each, with 150 char overlap
        
        Chunk 0: chars 0-900
        Chunk 1: chars 750-1650  (starts 150 before previous chunk ended)
        Chunk 2: chars 1500-2000 (starts 150 before previous chunk ended)
    """
    # Create empty list to collect all chunks from all pages
    chunks: List[Chunk] = []
    
    # Process each page one at a time
    for page in pages:
        # Get the text for this page (might be empty)
        text = page.text or ""
        
        # Variables to track our position while chunking
        start = 0  # Where we start reading in the text
        chunk_idx = 0  # Count chunks on this page (0, 1, 2, ...)
        
        # Keep making chunks until we've covered all the text
        # "while start < len(text)" means "while we haven't reached the end"
        while start < len(text):
            # Calculate where this chunk should end
            # min() picks the smaller value (prevents going past end of text)
            end = start + chunk_size
            
            # Extract the chunk text using slice notation [start:end]
            # .strip() removes extra whitespace from beginning and end
            chunk_text = text[start:end].strip()
            
            # Only save this chunk if it has actual content
            # (Don't save empty chunks)
            if chunk_text:
                # Create a Chunk object with:
                # - Unique ID combining page number and chunk index
                # - Page number for citation
                # - The actual text
                chunks.append(
                    Chunk(
                        chunk_id=f"p{page.page_num}_c{chunk_idx}",  # f-string: f"p{1}_c{0}" = "p1_c0"
                        page=page.page_num,
                        text=chunk_text,
                    )
                )
            
            # Move to the next chunk position
            # We subtract overlap so chunks overlap by that many characters
            # Example: if end=900 and overlap=150, next start=750
            start = end - overlap
            
            # Increment the chunk counter for the next chunk on this page
            chunk_idx += 1
    
    # Return all chunks from all pages
    return chunks
