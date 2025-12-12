"""
RAG Lab - FastAPI application for RAG-as-a-Service

Production-ready API for Retrieval Augmented Generation using:
- Vertex AI (embeddings, Gemini for generation)
- PostgreSQL + pgvector (vector storage and search)
- FastAPI (async REST API)
- Cloud Run (deployment target)

Architecture:
- Multi-cloud portable (PostgreSQL works on GCP/AWS/Azure)
- Can migrate to GKE without code changes (same Docker container)
- Two-level storage: original documents + searchable chunks
"""

import asyncio
import os
import warnings
from contextlib import asynccontextmanager
from datetime import datetime
from typing import List, Optional
from pathlib import Path

# Load environment variables from .env.local (local dev) or .env (production)
from dotenv import load_dotenv

# Load .env.local first (highest priority), then .env as fallback
env_local = Path(__file__).parent.parent / ".env.local"
env_file = Path(__file__).parent.parent / ".env"

if env_local.exists():
    print(f"Loading environment from: {env_local}")
    load_dotenv(env_local, override=True)
elif env_file.exists():
    print(f"Loading environment from: {env_file}")
    load_dotenv(env_file, override=True)
else:
    print("WARNING: No .env.local or .env file found - using system environment variables only")

import vertexai
from fastapi import FastAPI, HTTPException, UploadFile, File, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from google import genai
from google.genai.types import EmbedContentConfig, HttpOptions

# Import utilities
from .utils import calculate_file_hash
from .file_validator import FileValidator

from .database import vector_db
from .document_processor import DocumentProcessor, EmbeddingProvider
from .storage import DocumentStorage

# Configuration from environment variables
PROJECT_ID = os.getenv("GCP_PROJECT_ID", "your-project-id")
LOCATION = os.getenv("GCP_LOCATION", "us-central1")
PORT = int(os.getenv("PORT", "8080"))
GCS_BUCKET = os.getenv("GCS_BUCKET", "raglab-documents")

# Version tracking
APP_VERSION = "0.2.0"
APP_START_TIME = datetime.utcnow().isoformat() + "Z"

# Initialize storage with env bucket
document_storage = DocumentStorage(bucket_name=GCS_BUCKET)

# Global instances
genai_client = None
document_processor = None
file_validator = FileValidator()  # Initialize file validator


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize and cleanup resources"""
    global genai_client, document_processor
    
    # Startup: Initialize Vertex AI with new Google Gen AI SDK
    print(f"Initializing Google Gen AI (project={PROJECT_ID}, location={LOCATION})...")
    vertexai.init(project=PROJECT_ID, location=LOCATION)
    genai_client = genai.Client(vertexai=True, project=PROJECT_ID, location=LOCATION)
    print("Google Gen AI client initialized successfully")
    
    # Initialize database
    print("Connecting to database...")
    await vector_db.connect()
    await vector_db.init_schema()
    print("Database initialized successfully")
    
    # Initialize document processor with genai client
    document_processor = DocumentProcessor(
        embedding_provider=EmbeddingProvider.VERTEX_AI,
        genai_client=genai_client
    )
    print("Document processor initialized")
    
    yield
    
    # Shutdown: Cleanup resources
    print("Shutting down...")
    await vector_db.disconnect()
    genai_client = None
    document_processor = None


# FastAPI app
app = FastAPI(
    title="RAG Lab API",
    description="Production RAG-as-a-Service with Vertex AI",
    version=APP_VERSION,
    lifespan=lifespan,
)

# CORS middleware for frontend integration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure properly in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Request/Response models
class HealthResponse(BaseModel):
    status: str
    project_id: str
    location: str
    version: str
    started_at: str
    uptime_seconds: float


class EmbeddingRequest(BaseModel):
    text: str = Field(..., description="Text to embed", min_length=1)


class EmbeddingResponse(BaseModel):
    embedding: List[float]
    dimension: int


class QueryRequest(BaseModel):
    query: str = Field(..., description="User query", min_length=1)
    top_k: int = Field(default=5, ge=1, le=20, description="Number of results")
    min_similarity: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="Minimum similarity threshold (0.0-1.0). Results below this are filtered out."
    )


class QueryResultItem(BaseModel):
    chunk_text: str
    similarity: float
    chunk_index: int
    filename: str
    original_doc_id: int
    doc_uuid: str
    doc_metadata: dict
    download_url: Optional[str] = None


class QueryResponse(BaseModel):
    query: str
    results: List[QueryResultItem]
    total: int


class DocumentUploadResponse(BaseModel):
    doc_id: int
    doc_uuid: str
    filename: str
    file_hash: str = Field(..., description="SHA256 hash of file content (64 hex chars)")
    chunks_created: int
    splits_performed: int = Field(default=0, description="Number of chunk splits due to token limit")
    max_split_depth: int = Field(default=0, description="Maximum recursion depth during splitting")
    message: str


class DocumentDeleteResponse(BaseModel):
    doc_id: int
    filename: str
    chunks_deleted: int
    message: str


class DocumentInfo(BaseModel):
    doc_id: int
    doc_uuid: str
    filename: str
    file_type: str
    file_size: int
    file_hash: str = Field(..., description="SHA256 hash of file content (64 hex chars)")
    chunk_count: int
    uploaded_at: str


class DocumentListResponse(BaseModel):
    total: int
    documents: List[DocumentInfo]


class ChunkInfo(BaseModel):
    chunk_index: int
    chunk_text: str
    start_char: Optional[int] = None
    end_char: Optional[int] = None


class DocumentChunksResponse(BaseModel):
    doc_id: int
    filename: str
    total_chunks: int
    chunks: List[ChunkInfo]


# Routes
@app.get("/", response_model=dict)
async def root():
    """Root endpoint"""
    return {
        "service": "RAG Lab API",
        "version": APP_VERSION,
        "status": "running",
        "docs": "/docs",
    }


@app.get("/health", response_model=HealthResponse)
async def health():
    """Health check endpoint for Cloud Run"""
    start_time = datetime.fromisoformat(APP_START_TIME.rstrip('Z'))
    uptime = (datetime.utcnow() - start_time).total_seconds()
    
    return HealthResponse(
        status="healthy",
        project_id=PROJECT_ID,
        location=LOCATION,
        version=APP_VERSION,
        started_at=APP_START_TIME,
        uptime_seconds=round(uptime, 2),
    )


@app.post("/v1/documents/upload", response_model=DocumentUploadResponse)
async def upload_document(file: UploadFile = File(...)):
    """
    Upload and process document (PDF or TXT)
    
    - Stores original file
    - Extracts text
    - Chunks content
    - Generates embeddings
    - Stores in two-level architecture (original + chunks)
    
    Supported formats:
    - PDF: .pdf
    - Text: .txt, .md, .markdown, .rst, .log
    - Data: .json, .csv, .xml, .yaml, .yml, .toml, .ini
    - Code: .py, .js, .html, .css
    
    Example:
        POST /v1/documents/upload
        Content-Type: multipart/form-data
        file: document.pdf
    """
    try:
        # Read file content first (needed for validation)
        file_content = await file.read()
        
        # VALIDATION: Multi-tier file validation (strict/structured/lenient)
        # This is the quality gate for RAG system
        # Better to reject bad input once than get bad search results forever
        validation_result = file_validator.validate(file.filename, file_content)
        
        # Determine processing type based on validation
        if validation_result.format_type == "pdf":
            file_type = "pdf"
            content_type = "application/pdf"
        else:
            # All other formats processed as text (including JSON→YAML, XML→YAML)
            file_type = "txt"
            content_type = "text/plain"
        
        # Calculate file hash for deduplication (using shared utility)
        file_hash = calculate_file_hash(file_content)
        
        # Check if document already exists
        existing = await vector_db.check_document_exists(file_hash)
        if existing:
            doc_id, doc_uuid, existing_filename = existing
            print(f"Document already exists: ID={doc_id}, UUID={doc_uuid}, original={existing_filename}")
            return DocumentUploadResponse(
                doc_id=doc_id,
                doc_uuid=doc_uuid,
                filename=existing_filename,
                file_hash=file_hash,
                chunks_created=0,
                splits_performed=0,
                max_split_depth=0,
                message=f"Document already exists (uploaded as '{existing_filename}'). Skipping duplicate."
            )
        
        # Extract text from document
        print(f"Processing document: {file.filename} ({file_type})")
        extracted_text = document_processor.extract_text(file_content, file_type)
        print(f"Extracted {len(extracted_text)} characters")
        
        if not extracted_text.strip():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Could not extract text from document"
            )
        
        # Process chunks and embeddings FIRST (before DB record)
        print(f"Starting chunking and embedding generation...")
        chunks_data, embedding_stats = await document_processor.process_document(
            file_content=file_content,
            filename=file.filename,
            file_type=file_type
        )
        print(f"Generated {len(chunks_data)} chunks with embeddings")
        
        # Validate we got chunks
        if not chunks_data:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Document too short or could not generate chunks"
            )
        
        # Prepare chunks for GCS
        gcs_chunks = []
        embeddings_only = []
        
        for chunk_text, embedding, chunk_metadata in chunks_data:
            gcs_chunks.append({
                "text": chunk_text,
                "index": chunk_metadata["chunk_index"],
                "metadata": chunk_metadata
            })
            embeddings_only.append(embedding)
        
        # Create DB record (generates UUID) - AFTER validation
        doc_id, doc_uuid = await vector_db.insert_original_document(
            filename=file.filename,
            file_type=content_type,
            file_size=len(file_content),
            file_hash=file_hash,
            metadata={"original_filename": file.filename}
        )
        print(f"Created document record: ID={doc_id}, UUID={doc_uuid}")
        
        try:
            # Upload all files to GCS (parallel)
            await document_storage.upload_document(
                doc_uuid=doc_uuid,
                pdf_bytes=file_content,
                extracted_text=extracted_text,
                chunks=gcs_chunks,
                file_type=file_type
            )
            print(f"Uploaded {len(gcs_chunks)} files to GCS: {doc_uuid}/")
            
            # Store only embeddings in PostgreSQL
            for i, embedding in enumerate(embeddings_only):
                await vector_db.insert_chunk(
                    original_doc_id=doc_id,
                    embedding=embedding,
                    chunk_index=i
                )
            
            # Update chunk count
            await vector_db.update_chunk_count(doc_id, len(gcs_chunks))
            
        except Exception as e:
            # Rollback: delete DB record and GCS files
            print(f"Upload failed, rolling back: {e}")
            try:
                await document_storage.delete_document(doc_uuid)
            except Exception:
                pass  # GCS cleanup failed, but continue to delete DB
            await vector_db.delete_document(doc_id)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Document upload failed: {str(e)}"
            )
        
        print(f"Stored {len(gcs_chunks)} embeddings for document {file.filename}")
        
        return DocumentUploadResponse(
            doc_id=doc_id,
            doc_uuid=doc_uuid,
            filename=file.filename,
            file_hash=file_hash,
            chunks_created=len(gcs_chunks),
            splits_performed=embedding_stats.get("splits_performed", 0),
            max_split_depth=embedding_stats.get("max_depth_reached", 0),
            message=f"Document processed successfully: {len(gcs_chunks)} chunks created"
        )
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Document processing failed: {str(e)}",
        )


@app.post("/v1/embed", response_model=EmbeddingResponse)
async def create_embedding(request: EmbeddingRequest):
    """
    Generate text embeddings using Vertex AI
    
    Example:
        POST /v1/embed
        {
            "text": "What is RAG?"
        }
    """
    try:
        if genai_client is None:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Embedding model not initialized",
            )
        
        # Generate embedding using new Google Gen AI SDK
        response = genai_client.models.embed_content(
            model="text-embedding-005",
            contents=request.text,
        )
        embedding_vector = response.embeddings[0].values
        
        return EmbeddingResponse(
            embedding=embedding_vector,
            dimension=len(embedding_vector),
        )
    
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Embedding generation failed: {str(e)}",
        )


@app.post("/v1/query", response_model=QueryResponse)
async def query_rag(request: QueryRequest):
    """
    Query RAG system with semantic search and relevance filtering
    
    **Two-level retrieval process:**
    1. Generate query embedding using Vertex AI text-embedding-005
    2. Vector search in PostgreSQL (cosine similarity)
    3. Filter by similarity threshold (optional)
    4. Fetch chunk texts from GCS (parallel)
    5. Return ranked results with metadata
    
    **Parameters:**
    - `query` (str): Natural language query
    - `top_k` (int): Maximum number of results (1-20, default: 5)
    - `min_similarity` (float): Minimum similarity threshold 0.0-1.0 (default: 0.0)
      - 0.0 = no filtering (returns all top_k results)
      - 0.5 = moderate filter (good for production - filters irrelevant docs)
      - 0.7 = strict filter (only highly relevant results)
    
    **Similarity threshold benefits:**
    - Filters out irrelevant user documents in shared databases
    - Prevents low-quality results from polluting responses
    - "Better fewer good results than many bad ones"
    - Useful for multi-tenant deployments
    
    **Example with filtering:**
    ```json
    {
        "query": "Which smartphone has the best camera?",
        "top_k": 5,
        "min_similarity": 0.5
    }
    ```
    
    **Example without filtering:**
    ```json
    {
        "query": "What is RAG?",
        "top_k": 3
    }
    ```
    
    **Response includes:**
    - `chunk_text`: Actual text content from document
    - `similarity`: Cosine similarity score (0.0-1.0, higher = more relevant)
    - `filename`: Original document name
    - `chunk_index`: Position in document (0-based)
    - `doc_uuid`: Globally unique document identifier
    - `doc_metadata`: Custom metadata from upload
    """
    try:
        if genai_client is None:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Embedding model not initialized",
            )
        
        # Generate query embedding using new Google Gen AI SDK
        response = genai_client.models.embed_content(
            model="text-embedding-005",
            contents=request.query,
        )
        query_embedding = response.embeddings[0].values
        
        # Vector search (returns chunk indices + doc_uuid)
        results = await vector_db.search_similar_chunks(
            query_embedding=query_embedding,
            top_k=request.top_k,
            min_similarity=request.min_similarity
        )
        
        # Group by document UUID for efficient GCS fetching
        chunks_by_doc = {}
        for result in results:
            doc_uuid = result["doc_uuid"]
            if doc_uuid not in chunks_by_doc:
                chunks_by_doc[doc_uuid] = []
            chunks_by_doc[doc_uuid].append(result)
        
        # Fetch chunk texts from GCS (parallel across all documents)
        async def fetch_doc_chunks(doc_uuid, doc_results):
            try:
                chunk_indices = [r["chunk_index"] for r in doc_results]
                chunk_texts = await document_storage.fetch_chunks(doc_uuid, chunk_indices)
                for result, text in zip(doc_results, chunk_texts):
                    result["chunk_text"] = text
            except Exception as e:
                # If GCS fetch fails, mark chunks with error
                print(f"Failed to fetch chunks for {doc_uuid}: {e}")
                for result in doc_results:
                    result["chunk_text"] = f"[Error: chunk not available - {str(e)}]"
                    result["fetch_error"] = True
        
        # Use return_exceptions to continue even if some documents fail
        await asyncio.gather(*[
            fetch_doc_chunks(doc_uuid, doc_results)
            for doc_uuid, doc_results in chunks_by_doc.items()
        ], return_exceptions=True)
        
        # Format final response
        # Note: download_url can be obtained separately via GET /v1/documents/{doc_id}/download
        formatted_results = []
        for result in results:
            formatted_results.append(QueryResultItem(
                chunk_text=result["chunk_text"],
                similarity=result["similarity"],
                chunk_index=result["chunk_index"],
                filename=result["filename"],
                original_doc_id=result["original_doc_id"],
                doc_uuid=result["doc_uuid"],
                doc_metadata=result["doc_metadata"],
                download_url=None,  # Use separate endpoint for signed URLs
            ))
        
        return QueryResponse(
            query=request.query,
            results=formatted_results,
            total=len(formatted_results),
        )
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Query failed: {str(e)}",
        )


@app.get("/v1/documents/{doc_id}/download")
async def download_document(doc_id: int, format: str = "original"):
    """
    Download document in specified format
    
    Args:
        doc_id: Document ID
        format: Download format
            - "original": Original uploaded file (PDF/TXT) [default]
            - "extracted": Extracted text in Markdown format (from pymupdf4llm)
    
    Examples:
        GET /v1/documents/1/download              # Original file
        GET /v1/documents/1/download?format=original
        GET /v1/documents/1/download?format=extracted  # Markdown text
    """
    try:
        from fastapi.responses import Response
        
        # Validate format parameter
        if format not in ["original", "extracted"]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid format '{format}'. Must be 'original' or 'extracted'",
            )
        
        # Get document info
        doc_info = await vector_db.get_original_document(doc_id)
        if not doc_info:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Document with id {doc_id} not found",
            )
        
        doc_uuid = doc_info["doc_uuid"]
        filename = doc_info["filename"]
        file_type = doc_info["file_type"]
        
        if format == "extracted":
            # Fetch extracted text (Markdown from pymupdf4llm)
            content = await document_storage.fetch_extracted_text(doc_uuid)
            content_bytes = content.encode('utf-8')
            media_type = "text/plain; charset=utf-8"
            
            # Generate filename: "document.pdf" -> "document_extracted.txt"
            base_name = filename.rsplit('.', 1)[0] if '.' in filename else filename
            download_filename = f"{base_name}_extracted.txt"
        else:
            # Fetch original file from GCS
            content_bytes = await document_storage.fetch_original_file(doc_uuid, file_type="pdf")
            
            # Determine media type from stored file_type
            if "pdf" in file_type.lower():
                media_type = "application/pdf"
            else:
                media_type = "text/plain"
            
            download_filename = filename
        
        # Return file with proper headers
        # RFC 5987 encoding for non-ASCII filenames
        from urllib.parse import quote
        encoded_filename = quote(download_filename)
        
        return Response(
            content=content_bytes,
            media_type=media_type,
            headers={
                "Content-Disposition": f"attachment; filename*=UTF-8''{encoded_filename}"
            }
        )
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to download document: {str(e)}",
        )


@app.get("/v1/documents/{doc_id}/chunks", response_model=DocumentChunksResponse)
async def get_document_chunks(doc_id: int):
    """
    Get all chunks for a document in order
    
    Returns all chunks with their text and metadata in sequential order (0, 1, 2, ...).
    Useful for:
    - Verifying chunking pipeline integrity
    - Comparing extracted text vs. concatenated chunks
    - Testing that chunk ordering is preserved
    
    Example:
        GET /v1/documents/72/chunks
    """
    try:
        # Get document info
        doc_info = await vector_db.get_original_document(doc_id)
        if not doc_info:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Document with id {doc_id} not found",
            )
        
        doc_uuid = doc_info["doc_uuid"]
        filename = doc_info["filename"]
        chunk_count = doc_info["chunk_count"]
        
        # Fetch all chunks in order
        chunk_indices = list(range(chunk_count))
        chunks_data = await document_storage.fetch_chunks_with_metadata(doc_uuid, chunk_indices)
        
        # Build response
        chunks_info = []
        for chunk_data in chunks_data:
            metadata = chunk_data.get("metadata", {})
            chunks_info.append(ChunkInfo(
                chunk_index=chunk_data["index"],
                chunk_text=chunk_data["text"],
                start_char=metadata.get("start_char"),
                end_char=metadata.get("end_char")
            ))
        
        return DocumentChunksResponse(
            doc_id=doc_id,
            filename=filename,
            total_chunks=chunk_count,
            chunks=chunks_info
        )
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch chunks: {str(e)}",
        )


@app.get("/v1/documents/by-hash/{file_hash}", response_model=DocumentInfo)
async def get_document_by_hash(file_hash: str):
    """
    Get document info by SHA256 file hash
    
    Returns document metadata without downloading file content.
    Useful for checking if document exists before upload.
    """
    try:
        # Validate hash format
        if len(file_hash) != 64 or not all(c in "0123456789abcdef" for c in file_hash.lower()):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid hash format. Expected 64 lowercase hexadecimal characters (SHA256)",
            )
        
        async with vector_db.pool.acquire() as conn:
            row = await conn.fetchrow("""
                SELECT id, doc_uuid, filename, file_type, file_size, file_hash, chunk_count, uploaded_at
                FROM original_documents
                WHERE file_hash = $1
            """, file_hash.lower())
        
        if not row:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Document with hash {file_hash} not found",
            )
        
        return DocumentInfo(
            doc_id=row["id"],
            doc_uuid=str(row["doc_uuid"]),
            filename=row["filename"],
            file_type=row["file_type"],
            file_size=row["file_size"],
            file_hash=row["file_hash"],
            chunk_count=row["chunk_count"],
            uploaded_at=row["uploaded_at"].isoformat(),
        )
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get document: {str(e)}",
        )


@app.get("/v1/documents", response_model=DocumentListResponse)
async def list_documents():
    """
    List all documents in the system
    
    Returns metadata for all uploaded documents.
    
    Example:
        GET /v1/documents
    """
    try:
        async with vector_db.pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT 
                    id, doc_uuid, filename, file_type, file_size, file_hash,
                    chunk_count, uploaded_at
                FROM original_documents
                ORDER BY uploaded_at DESC
            """)
        
        documents = [
            DocumentInfo(
                doc_id=row["id"],
                doc_uuid=str(row["doc_uuid"]),
                filename=row["filename"],
                file_type=row["file_type"],
                file_size=row["file_size"],
                file_hash=row["file_hash"],
                chunk_count=row["chunk_count"],
                uploaded_at=row["uploaded_at"].isoformat(),
            )
            for row in rows
        ]
        
        return DocumentListResponse(
            total=len(documents),
            documents=documents,
        )
    
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to list documents: {str(e)}",
        )


@app.delete("/v1/documents/{doc_id}", response_model=DocumentDeleteResponse)
async def delete_document(doc_id: int):
    """
    Delete document and all its chunks
    
    Removes from both PostgreSQL and GCS storage.
    
    Example:
        DELETE /v1/documents/1
    """
    try:
        # Get document info before deletion
        doc_info = await vector_db.get_original_document(doc_id)
        if not doc_info:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Document with id {doc_id} not found",
            )
        
        filename = doc_info["filename"]
        doc_uuid = doc_info["doc_uuid"]
        chunk_count = doc_info["chunk_count"]
        
        # Delete from GCS
        try:
            await document_storage.delete_document(doc_uuid)
            print(f"Deleted GCS files for {doc_uuid}")
        except Exception as e:
            print(f"Warning: GCS deletion failed for {doc_uuid}: {e}")
            # Continue with DB deletion even if GCS fails
        
        # Delete from database (cascades to chunks)
        await vector_db.delete_document(doc_id)
        
        return DocumentDeleteResponse(
            doc_id=doc_id,
            filename=filename,
            chunks_deleted=chunk_count,
            message=f"Document '{filename}' deleted successfully ({chunk_count} chunks removed)",
        )
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Document deletion failed: {str(e)}",
        )


@app.delete("/v1/documents/by-hash/{file_hash}", response_model=DocumentDeleteResponse)
async def delete_document_by_hash(file_hash: str):
    """
    Delete document by SHA256 file hash
    
    Useful for automated cleanup when you know file content but not database ID.
    
    **Hash Calculation (Python):**
    ```python
    import hashlib
    with open("file.pdf", "rb") as f:  # Binary mode required!
        file_hash = hashlib.sha256(f.read()).hexdigest()
    ```
    
    **Hash Calculation (bash):**
    ```bash
    shasum -a 256 document.pdf | cut -d' ' -f1
    ```
    
    **Important:** Use binary mode (`rb`), not text mode. Hash must be 64 lowercase hex chars.
    """
    try:
        # Validate hash format (64 hex characters)
        if len(file_hash) != 64 or not all(c in "0123456789abcdef" for c in file_hash.lower()):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid hash format. Expected 64 lowercase hexadecimal characters (SHA256)",
            )
        
        # Delete by hash (returns info about deleted document)
        deleted_info = await vector_db.delete_document_by_hash(file_hash.lower())
        
        if not deleted_info:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Document with hash {file_hash} not found",
            )
        
        doc_uuid = deleted_info["doc_uuid"]
        filename = deleted_info["filename"]
        chunk_count = deleted_info["chunk_count"]
        doc_id = deleted_info["id"]
        
        # Delete from GCS
        try:
            await document_storage.delete_document(doc_uuid)
            print(f"Deleted GCS files for {doc_uuid} (hash: {file_hash})")
        except Exception as e:
            print(f"Warning: GCS deletion failed for {doc_uuid}: {e}")
            # Continue even if GCS fails (DB already deleted)
        
        return DocumentDeleteResponse(
            doc_id=doc_id,
            filename=filename,
            chunks_deleted=chunk_count,
            message=f"Document '{filename}' deleted successfully by hash ({chunk_count} chunks removed)",
        )
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Document deletion by hash failed: {str(e)}",
        )


@app.get("/v1/documents/{doc_uuid}/chunks/{chunk_index}/context")
async def get_chunk_context(
    doc_uuid: str,
    chunk_index: int,
    before: int = 1,
    after: int = 1,
):
    """
    Get chunk with surrounding context, reconstructed from original text.
    
    Returns continuous text from chunk N-before to chunk N+after,
    WITHOUT overlaps (uses start_char/end_char from original document).
    
    Example:
        GET /v1/documents/{uuid}/chunks/5/context?before=2&after=2
        
        Returns chunks 3, 4, 5, 6, 7 as one continuous text block.
    
    Args:
        doc_uuid: Document UUID
        chunk_index: Target chunk index (0-based)
        before: Number of chunks before target (default: 1)
        after: Number of chunks after target (default: 1)
    
    Returns:
        {
            "doc_uuid": str,
            "filename": str,
            "target_chunk_index": int,
            "context_range": [start_index, end_index],
            "text": str,  # Continuous text without overlaps
            "chunks_included": int
        }
    """
    try:
        # Validate parameters
        if before < 0 or after < 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="before and after must be >= 0"
            )
        
        # Get document info
        doc_info = await vector_db.get_document_by_uuid(doc_uuid)
        if not doc_info:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Document {doc_uuid} not found"
            )
        
        chunk_count = doc_info["chunk_count"]
        
        # Validate chunk_index
        if chunk_index < 0 or chunk_index >= chunk_count:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"chunk_index {chunk_index} out of range [0, {chunk_count-1}]"
            )
        
        # Calculate range (clamped to document bounds)
        start_idx = max(0, chunk_index - before)
        end_idx = min(chunk_count - 1, chunk_index + after)
        
        # Fetch chunk metadata from GCS to get start_char/end_char
        chunk_indices = list(range(start_idx, end_idx + 1))
        chunks = await document_storage.fetch_chunks_with_metadata(doc_uuid, chunk_indices)
        
        # Get original extracted text
        extracted_text = await document_storage.fetch_extracted_text(doc_uuid)
        
        # Find min start_char and max end_char from chunk metadata
        min_start = None
        max_end = None
        
        for chunk_data in chunks:
            metadata = chunk_data.get("metadata", {})
            start_char = metadata.get("start_char")
            end_char = metadata.get("end_char")
            
            if start_char is not None and end_char is not None:
                if min_start is None or start_char < min_start:
                    min_start = start_char
                if max_end is None or end_char > max_end:
                    max_end = end_char
        
        # Fallback: if no start_char/end_char, concatenate chunk texts
        if min_start is None or max_end is None:
            # Chunks don't have start_char/end_char metadata (shouldn't happen with current code)
            # Fall back to concatenating texts
            continuous_text = "\n\n".join(chunk["text"] for chunk in chunks)
        else:
            # Extract continuous text from original (NO overlaps!)
            continuous_text = extracted_text[min_start:max_end]
        
        return {
            "doc_uuid": doc_uuid,
            "filename": doc_info["filename"],
            "target_chunk_index": chunk_index,
            "context_range": [start_idx, end_idx],
            "text": continuous_text,
            "chunks_included": len(chunk_indices),
        }
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get chunk context: {str(e)}",
        )


@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    """Global exception handler"""
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "error": "Internal server error",
            "detail": str(exc),
        },
    )


if __name__ == "__main__":
    import uvicorn
    
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=PORT,
        reload=True,  # Development only
    )
