#!/usr/bin/env python3
"""Generate test PDF files for E2E testing"""

import fitz  # PyMuPDF
from pathlib import Path


def create_simple_pdf():
    """Create a simple PDF with text only"""
    doc = fitz.open()
    page = doc.new_page(width=595, height=842)  # A4 size
    
    text = """Test Document: Simple Invoice

Invoice #: INV-2025-001
Date: December 10, 2025
Customer: Test Company LLC

Items:
1. Cloud Storage Service - $100.00
2. Database Hosting - $50.00
3. API Gateway Usage - $25.00

Total: $175.00

Payment due: January 10, 2026

This is a test document for RAG system validation.
It contains multiple paragraphs to generate several chunks.

Additional notes:
- This document tests basic PDF text extraction
- No images or complex formatting
- Simple structure for reliable testing"""
    
    page.insert_text((50, 50), text, fontsize=11)
    
    output = Path(__file__).parent / "test_invoice.pdf"
    doc.save(output)
    doc.close()
    print(f"✓ Created: {output.name}")


def create_technical_doc():
    """Create a PDF with technical content"""
    doc = fitz.open()
    page = doc.new_page(width=595, height=842)
    
    text = """RAG System Technical Specification

Version: 1.0
Document ID: TECH-SPEC-001

1. OVERVIEW

This document describes the Retrieval-Augmented Generation (RAG)
system architecture and implementation details.

2. COMPONENTS

2.1 Vector Database
- PostgreSQL with pgvector extension
- Supports 768-dimensional embeddings
- Cosine similarity search

2.2 Storage Layer
- Google Cloud Storage for documents
- UUID-based file organization
- Support for PDF and TXT formats

2.3 Embedding Model
- Google's text-embedding-005
- 768 dimensions
- Multilingual support

3. API ENDPOINTS

POST /v1/documents/upload - Upload new document
GET /v1/documents - List all documents
DELETE /v1/documents/{id} - Remove document
POST /v1/query - Search similar content

4. TESTING

Comprehensive E2E tests validate:
- Document upload and deduplication
- Vector search accuracy
- File download with UTF-8 support
- Complete cleanup verification"""
    
    page.insert_text((50, 50), text, fontsize=10)
    
    output = Path(__file__).parent / "test_technical_doc.pdf"
    doc.save(output)
    doc.close()
    print(f"✓ Created: {output.name}")


def create_pdf_with_shapes():
    """Create a PDF with text and simple shapes/graphics"""
    doc = fitz.open()
    page = doc.new_page(width=595, height=842)
    
    # Header with background
    header_rect = fitz.Rect(0, 0, 595, 60)
    page.draw_rect(header_rect, color=(0.2, 0.4, 0.8), fill=(0.2, 0.4, 0.8))
    page.insert_text((50, 35), "QUARTERLY REPORT - Q4 2025", 
                     fontsize=16, color=(1, 1, 1))
    
    # Main content
    text = """EXECUTIVE SUMMARY

Revenue Performance:
- Q4 Revenue: $2.5M (↑15% YoY)
- Annual Revenue: $9.2M (↑22% YoY)
- Customer Count: 450 (↑35% YoY)

Key Achievements:
• Launched RAG-powered search feature
• Expanded to 3 new regions
• Achieved 99.95% uptime SLA
• Reduced infrastructure costs by 18%

Product Metrics:
- Daily Active Users: 12,500
- Average Query Response: 250ms
- Customer Satisfaction: 4.8/5.0

Strategic Initiatives for 2026:
1. Multi-modal RAG support (images, audio)
2. Enterprise tier launch
3. API marketplace integration
4. Advanced analytics dashboard

This document contains confidential information.
Distribution limited to executive team only."""
    
    page.insert_text((50, 100), text, fontsize=11)
    
    # Add colored boxes for visual elements
    box1 = fitz.Rect(450, 150, 550, 200)
    page.draw_rect(box1, color=(0, 0.6, 0.3), fill=(0.8, 0.95, 0.85))
    page.insert_text((460, 175), "↑ 22%\nRevenue", fontsize=12, color=(0, 0.4, 0.2))
    
    box2 = fitz.Rect(450, 220, 550, 270)
    page.draw_rect(box2, color=(0.8, 0.5, 0), fill=(1, 0.95, 0.8))
    page.insert_text((460, 245), "450\nCustomers", fontsize=12, color=(0.6, 0.3, 0))
    
    output = Path(__file__).parent / "test_quarterly_report.pdf"
    doc.save(output)
    doc.close()
    print(f"✓ Created: {output.name}")


if __name__ == "__main__":
    print("Generating test PDF files...")
    create_simple_pdf()
    create_technical_doc()
    create_pdf_with_shapes()
    print("\n✓ All test PDFs created successfully!")
