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
from typing import List, Tuple, Optional
from enum import Enum
from concurrent.futures import ThreadPoolExecutor

import pymupdf  # PyMuPDF for PDF processing

# Suppress vertexai deprecation warning - we're using the recommended API
warnings.filterwarnings('ignore', message='.*deprecated as of June 24, 2025.*')
from vertexai.language_models import TextEmbeddingModel


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
        chunk_size: int = 500,
        chunk_overlap: int = 50,
    ):
        self.embedding_provider = embedding_provider
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        
        # Initialize embedding model based on provider
        if embedding_provider == EmbeddingProvider.VERTEX_AI:
            self.embedding_model = TextEmbeddingModel.from_pretrained("text-embedding-005")
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
        Extract text from PDF using PyMuPDF
        
        Args:
            pdf_source: Path to PDF file (str) or PDF bytes (bytes)
        
        Returns:
            Extracted text
        """
        # Open PDF from path or bytes
        if isinstance(pdf_source, bytes):
            doc = pymupdf.open(stream=pdf_source, filetype="pdf")
        else:
            doc = pymupdf.open(pdf_source)
        
        text = ""
        
        for page_num, page in enumerate(doc):
            page_text = page.get_text()
            text += f"\n--- Page {page_num + 1} ---\n{page_text}"
        
        doc.close()
        return text
    
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
                print(f"Warning: UTF-8 decode failed, using latin-1")
                return txt_source.decode('latin-1', errors='replace')
        else:
            with open(txt_source, 'r', encoding='utf-8', errors='replace') as f:
                return f.read()
    
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
        
        if file_ext in ('pdf', 'application/pdf'):
            return self.extract_text_from_pdf(file_content)
        elif file_ext in ('txt', 'text/plain'):
            return self.extract_text_from_txt(file_content)
        else:
            raise ValueError(f"Unsupported file type: {file_type}")
    
    def chunk_text(self, text: str) -> List[Tuple[str, dict]]:
        """
        Split text into overlapping chunks
        
        Args:
            text: Input text to chunk
        
        Returns:
            List of (chunk_text, metadata) tuples
        """
        print(f"Chunking text ({len(text)} chars, chunk_size={self.chunk_size}, overlap={self.chunk_overlap})...")
        
        # Simple character-based chunking
        # TODO: Implement smarter sentence-aware chunking
        
        chunks = []
        start = 0
        
        while start < len(text):
            end = start + self.chunk_size
            chunk = text[start:end]
            
            # Try to find good boundaries in order of preference:
            # 1. Double newline (paragraph boundary)
            # 2. Single newline (line boundary)
            # 3. Period followed by space (sentence boundary)
            # 4. Space (word boundary)
            # 5. Take full chunk_size (for code/JSON/continuous text)
            
            if end < len(text):
                boundaries = [
                    chunk.rfind('\n\n'),      # Paragraph
                    chunk.rfind('\n'),        # Line
                    chunk.rfind('. '),        # Sentence (period + space, not just period)
                    chunk.rfind(' '),         # Word
                ]
                
                # Use first boundary that's far enough from start (min 100 chars)
                best_boundary = -1
                for boundary in boundaries:
                    if boundary > 100:
                        best_boundary = boundary
                        break
                
                if best_boundary > 0:
                    # +1 to include the separator character
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
            
            # Move start position with overlap
            start = end - self.chunk_overlap
        
        print(f"Created {len(chunks)} chunks")
        return chunks
    
    async def generate_embeddings(self, texts: List[str]) -> List[List[float]]:
        """
        Generate embeddings for text chunks (with parallel processing)
        
        Args:
            texts: List of text chunks
        
        Returns:
            List of embedding vectors
        """
        if self.embedding_provider == EmbeddingProvider.VERTEX_AI:
            # Process chunks in parallel (max 10 concurrent requests)
            return await self._generate_embeddings_parallel(texts, max_workers=10)
        
        elif self.embedding_provider == EmbeddingProvider.SENTENCE_TRANSFORMERS:
            # Local model - already efficient
            embeddings = self.embedding_model.encode(texts)
            return embeddings.tolist()
        
        else:
            raise ValueError(f"Provider {self.embedding_provider} not implemented")
    
    async def _generate_embeddings_parallel(self, texts: List[str], max_workers: int = 10) -> List[List[float]]:
        """
        Generate embeddings in parallel using ThreadPoolExecutor
        
        Args:
            texts: List of text chunks
            max_workers: Maximum concurrent API calls
        
        Returns:
            List of embedding vectors (preserves order)
        """
        print(f"Generating embeddings for {len(texts)} chunks (max {max_workers} parallel)...")
        
        def _get_embedding_sync(text: str) -> List[float]:
            """Synchronous wrapper for Vertex AI API call"""
            emb = self.embedding_model.get_embeddings([text])
            return emb[0].values
        
        # Run in thread pool to avoid blocking asyncio event loop
        loop = asyncio.get_event_loop()
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            # Submit all tasks
            futures = [loop.run_in_executor(executor, _get_embedding_sync, text) for text in texts]
            
            # Wait for all to complete with timeout (2 minutes max)
            try:
                embeddings = await asyncio.wait_for(
                    asyncio.gather(*futures),
                    timeout=120.0
                )
                print(f"✓ Generated {len(embeddings)} embeddings successfully")
            except asyncio.TimeoutError:
                print(f"✗ Timeout generating embeddings after 120s")
                raise TimeoutError("Embedding generation timeout (120s)")
        
        return list(embeddings)

    
    async def process_document(
        self,
        file_content: bytes,
        filename: str = "unknown.pdf",
        file_type: str = "pdf",
        metadata: Optional[dict] = None,
    ) -> List[Tuple[str, List[float], dict]]:
        """
        Full pipeline: extract → chunk → embed
        
        Args:
            file_content: File content as bytes
            filename: Original filename for metadata
            file_type: File extension (pdf, txt) or MIME type
            metadata: Additional metadata to attach
        
        Returns:
            List of (chunk_text, embedding, metadata) tuples
        """
        # Extract text based on file type
        text = self.extract_text(file_content, file_type)
        
        # Chunk text
        chunks = self.chunk_text(text)
        
        # Generate embeddings (parallel processing)
        chunk_texts = [chunk[0] for chunk in chunks]
        embeddings = await self.generate_embeddings(chunk_texts)
        
        # Combine with metadata
        results = []
        base_metadata = metadata or {}
        
        for (chunk_text, chunk_meta), embedding in zip(chunks, embeddings):
            combined_meta = {
                **base_metadata,
                **chunk_meta,
                "source_file": filename,
                "embedding_provider": self.embedding_provider.value,
            }
            results.append((chunk_text, embedding, combined_meta))
        
        return results


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
