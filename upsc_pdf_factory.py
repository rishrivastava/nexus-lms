"""
ReportLab PDF Study Resource Generator for UPSC Civil Services Examination.
Generates 40 structured, professionally formatted PDF documents (5 per module across 8 modules).
Files are placed in app/static/uploads/upsc/
"""

import os
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable, KeepTogether
)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle

def generate_pdf_doc(filepath, title, course_name, module_name, category_name, sections, table_data=None):
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    doc = SimpleDocTemplate(
        filepath,
        pagesize=A4,
        leftMargin=36,
        rightMargin=36,
        topMargin=36,
        bottomMargin=36
    )
    styles = getSampleStyleSheet()

    header_style = ParagraphStyle(
        'HeaderInst',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=10,
        leading=13,
        textColor=colors.HexColor('#1e3a8a')
    )
    tagline_style = ParagraphStyle(
        'HeaderTag',
        parent=styles['Normal'],
        fontName='Helvetica-Oblique',
        fontSize=8,
        leading=11,
        textColor=colors.HexColor('#64748b')
    )
    badge_style = ParagraphStyle(
        'CatBadge',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=8,
        leading=10,
        textColor=colors.HexColor('#0284c7'),
        alignment=2
    )
    title_style = ParagraphStyle(
        'DocTitle',
        parent=styles['Heading1'],
        fontName='Helvetica-Bold',
        fontSize=15,
        leading=19,
        textColor=colors.HexColor('#0f172a'),
        spaceAfter=4
    )
    h2_style = ParagraphStyle(
        'SecHeading',
        parent=styles['Heading2'],
        fontName='Helvetica-Bold',
        fontSize=11,
        leading=15,
        textColor=colors.HexColor('#1e40af'),
        spaceBefore=8,
        spaceAfter=3
    )
    body_style = ParagraphStyle(
        'DocBody',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=8.5,
        leading=12.5,
        textColor=colors.HexColor('#334155'),
        spaceAfter=5
    )
    bullet_style = ParagraphStyle(
        'DocBullet',
        parent=body_style,
        leftIndent=12,
        firstLineIndent=-8,
        spaceAfter=3
    )
    footer_style = ParagraphStyle(
        'DocFooter',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=7.5,
        leading=9,
        textColor=colors.HexColor('#94a3b8'),
        alignment=1
    )

    story = []
    # Header
    header_table = Table([
        [
            Paragraph("<b>LEADERSHIP BOULEVARD PVT. LTD. • NEXUS LMS</b>", header_style),
            Paragraph(f"<b>[ {category_name.upper()} ]</b>", badge_style)
        ],
        [
            Paragraph("<i>UPSC Civil Services Examination • Transforming Education</i>", tagline_style),
            Paragraph(f"<b>Course:</b> {course_name}", tagline_style)
        ]
    ], colWidths=[350, 170])
    header_table.setStyle(TableStyle([
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ('BOTTOMPADDING', (0,0), (-1,-1), 1),
        ('TOPPADDING', (0,0), (-1,-1), 1),
    ]))
    story.append(header_table)
    story.append(HRFlowable(width="100%", thickness=1.5, color=colors.HexColor("#3b82f6"), spaceBefore=4, spaceAfter=8))

    story.append(Paragraph(f"<b>Module:</b> {module_name}", tagline_style))
    story.append(Paragraph(title, title_style))
    story.append(Spacer(1, 4))

    for sec_title, paragraphs, bullets in sections:
        story.append(Paragraph(sec_title, h2_style))
        for p in paragraphs:
            story.append(Paragraph(p, body_style))
        for b in bullets:
            story.append(Paragraph(f"• <b>{b[0]}:</b> {b[1]}", bullet_style))
        story.append(Spacer(1, 4))

    if table_data:
        t_rows = []
        for r in table_data:
            t_rows.append([Paragraph(f"<b>{c}</b>" if r == table_data[0] else str(c), body_style) for c in r])
        t = Table(t_rows, colWidths=[130, 200, 190])
        t.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#f8fafc')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.HexColor('#0f172a')),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#cbd5e1')),
            ('TOPPADDING', (0, 0), (-1, -1), 3),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
            ('LEFTPADDING', (0, 0), (-1, -1), 5),
            ('RIGHTPADDING', (0, 0), (-1, -1), 5),
        ]))
        story.append(Spacer(1, 4))
        story.append(t)
        story.append(Spacer(1, 6))

    story.append(HRFlowable(width="100%", thickness=0.8, color=colors.HexColor("#e2e8f0"), spaceBefore=8, spaceAfter=4))
    story.append(Paragraph("Leadership Boulevard Pvt Ltd • Confidential Study Material for Registered UPSC CSE Aspirants", footer_style))

    doc.build(story)
    return filepath

def generate_all_40_pdfs(base_output_dir):
    """Generates all 40 PDFs and returns a mapping: (course_code, module_idx) -> list of 5 PDF filenames."""
    os.makedirs(base_output_dir, exist_ok=True)
    pdf_map = {}

    modules_info = [
        # POLITY
        ("UPSC-GS2-POLITY", 0, "Historical Background and Making of the Constitution", "polity_m1"),
        ("UPSC-GS2-POLITY", 1, "Fundamental Rights and Directive Principles", "polity_m2"),
        ("UPSC-GS2-POLITY", 2, "Union and State Government", "polity_m3"),
        ("UPSC-GS2-POLITY", 3, "Constitutional and Statutory Bodies", "polity_m4"),
        # HISTORY
        ("UPSC-GS1-HISTORY", 0, "Ancient Indian History", "history_m1"),
        ("UPSC-GS1-HISTORY", 1, "Medieval Indian History", "history_m2"),
        ("UPSC-GS1-HISTORY", 2, "Modern Indian History", "history_m3"),
        ("UPSC-GS1-HISTORY", 3, "Indian National Movement", "history_m4"),
    ]

    pdf_categories = [
        ("ncert", "NCERT Foundation Notes", "NCERT Class XI & XII Comprehensive Synthesized Study Material"),
        ("topic_notes", "Topic-Wise Detailed Notes", "In-Depth Analytical Study Notes & Core Conceptual Breakdown"),
        ("revision", "Important Facts & Revision Notes", "High-Yield Facts, Chronological Tables & Memory Retention Pointers"),
        ("prelims", "UPSC Prelims Focused Notes", "Prelims MCQ Traps, Statement Elimination Strategies & Key Articles"),
        ("mains", "UPSC Mains Focused Frameworks", "Mains Analytical Answer Frameworks, Case Citations & Model Answers")
    ]

    for c_code, m_idx, m_title, prefix in modules_info:
        c_title = "Indian Polity and Governance" if "POLITY" in c_code else "Indian History and Culture"
        m_list = []
        for cat_key, cat_label, cat_desc in pdf_categories:
            fname = f"{prefix}_{cat_key}.pdf"
            fpath = os.path.join(base_output_dir, fname)
            
            # Content tailored to the module and category
            sections, table_data = _get_content_for_pdf(c_code, m_idx, m_title, cat_key, cat_label)
            generate_pdf_doc(
                filepath=fpath,
                title=f"{cat_label}: {m_title}",
                course_name=c_title,
                module_name=m_title,
                category_name=cat_label,
                sections=sections,
                table_data=table_data
            )
            m_list.append({
                "filename": f"upsc/{fname}",
                "title": f"{cat_label} - {m_title}",
                "category": cat_label,
                "duration": 25
            })
        pdf_map[(c_code, m_idx)] = m_list

    return pdf_map

def _get_content_for_pdf(course_code, m_idx, m_title, cat_key, cat_label):
    """Constructs academic text and comparative tables for each PDF."""
    sections = []
    table_data = None

    if "POLITY" in course_code:
        if m_idx == 0: # M1 Making of Constitution
            sections.append((
                "1. Constitutional Evolution & Historical Foundation",
                ["The constitutional framework of modern India was not born in a vacuum; it was forged through sequential colonial legislative enactments starting from the Regulating Act of 1773 to the Indian Independence Act of 1947.",
                 "The Government of India Act 1935 remains the single largest structural blueprint, providing nearly 60% of our constitutional text, notably the federal scheme, Governor's office, and emergency machinery."],
                [("Regulating Act 1773", "Designated Governor of Bengal as Governor-General; established Supreme Court at Calcutta (1774) with Sir Elijah Impey as CJ."),
                 ("Pitt's India Act 1784", "Introduced dual governance: Board of Control (political) and Court of Directors (commercial)."),
                 ("Charter Act 1833", "Final step towards centralization; made Governor-General of Bengal the Governor-General of India (Lord William Bentinck)."),
                 ("GOI Act 1919", "Introduced dyarchy in provinces with transferred and reserved subjects; bicameralism at the centre."),
                 ("GOI Act 1935", "Abolished dyarchy in provinces, established provincial autonomy, and envisaged an All-India Federation.")]
            ))
            sections.append((
                "2. Constituent Assembly & The Drafting Process",
                ["Formed under the Cabinet Mission Plan (1946), the Constituent Assembly was a partly elected and partly nominated body reflecting India's vast diversity.",
                 "Dr. B.R. Ambedkar led the 7-member Drafting Committee, synthesizing global constitutional wisdom into an indigenous instrument."],
                [("December 9, 1946", "First meeting; Dr. Sachchidananda Sinha elected temporary President."),
                 ("December 13, 1946", "Jawaharlal Nehru moved the historic Objectives Resolution outlining the philosophy."),
                 ("November 26, 1949", "Constitution formally adopted and signed; celebrated as Samvidhan Diwas."),
                 ("January 26, 1950", "Constitution came into full legal force, commemorating Purna Swaraj day (1930).")]
            ))
            table_data = [
                ["Colonial Enactment", "Key Innovation", "Constitutional Impact"],
                ["Regulating Act 1773", "Supreme Court at Calcutta", "Origin of modern judicial institutions"],
                ["Charter Act 1853", "Open competition civil services", "Merit-based bureaucracy & Macaulay Report"],
                ["Indian Councils Act 1909", "Separate communal electorate", "Father of communal electorate (Lord Minto)"],
                ["GOI Act 1919", "Bicameralism & Dyarchy in Provinces", "Direct elections and federal budget division"],
                ["GOI Act 1935", "Provincial Autonomy & Federal Court", "Direct progenitor of 1950 Constitution"]
            ]
        elif m_idx == 1: # M2 FR & DPSP
            sections.append((
                "1. Fundamental Rights (Part III, Articles 12-35)",
                ["Fundamental Rights represent the Magna Carta of India, securing political democracy and safeguarding individuals against state tyranny.",
                 "Unlike American Bill of Rights which are absolute, Indian Fundamental Rights are subject to reasonable restrictions under public order, decency, morality, and sovereignty."],
                [("Article 12", "Defines the 'State' including Government, Parliament, State legislatures, local authorities, and statutory entities."),
                 ("Article 13", "Doctrine of Judicial Review; declares any law violative of Part III as null and void."),
                 ("Articles 14-18", "Right to Equality; equality before law (British) and equal protection of laws (American)."),
                 ("Articles 19-22", "Right to Freedom; six democratic freedoms under Art 19, protection in convictions Art 20, life & liberty Art 21."),
                 ("Article 32", "Right to Constitutional Remedies; writs of Habeas Corpus, Mandamus, Prohibition, Certiorari, and Quo-Warranto.")]
            ))
            sections.append((
                "2. Directive Principles of State Policy (Part IV, Articles 36-51)",
                ["Borrowed from the Irish Constitution, DPSPs embody the ideal of a 'Welfare State' aimed at establishing socio-economic democracy.",
                 "Though non-justiciable under Article 37, they are fundamental in the governance of the country and impose a moral and political obligation on lawmakers."],
                [("Socialistic Principles", "Equal pay for equal work (Art 39d), living wage (Art 43), equitable distribution of resources (Art 39b)."),
                 ("Gandhian Principles", "Village Panchayats (Art 40), cottage industries (Art 43), prohibition of intoxicating drinks (Art 47)."),
                 ("Liberal-Intellectual", "Uniform Civil Code (Art 44), separation of judiciary from executive (Art 50), international peace (Art 51).")]
            ))
            table_data = [
                ["Dimension", "Fundamental Rights (Part III)", "Directive Principles (Part IV)"],
                ["Nature", "Negative obligations (prohibit state action)", "Positive obligations (require state action)"],
                ["Justiciability", "Enforceable in SC (Art 32) & HC (Art 226)", "Non-justiciable in court (Art 37)"],
                ["Objective", "Establish Political Democracy", "Establish Social & Economic Democracy"],
                ["Sanction", "Legal sanction through courts", "Political & moral sanction through electorate"],
                ["Suspension", "Can be suspended during Emergency (except 20, 21)", "Cannot be suspended; permanently applicable"]
            ]
        elif m_idx == 2: # M3 Union & State Govt
            sections.append((
                "1. The Union Executive & Parliamentary Sovereignty",
                ["India adopted the Westminster parliamentary model based on collective responsibility of the executive to the popular house (Lok Sabha).",
                 "The President is the constitutional (de jure) head, while the Prime Minister is the real (de facto) executive heading the Council of Ministers."],
                [("Article 54 & 55", "Presidential Election; proportional representation via single transferable vote by elected MPs and MLAs."),
                 ("Article 61", "Impeachment of President; special majority of two-thirds of total membership of each House."),
                 ("Article 72", "Presidential pardoning power; extends to court martial and death sentences."),
                 ("Article 75(3)", "Council of Ministers collectively responsible to the Lok Sabha."),
                 ("Article 123", "Ordinance making power; temporary law when Parliament is prorogued, subject to judicial scrutiny.")]
            ))
            table_data = [
                ["Constitutional Aspect", "Union Parliament", "State Legislature"],
                ["Upper House", "Rajya Sabha (Permanent, 6 yr term, 1/3 retire every 2 yrs)", "Legislative Council (Abolishable under Art 169)"],
                ["Lower House", "Lok Sabha (5 yr term, direct universal adult franchise)", "Legislative Assembly (Vidhan Sabha)"],
                ["Money Bills", "Originates in LS only; RS has 14 days delay power", "Originates in Assembly only; Council has 14 days"],
                ["Joint Sitting", "Available under Article 108 for ordinary bills", "No provision for joint sitting at state level"],
                ["Ordinance Power", "President under Article 123", "Governor under Article 213"]
            ]
        else: # M4 Bodies
            sections.append((
                "1. Constitutional Watchdogs & Autonomous Institutions",
                ["The framers embedded independent institutions to preserve the integrity of elections, public finance, and meritocratic civil services.",
                 "Dr. Ambedkar singled out the Supreme Court, Election Commission, CAG, and UPSC as the four pillars of constitutional democracy."],
                [("Election Commission (Art 324)", "Superintendence, direction, and control of parliamentary, assembly, presidential elections."),
                 ("CAG of India (Art 148)", "Guardian of the public purse; friend, philosopher, and guide to Public Accounts Committee (PAC)."),
                 ("Finance Commission (Art 280)", "Quasi-judicial body for horizontal and vertical tax devolution and grants-in-aid (Art 275)."),
                 ("UPSC (Art 315-323)", "Central recruiting agency safeguarding merit; consultatory mandate for disciplinary matters.")]
            ))
            table_data = [
                ["Institution", "Constitutional Article", "Tenure & Removal Safeguard", "Primary Constitutional Role"],
                ["Election Commission", "Article 324", "6 yrs / 65 yrs; CEC removed like SC Judge", "Free & fair parliamentary & state elections"],
                ["CAG of India", "Article 148", "6 yrs / 65 yrs; removed like SC Judge", "Audit of Union, States & Consolidated Fund"],
                ["Finance Commission", "Article 280", "Constituted every 5 yrs by President", "Inter-state & Union-State tax devolution"],
                ["UPSC", "Article 315", "6 yrs / 65 yrs; inquiry by SC under Art 317", "Merit-based civil service examinations"]
            ]
    else: # HISTORY
        if m_idx == 0: # Ancient
            sections.append((
                "1. Indus Valley Civilisation & The Urban Dawn",
                ["The Harappan civilisation (c. 2600-1900 BCE) represents South Asia's first urban revolution, characterized by monumental brick engineering and grid town planning.",
                 "Notable sites demonstrate specialized commercial and industrial activities spanning Gujarat, Sindh, Punjab, and Haryana."],
                [("Town Planning", "Grid pattern with streets cutting at right angles; advanced subterranean drainage with soak pits."),
                 ("Lothal", "Tidal dockyard connected to Bhogava river; bead-making factories and double burial."),
                 ("Dholavira", "Three-tier town planning (Citadel, Middle, Lower town); monumental stone reservoirs; unique 10-symbol signboard."),
                 ("Kalibangan", "Ploughed agricultural field; fire altars (havana kundas); camel bones."),
                 ("Economy & Seals", "Standardized steatite seals with unicorn, bull, elephant; weight system based on binary ratio.")]
            ))
            table_data = [
                ["Ancient Period", "Economic Base", "Social Structure", "Religious Characteristics"],
                ["Harappan (2600-1900 BCE)", "Bronze-age trade & agriculture", "Merchant-artisan urban classes", "Mother goddess, Proto-Shiva, pipal tree"],
                ["Early Vedic (1500-1000 BCE)", "Pastoralism & cattle wealth (Gau)", "Tribal egalitarian (Sabha & Samiti)", "Nature deities (Indra, Agni, Varuna)"],
                ["Later Vedic (1000-600 BCE)", "Iron plow agriculture (PGW)", "Varna crystallization & Ashramas", "Complex sacrificial rituals (Yajnas)"],
                ["Mauryan (321-185 BCE)", "State-regulated agrarian trade", "Megasthenes 7 castes; guild system", "Buddhism, Ashoka's Dhamma, Jainism"],
                ["Gupta (320-550 CE)", "Land grants & feudalization", "Proliferation of sub-castes (Jatis)", "Puranic Hinduism, temple architecture"]
            ]
        elif m_idx == 1: # Medieval
            sections.append((
                "1. Delhi Sultanate & Administrative Innovations",
                ["The establishment of the Delhi Sultanate in 1206 by Qutb-ud-din Aibak brought the Perso-Islamic administrative framework into northern India.",
                 "The Iqta system replaced traditional tribute extraction with institutionalized revenue assignment to military commanders (muqtis)."],
                [("Iltutmish (1211-1236)", "Real consolidator; introduced silver Tanka and copper Jital; established Chalisa (Corps of Forty)."),
                 ("Balban (1266-1287)", "Theory of Kingship (Niyabat-i-Khudai); introduced Sijda and Paibos court rituals; blood and iron policy."),
                 ("Alauddin Khalji (1296-1316)", "Market regulation with fixed price controls; Dag (branding of horses) and Chehra (descriptive rolls)."),
                 ("Muhammad bin Tughlaq", "Token currency experiment; transfer of capital to Daulatabad; establishment of Diwan-i-Kohi (agriculture dept).")]
            ))
            table_data = [
                ["Dynasty / Empire", "Key Administrative Term", "Institutional Meaning", "Historical Impact"],
                ["Delhi Sultanate", "Iqta", "Revenue assignment in lieu of salary", "Decentralized military upkeep"],
                ["Mughal Empire", "Mansabdari (Zat/Sawar)", "Dual numeric ranking system for nobles", "Merit-based military bureaucracy"],
                ["Mughal Empire", "Ain-i-Dahsala", "10-year average crop price assessment", "Todar Mal's stable land revenue"],
                ["Vijayanagara", "Nayankara System", "Military chiefs (Nayakas) with land amaram", "Imperial defense & local autonomy"],
                ["Vijayanagara", "Ayagar System", "12 hereditary village administrative officers", "Village self-sufficiency"]
            ]
        elif m_idx == 2: # Modern
            sections.append((
                "1. British Colonial Expansion & Agrarian Settlements",
                ["Following the battles of Plassey (1757) and Buxar (1764), the East India Company transitioned from commercial merchants to sovereign landlords.",
                 "To maximize revenue extraction, the British imposed three distinct agrarian tenurial systems across the subcontinent."],
                [("Permanent Settlement (1793)", "Lord Cornwallis; Bengal, Bihar, Orissa; Zamindars declared hereditary owners; fixed revenue 10/11th to Company."),
                 ("Ryotwari System (1820)", "Thomas Munro & Alexander Read; Madras and Bombay; direct settlement with peasant cultivators (ryots)."),
                 ("Mahalwari System (1822)", "Holt Mackenzie; North-West provinces, Punjab; revenue assessed collectively on the village community (Mahal)."),
                 ("Drain of Wealth", "Dadabhai Naoroji & R.C. Dutt showed how home charges, pensions, and export surpluses impoverished India."),
                 ("De-industrialization", "Ruin of traditional Indian handicrafts and textiles due to British duty-free factory imports.")]
            ))
            table_data = [
                ["Land Settlement", "Architect & Year", "Geographical Coverage", "Core Tenurial Feature"],
                ["Permanent Settlement", "Lord Cornwallis (1793)", "Bengal, Bihar, Odisha, Varanasi (19%)", "Zamindar as owner; fixed state demand"],
                ["Ryotwari System", "Thomas Munro (1820)", "Madras, Bombay, Assam, Coorg (51%)", "Direct state-cultivator contract; 50% rent"],
                ["Mahalwari System", "Holt Mackenzie (1822)", "Punjab, Central Provinces, NWFP (30%)", "Village community collective responsibility"]
            ]
        else: # National Movement
            sections.append((
                "1. The Epic Arc of Indian Freedom Struggle",
                ["The Indian National Movement unfolded in three distinct phases: Moderate Phase (1885-1905), Extremist Phase (1905-1919), and Gandhian Mass Movements (1919-1947).",
                 "Mahatma Gandhi transformed the movement from an elite constitutional struggle into a massive pan-Indian people's movement based on Satyagraha and Ahimsa."],
                [("Swadeshi Movement (1905)", "Triggered by Curzon's partition of Bengal; boycott of British goods; national education schools."),
                 ("Non-Cooperation (1920-22)", "Response to Rowlatt Act and Jallianwala Bagh; surrender of titles; boycott of courts, schools; Chauri Chaura withdrawal."),
                 ("Civil Disobedience (1930-34)", "Launched with Dandi Salt March; violation of salt laws, refusal to pay taxes; Gandhi-Irwin Pact 1931."),
                 ("Quit India Movement (1942)", "August Kranti; 'Do or Die' call; underground revolutionary networks led by Aruna Asaf Ali, Jayaprakash Narayan."),
                 ("INA & RIN Mutiny (1945-46)", "Subhas Chandra Bose's Indian National Army trials and Royal Indian Navy strike broke British military resolve.")]
            ))
            table_data = [
                ["Phase / Movement", "Key Leaders", "Core Method", "Historical Milestone"],
                ["Moderate Phase (1885-1905)", "Naoroji, Gokhale, W.C. Bonnerjee", "Petitions, speeches, constitutional agitation", "Economic drain critique"],
                ["Swadeshi Movement (1905-08)", "Lal-Bal-Pal, Aurobindo Ghosh", "Boycott of foreign cloth, picketing, Atmasakti", "First popular mass mobilization"],
                ["Non-Cooperation (1920-22)", "Mahatma Gandhi, CR Das, Motilal Nehru", "Surrender of titles, boycott of British institutions", "Pan-Indian Hindu-Muslim unity"],
                ["Civil Disobedience (1930-34)", "Gandhiji, Sarojini Naidu, C. Rajagopalachari", "Salt Satyagraha, non-payment of land revenue", "Round Table Conferences"],
                ["Quit India (1942)", "Gandhiji, JP Narayan, Ram Manohar Lohia", "'Do or Die' mass defiance, parallel governments", "Decisive final blow to Empire"]
            ]

    return sections, table_data
