"""
Gemini LLM-based reranker using Google GenAI SDK.

Uses Gemini models to assess relevance of documents to a query.
This is Google's recommended approach for high-quality reranking.

Reference: https://github.com/GoogleCloudPlatform/generative-ai/tree/main/gemini/sample-apps/llamaindex-rag
"""

import logging
from typing import List
import json
import os

from google import genai
from google.genai import types

from .base import BaseReranker, RerankResult

logger = logging.getLogger(__name__)


class GeminiReranker(BaseReranker):
    """
    LLM-based reranker using Gemini models.
    
    Uses Gemini to evaluate relevance of all documents in a single batch request.
    This is more accurate than cross-encoder models and much faster than sequential calls.
    
    Based on Google's LlamaIndex RAG example:
    https://github.com/GoogleCloudPlatform/generative-ai/blob/main/gemini/sample-apps/llamaindex-rag/backend/README.md
    """
    
    BATCH_RERANK_PROMPT_TEMPLATE = """You are an expert at assessing document relevance.

Given a query and multiple documents, your task is to determine how relevant each document is to answering the query.

Query: {query}

Documents:
{documents}

For each document, rate its relevance to the query on a scale from 0 to 10:
- 0: Completely irrelevant, document has nothing to do with the query
- 5: Somewhat relevant, document mentions related topics but doesn't directly answer the query
- 10: Highly relevant, document directly answers or addresses the query

Respond with ONLY a JSON array in this exact format (no other text):
[
  {{"index": 0, "relevance_score": <number 0-10>, "reasoning": "<brief explanation>"}},
  {{"index": 1, "relevance_score": <number 0-10>, "reasoning": "<brief explanation>"}},
  ...
]"""
    
    def __init__(
        self,
        model_name: str = "gemini-2.5-flash",
        project_id: str = None,
        location: str = "us-central1",
        temperature: float = 0.0
    ):
        """
        Initialize Gemini reranker.
        
        Args:
            model_name: Gemini model to use (default: gemini-2.0-flash-exp)
            project_id: GCP project ID (reads from GOOGLE_CLOUD_PROJECT env if not provided)
            location: GCP region (default: us-central1)
            temperature: Model temperature (0.0 = deterministic)
        """
        self.model_name = model_name
        self.project_id = project_id or os.getenv("GOOGLE_CLOUD_PROJECT")
        self.location = location
        self.temperature = temperature
        
        if not self.project_id:
            raise ValueError(
                "GCP project ID required. Set GOOGLE_CLOUD_PROJECT env var or pass project_id parameter."
            )
        
        # Initialize Gemini client
        try:
            self.client = genai.Client(
                vertexai=True,
                project=self.project_id,
                location=self.location
            )
            logger.info(
                f"Gemini reranker initialized: {model_name} "
                f"(project={self.project_id}, location={self.location})"
            )
        except Exception as e:
            logger.error(f"Failed to initialize Gemini client: {e}")
            raise
    
    def _assess_batch_relevance(self, query: str, documents: List[str]) -> List[tuple[int, float, str]]:
        """
        Assess relevance of ALL documents to the query in a single Gemini API call.
        
        Args:
            query: Search query
            documents: List of document texts
            
        Returns:
            List of tuples: (index, relevance_score, reasoning)
            relevance_score is 0-10 (normalized to 0-1 later)
        """
        # Format documents with indices (NO TRUNCATION - preserve full chunk context)
        docs_text = ""
        for idx, doc in enumerate(documents):
            docs_text += f"\n[Document {idx}]\n{doc}\n"
        
        prompt = self.BATCH_RERANK_PROMPT_TEMPLATE.format(
            query=query,
            documents=docs_text
        )
        
        try:
            response = self.client.models.generate_content(
                model=self.model_name,
                contents=prompt,
                config=types.GenerateContentConfig(
                    temperature=self.temperature,
                    max_output_tokens=8000,  # Sufficient for batch reranking (batch_size * ~300 tokens/result)
                    response_mime_type="application/json"  # Force JSON output
                )
            )
            
            # Parse JSON response (expecting array)
            result_text = response.text.strip()
            logger.debug(f"Gemini raw response (first 500 chars): {result_text[:500]}")
            results = json.loads(result_text)
            
            if not isinstance(results, list):
                logger.error(f"Expected JSON array, got: {type(results)}")
                # Fallback: return zero scores
                return [(idx, 0.0, "Invalid response format") for idx in range(len(documents))]
            
            logger.debug(f"Gemini returned {len(results)} score entries")
            
            # Parse each result
            parsed_results = []
            for result in results:
                idx = int(result.get("index", -1))
                score = float(result.get("relevance_score", 0))
                reasoning = result.get("reasoning", "")
                
                logger.debug(f"Doc {idx}: raw_score={score}, reasoning={reasoning[:80]}")
                
                # Validate
                if idx < 0 or idx >= len(documents):
                    logger.warning(f"Invalid index {idx}, skipping")
                    continue
                
                if not (0 <= score <= 10):
                    logger.warning(f"Invalid score {score} for doc {idx}, clamping")
                    score = max(0, min(10, score))
                
                parsed_results.append((idx, score, reasoning))
            
            # If missing results, add zero scores
            parsed_indices = {r[0] for r in parsed_results}
            for idx in range(len(documents)):
                if idx not in parsed_indices:
                    logger.warning(f"Missing score for document {idx}, using 0.0")
                    parsed_results.append((idx, 0.0, "No score returned"))
            
            return parsed_results
            
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse Gemini response as JSON: {e}")
            logger.error(f"Response text: {response.text}")
            # Fallback: return zero scores
            return [(idx, 0.0, "JSON parse error") for idx in range(len(documents))]
        except Exception as e:
            logger.error(f"Gemini API error: {e}")
            # Fallback: return zero scores
            return [(idx, 0.0, f"API error: {str(e)}") for idx in range(len(documents))]
    
    async def rerank(
        self,
        query: str,
        documents: List[str],
        top_k: int = 5,
        batch_size: int = 2
    ) -> List[RerankResult]:
        """
        Rerank documents using Gemini LLM with parallel batching for large sets.
        
        Args:
            query: Search query text
            documents: List of document texts to rerank
            top_k: Number of top results to return
            batch_size: Max documents per API call (default: 2 for low latency)
            
        Returns:
            List of RerankResult, sorted by score (descending)
        """
        if not documents:
            return []
        
        logger.info(
            f"Reranking {len(documents)} documents with Gemini ({self.model_name}) - "
            f"BATCH MODE (batches of {batch_size})"
        )
        
        # Split into batches if needed
        all_results = []
        num_batches = (len(documents) + batch_size - 1) // batch_size
        
        if num_batches == 1:
            # Single batch - one API call
            batch_results = self._assess_batch_relevance(query, documents)
            all_results = batch_results
        else:
            # Multiple batches - parallel API calls using asyncio
            import asyncio
            
            async def process_batch(batch_idx: int) -> List[tuple[int, float, str]]:
                import time
                start_idx = batch_idx * batch_size
                end_idx = min(start_idx + batch_size, len(documents))
                batch_docs = documents[start_idx:end_idx]
                
                start_time = time.time()
                logger.info(f"⏱️ Batch {batch_idx + 1}/{num_batches} START ({len(batch_docs)} docs)")
                # Run sync Gemini call in thread pool to avoid blocking event loop
                batch_results = await asyncio.to_thread(
                    self._assess_batch_relevance, query, batch_docs
                )
                elapsed = time.time() - start_time
                logger.info(f"✅ Batch {batch_idx + 1}/{num_batches} DONE in {elapsed:.2f}s")
                
                # Adjust indices to global document list
                return [(idx + start_idx, score, reasoning) for idx, score, reasoning in batch_results]
            
            # Execute all batches in parallel (max 10 concurrent with small batches)
            semaphore = asyncio.Semaphore(10)  # Limit concurrent Gemini calls
            
            async def process_with_semaphore(batch_idx: int):
                async with semaphore:
                    return await process_batch(batch_idx)
            
            batch_tasks = [process_with_semaphore(i) for i in range(num_batches)]
            batch_results_list = await asyncio.gather(*batch_tasks)
            
            for batch_results in batch_results_list:
                all_results.extend(batch_results)
        
        # Convert to RerankResult objects
        results = []
        for idx, score, reasoning in all_results:
            # Normalize score to 0-1 range
            normalized_score = score / 10.0
            
            results.append(RerankResult(
                index=idx,
                score=normalized_score,
                text=documents[idx],
                reasoning=reasoning
            ))
            
            logger.debug(
                f"Document {idx}: score={normalized_score:.3f} (raw={score:.1f}/10) "
                f"reasoning='{reasoning[:50]}...'"
            )
        
        # Sort by score (descending) and return top_k
        results.sort(key=lambda x: x.score, reverse=True)
        top_results = results[:top_k]
        
        logger.info(
            f"Reranking complete. Top score: {top_results[0].score:.3f}, "
            f"Bottom score: {top_results[-1].score:.3f}"
        )
        
        return top_results
    
    def get_model_info(self) -> dict:
        """Get information about the Gemini reranker."""
        return {
            "name": self.model_name,
            "type": "gemini-llm",
            "provider": "Google Vertex AI",
            "project": self.project_id,
            "location": self.location,
            "temperature": self.temperature,
            "description": "LLM-based reranking using Gemini (Google's recommended approach)"
        }
    
    def close(self):
        """Cleanup (Gemini client doesn't require explicit cleanup)."""
        logger.info("Gemini reranker closed")
