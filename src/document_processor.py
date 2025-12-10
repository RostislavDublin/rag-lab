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
from typing import List, Tuple, Optional
from enum import Enum

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
            return txt_source.decode('utf-8')
        else:
            with open(txt_source, 'r', encoding='utf-8') as f:
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
        # Simple character-based chunking
        # TODO: Implement smarter sentence-aware chunking
        
        chunks = []
        start = 0
        
        while start < len(text):
            end = start + self.chunk_size
            chunk = text[start:end]
            
            # Find last complete sentence in chunk
            if end < len(text):
                last_period = chunk.rfind('.')
                last_newline = chunk.rfind('\n')
                boundary = max(last_period, last_newline)
                
                if boundary > 0:
                    end = start + boundary + 1
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
        
        return chunks
    
    def generate_embeddings(self, texts: List[str]) -> List[List[float]]:
        """
        Generate embeddings for text chunks
        
        Args:
            texts: List of text chunks
        
        Returns:
            List of embedding vectors
        """
        if self.embedding_provider == EmbeddingProvider.VERTEX_AI:
            # Process each chunk individually to avoid token limits
            embeddings = []
            for text in texts:
                emb = self.embedding_model.get_embeddings([text])
                embeddings.append(emb[0].values)
            return embeddings
        
        elif self.embedding_provider == EmbeddingProvider.SENTENCE_TRANSFORMERS:
            # Local model
            embeddings = self.embedding_model.encode(texts)
            return embeddings.tolist()
        
        else:
            raise ValueError(f"Provider {self.embedding_provider} not implemented")
    
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
        
        # Generate embeddings
        chunk_texts = [chunk[0] for chunk in chunks]
        embeddings = self.generate_embeddings(chunk_texts)
        
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
