"""
Cloud Storage module for document and chunk storage

Handles all GCS operations for the RAG system:
- Upload PDF documents, extracted text, and chunks
- Fetch specific chunks by UUID and index
- Delete documents and all associated files
- Generate signed URLs for document downloads

Structure in GCS:
gs://bucket/
└── {doc_uuid}/
    ├── original             # Original file (PDF/TXT, no extension)
    ├── extracted.txt        # Full extracted text
    └── chunks/
        ├── 000.json        # {"text": "...", "index": 0, "metadata": {...}}
        ├── 001.json
        └── ...
"""

import asyncio
import json
from typing import List, Optional

from google.cloud import storage


class DocumentStorage:
    """Cloud Storage handler for RAG documents"""
    
    def __init__(self, bucket_name: str = "raglab-documents"):
        """
        Initialize GCS client
        
        Args:
            bucket_name: GCS bucket name (must be in same region as Cloud Run)
        """
        self.client = storage.Client()
        self.bucket = self.client.bucket(bucket_name)
        self.bucket_name = bucket_name
    
    def get_chunk_path(self, doc_uuid: str, chunk_index: int) -> str:
        """Construct GCS path for chunk"""
        return f"{doc_uuid}/chunks/{chunk_index:03d}.json"
    
    async def upload_document(
        self,
        doc_uuid: str,
        pdf_bytes: bytes,
        extracted_text: str,
        chunks: List[dict],
        file_type: str = "pdf",
    ):
        """
        Upload all document artifacts to GCS
        
        Args:
            doc_uuid: Document UUID (from PostgreSQL)
            pdf_bytes: Original file bytes (PDF or TXT)
            extracted_text: Extracted text
            chunks: List of chunk dicts with 'text' and 'index' fields
            file_type: File type ('pdf' or 'txt')
        
        Note: Always saves original file as 'document.pdf' regardless of actual type.
        The real filename is stored in PostgreSQL metadata.
        """
        # Upload tasks
        tasks = []
        
        # 1. Upload original file (always as 'original' regardless of type)
        content_type = "application/pdf" if file_type == "pdf" else "text/plain"
        
        tasks.append(self._upload(
            path=f"{doc_uuid}/original",
            content=pdf_bytes,
            content_type=content_type
        ))
        
        # 2. Upload extracted text
        tasks.append(self._upload(
            path=f"{doc_uuid}/extracted.txt",
            content=extracted_text.encode('utf-8'),
            content_type="text/plain"
        ))
        
        # 3. Upload all chunks (parallel)
        for chunk in chunks:
            chunk_json = json.dumps({
                "text": chunk["text"],
                "index": chunk["index"],
                "metadata": chunk.get("metadata", {})
            })
            tasks.append(self._upload(
                path=self.get_chunk_path(doc_uuid, chunk["index"]),
                content=chunk_json.encode('utf-8'),
                content_type="application/json"
            ))
        
        # Execute all uploads in parallel
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Check for failures
        errors = [r for r in results if isinstance(r, Exception)]
        if errors:
            raise Exception(f"Failed to upload {len(errors)} files: {errors[0]}")
    
    async def fetch_chunks(
        self,
        doc_uuid: str,
        chunk_indices: List[int]
    ) -> List[str]:
        """
        Fetch specific chunks from GCS
        
        Args:
            doc_uuid: Document UUID
            chunk_indices: List of chunk indices to fetch
        
        Returns:
            List of chunk texts in same order as indices
        """
        async def fetch_one(index: int) -> str:
            try:
                path = self.get_chunk_path(doc_uuid, index)
                blob = self.bucket.blob(path)
                
                # Check if exists before download
                exists = await asyncio.to_thread(blob.exists)
                if not exists:
                    raise FileNotFoundError(f"Chunk not found: {path}")
                
                content = await asyncio.to_thread(blob.download_as_bytes)
                chunk_data = json.loads(content)
                
                if "text" not in chunk_data:
                    raise ValueError(f"Invalid chunk format: missing 'text' field")
                
                return chunk_data["text"]
            except json.JSONDecodeError as e:
                raise ValueError(f"Corrupted chunk JSON at {path}: {e}")
            except Exception as e:
                raise Exception(f"Failed to fetch chunk {index} for {doc_uuid}: {e}")
        
        # Fetch all chunks in parallel
        return await asyncio.gather(*[
            fetch_one(idx) for idx in chunk_indices
        ])
    
    async def fetch_extracted_text(self, doc_uuid: str) -> str:
        """Fetch extracted text from GCS"""
        path = f"{doc_uuid}/extracted.txt"
        blob = self.bucket.blob(path)
        content = await asyncio.to_thread(blob.download_as_bytes)
        return content.decode('utf-8')
    
    async def fetch_original_file(self, doc_uuid: str, file_type: str = "pdf") -> bytes:
        """Fetch original file from GCS (stored as 'original' without extension)"""
        path = f"{doc_uuid}/original"
        blob = self.bucket.blob(path)
        return await asyncio.to_thread(blob.download_as_bytes)
    
    def get_signed_url(
        self,
        doc_uuid: str,
        expiration: int = 3600
    ) -> str:
        """
        Generate signed URL for PDF download
        
        Args:
            doc_uuid: Document UUID
            expiration: URL expiration in seconds (default 1 hour)
        
        Returns:
            Signed URL for direct download
        """
        path = f"{doc_uuid}/document.pdf"
        blob = self.bucket.blob(path)
        return blob.generate_signed_url(expiration=expiration)
    
    async def delete_document(self, doc_uuid: str):
        """
        Delete all files for a document
        
        Args:
            doc_uuid: Document UUID
        """
        # List all blobs with prefix
        prefix = f"{doc_uuid}/"
        blobs = list(self.bucket.list_blobs(prefix=prefix))
        
        if not blobs:
            # No files found - might be already deleted or never uploaded
            return
        
        # Delete all in parallel with error tolerance
        tasks = [
            asyncio.to_thread(blob.delete)
            for blob in blobs
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Log errors but don't fail
        errors = [r for r in results if isinstance(r, Exception)]
        if errors:
            print(f"Warning: {len(errors)} files failed to delete for {doc_uuid}")
    
    async def _upload(
        self,
        path: str,
        content: bytes,
        content_type: str = "application/octet-stream"
    ):
        """Helper: upload single file"""
        blob = self.bucket.blob(path)
        await asyncio.to_thread(
            blob.upload_from_string,
            content,
            content_type=content_type
        )
