"""
Vision Processor Module

Purpose: Extract images from PDFs and generate text descriptions using AI vision models

What this does:
1. Opens PDF files and extracts all images
2. Filters out tiny/decorative images (logos, bullets, etc.)
3. Sends meaningful images to llama3.2-vision AI model
4. Gets back text descriptions that can be embedded and searched
5. Creates "image chunks" that work just like text chunks in RAG

Why this matters:
- Org charts, diagrams, flowcharts contain critical information
- Traditional RAG only sees text, missing visual content
- Vision AI can "read" images and describe what they show
- We convert visual information into searchable text

Python concepts used:
- Context managers (the "with" keyword for safe resource handling)
- Dictionaries (key-value pairs like {"page": 5, "index": 2})
- Try/except for error handling
- PIL (Python Imaging Library) for image manipulation
"""

from __future__ import annotations

from typing import List, Dict, Any, Optional
from pathlib import Path
import io  # For working with bytes in memory

import fitz  # PyMuPDF for PDF reading
from PIL import Image  # Python Imaging Library for image manipulation

# Import our Ollama client for vision model calls
from app.rag.ollama_client import OllamaClient
from app.rag.types import Chunk


# =============================================================================
# IMAGE EXTRACTION FUNCTIONS
# =============================================================================

def extract_images_from_pdf(pdf_path: str, min_size: int = 10000) -> List[Dict[str, Any]]:
    """
    Extract all meaningful images from a PDF file.
    
    Filters out tiny images (decorative elements, bullets, small logos).
    Only returns images large enough to contain actual information.
    
    Args:
        pdf_path: Path to the PDF file
        min_size: Minimum image size in bytes (default 10KB)
                 Images smaller than this are likely decorative
    
    Returns:
        List of dictionaries, each containing:
        - page: Page number (1-based)
        - index: Image number on that page (0-based)
        - image_bytes: The actual image data (PNG format)
        - width: Image width in pixels
        - height: Image height in pixels
        - size_bytes: Image size in bytes
    
    Example:
        images = extract_images_from_pdf("policy.pdf")
        # Result: [
        #   {"page": 3, "index": 0, "image_bytes": b"...", "width": 800, "height": 600},
        #   {"page": 5, "index": 0, "image_bytes": b"...", "width": 1024, "height": 768},
        # ]
    """
    # Open the PDF document
    doc = fitz.open(pdf_path)
    
    # List to collect all extracted images
    extracted_images: List[Dict[str, Any]] = []
    
    # Loop through each page in the PDF
    # enumerate(doc, start=1) gives us page numbers starting at 1 (not 0)
    for page_num, page in enumerate(doc, start=1):
        # Get all images on this page
        # get_images() returns a list of image references
        image_list = page.get_images()
        
        # Process each image on this page
        # enumerate() gives us both the index and the image reference
        for img_index, img in enumerate(image_list):
            # Extract the actual image data from the PDF
            # img[0] is the xref (cross-reference number - PDF's way of identifying objects)
            xref = img[0]
            
            # Get the image bytes and metadata from the PDF
            try:
                # extract_image() returns a dictionary with image data
                base_image = doc.extract_image(xref)
                
                # Get the raw image bytes
                image_bytes = base_image["image"]
                
                # Get image dimensions (if available)
                # Some PDFs don't have this metadata, so we use .get() with defaults
                width = base_image.get("width", 0)
                height = base_image.get("height", 0)
                
                # Check if image is large enough to be meaningful
                # Tiny images are usually decorative (bullets, icons, small logos)
                if len(image_bytes) < min_size:
                    continue  # Skip this image, move to next one
                
                # Convert image to PNG format (standardized format for vision models)
                # This ensures consistent input regardless of original format (JPEG, etc.)
                try:
                    # Open the image bytes as a PIL Image object
                    pil_image = Image.open(io.BytesIO(image_bytes))
                    
                    # Convert to PNG format in memory
                    png_buffer = io.BytesIO()  # Create in-memory buffer
                    pil_image.save(png_buffer, format="PNG")  # Save as PNG
                    png_bytes = png_buffer.getvalue()  # Get the bytes
                    
                    # Store all the image information
                    extracted_images.append({
                        "page": page_num,
                        "index": img_index,
                        "image_bytes": png_bytes,
                        "width": width,
                        "height": height,
                        "size_bytes": len(png_bytes),
                    })
                
                except Exception as img_error:
                    # If image conversion fails, skip it and continue
                    # (Some PDFs have corrupted/unsupported image formats)
                    print(f"Warning: Could not convert image on page {page_num}, index {img_index}: {img_error}")
                    continue
            
            except Exception as extract_error:
                # If extraction fails, skip this image
                print(f"Warning: Could not extract image on page {page_num}, index {img_index}: {extract_error}")
                continue
    
    # Close the PDF document (free up memory)
    doc.close()
    
    return extracted_images


# =============================================================================
# VISION AI DESCRIPTION FUNCTIONS
# =============================================================================

def describe_image_with_vision(
    ollama_client: OllamaClient,
    image_bytes: bytes,
    vision_model: str = "llama3.2-vision:11b",
    max_retries: int = 2,
) -> Optional[str]:
    """
    Use AI vision model to generate a text description of an image.
    
    This is the magic that makes images searchable!
    The vision model "looks at" the image and describes what it sees.
    
    Args:
        ollama_client: The Ollama client for making AI requests
        image_bytes: The image data (PNG format)
        vision_model: Which vision model to use (default: llama3.2-vision:11b)
        max_retries: How many times to retry if the model fails
    
    Returns:
        Text description of the image, or None if it failed
    
    Example:
        description = describe_image_with_vision(ollama, image_bytes)
        # Result: "This image shows an organizational chart with a hierarchical 
        #          structure. At the top is the County Manager position..."
    """
    # We'll try multiple times in case of temporary failures
    for attempt in range(max_retries):
        try:
            # Convert image bytes to base64 (text encoding of binary data)
            # Vision models expect base64-encoded images
            import base64
            image_base64 = base64.b64encode(image_bytes).decode("utf-8")
            
            # Create the vision prompt
            # This tells the AI what kind of description we want
            prompt = (
                "Describe this image in detail for document search purposes. "
                "Focus on the content, structure, and key information shown. "
                "If it's a chart or diagram, explain what it represents. "
                "If it contains text, include that text in your description."
            )
            
            # Build the messages array for the vision model
            # Vision models need both text (the prompt) and images
            messages = [
                {
                    "role": "user",
                    "content": prompt,
                    "images": [image_base64],  # List of base64-encoded images
                }
            ]
            
            # Call the vision model
            # This might take 2-10 seconds depending on image complexity
            description = ollama_client.chat(
                model=vision_model,
                messages=messages,
            )
            
            # Return the description if we got one
            if description and description.strip():
                return description.strip()
            else:
                # Empty response - try again
                continue
        
        except Exception as e:
            # If this was our last attempt, give up
            if attempt == max_retries - 1:
                print(f"Error describing image after {max_retries} attempts: {e}")
                return None
            # Otherwise, try again
            continue
    
    # If we get here, all retries failed
    return None


# =============================================================================
# IMAGE CHUNK CREATION FUNCTIONS
# =============================================================================

def create_image_chunks(
    ollama_client: OllamaClient,
    pdf_path: str,
    vision_model: str = "llama3.2-vision:11b",
    min_image_size: int = 10000,
) -> List[Chunk]:
    """
    Extract images from PDF and create searchable "image chunks".
    
    This is the high-level function that:
    1. Extracts all images from the PDF
    2. Describes each image with the vision model
    3. Creates Chunk objects (just like text chunks)
    4. Returns chunks ready to be embedded and indexed
    
    Args:
        ollama_client: Ollama client for vision AI
        pdf_path: Path to the PDF file
        vision_model: Which vision model to use
        min_image_size: Minimum image size to process (bytes)
    
    Returns:
        List of Chunk objects where:
        - chunk_id: Like "p3_img0" (page 3, image 0)
        - page: Page number for citations
        - text: AI-generated description of the image
    
    Example:
        chunks = create_image_chunks(ollama, "policy.pdf")
        # Result: [
        #   Chunk(chunk_id="p5_img0", page=5, text="Organizational chart showing..."),
        #   Chunk(chunk_id="p8_img0", page=8, text="Bar chart displaying budget..."),
        # ]
    """
    # Step 1: Extract all images from the PDF
    print(f"Extracting images from {pdf_path}...")
    images = extract_images_from_pdf(pdf_path, min_size=min_image_size)
    
    print(f"Found {len(images)} images (filtered for size > {min_image_size} bytes)")
    
    # Step 2: Describe each image and create chunks
    image_chunks: List[Chunk] = []
    
    for i, img_data in enumerate(images):
        # Show progress (helpful for large PDFs with many images)
        print(f"Processing image {i+1}/{len(images)} from page {img_data['page']}...")
        
        # Call the vision model to get a description
        description = describe_image_with_vision(
            ollama_client=ollama_client,
            image_bytes=img_data["image_bytes"],
            vision_model=vision_model,
        )
        
        # If we got a good description, create a chunk
        if description:
            # Create chunk ID: "p{page}_img{index}"
            # Example: "p5_img0" = page 5, image 0
            chunk_id = f"p{img_data['page']}_img{img_data['index']}"
            
            # Create a Chunk object (same type as text chunks)
            # This means it can be embedded, indexed, and retrieved just like text!
            image_chunks.append(
                Chunk(
                    chunk_id=chunk_id,
                    page=img_data["page"],
                    text=description,  # The AI description becomes the searchable text
                )
            )
            
            print(f"  ✓ Created chunk {chunk_id} ({len(description)} chars)")
        else:
            print(f"  ✗ Failed to describe image on page {img_data['page']}")
    
    print(f"Successfully created {len(image_chunks)} image chunks")
    
    return image_chunks
