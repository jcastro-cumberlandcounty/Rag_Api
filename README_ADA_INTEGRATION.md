# ADA Compliance Integration for Policy RAG System

## 📋 Overview

This update adds **ADA/WCAG accessibility checking** to your Policy RAG (Retrieval Augmented Generation) system. Documents must now pass WCAG Level AA compliance before being ingested into your knowledge base.

### What's New

✅ **Automatic accessibility validation** before RAG ingestion  
✅ **Detailed compliance reports** with remediation steps  
✅ **Support for PDF, Word (.docx), and Excel (.xlsx)** files  
✅ **Separate endpoint** for checking files without ingesting  
✅ **Clean separation** between RAG learning and ADA compliance  

---

## 🏗️ Architecture: RAG vs. ADA Checking

The system maintains **clear separation** between two distinct concerns:

### 1. RAG System (Existing - Learning from Documents)
**Purpose:** Enable semantic search and question-answering over policy documents

**Location:** `data/policies/{policy_id}/`

**What it does:**
- Extracts text from PDFs
- Chunks text into searchable segments
- Creates embeddings (vector representations)
- Builds FAISS search index
- Answers questions using relevant chunks

**Files:**
```
data/policies/policy-abc123/
├── source.pdf       ← Original document
├── chunks.json      ← Text chunks for search
├── metadata.json    ← Ingestion metadata
└── index.faiss      ← Vector search index
```

### 2. ADA Checking System (New - Validating Accessibility)
**Purpose:** Ensure documents meet WCAG AA accessibility standards

**Location:** `data/accessibility_reports/`

**What it does:**
- Checks PDF structure (tags, language, reading order)
- Validates alt text on images
- Verifies heading hierarchy
- Checks color contrast
- Validates table headers
- Reports all issues with remediation steps

**Files:**
```
data/accessibility_reports/
├── ada_xyz789.json  ← Compliance report for file 1
├── ada_def456.json  ← Compliance report for file 2
└── ...
```

### Why Keep Them Separate?

✅ **Independent Evolution:** RAG and ADA can be updated separately  
✅ **Clear Audit Trail:** All compliance checks in one location  
✅ **Flexibility:** Can check files without ingesting them  
✅ **Compliance Focus:** Easy to generate government compliance reports  

---

## 📦 Installation

### Step 1: Install New Dependencies

```bash
# Add these to your requirements.txt or install directly:
pip install python-docx==1.1.2
pip install openpyxl==3.1.2
pip install Pillow==10.2.0
```

Or use the provided file:
```bash
cat requirements_accessibility.txt >> requirements.txt
pip install -r requirements.txt
```

### Step 2: Copy New Files to Your Project

Copy these new files to your project:

```
your_project/
├── accessibility_models.py      ← NEW: Data structures for reports
├── accessibility_utils.py       ← NEW: File-specific checking logic
├── accessibility_checker.py     ← NEW: Main orchestrator
├── store.py                     ← UPDATED: Added report storage methods
└── main.py                      ← UPDATED: Added /check-accessibility endpoints
```

### Step 3: Update Import Paths

The new files assume they're in the same directory as your existing code. If your project structure is different, update the imports:

```python
# If you have a different structure like:
# app/
#   rag/
#     __init__.py
#   accessibility/
#     __init__.py

# Update imports in the new files accordingly
from app.rag.store import PolicyStore  # Adjust path as needed
```

---

## 🚀 Usage Guide

### Workflow 1: Check Accessibility First (Recommended)

**Scenario:** You want to check a file's accessibility before deciding to ingest it.

```bash
# Upload and check a file
curl -X POST "http://localhost:8000/check-accessibility" \
  -F "file=@/path/to/policy.pdf"

# Response includes full report:
{
  "report": {
    "file_name": "policy.pdf",
    "is_compliant": false,
    "total_issues": 5,
    "critical_issues": 3,
    "issues": [
      {
        "wcag_criterion": "1.3.1",
        "level": "critical",
        "description": "PDF is not tagged. Screen readers cannot understand structure.",
        "location": "Document properties",
        "remediation": "1. Open PDF in Adobe Acrobat Pro\n2. Go to Tools → Accessibility → Autotag Document..."
      }
    ],
    "summary": "Document does NOT meet WCAG AA standards...",
    "recommendations": [
      "Tag the PDF using Adobe Acrobat Pro's auto-tag feature...",
      "Add alternative text to 3 image(s)."
    ]
  }
}
```

### Workflow 2: Direct Ingestion (Automatic Check)

**Scenario:** You want to ingest a file. System automatically checks accessibility first.

```bash
# Try to ingest a file
curl -X POST "http://localhost:8000/ingest" \
  -F "pdf=@/path/to/policy.pdf"

# If file is NOT compliant (HTTP 400):
{
  "detail": {
    "message": "File 'policy.pdf' does NOT meet WCAG AA standards...",
    "is_compliant": false,
    "total_issues": 5,
    "critical_issues": 3,
    "report_id": "ada_abc123def456",
    "top_issues": [
      "PDF is not tagged. Screen readers cannot understand structure.",
      "Document language is not specified.",
      "Image #1 is missing alternative text."
    ]
  }
}

# Get full report details:
curl "http://localhost:8000/check-accessibility/ada_abc123def456"

# If file IS compliant (HTTP 200):
{
  "policy_id": "policy-xyz789",
  "pages": 45,
  "chunks": 120,
  "embedding_model": "nomic-embed-text:latest",
  "accessibility_report_id": "ada_abc123def456"
}
# → File is now in RAG system and ready for questions
```

### Workflow 3: Query Ingested Policies

Once a file is successfully ingested, you can ask questions:

```bash
curl -X POST "http://localhost:8000/ask" \
  -H "Content-Type: application/json" \
  -d '{
    "policy_id": "policy-xyz789",
    "question": "What is the vacation policy for new employees?"
  }'

# Response includes answer with citations:
{
  "answer": "New employees accrue 10 days of vacation per year (Page 12, p12_c3)...",
  "citations": [
    {
      "page": 12,
      "chunk_id": "p12_c3",
      "excerpt": "Full-time employees hired after January 1..."
    }
  ]
}
```

---

## 🔍 What Gets Checked?

### PDF Files (.pdf)

✅ **Tagged Structure** - Required for screen readers  
✅ **Document Language** - Required for proper pronunciation  
✅ **Image Alt Text** - Every image must describe its content  
✅ **Text Extractability** - Not a scanned image  
✅ **Reading Order** - Logical content flow  
✅ **Heading Structure** - Proper nesting (H1 → H2 → H3)  

### Word Documents (.docx)

✅ **Document Language** - Specified in properties  
✅ **Image Alt Text** - All images described  
✅ **Heading Styles** - Uses built-in styles, not just bold  
✅ **Table Headers** - Tables have header rows  
✅ **Color Contrast** - Manual verification note  
✅ **Hyperlinks** - Descriptive text (not "click here")  

### Excel Files (.xlsx)

✅ **Sheet Names** - Meaningful names (not "Sheet1")  
✅ **Data Structure** - Clear headers and organization  
✅ **Merged Cells** - Avoided (breaks screen readers)  
✅ **Color Contrast** - Manual verification note  
✅ **Chart Alt Text** - All charts described  

---

## 📊 Understanding Reports

### Report Structure

```json
{
  "file_name": "employee_handbook.pdf",
  "file_type": "pdf",
  "file_size_bytes": 2458912,
  "checked_at": "2025-02-12T14:30:00Z",
  
  "is_compliant": false,           // ← Overall status
  "compliance_level_met": null,    // ← "AA" if compliant
  
  "total_issues": 8,               // ← Total problems found
  "critical_issues": 3,            // ← Must fix for AA
  "error_issues": 2,               // ← Should fix for AA
  "warning_issues": 3,             // ← Nice to fix
  
  "issues": [...],                 // ← Detailed list
  "summary": "...",                // ← Human-readable summary
  "recommendations": [...]         // ← What to do next
}
```

### Issue Severity Levels

| Level | Meaning | Blocks Compliance? |
|-------|---------|-------------------|
| **CRITICAL** | Completely blocks users with disabilities | ✅ Yes |
| **ERROR** | Makes content very difficult to access | ✅ Yes |
| **WARNING** | Could cause problems for some users | ❌ No |
| **INFO** | Best practice recommendation | ❌ No |

### WCAG Success Criteria Reference

Each issue includes a WCAG criterion number. Here are the most common:

- **1.1.1** - Non-text Content (alt text for images)
- **1.3.1** - Info and Relationships (headings, tables, structure)
- **1.3.2** - Meaningful Sequence (reading order)
- **1.4.3** - Contrast (color contrast ratios)
- **2.4.2** - Page Titled (document has title)
- **2.4.4** - Link Purpose (descriptive hyperlinks)
- **2.4.6** - Headings and Labels (descriptive headers)
- **3.1.1** - Language of Page (document language)

Full WCAG 2.1 guidelines: https://www.w3.org/WAI/WCAG21/quickref/

---

## 🎨 Next Steps: UI/UX Design

Now that the backend is working, here's how to build a user interface:

### Option 1: Simple Web Dashboard (Recommended First)

**Technology:** HTML + JavaScript + Fetch API

**Features:**
1. **Upload Form**
   - Drag-and-drop file upload
   - Shows file type icon and size
   - "Check Accessibility" button

2. **Results Display**
   - ✅ Green checkmark if compliant
   - ❌ Red X if not compliant
   - Collapsible issue list
   - Color-coded by severity (red=critical, yellow=warning)

3. **Issue Details**
   - Accordion-style expandable items
   - Each issue shows:
     * Description
     * Location in document
     * WCAG criterion link
     * Step-by-step remediation
   
4. **Actions**
   - "Download Report" (PDF or JSON)
   - "Ingest Anyway" (for testing only)
   - "Fix and Re-upload"

**Example HTML Structure:**
```html
<div class="upload-area">
  <input type="file" id="fileInput" accept=".pdf,.docx,.xlsx">
  <button onclick="checkAccessibility()">Check File</button>
</div>

<div id="results" style="display:none;">
  <div class="status-badge">
    <!-- ✅ Compliant or ❌ Not Compliant -->
  </div>
  
  <div class="issues-list">
    <div class="issue critical">
      <h3>PDF is not tagged</h3>
      <p>Screen readers cannot understand document structure.</p>
      <button>Show Fix Instructions</button>
    </div>
  </div>
</div>
```

### Option 2: C# Blazor Interface (Your Specialty!)

Since you're experienced with **Blazor Server**, here's how to integrate:

**1. Create Blazor Component:**
```razor
@page "/accessibility-checker"
@inject HttpClient Http

<h1>ADA Compliance Checker</h1>

<InputFile OnChange="HandleFileSelected" accept=".pdf,.docx,.xlsx"/>
<button @onclick="CheckFile">Check Accessibility</button>

@if (report != null)
{
    <div class="report">
        <StatusBadge IsCompliant="@report.IsCompliant"/>
        
        @if (!report.IsCompliant)
        {
            <IssuesList Issues="@report.Issues"/>
        }
    </div>
}

@code {
    private AccessibilityReport? report;
    private IBrowserFile? selectedFile;
    
    private async Task CheckFile()
    {
        // Call your FastAPI backend
        var content = new MultipartFormDataContent();
        var fileStream = selectedFile.OpenReadStream();
        content.Add(new StreamContent(fileStream), "file", selectedFile.Name);
        
        var response = await Http.PostAsync(
            "http://localhost:8000/check-accessibility", 
            content
        );
        
        if (response.IsSuccessStatusCode)
        {
            var json = await response.Content.ReadAsStringAsync();
            report = JsonSerializer.Deserialize<AccessibilityReport>(json);
        }
    }
}
```

**2. Add Telerik Components** (since you use Telerik):
```razor
<TelerikUpload SaveUrl="@SaveUrl" 
               RemoveUrl="@RemoveUrl"
               AllowedExtensions="@(new List<string> { ".pdf", ".docx", ".xlsx" })"
               OnSuccess="@OnUploadSuccess"/>

@if (report != null)
{
    <TelerikGrid Data="@report.Issues">
        <GridColumns>
            <GridColumn Field="Level" Title="Severity">
                <Template>
                    @{
                        var issue = context as AccessibilityIssue;
                        <span class="badge @GetSeverityClass(issue.Level)">
                            @issue.Level
                        </span>
                    }
                </Template>
            </GridColumn>
            <GridColumn Field="Description" Title="Issue"/>
            <GridColumn Field="Location" Title="Location"/>
            <GridCommand>
                <GridCommandButton OnClick="@(() => ShowRemediation(context))">
                    Fix Instructions
                </GridCommandButton>
            </GridCommand>
        </GridColumns>
    </TelerikGrid>
}
```

**3. Add Accessibility-Focused UI:**
Since this is for government ADA compliance, the UI itself must be accessible:

```css
/* High contrast mode support */
@media (prefers-contrast: high) {
    .issue.critical { background: #ff0000; color: #ffffff; }
}

/* Keyboard navigation */
.issue:focus {
    outline: 3px solid #005fcc;
    outline-offset: 2px;
}

/* Screen reader announcements */
<div role="status" aria-live="polite" class="sr-only">
    @if (report?.IsCompliant == true)
    {
        <span>File is accessible and meets WCAG AA standards</span>
    }
</div>
```

### Option 3: Dashboard for Compliance Officers

**Features:**
- List all checked files
- Filter by compliance status
- Generate compliance reports
- Track remediation progress
- Export to Excel for audits

**API Endpoint Already Available:**
```
GET /accessibility-reports
```

---

## 🔧 Customization Options

### Change WCAG Level Requirement

Currently set to **WCAG Level AA**. To require AAA:

```python
# In accessibility_checker.py, _build_report method:

# Change this:
blocking_issues = critical_count + error_count

# To this (warnings also block AAA):
blocking_issues = critical_count + error_count + warning_count
```

### Add Custom Checks

Example: Check for specific government branding requirements

```python
# In accessibility_utils.py, add new check:

def check_government_branding(pdf_path: str) -> AccessibilityIssue | None:
    """Check if PDF has required government logo and seal."""
    doc = fitz.open(pdf_path)
    first_page = doc[0]
    
    # Check for logo image
    images = first_page.get_images()
    if len(images) == 0:
        return AccessibilityIssue(
            wcag_criterion="custom-1",
            level=IssueLevel.WARNING,
            description="Government logo not found on first page",
            location="Page 1",
            remediation="Add agency logo to header",
            blocks_compliance=False
        )
    
    return None
```

### Skip Checks for Internal Documents

```python
# In main.py, add parameter:

@app.post("/ingest")
async def ingest(
    pdf: UploadFile = File(...),
    skip_accessibility: bool = False,  # NEW
    ...
):
    if skip_accessibility:
        # Skip checks for internal-only documents
        pass
    else:
        # Run normal accessibility check
        ...
```

---

## 📚 Learning Resources

### Understanding the Code

Since you're learning Python, here are the key concepts used:

**1. Type Hints:**
```python
def check_file(file_path: str) -> AccessibilityReport:
#              ^^^^^^^^^^^       ^^^^^^^^^^^^^^^^^^^
#              Parameter type    Return type
```

**2. Pydantic Models:**
```python
class AccessibilityIssue(BaseModel):
    wcag_criterion: str  # Auto-validates that it's a string
    level: IssueLevel    # Auto-validates it's one of the enum values
```

**3. List Comprehensions:**
```python
# Traditional loop:
critical = []
for issue in issues:
    if issue.level == IssueLevel.CRITICAL:
        critical.append(issue)

# Python way (list comprehension):
critical = [issue for issue in issues if issue.level == IssueLevel.CRITICAL]
```

**4. Context Managers (with statement):**
```python
with tempfile.NamedTemporaryFile() as tmp:
    # File is automatically cleaned up when this block exits
    # Even if an error occurs!
```

### WCAG Resources

- **WCAG 2.1 Quick Reference:** https://www.w3.org/WAI/WCAG21/quickref/
- **How to Meet WCAG (Quick Guide):** https://www.w3.org/WAI/WCAG21/quickref/
- **WebAIM (Practical Tutorials):** https://webaim.org/
- **Section 508 (US Government):** https://www.section508.gov/

### Testing Tools

To manually verify accessibility:
- **PAC 3** (PDF Accessibility Checker) - Free tool from Access for All
- **Adobe Acrobat Pro** - Industry standard for PDF accessibility
- **NVDA** (Screen Reader) - Free, test how blind users experience content
- **Color Contrast Analyzer** - https://www.tpgi.com/color-contrast-checker/

---

## ❓ FAQ

**Q: Can I check Word/Excel files but only ingest PDFs?**  
A: Yes! Use the `/check-accessibility` endpoint for Word/Excel. The `/ingest` endpoint currently only accepts PDFs, but you can extend it.

**Q: What if I want to ingest a file but fix accessibility later?**  
A: Currently blocked by design for government compliance. If you need this, add a `skip_accessibility=true` parameter as shown in the customization section.

**Q: Are these checks 100% accurate?**  
A: No. Some checks (like "is alt text meaningful?") require human judgment. This tool automates what's technically feasible. Manual review is still recommended for legal compliance.

**Q: Can I customize which checks are run?**  
A: Yes! Edit `accessibility_utils.py` and comment out checks you don't need, or add new custom checks.

**Q: How do I fix a non-compliant PDF?**  
A: The reports include step-by-step remediation instructions. Most fixes require Adobe Acrobat Pro (standard tool for PDF accessibility).

---

## 🐛 Troubleshooting

### "ModuleNotFoundError: No module named 'docx'"
```bash
pip install python-docx
```

### "libmupdf.so not found" (Linux)
```bash
sudo apt-get install mupdf mupdf-tools
```

### "FAISS index dimension mismatch"
The accessibility check doesn't touch FAISS. If you see this, it's from the RAG system. Make sure you're using the same embedding model for ingestion and querying.

### High Memory Usage
PDFs are loaded into memory for checking. For very large PDFs (>100MB), consider:
1. Checking files in a separate worker process
2. Streaming PDF pages instead of loading entire file
3. Setting memory limits in Docker/Kubernetes

---

## 📝 Summary

You now have a complete ADA compliance checking system integrated with your RAG pipeline:

✅ **Backend:** FastAPI endpoints for checking and ingesting  
✅ **Storage:** Separate folders for RAG data and compliance reports  
✅ **Validation:** WCAG AA-level checks with detailed remediation  
✅ **Documentation:** Complete with examples and learning resources  

**Next Steps:**
1. Test the endpoints with your existing PDFs
2. Build a simple web UI for file upload and results display
3. Add any custom checks specific to your government requirements
4. Deploy and start building your compliance dashboard!

Need help with the UI or have questions? Just ask! 🚀
