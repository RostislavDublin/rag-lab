"""
Unit tests for FileValidator

Tests 3-tier validation strategy:
1. STRICT (PDF): Magic bytes validation, corruption detection
2. STRUCTURED (JSON/XML/YAML): Parse validation, syntax errors
3. LENIENT (text): UTF-8 validation, formatting tolerance
"""

import pytest

from src.file_validator import FileValidator, ValidationError


@pytest.fixture
def validator():
    """Create FileValidator instance"""
    return FileValidator()


class TestStrictValidation:
    """TIER 1: Binary formats - FAIL FAST on mismatch"""

    def test_valid_pdf(self, validator):
        """Valid PDF passes validation"""
        # Minimal valid PDF
        pdf_content = (
            b"%PDF-1.4\n"
            b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n"
            b"2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n"
            b"3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] >>\nendobj\n"
            b"xref\n0 4\n"
            b"0000000000 65535 f\n"
            b"0000000009 00000 n\n"
            b"0000000058 00000 n\n"
            b"0000000115 00000 n\n"
            b"trailer\n<< /Size 4 /Root 1 0 R >>\n"
            b"startxref\n198\n%%EOF"
        )

        result = validator.validate("document.pdf", pdf_content)
        assert result.format_type == "pdf"
        assert result.mime_type == "application/pdf"

    def test_fake_pdf_extension(self, validator):
        """Text file with .pdf extension fails"""
        fake_pdf = b"This is just text, not a PDF"

        with pytest.raises(ValidationError) as exc_info:
            validator.validate("fake.pdf", fake_pdf)

        error = str(exc_info.value.detail)
        assert "Format mismatch" in error
        assert "text/plain" in error
        assert "application/pdf" in error

    def test_corrupted_pdf(self, validator):
        """Corrupted PDF with valid magic bytes fails"""
        # PDF signature but truncated/corrupted content
        corrupted = b"%PDF-1.4\ncorrupted content"

        with pytest.raises(ValidationError) as exc_info:
            validator.validate("broken.pdf", corrupted)

        error = str(exc_info.value.detail)
        assert "Corrupted PDF" in error

    def test_file_too_large(self, validator):
        """Files exceeding size limit fail"""
        huge_file = b"x" * (101 * 1024 * 1024)  # 101MB

        with pytest.raises(ValidationError) as exc_info:
            validator.validate("huge.txt", huge_file)

        error = str(exc_info.value.detail)
        assert "too large" in error
        assert "100MB" in error or "100.0MB" in error


class TestStructuredValidation:
    """TIER 2: Structured data - PARSE validation"""

    def test_valid_json(self, validator):
        """Valid JSON passes and gets parsed"""
        json_content = b'{"name": "test", "items": [1, 2, 3]}'

        result = validator.validate("config.json", json_content)
        assert result.format_type == "json"
        assert result.parsed_data == {"name": "test", "items": [1, 2, 3]}

    def test_invalid_json_syntax(self, validator):
        """Invalid JSON syntax fails with detailed error"""
        # Missing closing bracket
        broken_json = b'{"name": "test", "items": [1, 2, 3}'

        with pytest.raises(ValidationError) as exc_info:
            validator.validate("broken.json", broken_json)

        error = str(exc_info.value.detail)
        assert "Invalid JSON" in error
        assert "syntax" in error.lower()

    def test_valid_xml(self, validator):
        """Valid XML passes and gets parsed"""
        xml_content = b'<?xml version="1.0"?><root><item>test</item></root>'

        result = validator.validate("data.xml", xml_content)
        assert result.format_type == "xml"
        assert result.parsed_data is not None

    def test_invalid_xml_syntax(self, validator):
        """Invalid XML syntax fails"""
        # Unclosed tag
        broken_xml = b'<?xml version="1.0"?><root><item>test</root>'

        with pytest.raises(ValidationError) as exc_info:
            validator.validate("broken.xml", broken_xml)

        error = str(exc_info.value.detail)
        assert "Invalid XML" in error or "syntax" in error.lower()

    def test_valid_yaml(self, validator):
        """Valid YAML passes and gets parsed"""
        yaml_content = b"name: test\nitems:\n  - 1\n  - 2\n  - 3"

        result = validator.validate("config.yaml", yaml_content)
        assert result.format_type == "yaml"
        assert result.parsed_data == {"name": "test", "items": [1, 2, 3]}

    def test_invalid_yaml_syntax(self, validator):
        """Invalid YAML syntax fails"""
        # Actual syntax error - duplicate keys (not allowed in YAML)
        broken_yaml = b"name: test\nname: test2\nitems: [\n  1,\n  2,"  # Unclosed bracket

        with pytest.raises(ValidationError) as exc_info:
            validator.validate("broken.yaml", broken_yaml)

        error = str(exc_info.value.detail)
        assert "Invalid YAML" in error or "syntax" in error.lower()


class TestLenientValidation:
    """TIER 3: Text formats - LENIENT, accept if UTF-8"""

    def test_valid_text(self, validator):
        """Valid UTF-8 text passes"""
        text_content = b"This is plain text\nWith multiple lines"

        result = validator.validate("notes.txt", text_content)
        assert result.format_type == "text"
        assert result.content == "This is plain text\nWith multiple lines"

    def test_valid_markdown(self, validator):
        """Markdown with 'dirty' formatting still passes (lenient)"""
        # Inconsistent list markers, trailing spaces - still valid
        dirty_md = b"# Heading\n\nSome text  \n\n- item 1\n* item 2\n+ item 3"

        result = validator.validate("notes.md", dirty_md)
        assert result.format_type == "text"
        # Lenient tier accepts "dirty" markdown

    def test_valid_python_code(self, validator):
        """Python code passes (even with style issues)"""
        # PEP8 violations but valid Python
        dirty_code = b"def foo( x,y ):\n  return x+y\n\n\n"

        result = validator.validate("script.py", dirty_code)
        assert result.format_type == "text"

    def test_non_utf8_text_fails(self, validator):
        """Binary data in text file fails"""
        # Invalid UTF-8 sequence
        binary_garbage = b"\xff\xfe\x00\x00invalid"

        with pytest.raises(ValidationError) as exc_info:
            validator.validate("garbage.txt", binary_garbage)

        error = str(exc_info.value.detail)
        assert "not valid UTF-8" in error


class TestExtensionValidation:
    """Extension whitelist and error messages"""

    def test_missing_extension(self, validator):
        """File without extension fails"""
        with pytest.raises(ValidationError) as exc_info:
            validator.validate("README", b"content")

        error = str(exc_info.value.detail)
        assert "no extension" in error

    def test_unsupported_extension(self, validator):
        """Unsupported extension fails with helpful message"""
        with pytest.raises(ValidationError) as exc_info:
            validator.validate("file.exe", b"content")

        error = str(exc_info.value.detail)
        assert "Unsupported" in error
        assert ".exe" in error
        assert "Supported formats" in error

    def test_supported_extensions_property(self, validator):
        """Validator exposes all supported extensions"""
        extensions = validator.supported_extensions
        assert ".pdf" in extensions
        assert ".json" in extensions
        assert ".txt" in extensions
        assert ".md" in extensions
        assert len(extensions) == 17  # Total count
