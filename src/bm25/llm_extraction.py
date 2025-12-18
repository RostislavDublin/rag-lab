"""
LLM-based document summarization and keyword extraction for BM25 hybrid search.

Uses Gemini 2.0 Flash Lite for cost-effective extraction:
- Summary: 2-3 concise sentences capturing main topics
- Keywords: 10-15 key terms for BM25 keyword boosting

Cost: ~$0.0004 per document (assuming 5KB text ≈ 1250 tokens)
"""

import logging
from typing import Dict, List

logger = logging.getLogger(__name__)


async def extract_summary_and_keywords(
    text: str,
    genai_client,
    model_name: str = "gemini-2.0-flash-exp"
) -> Dict[str, any]:
    """
    Extract summary and keywords from document text using Gemini LLM.
    
    Args:
        text: Full document text (original extracted text before chunking)
        genai_client: Google GenAI client instance
        model_name: Gemini model to use (default: gemini-2.0-flash-exp for cost efficiency)
    
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
        logger.error(f"LLM response is not valid JSON: {e}")
        logger.debug(f"Raw response: {response.text if 'response' in locals() else 'N/A'}")
        return default_result
    
    except Exception as e:
        logger.error(f"LLM extraction failed: {e}")
        return default_result
