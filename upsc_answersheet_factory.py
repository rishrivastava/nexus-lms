"""
Generates realistic UPSC Mains Answer Sheet PDFs for student submissions.
Placed in app/static/uploads/answer_sheets/
"""

import os
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable
)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle

SAMPLE_MAINS_QUESTIONS = [
    ("Q1. Basic Structure Doctrine & Constitutional Supremacy",
     "Discuss the evolution of the 'Basic Structure Doctrine' from Shankari Prasad to Kesavananda Bharati. How has it safeguarded constitutional supremacy against legislative overreach? (15 Marks, 250 Words)",
     ["<b>Introduction:</b> The Basic Structure Doctrine is a judicial innovation propounded by the Supreme Court of India in Kesavananda Bharati v. State of Kerala (1973) to limit the amending power of Parliament under Article 368.",
      "<b>Evolutionary Milestones:</b><br/>• <i>Shankari Prasad (1951) & Sajjan Singh (1965):</i> SC ruled Parliament can amend any part including Part III.<br/>• <i>Golaknath (1967):</i> 11-judge bench held Fundamental Rights possess transcendental position.<br/>• <i>24th Amendment (1971):</i> Parliament asserted unbridled amending powers.<br/>• <i>Kesavananda Bharati (1973):</i> 13-judge bench held Parliament can amend the Constitution without altering its basic structure.",
      "<b>Key Components:</b> Supremacy of Constitution, Republican & Democratic form, Secularism, Separation of Powers, Federalism, Judicial Review.",
      "<b>Conclusion:</b> The doctrine strikes a harmonious balance between constitutional rigidity and parliamentary flexibility, ensuring democracy endures."]),

    ("Q2. Electoral Reforms & Independence of Election Commission",
     "Examine the institutional autonomy of the Election Commission of India under Article 324. What structural reforms are required to enhance its independence and transparency? (15 Marks, 250 Words)",
     ["<b>Introduction:</b> Article 324 vests the superintendence, direction, and control of elections in an autonomous Election Commission to maintain the sanctity of Indian democracy.",
      "<b>Key Challenges to Autonomy:</b><br/>• <i>Appointment Procedure:</i> Historically executive-dominated until SC 2023 ruling and subsequent legislation.<br/>• <i>Removal Disparity:</i> While CEC enjoys protection akin to a SC Judge, Election Commissioners can be removed on CEC recommendation.<br/>• <i>Expenditure charged vs voted:</i> Administrative expenses are not charged on the Consolidated Fund of India.",
      "<b>Way Forward:</b> Implement Goswami Committee and 255th Law Commission recommendations to provide equal tenure safeguards to all three Commissioners and establish independent secretariat."]),

    ("Q3. Indus Valley Urban Planning & Modern Smart Cities",
     "The town planning and municipal engineering of the Indus Valley Civilisation offer invaluable lessons for contemporary sustainable urbanism. Elaborate. (15 Marks, 250 Words)",
     ["<b>Introduction:</b> Harappan civilisation (c. 2600-1900 BCE) achieved South Asia's first urban revolution characterized by sophisticated municipal standards.",
      "<b>Core Urban Features:</b><br/>• <i>Grid Iron Layout:</i> Rectilinear street grids cutting at right angles facilitating breeze and traffic flow.<br/>• <i>Underground Drainage:</i> Covered drains with inspection sumps and terracotta pipes.<br/>• <i>Water Conservation:</i> Monumental stone-cut reservoirs at Dholavira and rainwater harvesting.<br/>• <i>Standardization:</i> 1:2:4 ratio burnt bricks used ubiquitously.",
      "<b>Lessons for Modern Smart Cities:</b> Decentralized drainage maintenance, climate-resilient architecture, and efficient municipal zoning."]),

    ("Q4. The Great Revolt of 1857: Watershed in Colonial Rule",
     "Critically assess the political, administrative, and military consequences of the Revolt of 1857 on British governance in India. (15 Marks, 250 Words)",
     ["<b>Introduction:</b> The uprising of 1857 marked a profound rupture in British colonial hegemony, leading to the formal end of Company Raj.",
      "<b>Key Consequences:</b><br/>• <i>Government of India Act 1858:</i> Direct rule of the British Crown inaugurated; office of Secretary of State created.<br/>• <i>Army Reorganization:</i> Peel Commission recommendations implemented; increased British-to-Indian soldier ratio; martial vs non-martial race policy.<br/>• <i>End of Annexation:</i> Doctrine of Lapse abandoned; Queen's Proclamation promised respect for princely treaties.<br/>• <i>Social Conservatism:</i> British abandoned aggressive social reform to avoid inciting religious orthodox resistance."]),

    ("Q5. Gandhian Satyagraha vs Extremist Agitation Methods",
     "Compare and contrast the political methodologies of the Extremist leaders (Lal-Bal-Pal) with Mahatma Gandhi's philosophy of Non-Violent Satyagraha. (15 Marks, 250 Words)",
     ["<b>Introduction:</b> Both Extremists and Gandhiji rejected Moderate mendicancy, but differed fundamentally in their spiritual, philosophical, and tactical approaches to mass mobilization.",
      "<b>Comparative Analysis:</b><br/>• <i>Extremists (1905-1919):</i> Used passive resistance, swadeshi, national education, and religious revivalism (Ganapati/Shivaji festivals) to kindle patriotic fervor.<br/>• <i>Gandhian Satyagraha:</i> Grounded in Ahimsa (non-violence) and Satya (truth); emphasized moral purification, constructive work (Khadi, anti-untouchability), and voluntary suffering.",
      "<b>Synthesis:</b> Extremists expanded the political base beyond the elite; Gandhiji institutionalized it into an irresistible all-India mass movement."])
]

def generate_sample_answer_sheets(output_dir):
    os.makedirs(output_dir, exist_ok=True)
    generated_files = []
    styles = getSampleStyleSheet()

    header_style = ParagraphStyle(
        'SheetHeader',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=10,
        leading=13,
        textColor=colors.HexColor('#1e3a8a')
    )
    meta_style = ParagraphStyle(
        'SheetMeta',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=8,
        leading=11,
        textColor=colors.HexColor('#475569')
    )
    q_title_style = ParagraphStyle(
        'QuestionTitle',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=9.5,
        leading=13.5,
        textColor=colors.HexColor('#991b1b')
    )
    body_style = ParagraphStyle(
        'AnswerBody',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=8.5,
        leading=13,
        textColor=colors.HexColor('#1e293b'),
        spaceAfter=6
    )

    for idx, (title, question_text, answer_paras) in enumerate(SAMPLE_MAINS_QUESTIONS):
        fname = f"upsc_mains_answersheet_{idx+1}.pdf"
        fpath = os.path.join(output_dir, fname)
        doc = SimpleDocTemplate(
            fpath,
            pagesize=A4,
            leftMargin=36,
            rightMargin=36,
            topMargin=36,
            bottomMargin=36
        )

        story = [
            Table([
                [
                    Paragraph("<b>UPSC CIVIL SERVICES EXAMINATION - MAINS ANSWER BOOKLET</b>", header_style),
                    Paragraph("<b>TEST ID: UPSC-CSE-2026-MOCK</b>", meta_style)
                ],
                [
                    Paragraph("<i>Leadership Boulevard Pvt Ltd • Mentored Answer Evaluation Program</i>", meta_style),
                    Paragraph("Medium: English • Word Limit: 250", meta_style)
                ]
            ], colWidths=[360, 160]),
            HRFlowable(width="100%", thickness=1.5, color=colors.HexColor("#dc2626"), spaceBefore=4, spaceAfter=8),
            Paragraph(f"<b>{question_text}</b>", q_title_style),
            HRFlowable(width="100%", thickness=0.8, color=colors.HexColor("#e2e8f0"), spaceBefore=4, spaceAfter=8),
        ]

        for p in answer_paras:
            story.append(Paragraph(p, body_style))
            story.append(Spacer(1, 4))

        story.append(HRFlowable(width="100%", thickness=0.5, color=colors.HexColor("#cbd5e1"), spaceBefore=12, spaceAfter=4))
        story.append(Paragraph("Evaluator Margin: Keep this area clear for examiner comments, marks rubric and mentor feedback.", meta_style))

        doc.build(story)
        generated_files.append((fname, title))

    return generated_files
