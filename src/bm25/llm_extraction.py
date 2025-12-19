"""
LLM-based document summarization and keyword extraction for BM25 hybrid search.

MODEL SELECTION RATIONALE (Dec 2025):

We use Gemini 2.5 Flash (gemini-2.5-flash) for all LLM operations:
- Stability: Production-ready stable model (not experimental/preview)
- Availability: Available in both Vertex AI and Gemini API
- Performance: Latest 2.5 generation with improved reasoning
- Consistency: Single model across all project features (extraction + reranking)
- Cost: $0.30/1M input + $2.50/1M output tokens (Vertex AI pricing)

DO NOT USE:
- gemini-2.0-flash-exp (experimental, may change/disappear)
- gemini-2.0-flash (older 2.0 generation)
- gemini-1.5-* (deprecated generation)

Extraction output:
- Summary: 2-3 concise sentences capturing main topics
- Keywords: 10-15 key terms for BM25 keyword boosting

Actual cost per document (gemini-2.5-flash-lite):
- Input: ~1450 tokens @ $0.10/1M = $0.000145
- Output: ~200 tokens @ $0.40/1M = $0.000080
- Total: ~$0.000225/doc ($2.25 per 10K documents)

Alternative (gemini-2.5-flash for better quality):
- Total: ~$0.000935/doc ($9.35 per 10K documents, 4.2x more expensive)
"""

import asyncio
import logging
import os
from typing import Dict, List

logger = logging.getLogger(__name__)

# Model must be set via LLM_EXTRACTION_MODEL env var (e.g., gemini-2.0-flash-exp-local)
DEFAULT_MODEL = os.getenv("LLM_EXTRACTION_MODEL")
if not DEFAULT_MODEL:
    raise ValueError("LLM_EXTRACTION_MODEL environment variable is required")

# Retry configuration (similar to ADK HttpRetryOptions)
MAX_RETRY_ATTEMPTS = 5
RETRY_INITIAL_DELAY = 1.0  # seconds
RETRY_EXP_BASE = 2.0  # exponential backoff multiplier
RETRY_STATUS_CODES = {429, 500, 503, 504}  # Rate limit, server errors


async def extract_summary_and_keywords(
    text: str,
    genai_client,
    model_name: str = None
) -> Dict[str, any]:
    """
    Extract summary and keywords from document text using Gemini LLM.
    
    Args:
        text: Full document text (original extracted text before chunking)
        genai_client: Google GenAI client instance
        model_name: Gemini model to use (default: from LLM_EXTRACTION_MODEL env var, fallback: gemini-2.5-flash)
    
    Returns:
        Dict with:
            "summary": str (2-3 sentences, empty string on failure)
            "keywords": List[str] (10-15 terms, empty list on failure)
    
    Example:
        >>> result = await extract_summary_and_keywords(doc_text, client)
        >>> print(result["summary"])
        "Kubernetes deployment guide covering pod configuration, ..."
        >>> print(result["keywords"])
        ["kubernetes", "pod", "deployment", "container", ...]
    """
    # Use provided model or fallback to env var / default
    if model_name is None:
        model_name = DEFAULT_MODEL
    
    logger.debug(f"Extracting summary/keywords using model: {model_name}")
    
    # Default empty result (fallback on failure)
    default_result = {
        "summary": "",
        "keywords": []
    }
    
    # Skip if text too short (avoid unnecessary LLM calls)
    if not text or len(text.strip()) < 100:
        logger.warning("Text too short for summarization, skipping LLM call")
        return default_result
    
    # Truncate very long texts (Gemini Flash has 1M token limit, but we optimize cost)
    # ~25K chars ≈ 6K tokens (reasonable for summarization)
    MAX_TEXT_LENGTH = 25000
    truncated_text = text[:MAX_TEXT_LENGTH]
    if len(text) > MAX_TEXT_LENGTH:
        logger.info(f"Truncated text from {len(text)} to {MAX_TEXT_LENGTH} chars for summarization")
    
    # Prompt for LLM extraction
    prompt = f"""Analyze this document and provide:

1. **Summary**: 2-3 concise sentences capturing the main topics and purpose
2. **Keywords**: 10-15 key technical terms, concepts, or topics (single words or short phrases)

Document text:
{truncated_text}

Output format (valid JSON):
{{
  "summary": "your 2-3 sentence summary here",
  "keywords": ["keyword1", "keyword2", "keyword3", ...]
}}

Requirements:
- Summary must be 2-3 sentences maximum
- Keywords should be lowercase, single words or short phrases (e.g., "kubernetes", "machine learning")
- Keywords should be the most important technical terms, concepts, or topics
- Return valid JSON only, no additional text"""
    
    # Retry loop with exponential backoff (similar to ADK retry_options)
    last_error = None
    for attempt in range(MAX_RETRY_ATTEMPTS):
        try:
            # Call Gemini LLM
            response = genai_client.models.generate_content(
                model=model_name,
                contents=prompt,
                config={
                    "temperature": 0.1,  # Low temperature for consistent extraction
                    "max_output_tokens": 512,  # Summary + keywords should fit
                    "response_mime_type": "application/json"  # Force JSON output
                }
            )
            
            # Parse JSON response
            import json
            result = json.loads(response.text)
            
            # Validate structure
            if not isinstance(result, dict):
                raise ValueError("LLM response is not a dict")
            
            summary = result.get("summary", "")
            keywords = result.get("keywords", [])
            
            # Validate types
            if not isinstance(summary, str):
                logger.warning(f"Invalid summary type: {type(summary)}, using empty string")
                summary = ""
            
            if not isinstance(keywords, list):
                logger.warning(f"Invalid keywords type: {type(keywords)}, using empty list")
                keywords = []
            
            # Filter keywords to strings only
            keywords = [k for k in keywords if isinstance(k, str)]
            
            # Limit keywords count (10-15 target, but allow up to 20)
            if len(keywords) > 20:
                logger.info(f"Trimming keywords from {len(keywords)} to 20")
                keywords = keywords[:20]
            
            logger.info(f"Extracted summary ({len(summary)} chars) and {len(keywords)} keywords via LLM")
            
            return {
                "summary": summary,
                "keywords": keywords
            }
    
        except json.JSONDecodeError as e:
            last_error = e
            logger.warning(f"Attempt {attempt + 1}/{MAX_RETRY_ATTEMPTS}: LLM response is not valid JSON: {e}")
            logger.debug(f"Raw response: {response.text if 'response' in locals() else 'N/A'}")
            
            # Retry JSON errors (LLM can be unstable and return invalid JSON)
            if attempt < MAX_RETRY_ATTEMPTS - 1:
                delay = RETRY_INITIAL_DELAY * (RETRY_EXP_BASE ** attempt)
                logger.info(f"Retrying in {delay:.1f}s...")
                await asyncio.sleep(delay)
            else:
                logger.error(f"LLM response is not valid JSON after {MAX_RETRY_ATTEMPTS} attempts")
        
        except Exception as e:
            last_error = e
            logger.warning(f"Attempt {attempt + 1}/{MAX_RETRY_ATTEMPTS}: LLM extraction failed: {e}")
            
            # Check if error is retriable (rate limit, server error)
            error_code = getattr(e, 'code', None) or getattr(e, 'status_code', None)
            if error_code not in RETRY_STATUS_CODES:
                # Non-retriable error, fail fast
                logger.error(f"Non-retriable error (code {error_code}), stopping retries")
                break
            
            # Retry with exponential backoff
            if attempt < MAX_RETRY_ATTEMPTS - 1:
                delay = RETRY_INITIAL_DELAY * (RETRY_EXP_BASE ** attempt)
                logger.info(f"Retrying in {delay:.1f}s...")
                await asyncio.sleep(delay)
            else:
                logger.error(f"LLM extraction failed after {MAX_RETRY_ATTEMPTS} attempts")
    
    # All retries exhausted or non-retriable error
    logger.error(f"LLM extraction failed: {last_error}")
    return default_result
