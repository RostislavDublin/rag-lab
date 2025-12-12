"""
Test support for various text-based file formats
"""

import pytest
from unittest.mock import Mock
from src.document_processor import DocumentProcessor, EmbeddingProvider


@pytest.fixture
def processor():
    """Create processor without embedding model (we only test text extraction)"""
    # Create mock genai client (only needed for embedding, not text extraction)
    mock_client = Mock()
    return DocumentProcessor(
        embedding_provider=EmbeddingProvider.VERTEX_AI,
        genai_client=mock_client
    )


def test_markdown_extraction(processor):
    """Test .md file extraction"""
    markdown_content = b"""# Heading
    
This is a **markdown** file with _formatting_.

- Item 1
- Item 2
"""
    text = processor.extract_text(markdown_content, '.md')
    assert '# Heading' in text
    assert '**markdown**' in text
    assert 'Item 1' in text


def test_json_extraction(processor):
    """Test .json file extraction converts to YAML"""
    json_content = b'{"name": "test", "value": 123, "items": ["a", "b"]}'
    text = processor.extract_text(json_content, '.json')
    
    # Verify YAML conversion
    assert 'name: test' in text  # YAML format
    assert 'value: 123' in text  # Values preserved
    assert '- a' in text or '  - a' in text  # List items
    assert '- b' in text or '  - b' in text
    
    # Verify JSON syntax removed
    assert '{' not in text  # No curly braces
    assert '"name"' not in text  # No quoted keys
    
    # Verify it's valid YAML (parseable)
    import yaml
    parsed = yaml.safe_load(text)
    assert parsed['name'] == 'test'
    assert parsed['value'] == 123


def test_csv_extraction(processor):
    """Test .csv file extraction"""
    csv_content = b"""name,age,city
Alice,30,NYC
Bob,25,SF"""
    text = processor.extract_text(csv_content, '.csv')
    assert 'name,age,city' in text
    assert 'Alice,30,NYC' in text


def test_yaml_extraction(processor):
    """Test .yaml file extraction"""
    yaml_content = b"""name: test
version: 1.0
dependencies:
  - package1
  - package2
"""
    text = processor.extract_text(yaml_content, '.yaml')
    assert 'name: test' in text
    assert 'version: 1.0' in text
    assert 'package1' in text


def test_python_code_extraction(processor):
    """Test .py file extraction"""
    python_content = b"""def hello():
    print("Hello, world!")

if __name__ == "__main__":
    hello()
"""
    text = processor.extract_text(python_content, '.py')
    assert 'def hello():' in text
    assert 'print("Hello, world!")' in text


def test_xml_extraction(processor):
    """Test .xml file extraction converts to YAML preserving structure"""
    xml_content = b"""<?xml version="1.0"?>
<root>
    <item id="1">Test Content</item>
    <description>This is a test</description>
</root>"""
    text = processor.extract_text(xml_content, '.xml')
    
    # Verify content preserved
    assert 'Test Content' in text
    assert 'This is a test' in text
    
    # Verify YAML structure (tags become keys)
    assert 'root:' in text  # Root element
    assert 'item:' in text  # Child element
    assert 'description:' in text  # Another child
    
    # Verify attributes preserved with @ prefix
    assert '@id' in text  # Attribute convention
    assert "'1'" in text or '1' in text  # Attribute value
    
    # Verify XML syntax removed
    assert '<root>' not in text
    assert '</item>' not in text
    assert '<?xml' not in text
    
    # Verify it's valid YAML
    import yaml
    parsed = yaml.safe_load(text)
    assert 'root' in parsed


def test_rst_extraction(processor):
    """Test .rst (ReStructuredText) file extraction"""
    rst_content = b"""My Title
========

This is a reStructuredText document.

* Item 1
* Item 2
"""
    text = processor.extract_text(rst_content, '.rst')
    assert 'My Title' in text
    assert 'reStructuredText' in text


def test_log_file_extraction(processor):
    """Test .log file extraction"""
    log_content = b"""2025-12-11 10:30:45 INFO Starting application
2025-12-11 10:30:46 DEBUG Loading configuration
2025-12-11 10:30:47 ERROR Connection failed
"""
    text = processor.extract_text(log_content, '.log')
    assert '2025-12-11' in text
    assert 'INFO Starting application' in text
    assert 'ERROR Connection failed' in text


def test_html_extraction(processor):
    """Test .html file extraction with Markdown conversion"""
    html_content = b"""<!DOCTYPE html>
<html>
<head><title>Test Page</title></head>
<body>
    <h1>Main Heading</h1>
    <p>This is a <strong>bold</strong> and <em>italic</em> text.</p>
    <ul>
        <li>Item 1</li>
        <li>Item 2</li>
    </ul>
    <table>
        <tr><th>Name</th><th>Value</th></tr>
        <tr><td>Alpha</td><td>100</td></tr>
    </table>
    <a href="https://example.com">Example Link</a>
</body>
</html>"""
    
    text = processor.extract_text(html_content, '.html')
    
    # Verify Markdown conversion (structure preserved)
    assert '# Main Heading' in text or 'Main Heading' in text  # Heading converted
    assert 'bold' in text  # Text extracted
    assert 'italic' in text
    assert 'Item 1' in text  # List items preserved
    assert 'Item 2' in text
    assert 'Alpha' in text  # Table content preserved
    assert '100' in text
    assert 'example.com' in text or 'Example Link' in text  # Link preserved
    
    # Verify HTML tags removed
    assert '<html>' not in text
    assert '<strong>' not in text
    assert '<table>' not in text


def test_unsupported_format_raises_error(processor):
    """Test that unsupported formats raise ValueError"""
    binary_content = b'\x89PNG\r\n\x1a\n'  # PNG header
    
    with pytest.raises(ValueError, match="Unsupported file type"):
        processor.extract_text(binary_content, '.png')


def test_mime_type_support(processor):
    """Test MIME type variants"""
    # Plain text MIME types
    text_content = b"test content"
    assert processor.extract_text(text_content, 'text/plain')
    assert processor.extract_text(text_content, 'text/markdown')
    
    # JSON MIME type (needs valid JSON)
    json_content = b'{"key": "value"}'
    assert processor.extract_text(json_content, 'application/json')
    
    # XML MIME type (needs valid XML)
    xml_content = b'<root><item>value</item></root>'
    assert processor.extract_text(xml_content, 'application/xml')


def test_utf8_encoding(processor):
    """Test UTF-8 encoded content"""
    utf8_content = "Привет, мир! 你好世界".encode('utf-8')
    text = processor.extract_text(utf8_content, '.txt')
    assert 'Привет' in text
    assert '你好世界' in text
