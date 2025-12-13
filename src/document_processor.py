"""
Document processing pipeline for RAG Lab

Handles:
1. Document loading (PDF, TXT, etc.)
2. Text chunking with overlap
3. Embedding generation (Vertex AI or local models)
4. Storage in PostgreSQL + pgvector

Architecture decision:
- Use Vertex AI embeddings by default (high quality)
- But store in PostgreSQL (provider-agnostic storage)
- Can swap embedding provider later without data migration
"""

import os
import warnings
import asyncio
import logging
from typing import List, Tuple, Optional
from enum import Enum
from concurrent.futures import ThreadPoolExecutor

import pymupdf4llm  # PyMuPDF4LLM for LLM-optimized PDF processing
import html2text  # HTML to Markdown conversion

from google import genai
from google.genai.types import EmbedContentConfig

# Setup logging
logger = logging.getLogger(__name__)
# To enable detailed TRACE-level logging: logging.getLogger('src.document_processor').setLevel(logging.DEBUG)


class EmbeddingProvider(Enum):
    """Supported embedding providers"""
    VERTEX_AI = "vertex_ai"  # Google Vertex AI text-embedding-005
    SENTENCE_TRANSFORMERS = "sentence_transformers"  # Local open-source models
    OPENAI = "openai"  # OpenAI embeddings (future)


class DocumentProcessor:
    """Process documents into embeddings"""
    
    def __init__(
        self,
        embedding_provider: EmbeddingProvider = EmbeddingProvider.VERTEX_AI,
        chunk_size: int = 2000,  # Balanced: good RAG quality + retry safety net
        chunk_overlap: int = 200,
        max_input_tokens: Optional[int] = None,  # For testing: artificially limit token size to trigger splits
        genai_client: Optional[genai.Client] = None,  # New: Google Gen AI client (required for Vertex AI)
    ):
        self.embedding_provider = embedding_provider
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.max_input_tokens = max_input_tokens  # If set, will reject chunks larger than this (in tokens)
        
        # Initialize embedding model based on provider
        if embedding_provider == EmbeddingProvider.VERTEX_AI:
            if genai_client is None:
                raise ValueError("genai_client required for Vertex AI embedding provider")
            self.genai_client = genai_client
            self.embedding_dimension = 768
        elif embedding_provider == EmbeddingProvider.SENTENCE_TRANSFORMERS:
            # Lazy import to avoid dependency if not used
            from sentence_transformers import SentenceTransformer
            self.embedding_model = SentenceTransformer('all-MiniLM-L6-v2')
            self.embedding_dimension = 384
        else:
            raise ValueError(f"Unsupported provider: {embedding_provider}")
    
    def extract_text_from_pdf(self, pdf_source) -> str:
        """
        Extract text from PDF using PyMuPDF4LLM (optimized for LLM/RAG)
        
        Converts PDF to Markdown format preserving:
        - Document structure (headings, lists, tables)
        - Text formatting (bold, italic, code)
        - Proper reading order (multi-column support)
        
        Args:
            pdf_source: Path to PDF file (str) or PDF bytes (bytes)
        
        Returns:
            Extracted text in Markdown format
        """
        # pymupdf4llm.to_markdown() accepts file path or PyMuPDF Document
        if isinstance(pdf_source, bytes):
            # For bytes, we need to create a PyMuPDF Document first
            import pymupdf
            doc = pymupdf.open(stream=pdf_source, filetype="pdf")
            page_count = len(doc)
            logger.debug(f"PDF has {page_count} pages, extracting text...")
            markdown_text = pymupdf4llm.to_markdown(doc)
            doc.close()
            logger.debug(f"Extracted {len(markdown_text)} chars from PDF")
        else:
            # For file path, pymupdf4llm handles it directly
            logger.debug(f"Extracting text from PDF file...")
            markdown_text = pymupdf4llm.to_markdown(pdf_source)
            logger.debug(f"Extracted {len(markdown_text)} chars from PDF")
        
        return markdown_text
    
    def extract_text_from_txt(self, txt_source) -> str:
        """
        Extract text from TXT file
        
        Args:
            txt_source: Path to TXT file (str) or TXT bytes (bytes)
        
        Returns:
            Text content
        """
        if isinstance(txt_source, bytes):
            try:
                # Try UTF-8 first
                return txt_source.decode('utf-8')
            except UnicodeDecodeError:
                # Fallback to latin-1 (never fails)
                logger.warning(f"UTF-8 decode failed, using latin-1")
                return txt_source.decode('latin-1', errors='replace')
        else:
            with open(txt_source, 'r', encoding='utf-8', errors='replace') as f:
                return f.read()
    
    def extract_text_from_json(self, json_source) -> str:
        """
        Extract text from JSON file and convert to YAML format
        
        YAML is optimal for RAG because:
        - Minimal syntax noise (no {}, "", commas)
        - Preserves structure and semantics
        - LLM-friendly (well represented in training data)
        - Compact (more context per chunk)
        
        Args:
            json_source: JSON bytes or file path
        
        Returns:
            YAML representation of JSON data
        """
        import json
        import yaml
        
        # Load JSON
        if isinstance(json_source, bytes):
            data = json.loads(json_source.decode('utf-8'))
        else:
            with open(json_source, 'r', encoding='utf-8') as f:
                data = json.load(f)
        
        # Convert to YAML (preserves all structure and semantics)
        yaml_text = yaml.dump(
            data,
            default_flow_style=False,  # Use block style (readable)
            allow_unicode=True,         # Support non-ASCII
            sort_keys=False             # Preserve original order
        )
        
        return yaml_text
    
    def extract_text_from_xml(self, xml_source) -> str:
        """
        Extract text from XML file and convert to YAML format
        
        Uses xmltodict for clean conversion preserving:
        - Element structure (hierarchy)
        - Attributes (prefixed with @)
        - Text content (as #text when mixed with attributes)
        - Semantic meaning of tags
        
        Args:
            xml_source: XML bytes or file path
        
        Returns:
            YAML representation of XML data
        """
        import xmltodict
        import yaml
        
        # Parse XML to dict
        if isinstance(xml_source, bytes):
            xml_string = xml_source.decode('utf-8')
        else:
            with open(xml_source, 'r', encoding='utf-8') as f:
                xml_string = f.read()
        
        # Convert XML to OrderedDict (preserves structure and attributes)
        data = xmltodict.parse(
            xml_string,
            attr_prefix='@',      # Attributes get @ prefix
            cdata_key='#text',    # Text content key
            force_list=False      # Don't force single items into lists
        )
        
        # Convert to YAML (clean, readable format for LLM)
        yaml_text = yaml.dump(
            data,
            default_flow_style=False,  # Block style (readable)
            allow_unicode=True,         # Support non-ASCII
            sort_keys=False             # Preserve order
        )
        
        return yaml_text
    
    def extract_text_from_html(self, html_source) -> str:
        """
        Extract text from HTML file and convert to Markdown format
        
        Converts HTML to Markdown preserving:
        - Document structure (headings, lists, tables)
        - Text formatting (bold, italic, code)
        - Links (converted to Markdown syntax)
        - Tables (converted to Markdown tables)
        
        Similar to PDF processing: HTML → Markdown for consistent LLM/RAG quality
        
        Args:
            html_source: HTML bytes or file path
        
        Returns:
            Extracted text in Markdown format
        """
        # Decode HTML content
        if isinstance(html_source, bytes):
            html_string = html_source.decode('utf-8', errors='replace')
        else:
            with open(html_source, 'r', encoding='utf-8', errors='replace') as f:
                html_string = f.read()
        
        # Configure html2text for optimal Markdown conversion
        converter = html2text.HTML2Text()
        converter.ignore_links = False  # Keep links (converted to [text](url))
        converter.ignore_images = False  # Keep image references
        converter.body_width = 0  # No line wrapping (preserve structure)
        converter.single_line_break = False  # Use proper paragraph breaks
        converter.ignore_emphasis = False  # Keep bold/italic formatting
        
        # Convert HTML to Markdown
        markdown_text = converter.handle(html_string)
        
        return markdown_text
    
    def extract_text(self, file_content: bytes, file_type: str) -> str:
        """
        Extract text from file based on type
        
        Args:
            file_content: File content as bytes
            file_type: File extension (.pdf, .txt) or MIME type
        
        Returns:
            Extracted text
        """
        # Normalize file type
        file_ext = file_type.lower()
        if file_ext.startswith('.'):
            file_ext = file_ext[1:]
        
        # PDF format
        if file_ext in ('pdf', 'application/pdf'):
            return self.extract_text_from_pdf(file_content)
        
        # Structured formats - smart parsing
        elif file_ext in ('json', 'application/json'):
            return self.extract_text_from_json(file_content)
        
        elif file_ext in ('xml', 'application/xml', 'text/xml'):
            return self.extract_text_from_xml(file_content)
        
        # HTML - convert to Markdown (preserves structure like PDF)
        elif file_ext in ('html', 'text/html', 'htm'):
            return self.extract_text_from_html(file_content)
        
        # Plain text formats - simple decode
        elif file_ext in {
            'txt', 'text/plain',
            'md', 'markdown', 'text/markdown',
            'rst', 'text/x-rst',
            'csv', 'text/csv',
            'log', 'text/x-log',
            'yaml', 'yml', 'application/x-yaml', 'text/yaml',
            'toml', 'application/toml',
            'ini', 'text/plain',
            'py', 'text/x-python',
            'js', 'application/javascript',
            'css', 'text/css',
        }:
            return self.extract_text_from_txt(file_content)
        
        else:
            raise ValueError(f"Unsupported file type: {file_type}. Supported: PDF or text-based formats (txt, md, json, csv, xml, yaml, etc.)")
    
    def chunk_text(self, text: str) -> List[Tuple[str, dict]]:
        """
        Split text into overlapping chunks
        
        Args:
            text: Input text to chunk
        
        Returns:
            List of (chunk_text, metadata) tuples
        """
        logger.info(f"Chunking text: {len(text)} chars, chunk_size={self.chunk_size}, overlap={self.chunk_overlap}")
        
        # Simple character-based chunking
        # TODO: Implement smarter sentence-aware chunking
        
        chunks = []
        start = 0
        iteration = 0
        
        while start < len(text):
            iteration += 1
            if iteration % 10 == 0:  # Log every 10 chunks
                logger.debug(f"Chunking progress: {len(chunks)} chunks, position {start}/{len(text)}")
            end = start + self.chunk_size
            chunk = text[start:end]
            
            # Try to find good boundaries in order of preference:
            # Search in the LAST 20% of chunk to keep chunks close to target size
            # Instead of searching from start (which creates tiny chunks)
            
            if end < len(text):
                # Search for boundary in last 20% of chunk (e.g., last 400 chars of 2000)
                search_start = max(0, self.chunk_size - int(self.chunk_size * 0.2))
                search_region = chunk[search_start:]
                
                boundaries = [
                    search_region.rfind('\n\n'),      # Paragraph
                    search_region.rfind('\n'),        # Line
                    search_region.rfind('. '),        # Sentence (period + space)
                    search_region.rfind(' '),         # Word
                ]
                
                # Use first boundary found in the search region
                best_boundary = -1
                for boundary in boundaries:
                    if boundary > 0:  # Found in search region
                        best_boundary = search_start + boundary
                        break
                
                if best_boundary > 0:
                    # Adjust end to boundary position
                    if chunk[best_boundary:best_boundary+2] in ['\n\n', '. ']:
                        end = start + best_boundary + 2
                    else:
                        end = start + best_boundary + 1
                    chunk = text[start:end]
            
            chunks.append((
                chunk.strip(),
                {
                    "start_char": start,
                    "end_char": end,
                    "chunk_index": len(chunks),
                }
            ))
            
            # Log chunk size (DEBUG level for detailed trace)
            chunk_size_actual = end - start
            logger.debug(f"Chunk #{len(chunks)}: {chunk_size_actual} chars")
            
            # Move start position with overlap
            # With proper boundary detection in last 20%, overlap should work correctly
            start = end - self.chunk_overlap
        
        logger.info(f"Created {len(chunks)} chunks")
        return chunks
    
    async def generate_embeddings(self, texts: List[str]) -> tuple[List[tuple[str, List[float]]], dict]:
        """
        Generate embeddings for text chunks (with parallel processing).
        If chunk too large, splits it into multiple chunks.
        
        Args:
            texts: List of text chunks
        
        Returns:
            Tuple of (list of (text, embedding) pairs, stats dict)
            Note: May return MORE pairs than input if chunks split
        """
        if self.embedding_provider == EmbeddingProvider.VERTEX_AI:
            # Process chunks in parallel (max 10 concurrent requests)
            pairs, stats = await self._generate_embeddings_parallel(texts, max_workers=10)
            return pairs, stats
        
        elif self.embedding_provider == EmbeddingProvider.SENTENCE_TRANSFORMERS:
            # Local model - already efficient, no splits
            embeddings = self.embedding_model.encode(texts)
            pairs = [(text, emb.tolist()) for text, emb in zip(texts, embeddings)]
            return pairs, {"splits_performed": 0, "max_depth_reached": 0}
        
        else:
            raise ValueError(f"Provider {self.embedding_provider} not implemented")
    
    async def _generate_embeddings_parallel(self, texts: List[str], max_workers: int = 10) -> tuple[List[tuple[str, List[float]]], dict]:
        """
        Generate embeddings in parallel using ThreadPoolExecutor.
        If a chunk exceeds token limit, splits it in half and returns 2 separate chunks.
        
        Args:
            texts: List of text chunks
            max_workers: Maximum concurrent API calls
        
        Returns:
            Tuple of (list of (text, embedding) pairs, stats dict)
            Note: May return MORE pairs than input if chunks split
        """
        logger.info(f"Generating embeddings for {len(texts)} chunks (max {max_workers} parallel)")
        
        # Track statistics
        stats = {"splits_performed": 0, "max_depth_reached": 0}
        
        def _get_embedding_with_retry(text: str, depth: int = 0) -> List[tuple[str, List[float]]]:
            """
            Generate embedding with automatic retry on token limit errors.
            Splits chunk in half if too large and returns 2 separate (text, embedding) pairs.
            
            Args:
                text: Text to embed
                depth: Recursion depth (to prevent infinite loops)
            
            Returns:
                List of (text, embedding) pairs - single item normally, 2+ items if split
            """
            if depth > 3:
                # Safety: prevent infinite recursion
                raise ValueError(f"Chunk too small to split further (depth={depth})")
            
            try:
                # Check artificial token limit for testing (if set)
                if self.max_input_tokens is not None:
                    estimated_tokens = len(text) // 4  # Rough estimate: 4 chars per token
                    if estimated_tokens > self.max_input_tokens:
                        # Simulate token limit error
                        raise Exception(f"400 Token limit exceeded: {estimated_tokens} > {self.max_input_tokens}")
                
                # Try to get embedding using new Google Gen AI SDK
                response = self.genai_client.models.embed_content(
                    model="text-embedding-005",
                    contents=text,
                )
                return [(text, response.embeddings[0].values)]
            
            except Exception as e:
                error_msg = str(e).lower()
                
                # Check if it's a token limit error (400 status)
                if "400" in error_msg or "token" in error_msg or "exceed" in error_msg:
                    stats["splits_performed"] += 1
                    stats["max_depth_reached"] = max(stats["max_depth_reached"], depth + 1)
                    
                    logger.debug(f"Chunk too large ({len(text)} chars), splitting (depth={depth})")
                    logger.debug(f"Split #{stats['splits_performed']}: {len(text)} chars → 2 sub-chunks")
                    
                    # Split chunk in half at nearest semantic boundary
                    mid = len(text) // 2
                    
                    # Try to find good split point near middle
                    split_point = mid
                    for separator in ['\n\n', '\n', '. ', ' ']:
                        # Search ±20% around midpoint
                        search_start = int(mid * 0.8)
                        search_end = int(mid * 1.2)
                        boundary = text[search_start:search_end].find(separator)
                        if boundary != -1:
                            split_point = search_start + boundary + len(separator)
                            break
                    
                    # Split and retry recursively
                    # Important: Add overlap between split chunks to maintain continuity
                    # Use same overlap as regular chunking (self.chunk_overlap)
                    overlap = min(self.chunk_overlap, split_point // 4)  # Max 25% of first chunk
                    
                    chunk1 = text[:split_point].strip()
                    chunk2_start = max(0, split_point - overlap)
                    chunk2 = text[chunk2_start:].strip()
                    
                    logger.debug(f"Split with {overlap} char overlap for continuity")
                    
                    pairs1 = _get_embedding_with_retry(chunk1, depth + 1)
                    pairs2 = _get_embedding_with_retry(chunk2, depth + 1)
                    
                    # Return BOTH chunks as separate items
                    logger.debug(f"Created {len(pairs1) + len(pairs2)} sub-chunks from split #{stats['splits_performed']}")
                    return pairs1 + pairs2
                else:
                    # Not a token error - re-raise
                    raise
        
        # Run in thread pool to avoid blocking asyncio event loop
        loop = asyncio.get_event_loop()
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            # Submit all tasks
            futures = [loop.run_in_executor(executor, _get_embedding_with_retry, text) for text in texts]
            
            # Wait for all to complete with timeout (2 minutes max)
            try:
                results = await asyncio.wait_for(
                    asyncio.gather(*futures),
                    timeout=120.0
                )
                # Flatten results (each result is a list of pairs)
                all_pairs = []
                for pairs in results:
                    all_pairs.extend(pairs)
                
                logger.info(f"Generated {len(all_pairs)} embeddings (from {len(texts)} original chunks)")
                if stats["splits_performed"] > 0:
                    logger.info(f"Splits performed: {stats['splits_performed']}, max depth: {stats['max_depth_reached']}")
            except asyncio.TimeoutError:
                logger.error(f"Timeout generating embeddings after 120s")
                raise TimeoutError("Embedding generation timeout (120s)")
        
        return all_pairs, stats

    
    async def process_document(
        self,
        file_content: bytes,
        filename: str = "unknown.pdf",
        file_type: str = "pdf",
        metadata: Optional[dict] = None,
    ) -> Tuple[str, List[Tuple[str, List[float], dict]], dict]:
        """
        Full pipeline: extract → chunk → embed
        
        Args:
            file_content: File content as bytes
            filename: Original filename for metadata
            file_type: File extension (pdf, txt) or MIME type
            metadata: Additional metadata to attach
        
        Returns:
            Tuple of (extracted_text, list of (chunk_text, embedding, metadata) tuples, embedding_stats)
        """
        # Extract text based on file type
        text = self.extract_text(file_content, file_type)
        
        # Validate extracted text
        if not text.strip():
            raise ValueError(f"Could not extract text from {filename}")
        
        # Chunk text
        chunks = self.chunk_text(text)
        logger.debug(f"Prepared {len(chunks)} chunks for embedding")
        
        # Generate embeddings (parallel processing)
        # Returns list of (text, embedding) pairs - may be MORE than len(chunks) if splits occurred
        chunk_texts = [chunk[0] for chunk in chunks]
        logger.debug(f"Calling generate_embeddings() for {len(chunk_texts)} chunks")
        pairs, embedding_stats = await self.generate_embeddings(chunk_texts)
        logger.debug(f"Embeddings generated: {len(pairs)} pairs")
        
        # Combine with metadata
        # Note: We need to re-index because splits may have created extra chunks
        results = []
        base_metadata = metadata or {}
        
        for idx, (chunk_text, embedding) in enumerate(pairs):
            combined_meta = {
                **base_metadata,
                "chunk_index": idx,
                "chunk_size": len(chunk_text),
                "source_file": filename,
                "embedding_provider": self.embedding_provider.value,
            }
            results.append((chunk_text, embedding, combined_meta))
        
        # Return extracted text + chunks with embeddings + stats
        return text, results, embedding_stats


# Convenience function for default provider
def create_processor(provider: str = "vertex_ai") -> DocumentProcessor:
    """
    Create document processor with specified provider
    
    Args:
        provider: "vertex_ai" or "sentence_transformers"
    
    Returns:
        DocumentProcessor instance
    """
    provider_enum = EmbeddingProvider(provider)
    return DocumentProcessor(embedding_provider=provider_enum)
