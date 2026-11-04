"""
Data definitions and question banks for the UPSC Course Structure.
Generates:
- 8 Modules metadata
- 24 Video lessons mapping
- 40 PDF metadata and content generators
- 40 Quizzes and 400 UPSC Prelims MCQs
"""

MODULES_DATA = [
    # =========================================================================
    # SUBJECT 1: INDIAN POLITY AND GOVERNANCE (GS Paper II)
    # =========================================================================
    {
        "course_code": "UPSC-GS2-POLITY",
        "course_title": "Indian Polity and Governance",
        "course_subject": "Polity & Governance",
        "course_desc": "Comprehensive preparation for UPSC Civil Services Examination covering the Indian Constitution, political system, governance, constitutional bodies and public administration.",
        "course_thumbnail": "https://images.unsplash.com/photo-1541872703-74c5e44368f9?w=800&auto=format&fit=crop&q=80",
        "modules": [
            {
                "module_num": 1,
                "title": "Historical Background and Making of the Constitution",
                "desc": "Historical development of the Indian Constitution, Constituent Assembly, Sources of the Constitution, and Salient features of the Indian Constitution.",
                "video_keys": [
                    "StudyIQ IAS Historical Background of Indian Constitution",
                    "Drishti IAS Making of the Constitution Constituent Assembly",
                    "StudyIQ IAS Salient Features of Indian Constitution"
                ],
                "topics": ["Regulating Acts", "Charter Acts", "GOI Act 1919 & 1935", "Constituent Assembly", "Preamble & Salient Features"]
            },
            {
                "module_num": 2,
                "title": "Fundamental Rights and Directive Principles",
                "desc": "Fundamental Rights (Articles 12-35), Fundamental Duties (Article 51A), Directive Principles of State Policy (Articles 36-51), and Landmark Constitutional Amendments.",
                "video_keys": [
                    "StudyIQ IAS Fundamental Rights Articles 12 to 35",
                    "Drishti IAS Directive Principles of State Policy DPSP",
                    "StudyIQ IAS Fundamental Duties and Constitutional Amendments"
                ],
                "topics": ["Right to Equality", "Right to Freedom", "Article 21 & Due Process", "DPSPs Classification", "Basic Structure Doctrine"]
            },
            {
                "module_num": 3,
                "title": "Union and State Government",
                "desc": "President and Vice President, Prime Minister and Council of Ministers, Parliament, Governor and Chief Minister, and State Legislature.",
                "video_keys": [
                    "StudyIQ IAS President and Vice President of India Polity",
                    "Drishti IAS Parliament of India Lok Sabha Rajya Sabha",
                    "StudyIQ IAS Governor and State Legislature Polity"
                ],
                "topics": ["Presidential Powers & Ordinances", "Parliamentary Procedures & Committees", "Rajya Sabha Special Powers", "Governor's Discretionary Powers", "Centre-State Relations"]
            },
            {
                "module_num": 4,
                "title": "Constitutional and Statutory Bodies",
                "desc": "Election Commission of India, UPSC and State Public Service Commissions, CAG, Finance Commission, NITI Aayog, Central Vigilance Commission and other important institutions.",
                "video_keys": [
                    "StudyIQ IAS Election Commission of India UPSC Polity",
                    "Drishti IAS CAG Comptroller and Auditor General UPSC",
                    "StudyIQ IAS NITI Aayog Finance Commission UPSC"
                ],
                "topics": ["Election Commission (Art 324)", "CAG Constitutional Role (Art 148)", "Finance Commission (Art 280)", "UPSC & SPSC (Art 315-323)", "NITI Aayog & Statutory Bodies"]
            }
        ]
    },
    # =========================================================================
    # SUBJECT 2: INDIAN HISTORY AND CULTURE (GS Paper I)
    # =========================================================================
    {
        "course_code": "UPSC-GS1-HISTORY",
        "course_title": "Indian History and Culture",
        "course_subject": "History & Culture",
        "course_desc": "Comprehensive preparation covering Ancient, Medieval and Modern Indian History, the freedom struggle, art and culture, and important historical developments relevant to UPSC Prelims and Mains.",
        "course_thumbnail": "https://images.unsplash.com/photo-1599661046289-e31897846e41?w=800&auto=format&fit=crop&q=80",
        "modules": [
            {
                "module_num": 1,
                "title": "Ancient Indian History",
                "desc": "Indus Valley Civilisation, Vedic Period, Mauryan Empire, Gupta Empire, and Ancient Indian religions and philosophy.",
                "video_keys": [
                    "StudyIQ IAS Indus Valley Civilisation Ancient History",
                    "Drishti IAS Mauryan Empire Ashoka Ancient History",
                    "StudyIQ IAS Gupta Empire Ancient Indian History"
                ],
                "topics": ["Harappan Town Planning & Seals", "Early & Later Vedic Society", "Buddhism & Jainism Doctrines", "Mauryan Administration & Ashokan Edicts", "Gupta Art, Literature & Science"]
            },
            {
                "module_num": 2,
                "title": "Medieval Indian History",
                "desc": "Delhi Sultanate, Mughal Empire, Bhakti and Sufi Movements, Vijayanagara Empire, and Medieval administration and culture.",
                "video_keys": [
                    "StudyIQ IAS Delhi Sultanate Medieval Indian History",
                    "Drishti IAS Mughal Empire Akbar Administration History",
                    "StudyIQ IAS Vijayanagara Empire Bhakti Movement History"
                ],
                "topics": ["Iqta System & Market Reforms", "Mughal Mansabdari & Dahsala", "Bhakti Saints & Teachings", "Vijayanagara Architecture & Nayankara", "Sufi Silsilahs & Philosophy"]
            },
            {
                "module_num": 3,
                "title": "Modern Indian History",
                "desc": "Arrival of European powers, British expansion in India, Revolt of 1857, Socio-religious reform movements, and Economic impact of British rule.",
                "video_keys": [
                    "StudyIQ IAS Arrival of European Powers Modern History",
                    "Drishti IAS Revolt of 1857 Causes and Impact UPSC",
                    "StudyIQ IAS Socio Religious Reform Movements 19th Century"
                ],
                "topics": ["Battle of Plassey & Buxar", "Subsidiary Alliance & Doctrine of Lapse", "Revolt of 1857 Causes & Centers", "Drain of Wealth Theory", "Brahmo Samaj, Arya Samaj & Ramakrishna"]
            },
            {
                "module_num": 4,
                "title": "Indian National Movement",
                "desc": "Formation of Indian National Congress, Swadeshi Movement, Gandhian movements, Revolutionary movements, Constitutional developments, and Independence & Partition.",
                "video_keys": [
                    "StudyIQ IAS Indian National Congress Foundation Moderate Phase",
                    "Drishti IAS Non Cooperation Civil Disobedience Movement Gandhi",
                    "StudyIQ IAS Quit India Movement Independence and Partition"
                ],
                "topics": ["Moderate vs Extremist Phase", "Swadeshi & Boycott 1905", "Non-Cooperation & Khilafat 1920", "Civil Disobedience & Dandi 1930", "Quit India 1942 & Cabinet Mission 1946"]
            }
        ]
    }
]
