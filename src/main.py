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
from typing import List, Optional

# Suppress vertexai deprecation warning - we're using the recommended API
warnings.filterwarnings('ignore', message='.*deprecated as of June 24, 2025.*')
import vertexai
from fastapi import FastAPI, HTTPException, UploadFile, File, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from vertexai.language_models import TextEmbeddingModel

from .database import vector_db
from .document_processor import DocumentProcessor, EmbeddingProvider
from .storage import DocumentStorage

# Configuration from environment variables
PROJECT_ID = os.getenv("GCP_PROJECT_ID", "your-project-id")
LOCATION = os.getenv("GCP_LOCATION", "us-central1")
PORT = int(os.getenv("PORT", "8080"))
GCS_BUCKET = os.getenv("GCS_BUCKET", "raglab-documents")

# Initialize storage with env bucket
document_storage = DocumentStorage(bucket_name=GCS_BUCKET)

# Global instances
text_embedding_model = None
document_processor = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize and cleanup resources"""
    global text_embedding_model, document_processor
    
    # Startup: Initialize Vertex AI
    print(f"Initializing Vertex AI (project={PROJECT_ID}, location={LOCATION})...")
    vertexai.init(project=PROJECT_ID, location=LOCATION)
    text_embedding_model = TextEmbeddingModel.from_pretrained("text-embedding-004")
    print("Vertex AI initialized successfully")
    
    # Initialize database
    print("Connecting to database...")
    await vector_db.connect()
    await vector_db.init_schema()
    print("Database initialized successfully")
    
    # Initialize document processor
    document_processor = DocumentProcessor(
        embedding_provider=EmbeddingProvider.VERTEX_AI
    )
    print("Document processor initialized")
    
    yield
    
    # Shutdown: Cleanup resources
    print("Shutting down...")
    await vector_db.disconnect()
    text_embedding_model = None
    document_processor = None


# FastAPI app
app = FastAPI(
    title="RAG Lab API",
    description="Production RAG-as-a-Service with Vertex AI",
    version="0.1.0",
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


class EmbeddingRequest(BaseModel):
    text: str = Field(..., description="Text to embed", min_length=1)


class EmbeddingResponse(BaseModel):
    embedding: List[float]
    dimension: int


class QueryRequest(BaseModel):
    query: str = Field(..., description="User query", min_length=1)
    top_k: int = Field(default=5, ge=1, le=20, description="Number of results")


class QueryResponse(BaseModel):
    query: str
    results: List[dict]
    total: int


class DocumentUploadResponse(BaseModel):
    doc_id: int
    doc_uuid: str
    filename: str
    chunks_created: int
    message: str


# Routes
@app.get("/", response_model=dict)
async def root():
    """Root endpoint"""
    return {
        "service": "RAG Lab API",
        "version": "0.1.0",
        "status": "running",
        "docs": "/docs",
    }


@app.get("/health", response_model=HealthResponse)
async def health():
    """Health check endpoint for Cloud Run"""
    return HealthResponse(
        status="healthy",
        project_id=PROJECT_ID,
        location=LOCATION,
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
    
    Supported formats: .pdf, .txt
    
    Example:
        POST /v1/documents/upload
        Content-Type: multipart/form-data
        file: document.pdf
    """
    try:
        # Validate file type before reading
        filename_lower = file.filename.lower()
        if not (filename_lower.endswith('.pdf') or filename_lower.endswith('.txt')):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Only PDF and TXT files are supported"
            )
        
        # Determine file type
        file_type = 'pdf' if filename_lower.endswith('.pdf') else 'txt'
        content_type = 'application/pdf' if file_type == 'pdf' else 'text/plain'
        
        # Read file content
        file_content = await file.read()
        
        # Validate file size (max 50MB to avoid memory issues)
        MAX_FILE_SIZE = 50 * 1024 * 1024  # 50MB
        if len(file_content) > MAX_FILE_SIZE:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail=f"File too large. Maximum size: {MAX_FILE_SIZE // (1024*1024)}MB"
            )
        
        # Calculate file hash for deduplication
        import hashlib
        file_hash = hashlib.sha256(file_content).hexdigest()
        
        # Check if document already exists
        existing = await vector_db.check_document_exists(file_hash)
        if existing:
            doc_id, doc_uuid, existing_filename = existing
            print(f"Document already exists: ID={doc_id}, UUID={doc_uuid}, original={existing_filename}")
            return DocumentUploadResponse(
                doc_id=doc_id,
                doc_uuid=doc_uuid,
                filename=existing_filename,
                chunks_created=0,
                message=f"Document already exists (uploaded as '{existing_filename}'). Skipping duplicate."
            )
        
        # Extract text from document
        print(f"Processing document: {file.filename} ({file_type})")
        extracted_text = document_processor.extract_text(file_content, file_type)
        
        if not extracted_text.strip():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Could not extract text from document"
            )
        
        # Process chunks and embeddings FIRST (before DB record)
        chunks_data = await document_processor.process_document(
            file_content=file_content,
            filename=file.filename,
            file_type=file_type
        )
        
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
                chunks=gcs_chunks
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
            chunks_created=len(gcs_chunks),
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
        if text_embedding_model is None:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Embedding model not initialized",
            )
        
        # Generate embedding
        embeddings = text_embedding_model.get_embeddings([request.text])
        embedding_vector = embeddings[0].values
        
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
    Query RAG system with two-level retrieval
    
    1. Generate query embedding
    2. Search similar chunks (vector search)
    3. Return chunks with references to original documents
    
    Example:
        POST /v1/query
        {
            "query": "What is RAG?",
            "top_k": 5
        }
    """
    try:
        if text_embedding_model is None:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Embedding model not initialized",
            )
        
        # Generate query embedding
        embeddings = text_embedding_model.get_embeddings([request.query])
        query_embedding = embeddings[0].values
        
        # Vector search (returns chunk indices + doc_uuid)
        results = await vector_db.search_similar_chunks(
            query_embedding=query_embedding,
            top_k=request.top_k
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
        formatted_results = []
        for result in results:
            formatted_results.append({
                "chunk_text": result["chunk_text"],
                "similarity": result["similarity"],
                "chunk_index": result["chunk_index"],
                "filename": result["filename"],
                "original_doc_id": result["original_doc_id"],
                "doc_uuid": result["doc_uuid"],
                "doc_metadata": result["doc_metadata"],
            })
        
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
