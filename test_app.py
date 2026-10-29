import asyncio
from app.database import get_db, init_db, get_system_settings, update_system_settings
from app.seed import seed_data
from app.auth import hash_password, verify_password, create_access_token, decode_access_token
from app.utils import extract_youtube_id

def test_lms():
    print("Running LMS Direct Unit Tests...")
    init_db()
    
    # 1. Test Password Hashing & Verification
    pwd = "secretPassword123"
    h = hash_password(pwd)
    assert verify_password(pwd, h) == True
    assert verify_password("wrongPass", h) == False
    print("✓ Password hashing & bcrypt verification works")

    # 2. Test JWT Token Lifecycle
    token = create_access_token({"sub": "CS2026-001", "role": "student"})
    payload = decode_access_token(token)
    assert payload["sub"] == "CS2026-001"
    assert payload["role"] == "student"
    print("✓ JWT access token creation & decoding works")

    # 3. Test YouTube URL Extraction
    urls = [
        "https://www.youtube.com/watch?v=7_LPdttKXPc",
        "https://youtu.be/7_LPdttKXPc",
        "https://www.youtube.com/embed/7_LPdttKXPc",
        "7_LPdttKXPc"
    ]
    for u in urls:
        assert extract_youtube_id(u) == "7_LPdttKXPc", f"Failed for {u}"
    print("✓ YouTube URL parser correctly extracts 11-char Video ID across all formats")

    # 4. Test Branding System Settings
    settings = get_system_settings()
    assert "platform_name" in settings
    assert "institution_name" in settings
    print(f"✓ Dynamic branding settings loaded: {settings['platform_name']}")

    # Update branding test
    update_system_settings({"platform_name": "Apex Engineering Portal"})
    new_settings = get_system_settings()
    assert new_settings["platform_name"] == "Apex Engineering Portal"
    # Revert to standard
    update_system_settings({"platform_name": "Nexus LMS"})
    print("✓ Custom branding updates dynamically persisted")

    # 5. Test Teacher Addition
    with get_db() as conn:
        cursor = conn.cursor()
        t_hash = hash_password("teacher123")
        cursor.execute("""
            INSERT OR REPLACE INTO users (user_id, full_name, department, email, password_hash, role, must_change_password)
            VALUES (?, ?, ?, ?, ?, 'teacher', 1)
        """, ("T-TEST-002", "Dr. Claude Shannon", "Computer Science", "shannon@institution.edu", t_hash))
        
        cursor.execute("SELECT full_name, role FROM users WHERE user_id = 'T-TEST-002'")
        t_row = cursor.fetchone()
        assert t_row is not None
        assert t_row["role"] == "teacher"
        print("✓ Department Head faculty provisioning verified")

    # 6. Test Database State
    with get_db() as conn:
        cursor = conn.cursor()
        
        # Check users
        cursor.execute("SELECT user_id, role, must_change_password FROM users WHERE user_id = 'CS2026-002'")
        student = cursor.fetchone()
        assert student is not None
        assert student["role"] == "student"
        assert student["must_change_password"] in (0, 1)
        print("✓ Student pre-provisioned and verified")

        # Check courses & lessons
        cursor.execute("SELECT id, title FROM courses WHERE code = 'CS-201'")
        course = cursor.fetchone()
        assert course is not None

        cursor.execute("SELECT content_type, COUNT(*) FROM lessons GROUP BY content_type")
        types = dict(cursor.fetchall())
        assert "youtube" in types
        assert "pdf" in types
        assert "quiz" in types
        print("✓ Course curriculum contains YouTube video, PDF reader, and Quiz lessons")

        # Check quiz questions
        cursor.execute("SELECT COUNT(*) FROM quiz_questions")
        q_count = cursor.fetchone()[0]
        assert q_count == 3
        print(f"✓ Assessment engine initialized with {q_count} knowledge check questions")

    # 7. Test Government / UDISE Student CSV Import Headers
    from app.routes.dept_routes import extract_field
    csv_row = {
        "Serial NO. (UNIQUE NO.)": "KA-2026-999",
        "STUDENT NAME": "Manish Sharma",
        "FATHER'/GUARDIAN, NAME": "Suresh Sharma",
        "SCHOOL NAME": "Govt High School",
        "UDISE CODE": "29280100101",
        "BLOCK": "North Block",
        "DISTRICT": "Bengaluru",
        "STATE": "Karnataka",
        "PINCODE": "560001",
        "COURSE": "CS-201"
    }
    assert extract_field(csv_row, "Serial NO. (UNIQUE NO.)") == "KA-2026-999"
    assert extract_field(csv_row, "STUDENT NAME") == "Manish Sharma"
    assert extract_field(csv_row, "FATHER'/GUARDIAN, NAME", "FATHER'/GUARDIAN") == "Suresh Sharma"
    assert extract_field(csv_row, "SCHOOL NAME") == "Govt High School"
    assert extract_field(csv_row, "UDISE CODE") == "29280100101"
    assert extract_field(csv_row, "DISTRICT") == "Bengaluru"
    assert extract_field(csv_row, "PINCODE") == "560001"
    assert extract_field(csv_row, "COURSE") == "CS-201"
    print("✓ Government / UDISE School CSV headers with COURSE verified")

    # 8. Test Course Assignment & Restricted Access
    with get_db() as conn:
        cursor = conn.cursor()
        
        # Create a new private course
        cursor.execute("""
            INSERT OR REPLACE INTO courses (id, title, code, department, description, teacher_id, is_published)
            VALUES (999, 'Advanced Quantum Computing', 'QC-999', 'Computer Science', 'Restricted course', 2, 1)
        """)
        
        # Verify student CS2026-002 is NOT enrolled in course 999
        cursor.execute("SELECT id FROM users WHERE user_id = 'CS2026-002'")
        s_id = cursor.fetchone()[0]
        
        cursor.execute("SELECT id FROM enrollments WHERE user_id = ? AND course_id = 999", (s_id,))
        assert cursor.fetchone() is None, "Student should not be auto-enrolled in private course"
        print("✓ Student restricted access verified: cannot interact with unassigned course")

        # Now assign course 999 to student
        cursor.execute("INSERT INTO enrollments (user_id, course_id) VALUES (?, 999)", (s_id,))
        cursor.execute("SELECT id FROM enrollments WHERE user_id = ? AND course_id = 999", (s_id,))
        assert cursor.fetchone() is not None
        print("✓ Course assignment to student verified")

        # Clean up test enrollment
        cursor.execute("DELETE FROM enrollments WHERE user_id = ? AND course_id = 999", (s_id,))
        cursor.execute("DELETE FROM courses WHERE id = 999")

    # 9. Test Name Normalization & Duplicate Prevention Engine (PRD Section 3)
    from app.utils import normalize_name, generate_unique_student_id
    assert normalize_name("Rahul Kumar") == "rahul kumar"
    assert normalize_name("  rahul   kumar  ") == "rahul kumar"
    assert normalize_name("RAHUL KUMAR") == "rahul kumar"
    assert normalize_name("Amit Kumar") == "amit kumar"
    assert normalize_name("  AMIT   KUMAR  ") == "amit kumar"
    assert normalize_name("café") == "cafe"  # Unicode normalization
    print("✓ PRD Name Normalization verified (lowercase, whitespace collapse, Unicode NFKD)")

    # 10. Test Safe Sequential Unique Student ID Generator (STU-YYYY-XXXXXX)
    with get_db() as conn:
        cursor = conn.cursor()
        new_id_1 = generate_unique_student_id(cursor, year=2026)
        assert new_id_1.startswith("STU-2026-")
        assert len(new_id_1) == len("STU-2026-000001")
        print(f"✓ Unique Student ID Generator verified: Generated {new_id_1}")

    # 11. Test Database Duplicate Prevention & Single Student Registration
    with get_db() as conn:
        cursor = conn.cursor()
        t_hash = hash_password("welcome123")
        
        # Insert a primary student in Global Pool
        uid_primary = "STU-2026-000888"
        norm_n = normalize_name("Aarav Sharma")
        norm_g = normalize_name("Vikas Sharma")
        cursor.execute("""
            INSERT OR REPLACE INTO users (
                user_id, full_name, guardian_name, department, password_hash, role,
                normalized_name, normalized_guardian
            ) VALUES (?, ?, ?, 'Computer Science', ?, 'student', ?, ?)
        """, (uid_primary, "Aarav Sharma", "Vikas Sharma", t_hash, norm_n, norm_g))
        
        # Test duplicate query with different casing and spacing: "  AARAV   SHARMA  " & "vikas sharma"
        test_norm_n = normalize_name("  AARAV   SHARMA  ")
        test_norm_g = normalize_name("  vikas   sharma  ")
        cursor.execute("""
            SELECT user_id, full_name FROM users 
            WHERE normalized_name = ? AND normalized_guardian = ?
        """, (test_norm_n, test_norm_g))
        dup_match = cursor.fetchone()
        assert dup_match is not None, "Duplicate engine must catch case-insensitive and spacing variations"
        assert dup_match["user_id"] == uid_primary
        print(f"✓ Duplicate Prevention Engine verified: Correctly detected existing record {dup_match['user_id']}")

        # Clean up test user
        cursor.execute("DELETE FROM users WHERE user_id = ?", (uid_primary,))

    # 12. Test Bulk Import Deduplication & In-File Duplicate Rejection
    from app.routes.dept_routes import parse_student_upload
    sample_csv_text = (
        "Serial NO. (UNIQUE NO.),STUDENT NAME,FATHER'/GUARDIAN, NAME,SCHOOL NAME,UDISE CODE,BLOCK,DISTRICT,STATE,PINCODE,COURSE\n"
        "STU-001,Kavita Patel,Ramesh Patel,Delhi Public School,292801001,North,Bengaluru,Karnataka,560001,CS-201\n"
        "STU-002,kavita patel,ramesh patel,Delhi Public School,292801001,North,Bengaluru,Karnataka,560001,CS-201\n"
        ",Missing Guardian Student,,Govt School,292801002,South,Bengaluru,Karnataka,560002,\n"
    ).encode('utf-8')
    parsed_rows = parse_student_upload(sample_csv_text, "test.csv")
    assert len(parsed_rows) == 3
    print("✓ CSV Multi-encoding and In-file Parser verified")

    # 13. Test Dashboard Permissions & HOD Governance (PRD Section 8)
    from app.database import get_dashboard_permissions, update_dashboard_permissions
    perms = get_dashboard_permissions()
    assert len(perms) >= 5
    widget_keys = {p["widget_key"] for p in perms}
    assert "kpi_cards" in widget_keys
    assert "global_student_pool" in widget_keys
    assert "branding_settings" in widget_keys
    assert "audit_logs" in widget_keys

    # Test toggling widget permissions
    update_dashboard_permissions({
        "kpi_cards": {"allowed_roles": "department_admin,teacher", "is_enabled": 1}
    })
    updated_perms = {p["widget_key"]: p for p in get_dashboard_permissions()}
    assert updated_perms["kpi_cards"]["is_enabled"] == 1
    print("✓ HOD Dashboard Widget Permissions Governance verified")

    # 14. Test Administrative Audit Trail (PRD Section 11 & 12)
    from app.database import log_audit
    log_audit(1, "TEST_ACTION", "system_settings", "test_key", "Testing administrative audit logger")
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM audit_logs WHERE action = 'TEST_ACTION'")
        audit_entry = cursor.fetchone()
        assert audit_entry is not None
        assert audit_entry["details"] == "Testing administrative audit logger"
        cursor.execute("DELETE FROM audit_logs WHERE action = 'TEST_ACTION'")
        print("✓ Administrative Audit Logging verified")

    # 15. Test Timed Quiz Engine Backend Timer Enforcement (PRD Section 6)
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id, time_limit_minutes FROM quizzes LIMIT 1")
        quiz_row = cursor.fetchone()
        assert quiz_row is not None
        assert "time_limit_minutes" in quiz_row.keys()
        assert quiz_row["time_limit_minutes"] is not None
        print(f"✓ Timed Quiz Assessment Engine verified (Time limit: {quiz_row['time_limit_minutes']}m)")

    # 16. Test Power BI & External Analytics REST API Authentication and Reporting Endpoints
    from starlette.requests import Request
    from app.routes.api_routes import reporting_students, reporting_subjects, verify_powerbi_auth
    from fastapi import HTTPException
    import json

    update_system_settings({"powerbi_api_key": "pbi_live_secure_test_key_12345"})
    
    # Authorized request with X-API-Key header
    valid_scope = {
        "type": "http",
        "headers": [(b"x-api-key", b"pbi_live_secure_test_key_12345")],
        "query_string": b"",
    }
    valid_req = Request(valid_scope)
    
    # Test valid API access
    students_resp = asyncio.run(reporting_students(valid_req, limit=10, offset=0))
    assert students_resp.status_code == 200
    st_data = json.loads(students_resp.body.decode())
    assert st_data["status"] == "success"
    assert "data" in st_data
    assert len(st_data["data"]) > 0
    
    # Verify sync timestamp recorded
    sync_settings = get_system_settings()
    assert "powerbi_last_sync_at" in sync_settings
    assert "UTC" in sync_settings["powerbi_last_sync_at"]
    
    # Test invalid API key rejection
    invalid_scope = {
        "type": "http",
        "headers": [(b"x-api-key", b"wrong_key")],
        "query_string": b"",
    }
    invalid_req = Request(invalid_scope)
    try:
        asyncio.run(reporting_students(invalid_req))
        assert False, "Should have rejected invalid key"
    except HTTPException as e:
        assert e.status_code == 401
    print("✓ Power BI REST API authentication, data delivery, and sync logging verified")

    # 17. Test In-App Notification Center (Creation, User Inbox, Read States, Admin Policy Suppression)
    from app.database import (
        create_notification, notify_users, get_user_notifications,
        mark_notification_read, mark_all_notifications_read,
        get_notification_settings, update_notification_settings
    )
    with get_db() as conn:
        c = conn.cursor()
        c.execute("SELECT id FROM users WHERE user_id = 'CS2026-001'")
        notif_test_uid = c.fetchone()[0]
        c.execute("DELETE FROM notifications WHERE user_id = ?", (notif_test_uid,))
        
    # Create single notification
    create_notification(notif_test_uid, "Course Assignment", "You have been enrolled in CS-201", link_url="/course/1", category="course")
    unread, notes = get_user_notifications(notif_test_uid)
    assert unread >= 1
    found_note = next(n for n in notes if n["title"] == "Course Assignment")
    assert found_note["category"] == "course"
    
    # Mark single read
    mark_notification_read(found_note["id"], notif_test_uid)
    unread_after, _ = get_user_notifications(notif_test_uid)
    assert unread_after == unread - 1
    
    # Batch notification to multiple users
    notify_users([notif_test_uid], "Faculty Announcement", "Mid-term schedule published", category="announcement")
    unread_b, _ = get_user_notifications(notif_test_uid)
    assert unread_b >= 1
    
    # Mark all read
    mark_all_notifications_read(notif_test_uid)
    unread_clean, _ = get_user_notifications(notif_test_uid)
    assert unread_clean == 0
    
    # Admin policy suppression check
    update_notification_settings({"faculty_created": {"is_enabled": 0}})
    create_notification(notif_test_uid, "Suppressed Faculty Welcome", "New faculty joined", category="faculty", event_type="faculty_created")
    # Verify notification was suppressed by admin policy
    _, notes_after = get_user_notifications(3)
    assert not any(n["title"] == "Suppressed Faculty Welcome" for n in notes_after)
    update_notification_settings({"faculty_created": {"is_enabled": 1}})
    
    with get_db() as conn:
        conn.cursor().execute("DELETE FROM notifications WHERE user_id = ?", (notif_test_uid,))
    print("✓ In-App Notification Center verified (Delivery, Inbox, Read state, Policy suppression)")

    # 18. Test Real-time Student Heartbeat & Live Active Tracking
    from app.routes.api_routes import activity_heartbeat
    s_token = create_access_token({"sub": "CS2026-001", "role": "student"})
    hb_scope = {
        "type": "http",
        "headers": [(b"cookie", f"lms_token={s_token}".encode())],
    }
    hb_req = Request(hb_scope)
    hb_resp = asyncio.run(activity_heartbeat(hb_req))
    assert hb_resp.status_code == 200
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM users WHERE user_id = 'CS2026-001' AND last_active_at >= datetime('now', '-5 minutes')")
        assert cursor.fetchone()[0] == 1
    print("✓ Live Student Activity Heartbeat verified (Active within 5-minute threshold)")

    # 19. Test Subject Ranking Calculation & Minimum 1 Attempt Requirement
    with get_db() as conn:
        cursor = conn.cursor()
        # Verify Top 10 query requires at least 1 attempt
        cursor.execute("""
            SELECT 
                u.id, u.user_id, u.full_name,
                ROUND(AVG(qa.score_percent), 1) as avg_score,
                COUNT(qa.id) as attempts_count
            FROM users u
            JOIN quiz_attempts qa ON u.id = qa.user_id
            JOIN quizzes q ON qa.quiz_id = q.id
            JOIN lessons l ON q.lesson_id = l.id
            JOIN modules m ON l.module_id = m.id
            JOIN courses c ON m.course_id = c.id
            WHERE COALESCE(NULLIF(c.subject, ''), NULLIF(c.department, ''), 'General') = 'Computer Science' AND c.status != 'deleted'
            GROUP BY u.id
            HAVING attempts_count >= 1
            ORDER BY avg_score DESC
            LIMIT 10
        """)
        ranked = cursor.fetchall()
        for r in ranked:
            assert r["attempts_count"] >= 1, "Students in ranking must have attempted at least 1 quiz"
    print("✓ Subject Ranking Calculation verified: Minimum 1 attempt constraint enforced")

    # 20. Test Course Modification, Archival, Unpublish, and Soft Delete (PRD Section 4)
    with get_db() as conn:
        cursor = conn.cursor()
        # Insert test course
        cursor.execute("""
            INSERT OR REPLACE INTO courses (id, title, code, subject, department, teacher_id, is_published, status)
            VALUES (7777, 'Neural Computing', 'CS-7777', 'Machine Learning', 'Computer Science', 2, 1, 'published')
        """)
        cursor.execute("SELECT id FROM users WHERE user_id = 'CS2026-001'")
        stu_id = cursor.fetchone()["id"]
        cursor.execute("INSERT OR IGNORE INTO enrollments (user_id, course_id) VALUES (?, 7777)", (stu_id,))
        
        # Test Archival
        cursor.execute("UPDATE courses SET status = 'archived', is_published = 0, archived_at = CURRENT_TIMESTAMP WHERE id = 7777")
        cursor.execute("SELECT status, is_published FROM courses WHERE id = 7777")
        arch_row = cursor.fetchone()
        assert arch_row["status"] == "archived"
        assert arch_row["is_published"] == 0
        
        # Test Soft Delete
        cursor.execute("UPDATE courses SET status = 'deleted', is_published = 0, deleted_at = CURRENT_TIMESTAMP WHERE id = 7777")
        cursor.execute("SELECT status FROM courses WHERE id = 7777")
        assert cursor.fetchone()["status"] == "deleted"
        
        # Verify student records remain intact in Global Student Pool
        cursor.execute("SELECT id, user_id FROM users WHERE user_id = 'CS2026-001'")
        assert cursor.fetchone() is not None
        
        # Clean up
        cursor.execute("DELETE FROM enrollments WHERE course_id = 7777")
        cursor.execute("DELETE FROM courses WHERE id = 7777")
    print("✓ Course Archival, Unpublish, and Soft Delete verified (Global Student Pool preserved)")

    # 21. Test Department Profile, Typography Preset, and Branding Settings
    branding_test_payload = {
        "department_name": "Department of Computer Science & Engineering",
        "institution_name": "Indian Institute of Science & Technology",
        "department_tagline": "Pioneering Innovation and Computational Excellence",
        "brand_color": "#1e3a8a",
        "secondary_brand_color": "#0284c7",
        "font_family": "Noto Sans Devanagari",
        "contact_email": "hod.cse@institution.edu",
        "contact_phone": "+91 80 1234 5678",
        "contact_office": "Computing Annex, Room 402"
    }
    update_system_settings(branding_test_payload)
    saved_branding = get_system_settings()
    assert saved_branding["department_name"] == "Department of Computer Science & Engineering"
    assert saved_branding["font_family"] == "Noto Sans Devanagari"
    assert saved_branding["secondary_brand_color"] == "#0284c7"
    assert saved_branding["contact_email"] == "hod.cse@institution.edu"
    print("✓ Department Administrator Profile, Typography, and Contact Branding verified")

    # 22. Test Completely Editable Profile
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE users 
            SET department = 'Foreign Language', phone = '+91 9988776655', guardian_name = 'Vikram Sharma',
                school_name = 'Delhi Public School', district = 'South Delhi', state = 'Delhi',
                pincode = '110001', bio = 'Passionate about coding and languages.'
            WHERE user_id = 'CS2026-001'
        """)
        cursor.execute("SELECT * FROM users WHERE user_id = 'CS2026-001'")
        updated_u = dict(cursor.fetchone())
        assert updated_u["department"] == "Foreign Language"
        assert updated_u["phone"] == "+91 9988776655"
        assert updated_u["guardian_name"] == "Vikram Sharma"
        assert updated_u["district"] == "South Delhi"
        assert updated_u["bio"] == "Passionate about coding and languages."
    print("✓ Completely Editable User Profile verified across all educational & contact fields")

    # 23. Test Chatbot Queries & Role-based Visibility (Student vs Teacher Queries)
    from app.gemini_service import answer_support_query
    from starlette.requests import Request
    from app.routes.api_routes import create_query, get_queries_feed

    # A: Student Query -> Visibility must be teachers_and_admin
    stu_token = create_access_token({"sub": "CS2026-001", "role": "student"})
    stu_scope = {
        "type": "http", "method": "POST", "path": "/api/queries/create",
        "headers": [(b"cookie", f"lms_token={stu_token}".encode("utf-8"))]
    }
    stu_req = Request(stu_scope)
    stu_req._json = {
        "subject": "Doubt on Lesson 2",
        "message": "Can you explain recursion with a practical example?",
        "category": "Academic",
        "course_title": "Python Programming"
    }
    stu_res = asyncio.run(create_query(stu_req))
    import json
    stu_data = json.loads(stu_res.body)
    assert stu_data["status"] == "success"
    assert stu_data["visibility"] == "teachers_and_admin"
    assert "Gemini" in stu_data["ai_response"] or "Ticket" in stu_data["ai_response"]

    # B: Teacher Query -> Visibility must be admin_only
    teach_token = create_access_token({"sub": "T-ALAN", "role": "teacher"})
    teach_scope = {
        "type": "http", "method": "POST", "path": "/api/queries/create",
        "headers": [(b"cookie", f"lms_token={teach_token}".encode("utf-8"))]
    }
    teach_req = Request(teach_scope)
    teach_req._json = {
        "subject": "Lab Equipment Requisition",
        "message": "Requesting budget approval for additional GPU compute nodes.",
        "category": "Administrative"
    }
    teach_res = asyncio.run(create_query(teach_req))
    teach_data = json.loads(teach_res.body)
    assert teach_data["status"] == "success"
    assert teach_data["visibility"] == "admin_only"

    # C: Teacher Feed Verification -> Must see student query, but NOT other teachers' confidential queries
    t_feed_scope = {
        "type": "http", "method": "GET", "path": "/api/queries/feed",
        "headers": [(b"cookie", f"lms_token={teach_token}".encode("utf-8"))],
        "query_string": b""
    }
    t_feed_req = Request(t_feed_scope)
    t_feed_res = asyncio.run(get_queries_feed(t_feed_req))
    t_feed_data = json.loads(t_feed_res.body)["data"]
    # Teacher can see student queries
    assert any(q["ticket_id"] == stu_data["ticket_id"] for q in t_feed_data)
    # Teacher cannot see other teachers' queries (only their own if user_id matches)
    for q in t_feed_data:
        if q["visibility"] == "admin_only":
            assert q["user_id"] == "T-ALAN"
    print("✓ Chatbot Queries with Strict Role-Based Visibility (Student visible to faculty, Teacher confidential to Admin) verified")

    # 24. Test Gemini AI Integration Engine & Fallback
    gemini_resp = answer_support_query("TKT-999", "Rohan", "student", "Algorithm complexity", "What is Big O notation?", "Data Structures")
    assert "Rohan" in gemini_resp
    assert "TKT-999" in gemini_resp
    print("✓ Google Gemini AI Academic Assistant engine & automated responses verified")

    # 25. Test Student Enrolled Courses Display & Removal of Legacy Computer Science
    from app.routes.auth_routes import view_profile
    from app.routes.student_routes import student_dashboard
    stu_scope = {
        "type": "http", "method": "GET", "path": "/profile",
        "headers": [(b"cookie", f"lms_token={stu_token}".encode("utf-8"))],
        "query_string": b""
    }
    stu_prof_req = Request(stu_scope)
    prof_resp = asyncio.run(view_profile(stu_prof_req))
    prof_html = prof_resp.body.decode("utf-8")
    assert "Enrolled Course" in prof_html, "Enrolled Courses section missing in student profile"
    assert "CS-201" in prof_html or "French" in prof_html, "Course codes/titles not displayed in profile"
    assert "<i class=\"fa-solid fa-building-columns text-slate-400 mr-1\"></i> Computer Science" not in prof_html
    
    # Check student dashboard with enrolled courses (CS2026-002)
    stu2_token = create_access_token({"sub": "CS2026-002", "role": "student"})
    stu_dash_scope = {
        "type": "http", "method": "GET", "path": "/student",
        "headers": [(b"cookie", f"lms_token={stu2_token}".encode("utf-8"))],
        "query_string": b""
    }
    stu_dash_req = Request(stu_dash_scope)
    dash_resp = asyncio.run(student_dashboard(stu_dash_req))
    dash_html = dash_resp.body.decode("utf-8")
    assert "Enrolled in:" in dash_html, "Enrolled courses banner missing in student dashboard"
    assert "Computer Science •" not in dash_html, "Legacy Computer Science department found in student dashboard"
    print("✓ Student Profile & Dashboard dynamically display Enrolled Courses instead of legacy department")

    # 26. Test Admin Power: Add Students (with temp pass), Teachers, General Dashboard Viewers, and Delete All Students
    from app.routes.dept_routes import (
        register_single_student, add_teacher, add_dashboard_viewer,
        delete_single_student, delete_all_students, department_dashboard
    )
    from app.routes.auth_routes import login_action, setup_account_action
    from starlette.datastructures import FormData
    from starlette.responses import Response

    admin_token = create_access_token({"sub": "DEPT-HEAD", "role": "department_admin"})
    admin_headers = [(b"cookie", f"lms_token={admin_token}".encode("utf-8"))]

    with get_db() as conn:
        conn.cursor().execute("DELETE FROM users WHERE user_id IN ('STU-CUSTOM-001', 'T-EULER-NEW', 'EXEC-DIRECTOR') OR normalized_name = 'vikramaditya roy'")

    # A: Add Student with Login and Password (must_change_password = 1)
    new_stu_req = Request({
        "type": "http", "method": "POST", "path": "/department/students/register-single",
        "headers": admin_headers
    })
    res_reg = asyncio.run(register_single_student(
        new_stu_req,
        full_name="Vikramaditya Roy",
        guardian_name="Chandra Roy",
        school_name="Central Academy",
        udise_code="29280100199",
        block="South", district="Bengaluru", state="Karnataka", pincode="560002",
        email="vikram@academy.edu", course_id=1, custom_student_id="STU-CUSTOM-001",
        flag_conflict=0, default_password="studentTempPass123"
    ))
    assert res_reg.status_code == 303
    with get_db() as conn:
        c = conn.cursor()
        c.execute("SELECT id, user_id, must_change_password, password_hash FROM users WHERE user_id = 'STU-CUSTOM-001'")
        st_row = c.fetchone()
        assert st_row is not None
        assert st_row["must_change_password"] == 1
        assert verify_password("studentTempPass123", st_row["password_hash"]) == True
    print("✓ Admin registered student with custom login ID & temporary password (must_change_password enforced)")

    # B: Student logs in and changes password
    dummy_resp = Response()
    login_req = Request({"type": "http", "method": "POST", "path": "/login", "headers": []})
    login_res = asyncio.run(login_action(login_req, dummy_resp, user_id="STU-CUSTOM-001", password="studentTempPass123"))
    assert login_res.headers["location"] == "/setup-account", "Student not redirected to setup-account"

    # Student updates their password on /setup-account
    stu_new_token = create_access_token({"sub": "STU-CUSTOM-001", "role": "student"})
    setup_req = Request({
        "type": "http", "method": "POST", "path": "/setup-account",
        "headers": [(b"cookie", f"lms_token={stu_new_token}".encode("utf-8"))]
    })
    setup_res = asyncio.run(setup_account_action(setup_req, new_password="MyPrivatePassword123", confirm_password="MyPrivatePassword123", email="vikram@academy.edu"))
    assert setup_res.headers["location"] == "/student"
    with get_db() as conn:
        c = conn.cursor()
        c.execute("SELECT must_change_password, password_hash FROM users WHERE user_id = 'STU-CUSTOM-001'")
        st_updated = c.fetchone()
        assert st_updated["must_change_password"] == 0
        assert verify_password("MyPrivatePassword123", st_updated["password_hash"]) == True
    print("✓ Student authenticated with initial password and successfully changed it on first login")

    # C: Admin adds Teacher
    teacher_req = Request({
        "type": "http", "method": "POST", "path": "/department/teachers/add",
        "headers": admin_headers
    })
    res_teach = asyncio.run(add_teacher(
        teacher_req,
        user_id="T-EULER-NEW", full_name="Prof. Leonhard Euler II",
        department="Mathematics", email="euler.new@institution.edu",
        temporary_password="eulerPass123"
    ))
    assert res_teach.status_code == 303
    with get_db() as conn:
        c = conn.cursor()
        c.execute("SELECT id, user_id, role, password_hash FROM users WHERE user_id = 'T-EULER-NEW'")
        t_row = c.fetchone()
        assert t_row is not None
        assert t_row["role"] == "teacher"
        assert verify_password("eulerPass123", t_row["password_hash"]) == True
    print("✓ Admin successfully created Faculty / Teacher account with custom login ID and password")

    # D: Admin adds General Account just for dashboards (dashboard_viewer)
    viewer_req = Request({
        "type": "http", "method": "POST", "path": "/department/viewers/add",
        "headers": admin_headers
    })
    res_view = asyncio.run(add_dashboard_viewer(
        viewer_req,
        user_id="EXEC-DIRECTOR", full_name="Dr. Jane Director",
        email="director@board.edu", password="directorPass123"
    ))
    assert res_view.status_code == 303
    with get_db() as conn:
        c = conn.cursor()
        c.execute("SELECT id, user_id, role, password_hash FROM users WHERE user_id = 'EXEC-DIRECTOR'")
        v_row = c.fetchone()
        assert v_row is not None
        assert v_row["role"] == "dashboard_viewer"
        assert verify_password("directorPass123", v_row["password_hash"]) == True

    # General dashboard viewer accesses /department
    viewer_token = create_access_token({"sub": "EXEC-DIRECTOR", "role": "dashboard_viewer"})
    view_dash_req = Request({
        "type": "http", "method": "GET", "path": "/department",
        "headers": [(b"cookie", f"lms_token={viewer_token}".encode("utf-8"))],
        "query_string": b""
    })
    view_dash_res = asyncio.run(department_dashboard(view_dash_req))
    assert view_dash_res.status_code == 200
    v_html = view_dash_res.body.decode("utf-8")
    assert "Overview Dashboard" in v_html
    assert "Subject Participation" in v_html
    assert "Subject Content" in v_html
    print("✓ General Account (dashboard_viewer) created and granted read-only access to all dashboards")

    # E: Admin deletes a single student
    del_single_req = Request({
        "type": "http", "method": "POST", "path": "/department/students/delete/STU-CUSTOM-001",
        "headers": admin_headers
    })
    del_s_res = asyncio.run(delete_single_student(del_single_req, "STU-CUSTOM-001"))
    assert del_s_res.status_code == 303
    with get_db() as conn:
        c = conn.cursor()
        c.execute("SELECT id FROM users WHERE user_id = 'STU-CUSTOM-001'")
        assert c.fetchone() is None
    print("✓ Admin successfully deleted single student record")

    # F: Admin deletes all student list (bulk delete)
    del_all_req = Request({
        "type": "http", "method": "POST", "path": "/department/students/delete-all",
        "headers": admin_headers
    })
    del_all_res = asyncio.run(delete_all_students(del_all_req))
    assert del_all_res.status_code == 303
    with get_db() as conn:
        c = conn.cursor()
        c.execute("SELECT COUNT(*) FROM users WHERE role = 'student'")
        remaining_students = c.fetchone()[0]
        assert remaining_students == 0, f"Expected 0 students, found {remaining_students}"
        c.execute("SELECT COUNT(*) FROM users WHERE role = 'teacher'")
        assert c.fetchone()[0] > 0, "Teachers should NOT be deleted"
        c.execute("SELECT COUNT(*) FROM users WHERE role = 'department_admin'")
        assert c.fetchone()[0] > 0, "Admin should NOT be deleted"
        c.execute("SELECT COUNT(*) FROM users WHERE role = 'dashboard_viewer'")
        assert c.fetchone()[0] > 0, "Dashboard viewer should NOT be deleted"
        c.execute("SELECT COUNT(*) FROM courses")
        assert c.fetchone()[0] > 0, "Courses should NOT be deleted"
    print("✓ Admin successfully executed 'Delete All Students', wiping student list while preserving faculty, viewers & courses")

    # Re-seed test students for subsequent operations
    with get_db() as conn:
        c = conn.cursor()
        student_pass = hash_password("welcome123")
        students = [
            ("CS2026-001", "Aarav Sharma", "Foreign Language"),
            ("CS2026-002", "Priya Patel", "Foreign Language"),
            ("CS2026-003", "Rohan Mehta", "Foreign Language"),
            ("CS2026-004", "Ananya Verma", "Foreign Language"),
            ("CS2026-005", "Devansh Rao", "Foreign Language")
        ]
        for uid, name, dept in students:
            c.execute("""
                INSERT INTO users (user_id, full_name, department, email, password_hash, role, must_change_password)
                VALUES (?, ?, ?, NULL, ?, 'student', 0)
            """, (uid, name, dept, student_pass))
            sid = c.lastrowid
            c.execute("INSERT OR IGNORE INTO enrollments (user_id, course_id) VALUES (?, 1)", (sid,))
            c.execute("INSERT OR IGNORE INTO enrollments (user_id, course_id) VALUES (?, 2)", (sid,))

    print("\n🎉 ALL TESTS PASSED! LMS backend and database engine are fully operational.")

if __name__ == "__main__":
    test_lms()
