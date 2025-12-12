"""
File Validation Module

Quality-First Philosophy for RAG Systems:
-----------------------------------------
"Better to reject bad input once than get bad search results forever"

Upload is a one-time operation, but queries happen hundreds of times.
Invalid files → bad embeddings → poor search quality → wasted money.

This module implements 3-tier validation:
1. STRICT (binary formats): Fail fast on any corruption
2. STRUCTURED (JSON/XML/YAML): Parse validation, fail on syntax errors  
3. LENIENT (text formats): Accept if UTF-8 decodable

Why fail fast?
- Embeddings are expensive (API costs)
- Bad data is permanent (re-embedding entire DB is costly)
- Debugging "why search doesn't work" 3 months later is nightmare
- Users deserve explicit errors over silent failures
"""

import json
from pathlib import Path
from typing import Any, Literal

import magic
import pymupdf
import xmltodict
import yaml
from fastapi import HTTPException, status


class ValidationError(HTTPException):
    """File validation failed with actionable error message"""

    def __init__(self, message: str):
        super().__init__(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=message,
        )


class ValidationResult:
    """Result of file validation with metadata"""

    def __init__(
        self,
        format_type: Literal["pdf", "json", "xml", "yaml", "text"],
        mime_type: str,
        content: bytes | str | dict | None = None,
        parsed_data: Any = None,
    ):
        self.format_type = format_type
        self.mime_type = mime_type
        self.content = content
        self.parsed_data = parsed_data


class FileValidator:
    """
    Multi-tier file validation with fail-fast philosophy
    
    Validates uploaded files to ensure RAG quality:
    - Extension whitelist (first line of defense)
    - Magic bytes detection (prevent spoofing)
    - Format-specific validation (ensure parse-ability)
    - Size limits (prevent DoS)
    """

    # Tier 1: Binary formats - STRICT validation
    STRICT_FORMATS = {".pdf"}
    STRICT_MIME_MAP = {".pdf": "application/pdf"}

    # Tier 2: Structured data - PARSE validation
    STRUCTURED_FORMATS = {".json", ".xml", ".yaml", ".yml"}

    # Tier 3: Text formats - LENIENT validation
    TEXT_FORMATS = {
        ".txt",
        ".md",
        ".markdown",
        ".rst",
        ".log",
        ".csv",
        ".toml",
        ".ini",
        ".py",
        ".js",
        ".html",
        ".css",
    }

    MAX_FILE_SIZE = 100 * 1024 * 1024  # 100MB

    def __init__(self):
        """Initialize magic detector for MIME type detection"""
        self.mime_detector = magic.Magic(mime=True)

    @property
    def supported_extensions(self) -> set[str]:
        """All supported file extensions"""
        return self.STRICT_FORMATS | self.STRUCTURED_FORMATS | self.TEXT_FORMATS

    def validate(self, filename: str, content: bytes) -> ValidationResult:
        """
        Validate uploaded file using 3-tier strategy
        
        Args:
            filename: Original filename with extension
            content: File content as bytes
            
        Returns:
            ValidationResult with format type and metadata
            
        Raises:
            ValidationError: If validation fails with actionable message
        """
        # Step 1: File size check (prevent DoS)
        if len(content) > self.MAX_FILE_SIZE:
            raise ValidationError(
                f"File '{filename}' is too large ({len(content) / 1024 / 1024:.1f}MB).\n"
                f"Maximum allowed: {self.MAX_FILE_SIZE / 1024 / 1024}MB.\n"
                f"Reason: Large files consume excessive processing resources."
            )

        # Step 2: Extension whitelist
        ext = Path(filename).suffix.lower()
        if not ext:
            raise ValidationError(
                f"File '{filename}' has no extension.\n"
                f"Please add file extension (e.g., .pdf, .txt, .json).\n"
                f"Supported: {', '.join(sorted(self.supported_extensions))}"
            )

        if ext not in self.supported_extensions:
            raise ValidationError(
                f"Unsupported file extension '{ext}' in '{filename}'.\n"
                f"Supported formats:\n"
                f"  Documents: .pdf, .txt, .md, .log\n"
                f"  Structured: .json, .xml, .yaml, .csv\n"
                f"  Code: .py, .js, .html, .css\n"
                f"Full list: {', '.join(sorted(self.supported_extensions))}"
            )

        # Step 3: Detect actual content type (magic bytes)
        detected_mime = self._detect_mime_type(content)

        # Step 4: Tier-specific validation
        if ext in self.STRICT_FORMATS:
            return self._validate_strict(ext, detected_mime, content, filename)
        elif ext in self.STRUCTURED_FORMATS:
            return self._validate_structured(ext, content, filename)
        else:  # TEXT_FORMATS
            return self._validate_text(content, filename)

    def _detect_mime_type(self, content: bytes) -> str:
        """Detect MIME type from file content (first 2KB)"""
        return self.mime_detector.from_buffer(content[:2048])

    def _validate_strict(
        self, ext: str, detected_mime: str, content: bytes, filename: str
    ) -> ValidationResult:
        """
        TIER 1: STRICT validation for binary formats
        
        Fail fast on any mismatch between extension and content.
        Binary formats are either valid or broken - no middle ground.
        """
        expected_mime = self.STRICT_MIME_MAP[ext]

        # Check 1: Magic bytes must match extension
        if detected_mime != expected_mime:
            raise ValidationError(
                f"Format mismatch in '{filename}':\n"
                f"  Extension claims: {ext} ({expected_mime})\n"
                f"  Actual content: {detected_mime}\n\n"
                f"Solutions:\n"
                f"  1. Rename to correct extension\n"
                f"  2. Convert file to {ext[1:].upper()} format\n"
                f"  3. Upload as correct format\n\n"
                f"Reason: RAG quality depends on correct format detection.\n"
                f"We cannot process files with mismatched extensions."
            )

        # Check 2: PDF-specific validation (attempt to open)
        if ext == ".pdf":
            try:
                doc = pymupdf.open(stream=content, filetype="pdf")
                page_count = len(doc)
                doc.close()

                if page_count == 0:
                    raise ValidationError(
                        f"PDF '{filename}' is empty (0 pages).\n"
                        f"Cannot extract text from empty documents."
                    )

            except Exception as e:
                error_msg = str(e)[:200]  # Truncate long errors
                raise ValidationError(
                    f"Corrupted PDF: '{filename}'\n"
                    f"Error: {error_msg}\n\n"
                    f"Solutions:\n"
                    f"  1. Re-save PDF from original source\n"
                    f"  2. Try PDF repair tool\n"
                    f"  3. Convert from source format again\n\n"
                    f"Reason: Corrupted PDFs produce garbage text,\n"
                    f"degrading RAG search quality."
                )

        return ValidationResult(
            format_type="pdf", mime_type=detected_mime, content=content
        )

    def _validate_structured(
        self, ext: str, content: bytes, filename: str
    ) -> ValidationResult:
        """
        TIER 2: STRUCTURED validation for JSON/XML/YAML
        
        Parse the file to ensure syntax is valid.
        Broken structure = broken semantics = poor RAG quality.
        Better to reject than lose semantic information.
        """
        try:
            text = content.decode("utf-8")
        except UnicodeDecodeError as e:
            raise ValidationError(
                f"File '{filename}' is not valid UTF-8 text.\n"
                f"Error: {str(e)[:100]}\n"
                f"Ensure file encoding is UTF-8."
            )

        parsed_data = None

        try:
            if ext == ".json":
                parsed_data = json.loads(text)
                format_type = "json"

            elif ext == ".xml":
                parsed_data = xmltodict.parse(text)
                format_type = "xml"

            elif ext in {".yaml", ".yml"}:
                parsed_data = yaml.safe_load(text)
                format_type = "yaml"

            else:
                raise ValueError(f"Unknown structured format: {ext}")

        except json.JSONDecodeError as e:
            raise ValidationError(
                f"Invalid JSON syntax in '{filename}':\n"
                f"  Line {e.lineno}, column {e.colno}\n"
                f"  Error: {e.msg}\n"
                f"  Context: ...{text[max(0, e.pos-50):e.pos+50]}...\n\n"
                f"Please fix JSON syntax and re-upload.\n\n"
                f"Reason: Corrupted JSON loses semantic structure.\n"
                f"We convert JSON→YAML for optimal RAG chunking.\n"
                f"Broken structure = poor search quality."
            )

        except yaml.YAMLError as e:
            raise ValidationError(
                f"Invalid YAML syntax in '{filename}':\n"
                f"  {str(e)[:300]}\n\n"
                f"Please fix YAML syntax and re-upload.\n\n"
                f"Reason: Malformed YAML cannot be parsed reliably,\n"
                f"leading to incorrect semantic chunking."
            )

        except Exception as e:
            # XML parsing errors
            raise ValidationError(
                f"Invalid {ext[1:].upper()} syntax in '{filename}':\n"
                f"  {str(e)[:300]}\n\n"
                f"Please fix syntax errors and re-upload.\n\n"
                f"Reason: Corrupted structured data degrades RAG quality.\n"
                f"We prefer accurate data over partial data."
            )

        return ValidationResult(
            format_type=format_type,
            mime_type=f"application/{format_type}",
            content=text,
            parsed_data=parsed_data,
        )

    def _validate_text(self, content: bytes, filename: str) -> ValidationResult:
        """
        TIER 3: LENIENT validation for text formats
        
        Text formats are fault-tolerant by design:
        - Markdown with formatting issues still renders
        - Python with style violations still runs
        - Logs can have any structure
        
        Only requirement: Must be valid UTF-8 text.
        """
        try:
            text = content.decode("utf-8")
        except UnicodeDecodeError as e:
            raise ValidationError(
                f"File '{filename}' is not valid UTF-8 text.\n"
                f"Error at byte position {e.start}: {e.reason}\n\n"
                f"Solutions:\n"
                f"  1. Convert file to UTF-8 encoding\n"
                f"  2. Save file with UTF-8 encoding\n"
                f"  3. Check for binary data in text file\n\n"
                f"Reason: Non-UTF-8 text cannot be processed reliably."
            )

        # Text formats are lenient - accept even if "dirty"
        # (Markdown with inconsistent formatting, code with style issues, etc.)
        return ValidationResult(
            format_type="text",
            mime_type="text/plain",
            content=text,
        )
