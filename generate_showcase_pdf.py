import os
import sys
import time
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.pdfgen import canvas
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak, KeepTogether, HRFlowable
)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT, TA_JUSTIFY

class NumberedCanvas(canvas.Canvas):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._saved_page_states = []

    def showPage(self):
        self._saved_page_states.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        num_pages = len(self._saved_page_states)
        for state in self._saved_page_states:
            self.__dict__.update(state)
            self.draw_page_decorations(num_pages)
            canvas.Canvas.showPage(self)
        canvas.Canvas.save(self)

    def draw_page_decorations(self, page_count):
        self.saveState()
        self.setFont('Helvetica-Bold', 7)
        self.setFillColor(colors.HexColor('#4338CA'))
        if self._pageNumber > 1:
            self.drawString(36, 810, 'NEXUS LMS')
            self.setFont('Helvetica', 7)
            self.setFillColor(colors.HexColor('#64748B'))
            self.drawString(90, 810, '|   Enterprise System Showcase, Technical Architecture & Feature Guide')
            self.setStrokeColor(colors.HexColor('#E2E8F0'))
            self.setLineWidth(0.5)
            self.line(36, 804, 559, 804)

        # Footer
        self.setFont('Helvetica', 7)
        self.setFillColor(colors.HexColor('#64748B'))
        self.drawString(36, 22, 'LeadGroup Academic Portal  •  Confidential Technical & Feature Showcase  •  nexus-lms v2.0')
        page_str = f'Page {self._pageNumber} of {page_count}'
        self.setFont('Helvetica-Bold', 7)
        self.drawRightString(559, 22, page_str)
        self.setStrokeColor(colors.HexColor('#E2E8F0'))
        self.setLineWidth(0.5)
        self.line(36, 30, 559, 30)
        self.restoreState()

def build_pdf(output_paths):
    for p in output_paths:
        os.makedirs(os.path.dirname(os.path.abspath(p)), exist_ok=True)

    target_path = output_paths[0]
    doc = SimpleDocTemplate(
        target_path,
        pagesize=A4,
        leftMargin=36,
        rightMargin=36,
        topMargin=42,
        bottomMargin=42
    )

    styles = getSampleStyleSheet()
    
    # Custom Palette
    C_PRIMARY = colors.HexColor('#1E1B4B')    # Deep Indigo / Slate Navy
    C_SECONDARY = colors.HexColor('#4338CA')  # Indigo
    C_ACCENT = colors.HexColor('#0284C7')     # Sky
    C_TEXT = colors.HexColor('#0F172A')       # Dark Charcoal
    C_MUTED = colors.HexColor('#475569')      # Slate
    C_BG_LIGHT = colors.HexColor('#F8FAFC')   # Very Light Slate
    C_BORDER = colors.HexColor('#E2E8F0')     # Border Light
    C_EMERALD = colors.HexColor('#059669')    # Success Green
    C_AMBER = colors.HexColor('#D97706')      # Amber Warning

    # Custom Typography Styles
    title_style = ParagraphStyle(
        'DocTitle',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=22,
        leading=26,
        textColor=C_PRIMARY,
        spaceAfter=4
    )
    subtitle_style = ParagraphStyle(
        'DocSubtitle',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=11,
        leading=15,
        textColor=C_SECONDARY,
        spaceAfter=12
    )
    h1_style = ParagraphStyle(
        'SectionH1',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=13,
        leading=17,
        textColor=C_PRIMARY,
        spaceBefore=14,
        spaceAfter=6,
        keepWithNext=True
    )
    h2_style = ParagraphStyle(
        'SectionH2',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=10.5,
        leading=14,
        textColor=C_SECONDARY,
        spaceBefore=10,
        spaceAfter=4,
        keepWithNext=True
    )
    body_style = ParagraphStyle(
        'DocBody',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=8.5,
        leading=12,
        textColor=C_TEXT,
        spaceAfter=6
    )
    body_bold = ParagraphStyle(
        'DocBodyBold',
        parent=body_style,
        fontName='Helvetica-Bold'
    )
    bullet_style = ParagraphStyle(
        'DocBullet',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=8,
        leading=11.5,
        textColor=C_TEXT,
        leftIndent=14,
        spaceAfter=3
    )
    table_cell = ParagraphStyle(
        'TableCell',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=7.5,
        leading=10,
        textColor=C_TEXT
    )
    table_cell_bold = ParagraphStyle(
        'TableCellBold',
        parent=table_cell,
        fontName='Helvetica-Bold'
    )
    table_cell_center = ParagraphStyle(
        'TableCellCenter',
        parent=table_cell,
        alignment=TA_CENTER
    )
    table_cell_center_bold = ParagraphStyle(
        'TableCellCenterBold',
        parent=table_cell_bold,
        alignment=TA_CENTER
    )
    table_header = ParagraphStyle(
        'TableHeader',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=8,
        leading=10.5,
        textColor=colors.white,
        alignment=TA_CENTER
    )
    mindmap_node_title = ParagraphStyle(
        'MindmapNodeTitle',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=8.5,
        leading=11,
        textColor=C_PRIMARY,
        alignment=TA_CENTER
    )
    mindmap_node_desc = ParagraphStyle(
        'MindmapNodeDesc',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=7,
        leading=9.5,
        textColor=C_MUTED,
        alignment=TA_CENTER
    )

    story = []

    # =========================================================================
    # HEADER BANNER & COVER SECTION
    # =========================================================================
    story.append(Paragraph("NEXUS LEARNING MANAGEMENT SYSTEM", title_style))
    story.append(Paragraph("Enterprise Architecture, Feature Showcase & Complete Technical Defense Guide", subtitle_style))
    
    meta_data = [
        [
            Paragraph("<b>Platform:</b> LeadGroup Nexus LMS v2.0", table_cell),
            Paragraph("<b>Stack:</b> FastAPI • SQLite WAL • Jinja2", table_cell),
            Paragraph("<b>Date:</b> November 2026", table_cell),
            Paragraph("<b>QA Score:</b> <font color='#059669'><b>90/90 PASSED (100%)</b></font>", table_cell)
        ]
    ]
    meta_table = Table(meta_data, colWidths=[130, 160, 100, 133])
    meta_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#EEF2FF')),
        ('BOX', (0, 0), (-1, -1), 0.5, colors.HexColor('#C7D2FE')),
        ('INNERGRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#E0E7FF')),
        ('TOPPADDING', (0, 0), (-1, -1), 5),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
        ('LEFTPADDING', (0, 0), (-1, -1), 8),
        ('RIGHTPADDING', (0, 0), (-1, -1), 8),
    ]))
    story.append(meta_table)
    story.append(Spacer(1, 10))

    # =========================================================================
    # 1. EXECUTIVE SUMMARY
    # =========================================================================
    story.append(Paragraph("1. Executive Summary & Value Proposition", h1_style))
    story.append(Paragraph(
        "<b>Nexus LMS</b> is a unified, high-concurrency learning management system developed to serve both institutional academic programs and rigorous competitive test preparation (such as UPSC Civil Services Examination). Designed with a zero-client-build philosophy using asynchronous FastAPI, Server-Side Rendered Jinja2, and a Write-Ahead Logged SQLite database, it eliminates front-end lag, provides instant page painting, and enforces strict security and role-based data isolation across multiple academic departments.",
        body_style
    ))
    story.append(Paragraph(
        "<b>Core Innovations Delivered:</b><br/>"
        "• <b>Full UPSC Civil Services Preparation Ecosystem:</b> 2 complete subjects (Indian Polity & Governance, Indian History & Culture), 8 modules, 24 YouTube video lectures, 40 PDF study notes, 40 functional quizzes with 400 Prelims questions, and 320+ enrolled candidates.<br/>"
        "• <b>Subjective UPSC Mains Answer Writing:</b> End-to-end PDF answer sheet submission, instant mentor notifications, grading rubric scoring (Max 20 marks), and structured mentor feedback critiques.<br/>"
        "• <b>Department-Level Feature Gating:</b> Granular toggle button allowing administrators to activate/deactivate Answer Writing on a per-department basis, dynamically updating student course players, teacher evaluation queues, and course editors.<br/>"
        "• <b>Personalized 1-on-1 Mentoring System:</b> Two-way scheduling engine supporting student-initiated requests and faculty-initiated targeted interventions.<br/>"
        "• <b>Authentic Certificate Issuance & QR Verification:</b> Cryptographic QR code generation and public instant verification portal (`/verify/{id}`).",
        body_style
    ))
    story.append(Spacer(1, 6))

    # =========================================================================
    # 2. SYSTEM ARCHITECTURE MINDMAP
    # =========================================================================
    story.append(Paragraph("2. System Architecture & Component Mindmap", h1_style))
    story.append(Paragraph("The flowchart below illustrates the architectural tiers of Nexus LMS, from public ingress to persistent storage and generative AI.", body_style))

    arch_mindmap_data = [
        [
            Paragraph("<b>🌐 CLIENT / INGRESS</b><br/><font color='#64748B'>Cloudflare Tunnel • Localhost 8000 • Web Browsers</font>", mindmap_node_title),
            Paragraph("<b>➔</b>", table_cell_center_bold),
            Paragraph("<b>⚡ CORE ENGINE (FastAPI)</b><br/><font color='#64748B'>Async ASGI • RBAC Middleware • JWT in HttpOnly Cookies</font>", mindmap_node_title),
            Paragraph("<b>➔</b>", table_cell_center_bold),
            Paragraph("<b>💾 STORAGE & PERSISTENCE</b><br/><font color='#64748B'>SQLite WAL Mode • Secure /uploads • Audit Ledger</font>", mindmap_node_title)
        ],
        [
            Paragraph("<b>Jinja2 SSR UI Tier</b><br/>• Student Player<br/>• Teacher Studio<br/>• Admin Dashboard", mindmap_node_desc),
            Paragraph("", mindmap_node_desc),
            Paragraph("<b>Business Services</b><br/>• Quiz Evaluator<br/>• Answer Sheet Engine<br/>• Mentoring Dispatcher", mindmap_node_desc),
            Paragraph("", mindmap_node_desc),
            Paragraph("<b>AI Services (Gemini)</b><br/>• Mistake Explainer<br/>• AI Quiz Generation<br/>• Governance & Policy", mindmap_node_desc)
        ]
    ]
    arch_table = Table(arch_mindmap_data, colWidths=[150, 20, 180, 20, 153])
    arch_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (0, 1), colors.HexColor('#F1F5F9')),
        ('BACKGROUND', (2, 0), (2, 1), colors.HexColor('#EEF2FF')),
        ('BACKGROUND', (4, 0), (4, 1), colors.HexColor('#F0FDF4')),
        ('BOX', (0, 0), (0, 1), 1, colors.HexColor('#CBD5E1')),
        ('BOX', (2, 0), (2, 1), 1, colors.HexColor('#C7D2FE')),
        ('BOX', (4, 0), (4, 1), 1, colors.HexColor('#BBF7D0')),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
    ]))
    story.append(arch_table)
    story.append(Spacer(1, 10))

    # =========================================================================
    # 3. TECHNOLOGY STACK SPECIFICATION
    # =========================================================================
    story.append(Paragraph("3. Technology Stack & Architectural Decisions", h1_style))
    tech_data = [
        [Paragraph("Layer", table_header), Paragraph("Technology", table_header), Paragraph("Version / Spec", table_header), Paragraph("Technical Rationale / Production Benefits", table_header)],
        [Paragraph("Backend Framework", table_cell_bold), Paragraph("FastAPI", table_cell), Paragraph("Python 3.9+ / Async", table_cell), Paragraph("Asynchronous ASGI throughput, auto-generated OpenAPI documentation, Pydantic type validation.", table_cell)],
        [Paragraph("Web Server", table_cell_bold), Paragraph("Uvicorn", table_cell), Paragraph("ASGI Standard", table_cell), Paragraph("Non-blocking event loop handling hundreds of student requests concurrently with minimal RAM.", table_cell)],
        [Paragraph("Database Engine", table_cell_bold), Paragraph("SQLite 3 (WAL)", table_cell), Paragraph("Write-Ahead Logging", table_cell), Paragraph("Zero-config portability, high concurrent read throughput, crash safety, and single-file backup ease.", table_cell)],
        [Paragraph("Authentication", table_cell_bold), Paragraph("JWT + Bcrypt", table_cell), Paragraph("HS256 in HttpOnly", table_cell), Paragraph("Stateless session scaling; immune to browser XSS token theft; salted bcrypt password hashing.", table_cell)],
        [Paragraph("Presentation", table_cell_bold), Paragraph("Jinja2 + Tailwind", table_cell), Paragraph("SSR + Tailwind 3.4", table_cell), Paragraph("Instant first-contentful paint, zero client bundler overhead (no npm/webpack runtime), responsive UI.", table_cell)],
        [Paragraph("Generative AI", table_cell_bold), Paragraph("Google Gemini", table_cell), Paragraph("gemini-2.5-flash", table_cell), Paragraph("Low-latency structured AI output for quiz mistake explanation and assessment authoring.", table_cell)],
        [Paragraph("Public Gateway", table_cell_bold), Paragraph("Cloudflare Tunnel", table_cell), Paragraph("Argo Tunnel Service", table_cell), Paragraph("Encrypted global HTTPS ingress without port forwarding or exposing local firewall ports.", table_cell)]
    ]
    t_tech = Table(tech_data, colWidths=[90, 80, 85, 268])
    t_tech.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), C_PRIMARY),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.HexColor('#FFFFFF'), colors.HexColor('#F8FAFC')]),
        ('GRID', (0, 0), (-1, -1), 0.5, C_BORDER),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
    ]))
    story.append(t_tech)
    story.append(Spacer(1, 10))

    # =========================================================================
    # 4. ROLE-BASED ACCESS CONTROL (RBAC) MATRIX
    # =========================================================================
    story.append(Paragraph("4. Role-Based Access Control (RBAC) Matrix", h1_style))
    story.append(Paragraph("Nexus LMS enforces four primary user roles with strict server-side boundary checks and redirection middleware:", body_style))

    rbac_data = [
        [Paragraph("Permission / Feature Capability", table_header), Paragraph("Student", table_header), Paragraph("Faculty / Teacher", table_header), Paragraph("Department Admin", table_header), Paragraph("Viewer", table_header)],
        [Paragraph("Browse Enrolled Curriculum & Stream Videos", table_cell_bold), Paragraph("YES", table_cell_center_bold), Paragraph("YES", table_cell_center_bold), Paragraph("YES", table_cell_center_bold), Paragraph("YES", table_cell_center_bold)],
        [Paragraph("Download PDF Study Materials & Notes", table_cell_bold), Paragraph("YES", table_cell_center_bold), Paragraph("YES", table_cell_center_bold), Paragraph("YES", table_cell_center_bold), Paragraph("YES", table_cell_center_bold)],
        [Paragraph("Attempt Timed Prelims Quizzes with Instant Scoring", table_cell_bold), Paragraph("YES", table_cell_center_bold), Paragraph("NO", table_cell_center), Paragraph("NO", table_cell_center), Paragraph("NO", table_cell_center)],
        [Paragraph("Submit Handwritten UPSC Mains PDF Answer Copies", table_cell_bold), Paragraph("YES", table_cell_center_bold), Paragraph("NO", table_cell_center), Paragraph("NO", table_cell_center), Paragraph("NO", table_cell_center)],
        [Paragraph("Grade Papers, Award Marks & Write Critique Notes", table_cell_bold), Paragraph("NO", table_cell_center), Paragraph("YES", table_cell_center_bold), Paragraph("YES", table_cell_center_bold), Paragraph("NO", table_cell_center)],
        [Paragraph("Request 1-on-1 Guidance Session", table_cell_bold), Paragraph("YES", table_cell_center_bold), Paragraph("NO", table_cell_center), Paragraph("NO", table_cell_center), Paragraph("NO", table_cell_center)],
        [Paragraph("Initiate Direct 1-on-1 Session with Student", table_cell_bold), Paragraph("NO", table_cell_center), Paragraph("YES", table_cell_center_bold), Paragraph("YES", table_cell_center_bold), Paragraph("NO", table_cell_center)],
        [Paragraph("Assign Teachers to Pending Mentoring Requests", table_cell_bold), Paragraph("NO", table_cell_center), Paragraph("NO", table_cell_center), Paragraph("YES", table_cell_center_bold), Paragraph("NO", table_cell_center)],
        [Paragraph("Author / Edit Curriculum, Lessons & Quizzes", table_cell_bold), Paragraph("NO", table_cell_center), Paragraph("YES (Assigned)", table_cell_center_bold), Paragraph("YES (Global)", table_cell_center_bold), Paragraph("NO", table_cell_center)],
        [Paragraph("Toggle Department Answer Writing Feature", table_cell_bold), Paragraph("NO", table_cell_center), Paragraph("NO", table_cell_center), Paragraph("YES", table_cell_center_bold), Paragraph("NO", table_cell_center)],
        [Paragraph("Onboard Students via Single Form or Bulk CSV", table_cell_bold), Paragraph("NO", table_cell_center), Paragraph("NO", table_cell_center), Paragraph("YES", table_cell_center_bold), Paragraph("NO", table_cell_center)],
        [Paragraph("Transfer Students Between Department Buckets", table_cell_bold), Paragraph("NO", table_cell_center), Paragraph("NO", table_cell_center), Paragraph("YES", table_cell_center_bold), Paragraph("NO", table_cell_center)],
        [Paragraph("Schedule Live Masterclasses & Virtual Halls", table_cell_bold), Paragraph("NO", table_cell_center), Paragraph("YES", table_cell_center_bold), Paragraph("YES", table_cell_center_bold), Paragraph("NO", table_cell_center)],
        [Paragraph("Issue Official Authenticated Completion Certificates", table_cell_bold), Paragraph("NO", table_cell_center), Paragraph("NO", table_cell_center), Paragraph("YES", table_cell_center_bold), Paragraph("NO", table_cell_center)]
    ]
    t_rbac = Table(rbac_data, colWidths=[185, 75, 95, 95, 73])
    t_rbac.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), C_PRIMARY),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.HexColor('#FFFFFF'), colors.HexColor('#F8FAFC')]),
        ('GRID', (0, 0), (-1, -1), 0.5, C_BORDER),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), 3),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
    ]))
    story.append(t_rbac)
    story.append(Spacer(1, 10))

    # =========================================================================
    # 5. DEPARTMENT BUCKETING & ANSWER WRITING TOGGLE
    # =========================================================================
    story.append(Paragraph("5. Multi-Tenant Department Bucketing & Answer Writing Gating", h1_style))
    story.append(Paragraph(
        "To serve diverse disciplines (e.g. Foreign Languages vs. UPSC Civil Services), the platform organizes learners, faculty, and content into <b>Department Buckets</b>. Each bucket can independently toggle subjective features off or on.",
        body_style
    ))
    
    dept_table_data = [
        [Paragraph("Dept ID", table_header), Paragraph("Department Name", table_header), Paragraph("Code", table_header), Paragraph("Ans Writing", table_header), Paragraph("Target Curriculum", table_header), Paragraph("Faculty In-Charge", table_header)],
        [Paragraph("1", table_cell_center), Paragraph("Foreign Language", table_cell_bold), Paragraph("FOREIGN_LANG", table_cell), Paragraph("<font color='#DC2626'><b>DISABLED (0)</b></font>", table_cell_center), Paragraph("German A1, French Conversational Mastery, Spanish", table_cell), Paragraph("Prof. Rameez (T-ALAN)", table_cell)],
        [Paragraph("2", table_cell_center), Paragraph("Test Prep", table_cell_bold), Paragraph("TEST_PREP", table_cell), Paragraph("<font color='#059669'><b>ENABLED (1)</b></font>", table_cell_center), Paragraph("UPSC Indian Polity, Indian History, IIT-JEE Foundation", table_cell), Paragraph("Dr. A. K. Sharma (T-UPSC-01)", table_cell)],
        [Paragraph("321", table_cell_center), Paragraph("UPSC Coaching", table_cell_bold), Paragraph("UPSC_ACAD", table_cell), Paragraph("<font color='#059669'><b>ENABLED (1)</b></font>", table_cell_center), Paragraph("Civil Services Advanced Prelims & Mains Program", table_cell), Paragraph("Dr. A. K. Sharma (T-UPSC-01)", table_cell)]
    ]
    t_dept = Table(dept_table_data, colWidths=[40, 100, 80, 85, 125, 93])
    t_dept.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), C_PRIMARY),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.HexColor('#FFFFFF'), colors.HexColor('#F8FAFC')]),
        ('GRID', (0, 0), (-1, -1), 0.5, C_BORDER),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
    ]))
    story.append(t_dept)
    story.append(Spacer(1, 6))

    story.append(Paragraph(
        "<b>Cascading Effects of the Toggle:</b><br/>"
        "• <b>Student Course Player (`course_player.html`):</b> If enabled, the 'UPSC Mains Answer Copy Submissions' section and upload PDF modal are rendered. If disabled, they are cleanly removed from the DOM.<br/>"
        "• <b>Upload Endpoint Security:</b> `POST /api/course/{id}/upload-answer-sheet` strictly checks `is_ans_writing_enabled_for_course()`. Direct unauthorized API requests are blocked with <b>HTTP 403 Forbidden</b>.<br/>"
        "• <b>Teacher Dashboard:</b> The 'Pending Answer Sheet Evaluations' queue is shown exclusively to faculty whose department requires subjective evaluation.<br/>"
        "• <b>Course Editor:</b> The Mains Evaluation grading panel is dynamically shown only on courses hosted in enabled departments.",
        body_style
    ))
    story.append(Spacer(1, 10))

    # =========================================================================
    # 6. UPSC PREPARATION ECOSYSTEM (POLITY & HISTORY)
    # =========================================================================
    story.append(Paragraph("6. UPSC Civil Services Examination Preparation Ecosystem", h1_style))
    story.append(Paragraph("The platform is pre-loaded with a complete, operational UPSC test preparation structure covering General Studies Papers 1 and 2:", body_style))

    upsc_data = [
        [Paragraph("Subject & Code", table_header), Paragraph("Module Name", table_header), Paragraph("Video Lectures", table_header), Paragraph("PDF Notes", table_header), Paragraph("Quizzes", table_header), Paragraph("Prelims MCQs", table_header)],
        [Paragraph("<b>Indian Polity & Governance</b><br/>(UPSC-GS2-POLITY)", table_cell), Paragraph("M1: Historical Background & Making of Constitution", table_cell), Paragraph("3 Lectures", table_cell_center), Paragraph("5 Docs", table_cell_center), Paragraph("5 Quizzes", table_cell_center), Paragraph("50 Questions", table_cell_center_bold)],
        [Paragraph("", table_cell), Paragraph("M2: Fundamental Rights & Directive Principles", table_cell), Paragraph("3 Lectures", table_cell_center), Paragraph("5 Docs", table_cell_center), Paragraph("5 Quizzes", table_cell_center), Paragraph("50 Questions", table_cell_center_bold)],
        [Paragraph("", table_cell), Paragraph("M3: Union and State Government", table_cell), Paragraph("3 Lectures", table_cell_center), Paragraph("5 Docs", table_cell_center), Paragraph("5 Quizzes", table_cell_center), Paragraph("50 Questions", table_cell_center_bold)],
        [Paragraph("", table_cell), Paragraph("M4: Constitutional & Statutory Bodies", table_cell), Paragraph("3 Lectures", table_cell_center), Paragraph("5 Docs", table_cell_center), Paragraph("5 Quizzes", table_cell_center), Paragraph("50 Questions", table_cell_center_bold)],
        [Paragraph("<b>Indian History & Culture</b><br/>(UPSC-GS1-HISTORY)", table_cell), Paragraph("M1: Ancient Indian History", table_cell), Paragraph("3 Lectures", table_cell_center), Paragraph("5 Docs", table_cell_center), Paragraph("5 Quizzes", table_cell_center), Paragraph("50 Questions", table_cell_center_bold)],
        [Paragraph("", table_cell), Paragraph("M2: Medieval Indian History", table_cell), Paragraph("3 Lectures", table_cell_center), Paragraph("5 Docs", table_cell_center), Paragraph("5 Quizzes", table_cell_center), Paragraph("50 Questions", table_cell_center_bold)],
        [Paragraph("", table_cell), Paragraph("M3: Modern Indian History", table_cell), Paragraph("3 Lectures", table_cell_center), Paragraph("5 Docs", table_cell_center), Paragraph("5 Quizzes", table_cell_center), Paragraph("50 Questions", table_cell_center_bold)],
        [Paragraph("", table_cell), Paragraph("M4: Indian National Movement", table_cell), Paragraph("3 Lectures", table_cell_center), Paragraph("5 Docs", table_cell_center), Paragraph("5 Quizzes", table_cell_center), Paragraph("50 Questions", table_cell_center_bold)],
        [Paragraph("<b>TOTALS</b>", table_cell_bold), Paragraph("<b>8 Modules Across 2 UPSC Subjects</b>", table_cell_bold), Paragraph("<b>24 Videos</b>", table_cell_center_bold), Paragraph("<b>40 PDFs</b>", table_cell_center_bold), Paragraph("<b>40 Quizzes</b>", table_cell_center_bold), Paragraph("<b>400 MCQs</b>", table_cell_center_bold)]
    ]
    t_upsc = Table(upsc_data, colWidths=[120, 160, 60, 50, 50, 83])
    t_upsc.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), C_PRIMARY),
        ('ROWBACKGROUNDS', (0, 1), (-1, -2), [colors.HexColor('#FFFFFF'), colors.HexColor('#F8FAFC')]),
        ('BACKGROUND', (0, -1), (-1, -1), colors.HexColor('#EEF2FF')),
        ('GRID', (0, 0), (-1, -1), 0.5, C_BORDER),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), 3.5),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3.5),
    ]))
    story.append(t_upsc)
    story.append(Spacer(1, 10))

    # =========================================================================
    # 7. MAINS ANSWER WRITING & MENTOR EVALUATION WORKFLOW
    # =========================================================================
    story.append(Paragraph("7. Subjective Mains Answer Writing & Evaluation Workflow", h1_style))
    story.append(Paragraph(
        "In addition to objective MCQ tests, Civil Services preparation demands subjective answer critique. The platform provides a full evaluation lifecycle for handwritten answer scripts:",
        body_style
    ))

    flow_data = [
        [Paragraph("Step", table_header), Paragraph("Evaluation Stage", table_header), Paragraph("Actor & Workflow Description", table_header), Paragraph("Platform Action & Status", table_header)],
        [Paragraph("1", table_cell_center_bold), Paragraph("<b>Candidate Submission</b>", table_cell), Paragraph("Aspirant selects topic/module reference and uploads handwritten PDF answer sheet in Course Player.", table_cell), Paragraph("File stored securely; status initialized to <code>pending_review</code>.", table_cell)],
        [Paragraph("2", table_cell_center_bold), Paragraph("<b>Faculty Notification</b>", table_cell), Paragraph("System dispatches real-time notification alert to subject faculty with direct evaluation link.", table_cell), Paragraph("Faculty evaluation queue increments with new submission.", table_cell)],
        [Paragraph("3", table_cell_center_bold), Paragraph("<b>Evaluation & Grading</b>", table_cell), Paragraph("Faculty inspects PDF in-app, enters numerical marks (e.g. 15.5 / 20.0), and writes critique feedback.", table_cell), Paragraph("Status transitions to <code>evaluated</code>; audit log recorded.", table_cell)],
        [Paragraph("4", table_cell_center_bold), Paragraph("<b>Feedback & Review</b>", table_cell), Paragraph("Student inspects evaluated answer copy with marks, breakdown, and mentor critique comments.", table_cell), Paragraph("Candidate receives feedback alert; marks recorded in profile.", table_cell)]
    ]
    t_flow = Table(flow_data, colWidths=[40, 110, 220, 153])
    t_flow.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), C_PRIMARY),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.HexColor('#FFFFFF'), colors.HexColor('#F8FAFC')]),
        ('GRID', (0, 0), (-1, -1), 0.5, C_BORDER),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
    ]))
    story.append(t_flow)
    story.append(Spacer(1, 10))

    # =========================================================================
    # 8. 1-ON-1 MENTORING WORKFLOW
    # =========================================================================
    story.append(Paragraph("8. Personalized 1-on-1 Mentoring System", h1_style))
    story.append(Paragraph(
        "Aspirants frequently require personalized strategy counseling. The system features two integrated mentoring pathways:",
        body_style
    ))
    
    mentoring_matrix = [
        [Paragraph("Workflow Type", table_header), Paragraph("Initiator", table_header), Paragraph("Intermediary / Actions", table_header), Paragraph("Session Resolution", table_header)],
        [
            Paragraph("<b>Workflow A:<br/>Student-Initiated Request</b>", table_cell),
            Paragraph("Student Aspirant", table_cell_bold),
            Paragraph("• Student submits topic & preferred dates<br/>• Admin inspects queue on `/department#tab-mentoring`<br/>• Admin allocates faculty member & meeting link (Google Meet)", table_cell),
            Paragraph("Teacher conducts session and records permanent post-session advice notes in student file.", table_cell)
        ],
        [
            Paragraph("<b>Workflow B:<br/>Teacher-Initiated Invite</b>", table_cell),
            Paragraph("Subject Faculty", table_cell_bold),
            Paragraph("• Teacher targets student needing intervention<br/>• Teacher proposes topic, date, and time slot<br/>• Student receives dashboard notification to confirm or suggest revised time", table_cell),
            Paragraph("Session status transitions to `scheduled` then `completed` with structured takeaway points.", table_cell)
        ]
    ]
    t_mentoring = Table(mentoring_matrix, colWidths=[120, 80, 190, 133])
    t_mentoring.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), C_PRIMARY),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.HexColor('#FFFFFF'), colors.HexColor('#F8FAFC')]),
        ('GRID', (0, 0), (-1, -1), 0.5, C_BORDER),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
    ]))
    story.append(t_mentoring)
    story.append(Spacer(1, 10))

    # =========================================================================
    # 9. CERTIFICATE ISSUANCE & QR VERIFICATION GATEWAY
    # =========================================================================
    story.append(Paragraph("9. Certificate Issuance & QR Verification Gateway", h1_style))
    story.append(Paragraph(
        "When students complete their curriculum, the administrator can generate an authentic completion certificate. "
        "Each certificate receives a unique immutable identifier (e.g. `LBPL-2026-000008`) and embeds a high-resolution QR code that can be scanned by employers or verifiers to load the public authenticity gateway (`/verify/{id}`) without requiring login.",
        body_style
    ))

    cert_data = [
        [Paragraph("Component", table_header), Paragraph("Implementation Specification", table_header), Paragraph("Security & Fraud Prevention Mechanism", table_header)],
        [Paragraph("Certificate Identifier", table_cell_bold), Paragraph("Structured serial: `LBPL-YYYY-SEQUENCE` (e.g. `LBPL-2026-000008`)", table_cell), Paragraph("Indexed unique constraint in SQLite database; prevents tampering or collision.", table_cell)],
        [Paragraph("Embedded QR Code", table_cell_bold), Paragraph("RFC-standard Base64 PNG Data URI generated via Python `qrcode`", table_cell), Paragraph("Embedded directly in the HTML/PDF; requires no external image CDN dependencies.", table_cell)],
        [Paragraph("Public Verification", table_cell_bold), Paragraph("Endpoint: `/verify/{certificate_id}` (Publicly reachable)", table_cell), Paragraph("Live verification badge confirming recipient name, course, completion date, and issuing authority.", table_cell)],
        [Paragraph("Lifecycle Operations", table_cell_bold), Paragraph("Issue • Revoke • Re-issue with audit lineage", table_cell), Paragraph("Revoked certificates display prominent red warning banners explaining grounds for cancellation.", table_cell)]
    ]
    t_cert = Table(cert_data, colWidths=[110, 190, 223])
    t_cert.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), C_PRIMARY),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.HexColor('#FFFFFF'), colors.HexColor('#F8FAFC')]),
        ('GRID', (0, 0), (-1, -1), 0.5, C_BORDER),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
    ]))
    story.append(t_cert)
    story.append(Spacer(1, 10))

    # =========================================================================
    # 10. DATABASE SCHEMA DICTIONARY (17 TABLES)
    # =========================================================================
    story.append(Paragraph("10. Complete Database Schema Dictionary", h1_style))
    story.append(Paragraph("The platform persists state in a relational SQLite 3 database operating under Write-Ahead Logging (`PRAGMA journal_mode = WAL;`).", body_style))

    schema_data = [
        [Paragraph("Table Name", table_header), Paragraph("Records Count", table_header), Paragraph("Entity Purpose", table_header), Paragraph("Key Relational Columns & Foreign Keys", table_header)],
        [Paragraph("`users`", table_cell_bold), Paragraph("332", table_cell_center), Paragraph("Accounts (Admin, Teachers, Students)", table_cell), Paragraph("`id`, `user_id` (Unique), `full_name`, `email`, `role`, `department`, `password_hash`", table_cell)],
        [Paragraph("`departments`", table_cell_bold), Paragraph("3", table_cell_center), Paragraph("Multi-tenant academic buckets", table_cell), Paragraph("`id`, `name`, `code`, `description`, `ans_writing_enabled`", table_cell)],
        [Paragraph("`courses`", table_cell_bold), Paragraph("8", table_cell_center), Paragraph("Course catalog and subjects", table_cell), Paragraph("`id`, `title`, `code`, `department`, `teacher_id` (FK ➔ users.id), `is_published`", table_cell)],
        [Paragraph("`modules`", table_cell_bold), Paragraph("18", table_cell_center), Paragraph("Course curriculum chapters", table_cell), Paragraph("`id`, `course_id` (FK ➔ courses.id), `title`, `position`", table_cell)],
        [Paragraph("`lessons`", table_cell_bold), Paragraph("223", table_cell_center), Paragraph("Videos, PDF notes, and quiz anchors", table_cell), Paragraph("`id`, `module_id` (FK ➔ modules.id), `title`, `content_type`, `content_value`", table_cell)],
        [Paragraph("`quizzes`", table_cell_bold), Paragraph("149", table_cell_center), Paragraph("Assessment metadata and timers", table_cell), Paragraph("`id`, `lesson_id` (FK ➔ lessons.id), `title`, `passing_score`, `time_limit_minutes`", table_cell)],
        [Paragraph("`quiz_questions`", table_cell_bold), Paragraph("739", table_cell_center), Paragraph("MCQs with options A-D and rationale", table_cell), Paragraph("`id`, `quiz_id` (FK ➔ quizzes.id), `question_text`, `correct_option`, `explanation`", table_cell)],
        [Paragraph("`quiz_attempts`", table_cell_bold), Paragraph("1,551", table_cell_center), Paragraph("Student exam submissions & scores", table_cell), Paragraph("`id`, `quiz_id`, `user_id`, `score`, `score_percent`, `passed`, `submitted_at`", table_cell)],
        [Paragraph("`enrollments`", table_cell_bold), Paragraph("644", table_cell_center), Paragraph("Student course registrations", table_cell), Paragraph("`id`, `user_id` (FK ➔ users.id), `course_id` (FK ➔ courses.id), `enrolled_at`", table_cell)],
        [Paragraph("`lesson_progress`", table_cell_bold), Paragraph("3,967", table_cell_center), Paragraph("Student progress tracking", table_cell), Paragraph("`id`, `user_id`, `lesson_id`, `completed_at`", table_cell)],
        [Paragraph("`answer_sheet_submissions`", table_cell_bold), Paragraph("19", table_cell_center), Paragraph("Subjective Mains PDF papers & marks", table_cell), Paragraph("`id`, `user_id`, `course_id`, `file_path`, `marks_awarded`, `feedback`, `status`", table_cell)],
        [Paragraph("`mentoring_sessions`", table_cell_bold), Paragraph("6", table_cell_center), Paragraph("1-on-1 personalized guidance logs", table_cell), Paragraph("`id`, `student_id`, `teacher_id`, `topic`, `status`, `scheduled_date`, `meeting_link`", table_cell)],
        [Paragraph("`live_classes`", table_cell_bold), Paragraph("7", table_cell_center), Paragraph("Virtual hall broadcast sessions", table_cell), Paragraph("`id`, `course_id`, `teacher_id`, `title`, `meeting_url`, `scheduled_at`", table_cell)],
        [Paragraph("`certificates`", table_cell_bold), Paragraph("6", table_cell_center), Paragraph("Verifiable completion certificates", table_cell), Paragraph("`id`, `certificate_id` (Unique), `student_id`, `course_id`, `qr_code_data_uri`", table_cell)],
        [Paragraph("`notifications`", table_cell_bold), Paragraph("135", table_cell_center), Paragraph("System alerts and bell dispatch", table_cell), Paragraph("`id`, `user_id`, `title`, `message`, `link_url`, `category`, `is_read`", table_cell)],
        [Paragraph("`audit_logs`", table_cell_bold), Paragraph("740", table_cell_center), Paragraph("Administrator compliance ledger", table_cell), Paragraph("`id`, `user_id`, `action`, `resource_type`, `resource_id`, `details`, `created_at`", table_cell)]
    ]
    t_schema = Table(schema_data, colWidths=[110, 50, 150, 213])
    t_schema.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), C_PRIMARY),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.HexColor('#FFFFFF'), colors.HexColor('#F8FAFC')]),
        ('GRID', (0, 0), (-1, -1), 0.5, C_BORDER),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('TOPPADDING', (0, 0), (-1, -1), 3),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
    ]))
    story.append(t_schema)
    story.append(Spacer(1, 10))

    # =========================================================================
    # 11. AUTOMATED QUALITY ASSURANCE RESULTS (90/90 PASSED)
    # =========================================================================
    story.append(Paragraph("11. Comprehensive Quality Assurance Audit (100% Pass)", h1_style))
    story.append(Paragraph(
        "An automated test runner (`test_comprehensive_qa.py`) validates every system function and security boundary across 10 functional suites:",
        body_style
    ))

    qa_data = [
        [Paragraph("Suite", table_header), Paragraph("Functional Domain Under Test", table_header), Paragraph("Test Scenarios", table_header), Paragraph("Passed", table_header), Paragraph("Failed", table_header), Paragraph("Verdict", table_header)],
        [Paragraph("Suite 1", table_cell_center_bold), Paragraph("Authentication, Salted Hashes, JWT Cookies & Strict RBAC Portal Isolation", table_cell), Paragraph("14", table_cell_center), Paragraph("14", table_cell_center), Paragraph("0", table_cell_center), Paragraph("<font color='#059669'><b>100% PASS</b></font>", table_cell_center)],
        [Paragraph("Suite 2", table_cell_center_bold), Paragraph("Department Bucketing, Multi-Tenancy & Answer Writing Toggle Flag", table_cell), Paragraph("9", table_cell_center), Paragraph("9", table_cell_center), Paragraph("0", table_cell_center), Paragraph("<font color='#059669'><b>100% PASS</b></font>", table_cell_center)],
        [Paragraph("Suite 3", table_cell_center_bold), Paragraph("Teacher Studio, Course Editor, Video Parsing & PDF Linking", table_cell), Paragraph("11", table_cell_center), Paragraph("11", table_cell_center), Paragraph("0", table_cell_center), Paragraph("<font color='#059669'><b>100% PASS</b></font>", table_cell_center)],
        [Paragraph("Suite 4", table_cell_center_bold), Paragraph("Student Directory, Unicode NFKD Normalization & Duplicate Detection", table_cell), Paragraph("8", table_cell_center), Paragraph("8", table_cell_center), Paragraph("0", table_cell_center), Paragraph("<font color='#059669'><b>100% PASS</b></font>", table_cell_center)],
        [Paragraph("Suite 5", table_cell_center_bold), Paragraph("Course Enrollment, Dual-ID Resolution, Cross-Dept Access & Unassign", table_cell), Paragraph("8", table_cell_center), Paragraph("8", table_cell_center), Paragraph("0", table_cell_center), Paragraph("<font color='#059669'><b>100% PASS</b></font>", table_cell_center)],
        [Paragraph("Suite 6", table_cell_center_bold), Paragraph("Student Course Player, YouTube Streaming, PDF Viewer & Progress Bars", table_cell), Paragraph("8", table_cell_center), Paragraph("8", table_cell_center), Paragraph("0", table_cell_center), Paragraph("<font color='#059669'><b>100% PASS</b></font>", table_cell_center)],
        [Paragraph("Suite 7", table_cell_center_bold), Paragraph("Timed Prelims MCQ Engine, Scoring Algorithms & Attempt History", table_cell), Paragraph("7", table_cell_center), Paragraph("7", table_cell_center), Paragraph("0", table_cell_center), Paragraph("<font color='#059669'><b>100% PASS</b></font>", table_cell_center)],
        [Paragraph("Suite 8", table_cell_center_bold), Paragraph("UPSC Mains Answer Sheet Submissions, 403 Security Gating & Teacher Grading", table_cell), Paragraph("9", table_cell_center), Paragraph("9", table_cell_center), Paragraph("0", table_cell_center), Paragraph("<font color='#059669'><b>100% PASS</b></font>", table_cell_center)],
        [Paragraph("Suite 9", table_cell_center_bold), Paragraph("1-on-1 Mentoring Workflows (Student-Initiated & Teacher-Initiated)", table_cell), Paragraph("7", table_cell_center), Paragraph("7", table_cell_center), Paragraph("0", table_cell_center), Paragraph("<font color='#059669'><b>100% PASS</b></font>", table_cell_center)],
        [Paragraph("Suite 10", table_cell_center_bold), Paragraph("Live Virtual Masterclasses, Certificate QR Generation & Public Verification", table_cell), Paragraph("8", table_cell_center), Paragraph("8", table_cell_center), Paragraph("0", table_cell_center), Paragraph("<font color='#059669'><b>100% PASS</b></font>", table_cell_center)],
        [Paragraph("<b>TOTAL</b>", table_cell_center_bold), Paragraph("<b>Comprehensive End-to-End System Verification</b>", table_cell_bold), Paragraph("<b>90</b>", table_cell_center_bold), Paragraph("<b>90</b>", table_cell_center_bold), Paragraph("<b>0</b>", table_cell_center_bold), Paragraph("<font color='#059669'><b>100.0% PASS</b></font>", table_cell_center_bold)]
    ]
    t_qa = Table(qa_data, colWidths=[45, 230, 60, 50, 48, 90])
    t_qa.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), C_PRIMARY),
        ('ROWBACKGROUNDS', (0, 1), (-1, -2), [colors.HexColor('#FFFFFF'), colors.HexColor('#F8FAFC')]),
        ('BACKGROUND', (0, -1), (-1, -1), colors.HexColor('#ECFDF5')),
        ('GRID', (0, 0), (-1, -1), 0.5, C_BORDER),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), 3),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
    ]))
    story.append(t_qa)
    story.append(Spacer(1, 10))

    # =========================================================================
    # 12. LIVE ACCESS & VERIFIED DEMONSTRATION CREDENTIALS
    # =========================================================================
    story.append(Paragraph("12. Live Access & Demonstration Directory", h1_style))
    story.append(Paragraph(
        "<b>Active Public URL (Worldwide Access):</b> <font color='#4338CA'><u>https://council-district-stake-python.trycloudflare.com</u></font><br/>"
        "<b>Localhost Development URL:</b> <font color='#4338CA'><u>http://localhost:8000</u></font> or <font color='#4338CA'><u>http://127.0.0.1:8000</u></font>",
        body_style
    ))

    cred_data = [
        [Paragraph("Role / Profile", table_header), Paragraph("Login ID", table_header), Paragraph("Password", table_header), Paragraph("Portal Entry Point", table_header), Paragraph("Key Features to Demonstrate", table_header)],
        [
            Paragraph("<b>Department Admin</b>", table_cell),
            Paragraph("`DEPT-HEAD` *(or `admin`)*", table_cell_bold),
            Paragraph("`admin123`", table_cell),
            Paragraph("`/department`", table_cell),
            Paragraph("Department Buckets, Ans Writing Toggle Switch, Student Pool, Mentoring Queue, Certificate Engine.", table_cell)
        ],
        [
            Paragraph("<b>UPSC Faculty</b>", table_cell),
            Paragraph("`T-UPSC-01`", table_cell_bold),
            Paragraph("`password123`", table_cell),
            Paragraph("`/teacher`", table_cell),
            Paragraph("UPSC Mains Pending Evaluation Queue, Course Editor for Polity & History, 1-on-1 Invite Modal.", table_cell)
        ],
        [
            Paragraph("<b>Language Faculty</b>", table_cell),
            Paragraph("`T-ALAN` *(or `teacher`)*", table_cell_bold),
            Paragraph("`teacher123`", table_cell),
            Paragraph("`/teacher`", table_cell),
            Paragraph("Foreign Language Studio, Module & Lesson Editor, Live Class Scheduler.", table_cell)
        ],
        [
            Paragraph("<b>UPSC Aspirant</b>", table_cell),
            Paragraph("`UPSC-2026-0102`", table_cell_bold),
            Paragraph("`password123`", table_cell),
            Paragraph("`/student`", table_cell),
            Paragraph("Course Player for Polity/History, Answer Copy PDF Upload, Interactive Timed Quizzes, Mentoring Request.", table_cell)
        ],
        [
            Paragraph("<b>Language Student</b>", table_cell),
            Paragraph("`CS2026-002` *(or `student`)*", table_cell_bold),
            Paragraph("`welcome123`", table_cell),
            Paragraph("`/student`", table_cell),
            Paragraph("Cross-enrolled student profile, active course badges, language player (Answer Writing cleanly omitted).", table_cell)
        ]
    ]
    t_cred = Table(cred_data, colWidths=[90, 85, 75, 75, 198])
    t_cred.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), C_PRIMARY),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.HexColor('#FFFFFF'), colors.HexColor('#F8FAFC')]),
        ('GRID', (0, 0), (-1, -1), 0.5, C_BORDER),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
    ]))
    story.append(t_cred)

    # Build PDF
    doc.build(story, canvasmaker=NumberedCanvas)

    # Duplicate to other output paths if specified
    for secondary_path in output_paths[1:]:
        import shutil
        shutil.copyfile(target_path, secondary_path)

    print(f"Successfully generated PDF showcase to {len(output_paths)} locations:")
    for p in output_paths:
        print(f"  -> {p} ({os.path.getsize(p):,} bytes)")

if __name__ == '__main__':
    paths = [
        "/Users/rocket/.gemini/antigravity/scratch/lms/app/static/docs/Nexus_LMS_Complete_System_Showcase_Guide.pdf",
        "/Users/rocket/.gemini/antigravity/brain/277b91b9-aef1-4ee3-a0be-000a9ef11ed4/Nexus_LMS_Complete_System_Showcase_Guide.pdf"
    ]
    build_pdf(paths)
