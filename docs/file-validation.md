# File Validation Guide

RAG Lab implements a 3-tier validation strategy for secure and reliable document processing.

## Validation Strategy

### Tier 1: Extension Check

**Purpose:** Fast rejection of obviously wrong files

**Check:** File extension matches allowed list

**Supported:**
- Documents: `.pdf`, `.docx`, `.doc`, `.txt`, `.md`
- Presentations: `.pptx`, `.ppt`
- Spreadsheets: `.xlsx`, `.xls`

**Example:**
```python
if not filename.lower().endswith(('.pdf', '.docx', '.txt')):
    raise ValueError("Unsupported file type")
```

### Tier 2: Magic Bytes Verification

**Purpose:** Detect extension spoofing (security)

**Check:** File signature (magic bytes) matches declared extension

**Implementation:**
```python
import magic

def verify_file_type(file_path: str, declared_extension: str) -> bool:
    """Verify file magic bytes match extension."""
    mime = magic.from_file(file_path, mime=True)
    
    MIME_MAP = {
        'pdf': 'application/pdf',
        'docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
        'txt': 'text/plain',
        'md': 'text/plain',
    }
    
    expected_mime = MIME_MAP.get(declared_extension.lstrip('.'))
    return mime == expected_mime
```

**Security Benefit:** Prevents malicious files disguised as documents

**Example Attack Prevented:**
```bash
# Attacker renames malware.exe to malware.pdf
cp malware.exe malware.pdf

# Tier 1: PASS (extension is .pdf)
# Tier 2: FAIL (magic bytes show "application/x-executable")
# Upload rejected ✅
```

### Tier 3: Successful Text Extraction

**Purpose:** Ensure file is processable

**Check:** Text extraction completes without errors

**Implementation:**
```python
try:
    text = await extract_text(file_path)
    if len(text.strip()) == 0:
        raise ValueError("No text could be extracted")
except Exception as e:
    raise ValueError(f"Text extraction failed: {e}")
```

**Catches:**
- Corrupted files (damaged PDFs, incomplete downloads)
- Password-protected files
- Image-only PDFs without OCR
- Empty documents

**Example:**
```bash
# User uploads corrupted.pdf
# Tier 1: PASS (extension is .pdf)
# Tier 2: PASS (magic bytes show application/pdf)
# Tier 3: FAIL (PyPDF2 raises "EOF marker not found")
# Upload rejected with clear error message ✅
```

## Magic Bytes Reference

**Common File Signatures:**

| Format | Extension | Magic Bytes (Hex) | Magic Bytes (ASCII) |
|--------|-----------|-------------------|---------------------|
| PDF | .pdf | `25 50 44 46` | `%PDF` |
| DOCX | .docx | `50 4B 03 04` | `PK..` (ZIP) |
| DOC | .doc | `D0 CF 11 E0 A1 B1 1A E1` | `ÐÏ..¡±..` (OLE) |
| TXT | .txt | No signature | Plain text |
| Markdown | .md | No signature | Plain text |
| PPTX | .pptx | `50 4B 03 04` | `PK..` (ZIP) |
| XLSX | .xlsx | `50 4B 03 04` | `PK..` (ZIP) |

**Note:** DOCX/PPTX/XLSX are ZIP archives. Magic bytes verification checks MIME type, not just ZIP signature.

## Implementation Details

### File Upload Flow

```python
@app.post("/upload")
async def upload_files(files: List[UploadFile]):
    for file in files:
        # Tier 1: Extension check
        if not is_supported_extension(file.filename):
            raise HTTPException(400, "Unsupported file type")
        
        # Save temporary file
        temp_path = save_temp_file(file)
        
        try:
            # Tier 2: Magic bytes
            if not verify_magic_bytes(temp_path, file.filename):
                raise HTTPException(400, "File signature mismatch")
            
            # Tier 3: Extract text
            text = await extract_text(temp_path)
            if not text.strip():
                raise HTTPException(400, "No text extracted")
            
            # Process document
            await process_document(text, file.filename)
            
        finally:
            os.remove(temp_path)
```

### libmagic Installation

**macOS:**
```bash
brew install libmagic
pip install python-magic
```

**Ubuntu/Debian:**
```bash
sudo apt-get install libmagic1
pip install python-magic
```

**Windows:**
```bash
pip install python-magic-bin  # Includes libmagic DLL
```

**Docker:**
```dockerfile
FROM python:3.12-slim
RUN apt-get update && apt-get install -y libmagic1
RUN pip install python-magic
```

## Error Messages

### Extension Not Supported

```json
{
  "detail": "File 'document.xyz' has unsupported extension. Supported: .pdf, .docx, .txt, .md"
}
```

### Magic Bytes Mismatch

```json
{
  "detail": "File 'document.pdf' signature mismatch. Expected application/pdf, got application/x-executable"
}
```

### Text Extraction Failed

```json
{
  "detail": "Text extraction failed for 'document.pdf': EOF marker not found. File may be corrupted."
}
```

## Security Considerations

### Why Magic Bytes Matter

**Attack Scenario:**
1. Attacker creates malicious executable
2. Renames to `innocent.pdf`
3. Uploads to RAG system
4. Without validation: Server executes malicious code during "processing"
5. With validation: Upload rejected at Tier 2

**Real-World Example:**
```bash
# Create fake PDF
echo "malicious code" > malware.exe
mv malware.exe invoice.pdf

# Upload attempt
curl -F "files=@invoice.pdf" http://localhost:8080/upload

# Response: 400 Bad Request
# "File signature mismatch. Expected application/pdf, got application/x-executable"
```

### Additional Security Measures

1. **File Size Limits:**
   ```python
   MAX_FILE_SIZE = 100 * 1024 * 1024  # 100MB
   
   if file.size > MAX_FILE_SIZE:
       raise HTTPException(413, "File too large")
   ```

2. **Filename Sanitization:**
   ```python
   import re
   
   def sanitize_filename(filename: str) -> str:
       # Remove path traversal attempts
       filename = os.path.basename(filename)
       # Remove dangerous characters
       filename = re.sub(r'[^\w\s.-]', '', filename)
       return filename
   ```

3. **Temporary File Isolation:**
   ```python
   import tempfile
   
   with tempfile.TemporaryDirectory() as tmpdir:
       temp_path = os.path.join(tmpdir, secure_filename)
       # Process file
       # Auto-deleted when exiting context
   ```

## Supported Formats

### Documents

**PDF (.pdf)**
- Validation: Magic bytes `%PDF`
- Extraction: PyPDF2 (text), pypdfium2 (images)
- OCR: Not yet implemented (roadmap)

**Word (.docx, .doc)**
- Validation: MIME type for OLE/ZIP
- Extraction: python-docx (docx), olefile (doc)
- Images: Embedded images extracted separately

**Text (.txt, .md)**
- Validation: MIME type `text/plain`
- Extraction: Direct UTF-8 read
- Markdown: Rendered to plain text

### Future Support (Roadmap)

**Presentations (.pptx, .ppt)**
- Extraction: python-pptx
- Status: Planned for v1.1

**Spreadsheets (.xlsx, .xls)**
- Extraction: openpyxl
- Status: Planned for v1.2

**Images (.png, .jpg)**
- Extraction: OCR (Tesseract)
- Status: Planned for v1.3

## Testing File Validation

### Unit Tests

```python
# tests/unit/test_validation.py

def test_extension_check():
    assert is_supported_extension("doc.pdf") == True
    assert is_supported_extension("doc.xyz") == False

def test_magic_bytes_pdf():
    # Create fake PDF
    with open("fake.pdf", "wb") as f:
        f.write(b"Not a PDF")
    
    assert verify_magic_bytes("fake.pdf", ".pdf") == False

def test_magic_bytes_real_pdf():
    # Real PDF
    assert verify_magic_bytes("tests/fixtures/sample.pdf", ".pdf") == True
```

### Integration Tests

```python
# tests/integration/test_upload_validation.py

def test_upload_wrong_extension(client):
    response = client.post(
        "/upload",
        files={"files": ("doc.xyz", b"content", "application/octet-stream")}
    )
    
    assert response.status_code == 400
    assert "unsupported extension" in response.json()["detail"].lower()

def test_upload_spoofed_pdf(client):
    # Executable renamed to .pdf
    response = client.post(
        "/upload",
        files={"files": ("malware.pdf", b"\x4D\x5A", "application/pdf")}  # MZ header (exe)
    )
    
    assert response.status_code == 400
    assert "signature mismatch" in response.json()["detail"].lower()
```

## Troubleshooting

### "python-magic not found"

**Solution:**
```bash
# macOS
brew install libmagic
pip install python-magic

# Linux
sudo apt-get install libmagic1
pip install python-magic
```

### "Magic bytes check fails for valid file"

**Cause:** MIME type mapping incorrect

**Debug:**
```python
import magic

mime = magic.from_file("document.pdf", mime=True)
print(f"Detected MIME: {mime}")

# Expected: application/pdf
# If different, update MIME_MAP in validation code
```

### "Text extraction succeeds but empty"

**Cause:** PDF is image-only (no text layer)

**Solution:** Implement OCR (roadmap) or reject with clear message

```python
if len(text.strip()) == 0:
    raise HTTPException(400, "PDF contains no text. OCR not yet supported.")
```

## Best Practices

1. **Always validate in order:** Extension → Magic bytes → Extraction
2. **Fail fast:** Reject at earliest tier to save resources
3. **Clear errors:** Tell users exactly what's wrong
4. **Log rejections:** Track validation failures for security monitoring
5. **Update signatures:** Keep magic bytes mappings current
6. **Test edge cases:** Corrupted files, empty files, password-protected
7. **Size limits:** Prevent DoS via huge uploads
8. **Sanitize filenames:** Prevent path traversal attacks
