import os
import sys
from reportlab.lib import colors
from reportlab.lib.colors import HexColor
from reportlab.pdfgen import canvas
import pypdfium2 as pdfium

def create_architecture_diagram(pdf_path: str, png_path: str):
    # Canvas dimensions: 1920 x 1200 pt (16:10 high-definition landscape)
    W = 1920
    H = 1200
    
    c = canvas.Canvas(pdf_path, pagesize=(W, H))
    
    # ── Background ───────────────────────────────────────────────────────────
    c.setFillColor(HexColor("#f8fafc"))
    c.rect(0, 0, W, H, fill=1, stroke=0)
    
    # Outer subtle border
    c.setStrokeColor(HexColor("#cbd5e1"))
    c.setLineWidth(1.5)
    c.rect(10, 10, W - 20, H - 20, fill=0, stroke=1)
    
    # ── Top Title Banner ─────────────────────────────────────────────────────
    banner_h = 75
    banner_y = H - 10 - banner_h
    c.setFillColor(HexColor("#0f2744"))
    c.rect(10, banner_y, W - 20, banner_h, fill=1, stroke=0)
    
    c.setFillColor(colors.white)
    c.setFont("Helvetica-Bold", 26)
    c.drawCentredString(W / 2, banner_y + 42, "FIR VisionAI – Complete Architecture & Step-by-Step User Guide")
    
    c.setFont("Helvetica", 13)
    c.setFillColor(HexColor("#93c5fd"))
    c.drawCentredString(W / 2, banner_y + 18, "Unified FIR & AI-Powered Case Intelligence Platform | Andhra Pradesh Prohibition & Excise Department")
    
    # Helper to draw section header pill
    def draw_section_header(title: str, x: float, y: float, w: float):
        c.setFillColor(HexColor("#1d4ed8"))
        c.roundRect(x, y - 24, w, 24, 4, fill=1, stroke=0)
        c.setFillColor(colors.white)
        c.setFont("Helvetica-Bold", 11)
        c.drawString(x + 10, y - 17, title)
        
    def draw_box(x: float, y: float, w: float, h: float, bg_color: str, border_color: str, title: str = "", title_color: str = "#0f172a"):
        c.setFillColor(HexColor(bg_color))
        c.setStrokeColor(HexColor(border_color))
        c.setLineWidth(1.2)
        c.roundRect(x, y, w, h, 6, fill=1, stroke=1)
        if title:
            c.setFillColor(HexColor(title_color))
            c.setFont("Helvetica-Bold", 10.5)
            c.drawCentredString(x + w / 2, y + h - 18, title)

    # ── SECTION 1: System Architecture Overview ──────────────────────────────
    s1_x = 20
    s1_y = H - 95
    s1_w = W - 40
    s1_h = 320
    
    draw_section_header("1. System Architecture Overview", s1_x, s1_y, 240)
    
    # Outer frame for section 1
    c.setStrokeColor(HexColor("#bfdbfe"))
    c.setLineWidth(1.5)
    c.setFillColor(HexColor("#ffffff"))
    c.roundRect(s1_x, s1_y - s1_h, s1_w, s1_h - 26, 8, fill=1, stroke=1)
    
    # 6 Columns inside Section 1
    gap = 22
    card_w = (s1_w - 40 - (gap * 5)) / 6
    card_h = s1_h - 60
    card_y = s1_y - s1_h + 16
    
    cols = [
        {
            "title": "Users (Frontend)",
            "bg": "#eff6ff", "border": "#93c5fd",
            "items": [
                "👮 Excise Officer",
                "🚓 Police Officer",
                "🕵 Investigation Team",
                "👔 Admin / Supervisors",
                "⚖ Legal & Policy Team",
                "🏛 Department Headquarters"
            ]
        },
        {
            "title": "Frontend (React)",
            "bg": "#f0fdf4", "border": "#86efac",
            "items": [
                "💻 Web Application (React 18)",
                "• Interactive Dashboard",
                "• Case Management Workspace",
                "• New FIR Intake & Evidence",
                "• AI & Legal Intelligence",
                "• Knowledge Base Hub",
                "• AI FIR Chatbot (RAG)",
                "• Investigation Graph Tools",
                "• Administration & Roles",
                "• Reports & Downloads"
            ]
        },
        {
            "title": "Backend (FastAPI)",
            "bg": "#faf5ff", "border": "#d8b4fe",
            "items": [
                "⚡ FastAPI (Python 3.12)",
                "• Auth & RBAC Authorization",
                "• FIR & Case Management APIs",
                "• Document Upload & OCR APIs",
                "• AI Extraction & Validation",
                "• Legal Intelligence APIs",
                "• RAG / Chatbot APIs",
                "• Entity Matching & Graph APIs",
                "• Administration & Audit APIs",
                "• Multi-format Export APIs"
            ]
        },
        {
            "title": "Processing Services",
            "bg": "#fefce8", "border": "#fde047",
            "items": [
                "⚙ Async Processing Workers",
                "• Image/PDF Pre-processing",
                "• Multilingual OCR (TE/HI/EN)",
                "• Layout & Zone Segmentation",
                "• Field Validation Engine",
                "• Legal Section Matcher",
                "• Entity Recognition (NER)",
                "• RAG Indexing & Chunking",
                "• Background Job Queues"
            ]
        },
        {
            "title": "Data Layer (Supabase)",
            "bg": "#ecfdf5", "border": "#6ee7b7",
            "items": [
                "🗄 Supabase (PostgreSQL)",
                "• Application Relational DB",
                "• pgvector Embedding Store",
                "• Evidence Storage Buckets",
                "• Row Level Security (RLS)",
                "• Realtime Event Bus",
                "• Automatic Daily Backups",
                "• Complete Audit Trail Tables"
            ]
        },
        {
            "title": "AI & External Services",
            "bg": "#f0f9ff", "border": "#7dd3fc",
            "items": [
                "🧠 Foundation AI & Models",
                "• Gemini 1.5 Pro / Flash Vision",
                "• Tesseract Indic OCR Engine",
                "• Text Embeddings (1536-dim)",
                "• Official Legal Acts Corpus",
                "• Nominatim OpenStreetMap",
                "• AP 26-District Centroid DB",
                "• Google Maps Directions API"
            ]
        }
    ]
    
    for i, col in enumerate(cols):
        cx = s1_x + 20 + i * (card_w + gap)
        draw_box(cx, card_y, card_w, card_h, col["bg"], col["border"], col["title"])
        
        # Draw items
        c.setFont("Helvetica", 9)
        c.setFillColor(HexColor("#1e293b"))
        item_y = card_y + card_h - 40
        for item in col["items"]:
            if item.startswith("💻") or item.startswith("⚡") or item.startswith("⚙") or item.startswith("🗄") or item.startswith("🧠") or item.startswith("👮"):
                c.setFont("Helvetica-Bold", 9.5)
                c.setFillColor(HexColor("#0f172a"))
            else:
                c.setFont("Helvetica", 8.5)
                c.setFillColor(HexColor("#334155"))
            c.drawString(cx + 12, item_y, item)
            item_y -= 19
            
        # Draw arrow to next column if not last
        if i < len(cols) - 1:
            arrow_x = cx + card_w + 3
            arrow_y = card_y + card_h / 2
            c.setStrokeColor(HexColor("#3b82f6"))
            c.setFillColor(HexColor("#3b82f6"))
            c.setLineWidth(2)
            c.line(arrow_x, arrow_y, arrow_x + gap - 8, arrow_y)
            # Arrowhead
            p = c.beginPath()
            p.moveTo(arrow_x + gap - 6, arrow_y)
            p.lineTo(arrow_x + gap - 12, arrow_y + 4)
            p.lineTo(arrow_x + gap - 12, arrow_y - 4)
            p.close()
            c.drawPath(p, fill=1, stroke=0)
            
            # Sub-labels for arrows
            c.setFont("Helvetica-Bold", 6.5)
            c.setFillColor(HexColor("#2563eb"))
            if i == 0:
                c.drawCentredString(arrow_x + (gap - 8) / 2, arrow_y + 7, "HTTPS")
            elif i == 2:
                c.drawCentredString(arrow_x + (gap - 8) / 2, arrow_y + 7, "Async")

    # ── SECTION 2: End-to-End Workflow (6 Main Stages) ───────────────────────
    s2_y = s1_y - s1_h - 18
    s2_h = 135
    draw_section_header("2. End-to-End Workflow (6 Main Stages)", s1_x, s2_y, 300)
    
    # Outer frame for section 2
    c.setStrokeColor(HexColor("#cbd5e1"))
    c.setLineWidth(1)
    c.setFillColor(HexColor("#ffffff"))
    c.roundRect(s1_x, s2_y - s2_h, s1_w, s2_h - 26, 8, fill=1, stroke=1)
    
    w_card_gap = 14
    w_card_w = (s1_w - 30 - (w_card_gap * 5)) / 6
    w_card_h = s2_h - 48
    w_card_y = s2_y - s2_h + 10
    
    workflow_stages = [
        {
            "num": "1. Evidence Upload & OCR",
            "bg": "#dbeafe", "border": "#60a5fa",
            "items": ["• Upload FIR (PDF / Image)", "• Pre-process & Despeckle", "• Extract Multilingual Text", "• Store Raw Evidence PDF", "• Bounding-box Inspection"]
        },
        {
            "num": "2. Officer Review & Sign-Off",
            "bg": "#dcfce7", "border": "#4ade80",
            "items": ["• Verify Extracted Fields", "• Correct Uncertain Data", "• Check Original FIR Page", "• Mandatory Human Sign-off", "• Approve or Reject Draft"]
        },
        {
            "num": "3. AI & Legal Intelligence",
            "bg": "#fef3c7", "border": "#facc15",
            "items": ["• Suggest Legal Sections", "• Match BNS / AP Excise", "• Confidence Scoring", "• Statutory Reference Links", "• Essential Ingredient Checks"]
        },
        {
            "num": "4. Investigation Tools",
            "bg": "#f3e8ff", "border": "#c084fc",
            "items": ["• Person / Vehicle Entities", "• Pin Exact Incident Map", "• Criminal Network Graph", "• Cross-case Connections", "• Investigation Timeline"]
        },
        {
            "num": "5. Administration & FIRs",
            "bg": "#ffe4e6", "border": "#f87171",
            "items": ["• Jurisdiction & Role Scopes", "• Manage Knowledge Base", "• Search Historic FIRs", "• Immutable Audit Trail", "• System Health Monitor"]
        },
        {
            "num": "6. Repeat Offender Intelligence",
            "bg": "#ccfbf1", "border": "#2dd4bf",
            "items": ["• Cross-Station Repeat Match", "• Link Alias & Vehicles", "• Network Visualization", "• Prior Conviction Insights", "• Seizure Pattern Analysis"]
        }
    ]
    
    for i, stg in enumerate(workflow_stages):
        wx = s1_x + 15 + i * (w_card_w + w_card_gap)
        draw_box(wx, w_card_y, w_card_w, w_card_h, stg["bg"], stg["border"], stg["num"])
        
        c.setFont("Helvetica", 8)
        c.setFillColor(HexColor("#1e293b"))
        item_y = w_card_y + w_card_h - 32
        for itm in stg["items"]:
            c.drawString(wx + 8, item_y, itm)
            item_y -= 14
            
        if i < len(workflow_stages) - 1:
            arrow_x = wx + w_card_w + 2
            arrow_y = w_card_y + w_card_h / 2
            c.setFillColor(HexColor("#3b82f6"))
            c.setStrokeColor(HexColor("#3b82f6"))
            c.setLineWidth(1.5)
            c.line(arrow_x, arrow_y, arrow_x + w_card_gap - 6, arrow_y)
            p = c.beginPath()
            p.moveTo(arrow_x + w_card_gap - 4, arrow_y)
            p.lineTo(arrow_x + w_card_gap - 9, arrow_y + 3)
            p.lineTo(arrow_x + w_card_gap - 9, arrow_y - 3)
            p.close()
            c.drawPath(p, fill=1, stroke=0)

    # ── MIDDLE 4 SECTIONS (3, 4, 5, 6) ────────────────────────────────────────
    mid_y = s2_y - s2_h - 18
    mid_h = 325
    
    # Section 3: Frontend - Key Pages (Left)
    s3_w = 440
    draw_section_header("3. Frontend - Key Pages and Buttons", s1_x, mid_y, 270)
    c.setStrokeColor(HexColor("#cbd5e1"))
    c.setFillColor(HexColor("#ffffff"))
    c.roundRect(s1_x, mid_y - mid_h, s3_w, mid_h - 26, 8, fill=1, stroke=1)
    
    pages = [
        ("Dashboard", "Total cases, under review, approved, pending drafts. Filtered KPI routing.", "#3b82f6"),
        ("New Case Intake", "Upload handwritten/printed FIR scans, monitor OCR progress.", "#10b981"),
        ("Case Management", "Search, filter by station/year/status, open evidence workspace.", "#06b6d4"),
        ("AI & Legal Intel", "View extracted sections, statutory penalties, legal citations.", "#8b5cf6"),
        ("Knowledge Base", "8 authorized categories: Official Laws, Circulars, SOPs, Seizures.", "#f59e0b"),
        ("AI FIR Chatbot", "Ask case questions, legal provisions, cross-case queries with citations.", "#ec4899"),
        ("Investigation Tools", "Entity graph, repeat offender detection, incident location map.", "#6366f1"),
        ("Administration", "Officer roles, jurisdiction scopes (State/Dist/Station), audit logs.", "#64748b"),
        ("Downloads & Reports", "Export Case Diary, Chargesheet in DOCX/PDF, architecture guides.", "#14b8a6")
    ]
    
    py_item = mid_y - 48
    for p_title, p_desc, p_color in pages:
        # Badge
        c.setFillColor(HexColor(p_color))
        c.roundRect(s1_x + 12, py_item - 14, 115, 17, 3, fill=1, stroke=0)
        c.setFillColor(colors.white)
        c.setFont("Helvetica-Bold", 8)
        c.drawString(s1_x + 18, py_item - 9, p_title)
        
        # Description
        c.setFillColor(HexColor("#334155"))
        c.setFont("Helvetica", 7.5)
        c.drawString(s1_x + 135, py_item - 9, p_desc[:62])
        py_item -= 29

    # Section 4: Database Schema (Center)
    s4_x = s1_x + s3_w + 16
    s4_w = 660
    draw_section_header("4. Database Schema (Supabase - Key Tables)", s4_x, mid_y, 310)
    c.setStrokeColor(HexColor("#cbd5e1"))
    c.setFillColor(HexColor("#ffffff"))
    c.roundRect(s4_x, mid_y - mid_h, s4_w, mid_h - 26, 8, fill=1, stroke=1)
    
    tables = [
        {"name": "users", "fields": ["id (PK)", "username", "role (State/Dist/Stn)", "jurisdiction", "full_name", "status"], "x": s4_x + 16, "y": mid_y - 120, "w": 140, "h": 90, "bg": "#eff6ff"},
        {"name": "cases / firs", "fields": ["id (PK)", "fir_number", "station", "district", "status", "incident_location", "created_at"], "x": s4_x + 175, "y": mid_y - 120, "w": 150, "h": 90, "bg": "#f0fdf4"},
        {"name": "fir_documents", "fields": ["id (PK)", "case_id (FK)", "file_name", "storage_path", "ocr_text", "page_count"], "x": s4_x + 345, "y": mid_y - 120, "w": 140, "h": 90, "bg": "#fefce8"},
        {"name": "fir_extractions", "fields": ["id (PK)", "case_id (FK)", "field_name", "field_value", "confidence", "verified"], "x": s4_x + 505, "y": mid_y - 120, "w": 140, "h": 90, "bg": "#fdf2f8"},
        {"name": "knowledge_base", "fields": ["id (PK)", "title", "category (1-8)", "file_path", "content_text", "created_at"], "x": s4_x + 16, "y": mid_y - 250, "w": 140, "h": 90, "bg": "#faf5ff"},
        {"name": "kb_chunks", "fields": ["id (PK)", "doc_id (FK)", "chunk_text", "embedding (1536)", "metadata_json"], "x": s4_x + 175, "y": mid_y - 250, "w": 150, "h": 90, "bg": "#f0fdfa"},
        {"name": "chat_history", "fields": ["id (PK)", "user_id (FK)", "source_type", "question", "answer", "citations"], "x": s4_x + 345, "y": mid_y - 250, "w": 140, "h": 90, "bg": "#fff7ed"},
        {"name": "audit_logs", "fields": ["id (PK)", "actor_id (FK)", "action_type", "object_type", "object_id", "timestamp"], "x": s4_x + 505, "y": mid_y - 250, "w": 140, "h": 90, "bg": "#f1f5f9"},
    ]
    
    for tbl in tables:
        draw_box(tbl["x"], tbl["y"], tbl["w"], tbl["h"], tbl["bg"], "#94a3b8")
        # Table Header
        c.setFillColor(HexColor("#0f2744"))
        c.rect(tbl["x"], tbl["y"] + tbl["h"] - 18, tbl["w"], 18, fill=1, stroke=0)
        c.setFillColor(colors.white)
        c.setFont("Helvetica-Bold", 8.5)
        c.drawCentredString(tbl["x"] + tbl["w"] / 2, tbl["y"] + tbl["h"] - 13, tbl["name"])
        
        # Fields
        c.setFont("Helvetica", 7.5)
        c.setFillColor(HexColor("#1e293b"))
        fy = tbl["y"] + tbl["h"] - 30
        for f in tbl["fields"]:
            c.drawString(tbl["x"] + 6, fy, f)
            fy -= 11

    # Section 5: AI & RAG Pipeline (Right 1)
    s5_x = s4_x + s4_w + 16
    s5_w = 370
    draw_section_header("5. AI & RAG Pipeline", s5_x, mid_y, 180)
    c.setStrokeColor(HexColor("#cbd5e1"))
    c.setFillColor(HexColor("#ffffff"))
    c.roundRect(s5_x, mid_y - mid_h, s5_w, mid_h - 26, 8, fill=1, stroke=1)
    
    rag_steps = [
        ("1. Multi-Category Ingestion", "Upload official laws, circulars, SOPs, seizures, FIRs"),
        ("2. Cleaning & Chunking", "Normalized text extraction, chunking with overlap"),
        ("3. Embedding Generation", "Gemini / text-embedding-3 vectors (1536-dim)"),
        ("4. Indexing in Supabase", "Stored in pgvector with HNSW cosine distance index"),
        ("5. Hybrid Vector Retrieval", "Balanced cosine retrieval across 8 authorized scopes"),
        ("6. Context Grounding", "Strict prompt template enforcing evidence boundaries"),
        ("7. Citations & Verification", "Answers returned with exact document name & citations")
    ]
    
    ry = mid_y - 48
    for s_title, s_desc in rag_steps:
        c.setFillColor(HexColor("#eff6ff"))
        c.setStrokeColor(HexColor("#93c5fd"))
        c.roundRect(s5_x + 10, ry - 18, s5_w - 20, 30, 4, fill=1, stroke=1)
        
        c.setFillColor(HexColor("#1e40af"))
        c.setFont("Helvetica-Bold", 8)
        c.drawString(s5_x + 18, ry + 1, s_title)
        
        c.setFillColor(HexColor("#475569"))
        c.setFont("Helvetica", 7)
        c.drawString(s5_x + 18, ry - 11, s_desc)
        ry -= 38

    # Section 6: Security & Access Control (Right 2)
    s6_x = s5_x + s5_w + 16
    s6_w = W - s6_x - 20
    draw_section_header("6. Security & Control", s6_x, mid_y, 180)
    c.setStrokeColor(HexColor("#cbd5e1"))
    c.setFillColor(HexColor("#ffffff"))
    c.roundRect(s6_x, mid_y - mid_h, s6_w, mid_h - 26, 8, fill=1, stroke=1)
    
    sec_items = [
        ("🛡 Supabase Authentication", "JWT Bearer tokens with auto-refresh"),
        ("👮 Role-Based Access (RBAC)", "STATE, DISTRICT, and STATION tiers"),
        ("📍 Jurisdiction Scoping", "Officers see only authorized cases"),
        ("🔒 Row Level Security (RLS)", "Postgres kernel-enforced data rules"),
        ("🗂 Signed Evidence URLs", "Direct access tokens for evidence PDFs"),
        ("📝 Immutable Audit Trail", "All edits, approvals & exports logged"),
        ("🔐 End-to-End Encryption", "TLS 1.3 in-transit and AES-256 at-rest"),
        ("⚠ No Auto-Guilty Finding", "AI assists only; human officer sign-off")
    ]
    
    sy = mid_y - 48
    for sc_title, sc_desc in sec_items:
        c.setFillColor(HexColor("#f8fafc"))
        c.setStrokeColor(HexColor("#e2e8f0"))
        c.roundRect(s6_x + 10, sy - 18, s6_w - 20, 30, 4, fill=1, stroke=1)
        
        c.setFillColor(HexColor("#0f172a"))
        c.setFont("Helvetica-Bold", 8)
        c.drawString(s6_x + 16, sy + 1, sc_title)
        
        c.setFillColor(HexColor("#64748b"))
        c.setFont("Helvetica", 7)
        c.drawString(s6_x + 16, sy - 11, sc_desc)
        sy -= 38

    # ── SECTION 7: Document Processing Pipeline & SECTION 8: Final Outputs ─────
    s7_y = mid_y - mid_h - 18
    s7_h = 105
    
    # Section 7: Ribbon
    s7_w = W - 40 - 320
    draw_section_header("7. Document Processing Pipeline (From Upload to Final Output)", s1_x, s7_y, 450)
    c.setStrokeColor(HexColor("#cbd5e1"))
    c.setFillColor(HexColor("#ffffff"))
    c.roundRect(s1_x, s7_y - s7_h, s7_w, s7_h - 26, 8, fill=1, stroke=1)
    
    p_steps = [
        "1. Upload FIR\n(PDF / Image)",
        "2. Storage Bucket\n& Checksum",
        "3. Deskew, Denoise\n& Binarize",
        "4. Multilingual OCR\n(TE / HI / EN)",
        "5. Field Validation\nConfidence Score",
        "6. Officer Review\n& Edit / Sign-Off",
        "7. Index for Search\n(Keywords+Vectors)",
        "8. Intelligence Tools\n& Generation"
    ]
    
    step_gap = 10
    step_w = (s7_w - 30 - (step_gap * 7)) / 8
    step_h = s7_h - 44
    step_y = s7_y - s7_h + 10
    
    for i, st in enumerate(p_steps):
        sx = s1_x + 15 + i * (step_w + step_gap)
        c.setFillColor(HexColor("#f0fdf4"))
        c.setStrokeColor(HexColor("#86efac"))
        c.roundRect(sx, step_y, step_w, step_h, 4, fill=1, stroke=1)
        
        c.setFillColor(HexColor("#065f46"))
        c.setFont("Helvetica-Bold", 7.5)
        lines = st.split("\n")
        c.drawCentredString(sx + step_w / 2, step_y + step_h - 16, lines[0])
        c.setFont("Helvetica", 7)
        c.setFillColor(HexColor("#334155"))
        c.drawCentredString(sx + step_w / 2, step_y + step_h - 28, lines[1])
        
        # Arrow
        if i < len(p_steps) - 1:
            ax = sx + step_w + 1
            ay = step_y + step_h / 2
            c.setStrokeColor(HexColor("#10b981"))
            c.setFillColor(HexColor("#10b981"))
            c.setLineWidth(1.5)
            c.line(ax, ay, ax + step_gap - 4, ay)
            p = c.beginPath()
            p.moveTo(ax + step_gap - 2, ay)
            p.lineTo(ax + step_gap - 6, ay + 2.5)
            p.lineTo(ax + step_gap - 6, ay - 2.5)
            p.close()
            c.drawPath(p, fill=1, stroke=0)

    # Section 8: Final Outputs
    s8_x = s1_x + s7_w + 16
    s8_w = W - s8_x - 20
    draw_section_header("8. Final Outputs", s8_x, s7_y, 160)
    c.setStrokeColor(HexColor("#cbd5e1"))
    c.setFillColor(HexColor("#ffffff"))
    c.roundRect(s8_x, s7_y - s7_h, s8_w, s7_h - 26, 8, fill=1, stroke=1)
    
    outputs = [
        "📄 Structured FIR JSON Record",
        "⚖ Verified Legal Sections & Acts",
        "💬 AI Answers with Grounded Citations",
        "🗺 Incident Location on Map & GPS",
        "📊 Case Diary & Chargesheet (DOCX/PDF)"
    ]
    
    oy = s7_y - 44
    for out in outputs:
        c.setFillColor(HexColor("#1e293b"))
        c.setFont("Helvetica-Bold", 7.5)
        c.drawString(s8_x + 12, oy, out)
        oy -= 11

    c.save()
    print(f"Generated PDF: {pdf_path}")
    
    # ── Render to High-DPI PNG using pypdfium2 ───────────────────────────────
    pdf_doc = pdfium.PdfDocument(pdf_path)
    page = pdf_doc[0]
    # scale=2 yields 3840 x 2400 ultra high-definition image!
    rendered = page.render(scale=2).to_pil()
    rendered.save(png_path)
    print(f"Rendered PNG: {png_path} (Dimensions: {rendered.size})")

if __name__ == "__main__":
    out_pdf = r"C:\Users\LENOVO\.gemini\antigravity\brain\0369432a-ca12-4fca-9eeb-0b6b0602cbd3\FIR_VisionAI_Architecture_Diagram.pdf"
    out_png = r"C:\Users\LENOVO\.gemini\antigravity\brain\0369432a-ca12-4fca-9eeb-0b6b0602cbd3\FIR_VisionAI_Architecture_Diagram.png"
    create_architecture_diagram(out_pdf, out_png)
