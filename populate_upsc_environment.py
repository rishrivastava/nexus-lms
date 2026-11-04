"""
Complete Master Population Script for UPSC CSE Learning Environment in Nexus LMS.
Populates:
- Faculty: Dr. A. K. Sharma (T-UPSC-01)
- 2 UPSC Subjects:
  1. Indian Polity and Governance (UPSC-GS2-POLITY)
  2. Indian History and Culture (UPSC-GS1-HISTORY)
- 8 Modules (4 in Polity, 4 in History)
- 24 Verified Educational YouTube Video Lessons (3 per module)
- 40 Styled ReportLab PDF Study Resources (5 per module in app/static/uploads/upsc/)
- 40 Functional Quizzes (5 per module)
- 400 UPSC Prelims Pattern Questions (10 per quiz with detailed explanations)
- 320 Realistic Indian Student Accounts Enrolled in Both Subjects
- Realistic Student Progress, Quiz Attempts, and Mains Answer Sheet Submissions
"""

import os
import sys
import json
import random
import sqlite3
import bcrypt
from datetime import datetime, timedelta

from generate_upsc_modules import MODULES_DATA
from upsc_pdf_factory import generate_all_40_pdfs
from upsc_question_factory import generate_questions_for_module
from upsc_answersheet_factory import generate_sample_answer_sheets

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "lms.db")
UPLOADS_DIR = os.path.join(BASE_DIR, "app", "static", "uploads")
UPSC_PDF_DIR = os.path.join(UPLOADS_DIR, "upsc")
ANSWERS_DIR = os.path.join(UPLOADS_DIR, "answer_sheets")
VIDEOS_JSON_PATH = os.path.join(BASE_DIR, "upsc_videos.json")

# Names bank for realistic Indian student generation
FIRST_NAMES_M = [
    "Aarav", "Aditya", "Akash", "Amit", "Anand", "Ankit", "Arjun", "Deepak",
    "Devendra", "Gaurav", "Harish", "Karthik", "Manish", "Nikhil", "Pranav",
    "Rahul", "Rajesh", "Rishi", "Rohan", "Sachin", "Sanjay", "Siddharth",
    "Suresh", "Tarun", "Varun", "Vikas", "Vikram", "Vinay", "Vivek", "Yash"
]
FIRST_NAMES_F = [
    "Aanya", "Aditi", "Ananya", "Anjali", "Aparna", "Deepa", "Divya", "Gayathri",
    "Isha", "Kavya", "Meera", "Neha", "Nisha", "Pooja", "Prerna", "Priya",
    "Radhika", "Ritu", "Roshni", "Sakshi", "Shalini", "Shreya", "Sneha", "Swati",
    "Tanvi", "Trisha", "Vandana", "Varsha", "Vidya", "Yamini"
]
LAST_NAMES = [
    "Agarwal", "Banerjee", "Bhatia", "Chatterjee", "Choudhary", "Das", "Deshmukh",
    "Dubey", "Gupta", "Iyer", "Jha", "Joshi", "Kaur", "Kulkarni", "Kumar",
    "Mehta", "Mishra", "Mukherjee", "Nair", "Pandey", "Patel", "Rao", "Reddy",
    "Saha", "Sen", "Sharma", "Singh", "Sinha", "Trivedi", "Verma", "Yadav"
]

INDIAN_STATES_DISTRICTS = [
    ("Delhi", "New Delhi", "110001", "St. Stephen's College / Delhi University"),
    ("Delhi", "North Delhi", "110007", "Hindu College / Delhi University"),
    ("Uttar Pradesh", "Prayagraj", "211002", "University of Allahabad"),
    ("Uttar Pradesh", "Varanasi", "221005", "Banaras Hindu University (BHU)"),
    ("Uttar Pradesh", "Lucknow", "226007", "University of Lucknow"),
    ("Bihar", "Patna", "800005", "Patna University"),
    ("Bihar", "Gaya", "823001", "Magadh University"),
    ("Maharashtra", "Pune", "411004", "Fergusson College Pune"),
    ("Maharashtra", "Mumbai", "400032", "St. Xavier's College Mumbai"),
    ("Tamil Nadu", "Chennai", "600034", "Loyola College Chennai"),
    ("Tamil Nadu", "Coimbatore", "641018", "PSG College of Arts and Science"),
    ("Karnataka", "Bengaluru", "560001", "National Law School / IISc"),
    ("Karnataka", "Mysuru", "570005", "University of Mysore"),
    ("Rajasthan", "Jaipur", "302004", "University of Rajasthan"),
    ("Rajasthan", "Jodhpur", "342001", "Jai Narain Vyas University"),
    ("West Bengal", "Kolkata", "700073", "Presidency University Kolkata"),
    ("Madhya Pradesh", "Bhopal", "462001", "MANIT Bhopal"),
    ("Madhya Pradesh", "Indore", "452001", "Devi Ahilya Vishwavidyalaya"),
    ("Gujarat", "Ahmedabad", "380009", "Gujarat University"),
    ("Telangana", "Hyderabad", "500007", "Osmania University"),
    ("Kerala", "Thiruvananthapuram", "695034", "University College Trivandrum"),
    ("Punjab", "Chandigarh", "160014", "Panjab University")
]

def hash_pw(password):
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(password.encode('utf-8'), salt).decode('utf-8')

def main():
    print("=" * 70)
    print("NEXUS LMS: POPULATING COMPLETE UPSC LEARNING ENVIRONMENT")
    print("=" * 70)

    # 1. Connect to database
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()

    # 2. Setup Department
    print("\n[Step 1] Ensuring 'Test Prep' Department exists...")
    c.execute("SELECT id FROM departments WHERE name = 'Test Prep' OR code = 'TEST_PREP'")
    dept_row = c.fetchone()
    if not dept_row:
        c.execute("""
            INSERT INTO departments (name, code, description, banner_url, branding_tagline, welcome_message)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            "Test Prep",
            "TEST_PREP",
            "UPSC Civil Services Examination (CSE) & Standardized Exam Preparation",
            "https://images.unsplash.com/photo-1434030216411-0b793f4b4173?w=1200",
            "transforming education",
            "Welcome to the UPSC CSE & Test Prep Learning Portal. Master your GS curriculum with curated video lectures, NCERT notes, prelims drills, and evaluated mains answer writing."
        ))
        conn.commit()
        print("  -> Created 'Test Prep' department.")
    else:
        print("  -> 'Test Prep' department already present.")

    # 3. Setup UPSC Faculty (Dr. A. K. Sharma)
    print("\n[Step 2] Setting up UPSC Faculty Account...")
    c.execute("SELECT id, user_id, full_name FROM users WHERE user_id = 'T-UPSC-01'")
    teacher_row = c.fetchone()
    teacher_pw_hash = hash_pw("password123")
    
    if not teacher_row:
        c.execute("""
            INSERT INTO users (
                user_id, full_name, department, email, password_hash, role,
                must_change_password, designation, bio
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            "T-UPSC-01",
            "Dr. A. K. Sharma (UPSC Faculty)",
            "Test Prep",
            "ak.sharma.upsc@leadgroup.in",
            teacher_pw_hash,
            "teacher",
            0,
            "Senior Faculty & Mentor, General Studies (Polity & History)",
            "Former civil servant and senior UPSC mentor with 18+ years of experience guiding CSE aspirants in Indian Polity, Governance, and Indian History."
        ))
        teacher_id = c.lastrowid
        conn.commit()
        print(f"  -> Created Faculty: Dr. A. K. Sharma (ID: {teacher_id}, User ID: T-UPSC-01)")
    else:
        teacher_id = teacher_row["id"]
        print(f"  -> Existing Faculty found: {teacher_row['full_name']} (ID: {teacher_id})")

    # 4. Generate 40 ReportLab PDFs
    print("\n[Step 3] Generating 40 Styled UPSC Study Material PDFs...")
    pdf_map = generate_all_40_pdfs(UPSC_PDF_DIR)
    print(f"  -> Generated {len(pdf_map) * 5} PDF documents in {UPSC_PDF_DIR}")

    # 5. Load YouTube Videos
    print("\n[Step 4] Loading 24 verified educational YouTube videos...")
    with open(VIDEOS_JSON_PATH) as f:
        videos_data = json.load(f)
    print(f"  -> Loaded {len(videos_data)} verified video records.")

    # 6. Create 2 Courses, 8 Modules, 24 Videos, 40 PDFs, 40 Quizzes, 400 Questions
    print("\n[Step 5] Building Course & Module Curriculum Structure...")
    course_ids = []

    for c_idx, c_info in enumerate(MODULES_DATA):
        c_code = c_info["course_code"]
        c_title = c_info["course_title"]
        print(f"\n  -- Setting up Subject {c_idx+1}: {c_title} ({c_code}) --")

        c.execute("SELECT id FROM courses WHERE code = ?", (c_code,))
        existing_course = c.fetchone()

        if existing_course:
            course_id = existing_course["id"]
            # Clean up old modules/lessons for this course to ensure clean idempotency
            c.execute("DELETE FROM courses WHERE id = ?", (course_id,))
            conn.commit()
            print(f"     Replacing existing course #{course_id} for a fresh population.")

        c.execute("""
            INSERT INTO courses (
                title, code, department, subject, description, thumbnail_url,
                teacher_id, is_published, status, subtitle, instructions
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            c_title,
            c_code,
            "Test Prep",
            c_info["course_subject"],
            c_info["course_desc"],
            c_info["course_thumbnail"],
            teacher_id,
            1,
            "published",
            "Comprehensive General Studies Preparation for UPSC Civil Services Examination (Prelims + Mains)",
            "Step 1: Watch the daily video lectures carefully. Step 2: Read the module NCERT and topic notes. Step 3: Attempt the timed Prelims assessments. Step 4: Write and upload handwritten subjective answers for mentor evaluation."
        ))
        course_id = c.lastrowid
        conn.commit()
        course_ids.append(course_id)
        print(f"     -> Created Course #{course_id}: {c_title}")

        # Add 4 Modules
        for m_idx, m_info in enumerate(c_info["modules"]):
            m_title = m_info["title"]
            m_desc = m_info["desc"]
            
            c.execute("""
                INSERT INTO modules (course_id, title, position, description)
                VALUES (?, ?, ?, ?)
            """, (course_id, m_title, m_idx + 1, m_desc))
            module_id = c.lastrowid
            conn.commit()
            print(f"        Module {m_idx+1}: {m_title} (ID: {module_id})")

            cur_pos = 1

            # A. 3 YouTube Videos
            for v_key in m_info["video_keys"]:
                v_obj = videos_data[v_key]
                v_title = v_obj["title"]
                v_id = v_obj["id"]
                c.execute("""
                    INSERT INTO lessons (
                        module_id, title, content_type, content_value, position,
                        duration_minutes, subtitle, description
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    module_id,
                    v_title,
                    "youtube",
                    v_id,
                    cur_pos,
                    20,
                    f"Video Lecture by {v_obj.get('author', 'StudyIQ / Drishti IAS')}",
                    f"In-depth video analysis covering {m_title} specifically prepared for UPSC CSE."
                ))
                cur_pos += 1
            print(f"           + 3 YouTube Video Lessons added.")

            # B. 5 PDF Resources
            pdfs = pdf_map.get((c_code, m_idx), [])
            for p_obj in pdfs:
                c.execute("""
                    INSERT INTO lessons (
                        module_id, title, content_type, content_value, position,
                        duration_minutes, subtitle, description
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    module_id,
                    p_obj["title"],
                    "pdf",
                    p_obj["filename"],
                    cur_pos,
                    p_obj["duration"],
                    p_obj["category"],
                    f"Official reading study material for {m_title}."
                ))
                cur_pos += 1
            print(f"           + 5 PDF Study Resource Lessons added.")

            # C. 5 Quizzes (each with 10 questions = 50 MCQs per module)
            quizzes = generate_questions_for_module(c_code, m_idx)
            for qz in quizzes:
                qz_title = qz["title"]
                c.execute("""
                    INSERT INTO lessons (
                        module_id, title, content_type, content_value, position,
                        duration_minutes, subtitle, description
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    module_id,
                    f"Assessment: {qz_title}",
                    "quiz",
                    "UPSC Prelims Pattern Timed Assessment",
                    cur_pos,
                    15,
                    "Timed Assessment (10 Questions)",
                    "Solve under strict timed conditions. Requires 70% to pass."
                ))
                lesson_id = c.lastrowid
                cur_pos += 1

                # Quizzes table
                c.execute("""
                    INSERT INTO quizzes (lesson_id, passing_score, time_limit_minutes)
                    VALUES (?, 70, 15)
                """, (lesson_id,))
                quiz_id = c.lastrowid

                # 10 Questions
                for q_item in qz["questions"]:
                    c.execute("""
                        INSERT INTO quiz_questions (
                            quiz_id, question_text, option_a, option_b, option_c, option_d,
                            correct_option, explanation
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        quiz_id,
                        q_item["question_text"],
                        q_item["option_a"],
                        q_item["option_b"],
                        q_item["option_c"],
                        q_item["option_d"],
                        q_item["correct_option"],
                        q_item["explanation"]
                    ))
            conn.commit()
            print(f"           + 5 Quizzes (50 Questions) added.")

    # 7. Generate & Enroll 320 Indian Student Accounts
    print("\n[Step 6] Creating 320 Indian Student Accounts & Enrolling in Both UPSC Courses...")
    reusable_pw_hash = teacher_pw_hash  # Hashing 'password123' once saves ~30s of bcrypt overhead
    
    student_records = []
    student_ids_db = []

    # Check how many UPSC students exist
    c.execute("SELECT user_id FROM users WHERE user_id LIKE 'UPSC-2026-%'")
    existing_uids = {r[0] for r in c.fetchall()}

    random.seed(42) # Reproducible realistic distribution
    num_students = 320

    for i in range(1, num_students + 1):
        uid = f"UPSC-2026-{i:04d}"
        
        # Alternate gender for realistic Indian name pairing
        is_male = (i % 2 == 1)
        fname = random.choice(FIRST_NAMES_M if is_male else FIRST_NAMES_F)
        lname = random.choice(LAST_NAMES)
        full_name = f"{fname} {lname}"
        email = f"{fname.lower()}.{lname.lower()}.{i}@leadgroup.in"

        # Demographics
        state_info = random.choice(INDIAN_STATES_DISTRICTS)
        state, district, pincode, college = state_info
        guardian_title = "Mr." if random.random() > 0.3 else "Dr."
        guardian_name = f"{guardian_title} {random.choice(FIRST_NAMES_M)} {lname}"
        block = f"{district} Central"

        if uid not in existing_uids:
            c.execute("""
                INSERT INTO users (
                    user_id, full_name, department, email, password_hash, role,
                    must_change_password, guardian_name, school_name, block,
                    district, state, pincode, designation, bio
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                uid, full_name, "Test Prep", email, reusable_pw_hash, "student",
                0, guardian_name, college, block, district, state, pincode,
                "UPSC CSE 2026 Aspirant",
                f"Preparing for UPSC Civil Services Examination 2026. Academic background: {college}."
            ))
            s_db_id = c.lastrowid
            student_ids_db.append((s_db_id, uid, full_name))
        else:
            c.execute("SELECT id FROM users WHERE user_id = ?", (uid,))
            s_db_id = c.fetchone()[0]
            student_ids_db.append((s_db_id, uid, full_name))

        # Enroll in both UPSC courses
        for cid in course_ids:
            c.execute("""
                INSERT INTO enrollments (user_id, course_id, enrolled_at)
                VALUES (?, ?, datetime('now', ?))
                ON CONFLICT(user_id, course_id) DO NOTHING
            """, (s_db_id, cid, f"-{random.randint(1, 30)} days"))

    conn.commit()
    print(f"  -> Total {len(student_ids_db)} student accounts verified & enrolled in both UPSC courses.")

    # 8. Populate Realistic Activity: Lesson Progress & Quiz Attempts
    print("\n[Step 7] Simulating Realistic Student Progress & Assessment Analytics...")
    # Get all lessons and quizzes for UPSC courses
    c.execute("""
        SELECT l.id, l.content_type, m.course_id, q.id as quiz_id
        FROM lessons l
        JOIN modules m ON l.module_id = m.id
        LEFT JOIN quizzes q ON l.id = q.lesson_id
        WHERE m.course_id IN (?, ?)
    """, (course_ids[0], course_ids[1]))
    all_course_lessons = [dict(r) for r in c.fetchall()]

    # Simulate activity for the first 180 students
    active_students = student_ids_db[:180]
    total_progress_count = 0
    total_attempts_count = 0

    for s_id, s_uid, s_name in active_students:
        # Each student has completed a random subset of 10 to 35 lessons
        completed_count = random.randint(10, 35)
        chosen_lessons = random.sample(all_course_lessons, min(completed_count, len(all_course_lessons)))

        for les in chosen_lessons:
            # Mark lesson progress
            c.execute("""
                INSERT INTO lesson_progress (user_id, lesson_id, is_completed, watched_seconds, completed_at)
                VALUES (?, ?, 1, 1200, datetime('now', ?))
                ON CONFLICT(user_id, lesson_id) DO UPDATE SET is_completed = 1
            """, (s_id, les["id"], f"-{random.randint(1, 20)} days"))
            total_progress_count += 1

            # If it's a quiz, generate realistic attempt score
            if les["content_type"] == "quiz" and les["quiz_id"]:
                score = random.choice([70.0, 80.0, 80.0, 90.0, 90.0, 100.0, 60.0, 50.0])
                passed = 1 if score >= 70.0 else 0
                time_taken = random.randint(300, 750)

                c.execute("""
                    INSERT INTO quiz_attempts (
                        user_id, quiz_id, score_percent, passed, attempted_at,
                        time_taken_seconds
                    ) VALUES (?, ?, ?, ?, datetime('now', ?), ?)
                """, (
                    s_id, les["quiz_id"], score, passed,
                    f"-{random.randint(1, 15)} days", time_taken
                ))
                total_attempts_count += 1

    conn.commit()
    print(f"  -> Recorded {total_progress_count} lesson completions and {total_attempts_count} quiz attempts across active students.")

    # 9. Populate Sample UPSC Mains Answer Sheet Submissions
    print("\n[Step 8] Generating Sample UPSC Mains Answer Sheets & Submissions...")
    sample_sheets = generate_sample_answer_sheets(ANSWERS_DIR)
    print(f"  -> Generated {len(sample_sheets)} sample Mains Answer Sheet PDFs in {ANSWERS_DIR}")

    # Insert sample submissions for 12 students
    eval_feedbacks = [
        (15.5, 20.0, "Excellent conceptual clarity. Good invocation of Kesavananda Bharati and Minerva Mills cases. Structure is well balanced with intro, body and conclusion."),
        (16.0, 20.0, "Outstanding presentation! Town planning diagram and comparative Harappan vs Vedic dimensions are very well argued. High scoring answer."),
        (14.0, 20.0, "Comprehensive analysis of 1857 Revolt impact. Peel commission and military reorganization points are well highlighted. Add 1-2 quotes in conclusion."),
        (15.0, 20.0, "Solid doctrinal breakdown of Article 324 and Election Commission autonomy. Recommendation of 255th Law Commission cited accurately."),
        (13.5, 20.0, "Good answer on Gandhian Satyagraha vs Extremist methods. Emphasize constructive programs and social reform aspects more."),
        (14.5, 20.0, "Well articulated arguments on Basic Structure. Time management and word limit strictly adhered to.")
    ]

    # Clean up previous sample answer sheet submissions for these courses to remain clean
    c.execute("DELETE FROM answer_sheet_submissions WHERE course_id IN (?, ?)", (course_ids[0], course_ids[1]))
    conn.commit()

    # Get module IDs for Course 1 and Course 2
    c.execute("SELECT id, course_id FROM modules WHERE course_id IN (?, ?)", (course_ids[0], course_ids[1]))
    mod_rows = c.fetchall()
    mod_id_c1 = [r["id"] for r in mod_rows if r["course_id"] == course_ids[0]]
    mod_id_c2 = [r["id"] for r in mod_rows if r["course_id"] == course_ids[1]]

    # 6 Evaluated submissions
    for idx, (marks, max_m, feedback) in enumerate(eval_feedbacks):
        stu = active_students[idx]
        cid = course_ids[idx % 2]
        m_id = mod_id_c1[0] if cid == course_ids[0] else mod_id_c2[0]
        sheet_file, sheet_title = sample_sheets[idx % len(sample_sheets)]

        c.execute("""
            INSERT INTO answer_sheet_submissions (
                user_id, course_id, module_id, file_path, original_filename,
                remarks, status, marks_awarded, max_marks, feedback,
                evaluated_by, evaluated_at, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now', '-2 days'), datetime('now', '-5 days'))
        """, (
            stu[0], cid, m_id, f"answer_sheets/{sheet_file}", sheet_file,
            f"Mains Test Submission: {sheet_title}",
            "evaluated", marks, max_m, feedback, teacher_id
        ))

    # 6 Pending/Under Review submissions
    pending_remarks = [
        "Mains Question: Discuss the discretionary powers of the Governor under Article 163.",
        "Mains Question: Evaluate the market control reforms of Alauddin Khalji.",
        "Mains Question: Analyze the causes of the failure of Cabinet Mission Plan 1946.",
        "Mains Question: Critically evaluate the financial autonomy of Panchayati Raj institutions.",
        "Mains Question: Assess the architectural achievements of the Vijayanagara Empire.",
        "Mains Question: Role of Subhas Chandra Bose and INA in the final phase of Indian independence."
    ]
    for idx in range(6):
        stu = active_students[6 + idx]
        cid = course_ids[idx % 2]
        m_id = mod_id_c1[1] if cid == course_ids[0] else mod_id_c2[1]
        sheet_file, _ = sample_sheets[idx % len(sample_sheets)]
        status_str = "under_review" if idx % 2 == 0 else "submitted"

        c.execute("""
            INSERT INTO answer_sheet_submissions (
                user_id, course_id, module_id, file_path, original_filename,
                remarks, status, max_marks, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, 20.0, datetime('now', '-1 days'))
        """, (
            stu[0], cid, m_id, f"answer_sheets/{sheet_file}", sheet_file,
            pending_remarks[idx], status_str
        ))

    conn.commit()
    print("  -> Inserted 12 sample UPSC Mains Answer Sheet submissions (6 evaluated, 6 pending review).")

    # 10. Summary Verification
    print("\n" + "=" * 70)
    print("FINAL VERIFICATION METRICS")
    print("=" * 70)

    c.execute("SELECT COUNT(*) FROM courses WHERE code LIKE 'UPSC%'")
    print(f"Total UPSC Courses:              {c.fetchone()[0]} (Target: 2)")

    c.execute("SELECT COUNT(*) FROM modules WHERE course_id IN (?, ?)", (course_ids[0], course_ids[1]))
    print(f"Total Modules in UPSC:           {c.fetchone()[0]} (Target: 8, 4 per subject)")

    c.execute("""
        SELECT COUNT(*) FROM lessons l
        JOIN modules m ON l.module_id = m.id
        WHERE m.course_id IN (?, ?) AND l.content_type = 'youtube'
    """, (course_ids[0], course_ids[1]))
    print(f"Total YouTube Video Lessons:     {c.fetchone()[0]} (Target: 24, 3 per module)")

    c.execute("""
        SELECT COUNT(*) FROM lessons l
        JOIN modules m ON l.module_id = m.id
        WHERE m.course_id IN (?, ?) AND l.content_type = 'pdf'
    """, (course_ids[0], course_ids[1]))
    print(f"Total PDF Study Resources:       {c.fetchone()[0]} (Target: 40, 5 per module)")

    c.execute("""
        SELECT COUNT(*) FROM lessons l
        JOIN modules m ON l.module_id = m.id
        WHERE m.course_id IN (?, ?) AND l.content_type = 'quiz'
    """, (course_ids[0], course_ids[1]))
    print(f"Total Functional Quizzes:        {c.fetchone()[0]} (Target: 40, 5 per module)")

    c.execute("""
        SELECT COUNT(*) FROM quiz_questions qq
        JOIN quizzes q ON qq.quiz_id = q.id
        JOIN lessons l ON q.lesson_id = l.id
        JOIN modules m ON l.module_id = m.id
        WHERE m.course_id IN (?, ?)
    """, (course_ids[0], course_ids[1]))
    print(f"Total UPSC Prelims MCQs:         {c.fetchone()[0]} (Target: 400, 10 per quiz)")

    c.execute("SELECT COUNT(*) FROM users WHERE user_id LIKE 'UPSC-2026-%'")
    print(f"Total Enrolled Student Accounts: {c.fetchone()[0]} (Target: At least 300)")

    c.execute("SELECT COUNT(*) FROM enrollments WHERE course_id IN (?, ?)", (course_ids[0], course_ids[1]))
    print(f"Total Course Enrollments:        {c.fetchone()[0]} (320 students x 2 courses = 640)")

    c.execute("SELECT COUNT(*) FROM quiz_attempts")
    print(f"Total Quiz Attempts Logged:      {c.fetchone()[0]}")

    c.execute("SELECT COUNT(*) FROM answer_sheet_submissions WHERE course_id IN (?, ?)", (course_ids[0], course_ids[1]))
    print(f"Total Mains Answer Submissions:  {c.fetchone()[0]} (6 evaluated + 6 pending review)")

    conn.close()
    print("\n>>> Population completed successfully! LMS is fully populated with UPSC CSE content.")

if __name__ == "__main__":
    main()
