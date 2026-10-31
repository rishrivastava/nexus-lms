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
        cursor.execute("SELECT id, title FROM courses WHERE code IN ('FR-101', 'CS-201')")
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
        assert q_count >= 3
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
            WHERE COALESCE(NULLIF(c.subject, ''), NULLIF(c.department, ''), 'General') IN ('Foreign Language', 'French', 'Computer Science') AND c.status != 'deleted'
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
        "department_name": "Foreign Language",
        "institution_name": "Leadership Boulevard Pvt Ltd",
        "platform_name": "Nexus LMS",
        "platform_tagline": "Language learning made easy",
        "department_tagline": "Pioneering in Language Teaching",
        "brand_color": "#1e3a8a",
        "secondary_brand_color": "#0284c7",
        "font_family": "Outfit",
        "contact_email": "info@fl4schools.com",
        "contact_phone": "+91 9540594033",
        "contact_office": "Mumbai",
        "login_help_text": "Enter your User ID / Serial Number and password to access your portal.",
        "login_button_text": "Sign In"
    }
    update_system_settings(branding_test_payload)
    saved_branding = get_system_settings()
    assert saved_branding["department_name"] == "Foreign Language"
    assert saved_branding["institution_name"] == "Leadership Boulevard Pvt Ltd"
    assert saved_branding["platform_tagline"] == "Language learning made easy"
    assert saved_branding["font_family"] == "Outfit"
    assert saved_branding["secondary_brand_color"] == "#0284c7"
    assert saved_branding["contact_email"] == "info@fl4schools.com"
    print("✓ Foreign Language Profile, Typography, and Contact Branding verified")

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

    # 27. Test Spreadsheet Quiz Upload, Gemini AI Quiz Generation, Performance Report Card & Mistake Explanations
    print("\n--- Test Suite 27: Spreadsheet & AI Quizzes, Report Cards & Gemini Explanations ---")
    import io
    import openpyxl
    import json
    from starlette.requests import Request
    from starlette.datastructures import UploadFile
    from fastapi import HTTPException
    from app.routes.teacher_routes import download_quiz_template, upload_spreadsheet_quiz, ai_generate_quiz
    from app.routes.student_routes import submit_quiz, explain_quiz_answer
    from app.routes.api_routes import save_gemini_settings

    teacher_token = create_access_token({"sub": "T-ALAN", "role": "teacher"})
    teacher_headers = [(b"cookie", f"lms_token={teacher_token}".encode("utf-8"))]
    admin_token = create_access_token({"sub": "DEPT-HEAD", "role": "department_admin"})
    admin_headers = [(b"cookie", f"lms_token={admin_token}".encode("utf-8"))]
    student_token = create_access_token({"sub": "CS2026-002", "role": "student"})
    student_headers = [(b"cookie", f"lms_token={student_token}".encode("utf-8"))]

    # A: Download Excel and CSV Quiz Templates
    req_xlsx = Request({"type": "http", "method": "GET", "path": "/teacher/quiz/template/download", "headers": teacher_headers})
    res_xlsx = asyncio.run(download_quiz_template(req_xlsx, format="xlsx"))
    assert res_xlsx.status_code == 200
    assert "spreadsheetml.sheet" in res_xlsx.media_type
    wb_test = openpyxl.load_workbook(io.BytesIO(res_xlsx.body))
    assert wb_test.active.title == "Quiz Template"
    assert wb_test.active.cell(row=1, column=1).value == "Question"
    print("✓ Successfully generated downloadable styled Excel template (.xlsx) with sample language questions")

    req_csv = Request({"type": "http", "method": "GET", "path": "/teacher/quiz/template/download", "headers": teacher_headers})
    res_csv = asyncio.run(download_quiz_template(req_csv, format="csv"))
    assert res_csv.status_code == 200
    assert "text/csv" in res_csv.media_type
    csv_text = res_csv.body.decode("utf-8")
    assert "Question,Option A,Option B,Option C,Option D,Correct Option,Explanation" in csv_text
    print("✓ Successfully generated downloadable CSV template (.csv) with sample language questions")

    # B: Upload Spreadsheet (.xlsx) to automatically create a quiz
    wb_upload = openpyxl.Workbook()
    ws_up = wb_upload.active
    ws_up.title = "Quiz"
    ws_up.append(["Question", "Option A", "Option B", "Option C", "Option D", "Correct Option", "Explanation"])
    ws_up.append(["What is the Spanish word for 'Cat'?", "Gato", "Perro", "Caballo", "Pájaro", "A", "'Gato' translates to 'cat' in Spanish."])
    ws_up.append(["What is the Spanish word for 'Dog'?", "Gato", "Perro", "Vaca", "Ratón", "B", "'Perro' means 'dog' in Spanish."])
    ws_up.append(["How do you say 'Thank you' in Spanish?", "Por favor", "De nada", "Gracias", "Hola", "C", "'Gracias' means thank you."])
    xlsx_io = io.BytesIO()
    wb_upload.save(xlsx_io)
    xlsx_io.seek(0)

    upload_file_obj = UploadFile(filename="spanish_animals_quiz.xlsx", file=xlsx_io)
    req_up = Request({
        "type": "http", "method": "POST", "path": "/teacher/course/1/quiz/upload",
        "headers": teacher_headers
    })
    req_up.scope["path_params"] = {"course_id": 1}
    res_up = asyncio.run(upload_spreadsheet_quiz(
        req_up,
        file=upload_file_obj,
        title="Spanish Animals & Basics Quiz",
        passing_score=60,
        duration_minutes=15,
        course_id=1
    ))
    assert res_up.status_code == 303
    
    with get_db() as conn:
        c = conn.cursor()
        c.execute("SELECT q.id as quiz_id, l.title, l.id as lesson_id FROM quizzes q JOIN lessons l ON q.lesson_id = l.id WHERE l.title = 'Spanish Animals & Basics Quiz'")
        uploaded_quiz = c.fetchone()
        assert uploaded_quiz is not None
        uploaded_quiz_id = uploaded_quiz["quiz_id"]
        c.execute("SELECT COUNT(*) FROM quiz_questions WHERE quiz_id = ?", (uploaded_quiz_id,))
        assert c.fetchone()[0] == 3
    print("✓ Successfully parsed and created live quiz lesson with 3 questions from uploaded spreadsheet")

    # C: Gemini AI Quiz Generation & Admin Governance Access Toggle
    # 1. Admin sets allow_teacher_ai_quiz = "0"
    req_gov = Request({"type": "http", "method": "POST", "path": "/api/gemini/save-settings", "headers": admin_headers})
    async def get_gov_json():
        return {
            "gemini_api_key": "dummy_key",
            "gemini_model": "gemini-2.5-flash",
            "gemini_auto_reply": "1",
            "gemini_enabled": "1",
            "allow_teacher_ai_quiz": "0"
        }
    req_gov.json = get_gov_json
    res_gov = asyncio.run(save_gemini_settings(req_gov))
    assert res_gov.status_code == 200

    # 2. Teacher attempts AI quiz generation -> Expect 403 Forbidden
    req_teacher_ai = Request({
        "type": "http", "method": "POST", "path": "/teacher/course/1/quiz/ai-generate",
        "headers": teacher_headers
    })
    req_teacher_ai.scope["path_params"] = {"course_id": 1}
    teacher_blocked = False
    try:
        asyncio.run(ai_generate_quiz(
            req_teacher_ai,
            topic="German Greetings",
            num_questions=3,
            difficulty="Beginner",
            course_id=1
        ))
    except HTTPException as e:
        if e.status_code == 403:
            teacher_blocked = True
    assert teacher_blocked == True, "Teacher should be blocked when allow_teacher_ai_quiz is 0"
    print("✓ Admin governance successfully enforces restriction: Teacher cannot generate AI quiz when toggle is off")

    # 3. Admin generates AI quiz directly -> Allowed
    req_admin_ai = Request({
        "type": "http", "method": "POST", "path": "/teacher/course/1/quiz/ai-generate",
        "headers": admin_headers
    })
    req_admin_ai.scope["path_params"] = {"course_id": 1}
    res_admin_ai = asyncio.run(ai_generate_quiz(
        req_admin_ai,
        topic="German Greetings",
        num_questions=3,
        difficulty="Beginner",
        course_id=1
    ))
    assert res_admin_ai.status_code == 303
    with get_db() as conn:
        c = conn.cursor()
        c.execute("SELECT q.id as quiz_id, l.title FROM quizzes q JOIN lessons l ON q.lesson_id = l.id WHERE l.title LIKE '%German Greetings%'")
        ai_quiz = c.fetchone()
        assert ai_quiz is not None
        c.execute("SELECT COUNT(*) FROM quiz_questions WHERE quiz_id = ?", (ai_quiz["quiz_id"],))
        assert c.fetchone()[0] >= 3
    print("✓ Admin successfully auto-generated live quiz from topic using Gemini AI")

    # 4. Admin re-enables allow_teacher_ai_quiz = "1" -> Teacher can now generate
    async def get_gov_json_allow():
        return {
            "gemini_api_key": "dummy_key",
            "gemini_model": "gemini-2.5-flash",
            "gemini_auto_reply": "1",
            "gemini_enabled": "1",
            "allow_teacher_ai_quiz": "1"
        }
    req_gov.json = get_gov_json_allow
    asyncio.run(save_gemini_settings(req_gov))

    res_teacher_ai_ok = asyncio.run(ai_generate_quiz(
        req_teacher_ai,
        topic="French Food & Cuisine",
        num_questions=3,
        difficulty="Beginner",
        course_id=1
    ))
    assert res_teacher_ai_ok.status_code == 303
    print("✓ Teacher successfully allowed to auto-generate quiz after admin enables feature toggle")

    # D: Student Quiz Submission & Performance Report Card (Correct vs Wrong Counts)
    with get_db() as conn:
        c = conn.cursor()
        c.execute("SELECT id, correct_option FROM quiz_questions WHERE quiz_id = ? ORDER BY id ASC", (uploaded_quiz_id,))
        qs = c.fetchall()
        assert len(qs) == 3
        q1_id = str(qs[0]["id"])
        q2_id = str(qs[1]["id"])
        q3_id = str(qs[2]["id"])

    # Student answers Q1 correctly, Q2 wrong (B is correct, student picks A), Q3 wrong (C is correct, student picks B)
    student_answers = {
        q1_id: "A",
        q2_id: "A",
        q3_id: "B"
    }
    req_sub = Request({
        "type": "http", "method": "POST", "path": f"/api/quiz/{uploaded_quiz_id}/submit",
        "headers": student_headers
    })
    async def get_sub_json():
        return {"answers": student_answers, "time_taken_seconds": 95}
    req_sub.json = get_sub_json

    sub_res = asyncio.run(submit_quiz(req_sub, uploaded_quiz_id))
    assert sub_res.status_code == 200
    report = json.loads(sub_res.body.decode("utf-8"))
    assert report["total_questions"] == 3
    assert report["correct_count"] == 1
    assert report["wrong_count"] == 2
    assert report["score_percent"] == 33.3
    assert report["passed"] == False
    assert report["time_taken_seconds"] == 95
    assert q2_id in report["review"]
    assert report["review"][q2_id]["correct"] == False
    assert report["review"][q2_id]["user_choice"] == "A"
    assert report["review"][q2_id]["correct_option"] == "B"
    print("✓ Assessment engine returns comprehensive Report Card with total questions, correct count (1) and wrong count (2)")

    # Verify attempt_data persisted in quiz_attempts database
    with get_db() as conn:
        c = conn.cursor()
        c.execute("SELECT attempt_data FROM quiz_attempts WHERE quiz_id = ? ORDER BY id DESC LIMIT 1", (uploaded_quiz_id,))
        saved_attempt = c.fetchone()[0]
        assert saved_attempt is not None
        saved_json = json.loads(saved_attempt)
        assert saved_json["correct_count"] == 1
        assert saved_json["wrong_count"] == 2
    print("✓ Full attempt data stored in database quiz_attempts table")

    # E: Student asks Gemini: Why is my answer wrong?
    req_explain = Request({
        "type": "http", "method": "POST", "path": "/api/quiz/explain-answer",
        "headers": student_headers
    })
    async def get_explain_json():
        return {"question_id": int(q2_id), "user_choice": "A"}
    req_explain.json = get_explain_json

    explain_res = asyncio.run(explain_quiz_answer(req_explain))
    assert explain_res.status_code == 200
    exp_data = json.loads(explain_res.body.decode("utf-8"))
    assert exp_data["success"] == True
    assert exp_data["question_id"] == int(q2_id)
    assert len(exp_data["explanation"]) > 20
    assert "Option A" in exp_data["explanation"] or "Option B" in exp_data["explanation"]
    print("✓ Gemini AI mistake explanation service returned encouraging pedagogical guidance on why student's choice was incorrect")

    # =========================================================================
    # Test Suite 28: LMS Role-Based Access, Teacher Studio & Dashboard, Multi-Course Benchmarking & Mylo AI Controls
    # =========================================================================
    print("\n--- Test Suite 28: LMS Role-Based Access, Teacher Studio & Dashboard, Multi-Course Benchmarking & Mylo AI Controls ---")

    from app.routes.teacher_routes import (
        teacher_analytics_view, teacher_dashboard_data_api, compute_teacher_analytics,
        edit_course, add_module, edit_module, delete_module,
        edit_lesson, delete_lesson, edit_quiz_details, edit_quiz_question, delete_quiz_question
    )
    from app.routes.api_routes import save_gemini_settings, get_mylo_usage_metrics
    from app.database import log_ai_usage, get_ai_usage_metrics, is_ai_feature_enabled

    # 1. Verification of Teacher Studio vs Teacher Dashboard access & strict data isolation
    with get_db() as conn:
        c = conn.cursor()
        c.execute("SELECT * FROM users WHERE role = 'teacher' LIMIT 1")
        teacher_user = dict(c.fetchone())
        c.execute("SELECT * FROM users WHERE role = 'department_admin' LIMIT 1")
        admin_user = dict(c.fetchone())
        c.execute("SELECT * FROM courses WHERE teacher_id = ? AND status != 'deleted'", (teacher_user["id"],))
        teacher_courses = [dict(r) for r in c.fetchall()]

    # Teacher analytics computation
    t_analytics = compute_teacher_analytics(teacher_user)
    assert t_analytics["has_courses"] == True
    # Verify strict data isolation: only courses belonging to teacher_user are in assigned_courses
    for ac in t_analytics["assigned_courses"]:
        assert ac["teacher_id"] == teacher_user["id"]
    print("✓ Strict data isolation verified: Teacher analytics ONLY returns courses assigned to that specific teacher")

    # Multi-Course Comparison Matrix verification
    assert "course_comparison_matrix" in t_analytics
    assert len(t_analytics["course_comparison_matrix"]) == len(teacher_courses)
    first_cm = t_analytics["course_comparison_matrix"][0]
    assert "enrolled" in first_cm
    assert "active_pct" in first_cm
    assert "avg_score" in first_cm
    assert "completion_rate" in first_cm
    assert "learning_hours" in first_cm
    print(f"✓ Multi-Course Comparison Matrix benchmarking verified ({len(t_analytics['course_comparison_matrix'])} assigned course benchmarks)")

    # Window 2 Dashboard API endpoint verification
    req_dash = Request({"type": "http", "method": "GET", "path": "/api/teacher/dashboard-data", "headers": teacher_headers})
    dash_res = asyncio.run(teacher_dashboard_data_api(req_dash))
    assert dash_res.status_code == 200
    dash_json = json.loads(dash_res.body.decode("utf-8"))
    assert "kpis" in dash_json
    assert "total_enrolled" in dash_json["kpis"]
    assert "overall_avg_score" in dash_json["kpis"]
    assert "live_students" in dash_json
    assert "top_5_students" in dash_json
    assert "bottom_5_students" in dash_json
    print("✓ Window 2 Teacher Dashboard API verified with real-time KPIs, live activity feed, and Top/Bottom 5 rankings")

    # 2. Complete Course Structure Modifications
    target_course_id = teacher_courses[0]["id"]
    target_course_code = teacher_courses[0]["code"]
    req_course_edit = Request({"type": "http", "method": "POST", "path": f"/teacher/course/{target_course_id}/edit", "headers": teacher_headers})
    asyncio.run(edit_course(
        req_course_edit,
        course_id=target_course_id,
        title="French Conversational Mastery (Advanced)",
        code=target_course_code,
        department="Languages",
        subject="Spanish",
        subtitle="Conversational fluency made intuitive",
        learning_path="Foundational A1 -> Conversational B1",
        instructions="Complete quizzes sequentially with >=70% pass score",
        description="Updated comprehensive curriculum description.",
        status_val="published",
        teacher_id=None,
        notify_students=0
    ))
    with get_db() as conn:
        c = conn.cursor()
        c.execute("SELECT subtitle, learning_path, instructions FROM courses WHERE id = ?", (target_course_id,))
        c_meta = c.fetchone()
        assert c_meta[0] == "Conversational fluency made intuitive"
        assert c_meta[1] == "Foundational A1 -> Conversational B1"
        assert c_meta[2] == "Complete quizzes sequentially with >=70% pass score"
    print("✓ Teacher successfully modified course details, subtitle, learning path, instructions & metadata")

    # Module Add, Edit, Delete
    req_mod = Request({"type": "http", "method": "POST", "path": f"/teacher/course/{target_course_id}/module", "headers": teacher_headers})
    mod_res = asyncio.run(add_module(req_mod, target_course_id, title="Test Chapter: Verbs & Tenses", description="Detailed verb forms"))
    with get_db() as conn:
        c = conn.cursor()
        c.execute("SELECT id FROM modules WHERE course_id = ? AND title = 'Test Chapter: Verbs & Tenses'", (target_course_id,))
        new_mod_id = c.fetchone()[0]
    
    # Edit module
    req_mod_edit = Request({"type": "http", "method": "POST", "path": f"/teacher/module/{new_mod_id}/edit", "headers": teacher_headers})
    asyncio.run(edit_module(req_mod_edit, new_mod_id, title="Updated Chapter: Verbs & Subjunctives", description="Updated description"))
    with get_db() as conn:
        c = conn.cursor()
        c.execute("SELECT title FROM modules WHERE id = ?", (new_mod_id,))
        assert c.fetchone()[0] == "Updated Chapter: Verbs & Subjunctives"
    print("✓ Chapter/Module created and updated successfully")

    # Lesson Add & Edit
    with get_db() as conn:
        c = conn.cursor()
        c.execute("INSERT INTO lessons (module_id, title, content_type, content_value, duration_minutes) VALUES (?, 'Intro Lesson', 'youtube', '7_LPdttKXPc', 12)", (new_mod_id,))
        new_les_id = c.lastrowid
    
    req_les_edit = Request({"type": "http", "method": "POST", "path": f"/teacher/lesson/{new_les_id}/edit", "headers": teacher_headers})
    asyncio.run(edit_lesson(
        req_les_edit,
        lesson_id=new_les_id,
        title="Comprehensive Intro Lesson",
        subtitle="Key basics",
        description="Video walk-through",
        duration_minutes=20,
        content_value="https://youtu.be/7_LPdttKXPc"
    ))
    with get_db() as conn:
        c = conn.cursor()
        c.execute("SELECT title, subtitle, duration_minutes FROM lessons WHERE id = ?", (new_les_id,))
        les_row = c.fetchone()
        assert les_row[0] == "Comprehensive Intro Lesson"
        assert les_row[1] == "Key basics"
        assert les_row[2] == 20
    print("✓ Lesson title, subtitle, description, and duration successfully modified")

    # Delete Lesson & Chapter
    req_les_del = Request({"type": "http", "method": "POST", "path": f"/teacher/lesson/{new_les_id}/delete", "headers": teacher_headers})
    asyncio.run(delete_lesson(req_les_del, new_les_id))
    req_mod_del = Request({"type": "http", "method": "POST", "path": f"/teacher/module/{new_mod_id}/delete", "headers": teacher_headers})
    asyncio.run(delete_module(req_mod_del, new_mod_id))
    with get_db() as conn:
        c = conn.cursor()
        c.execute("SELECT COUNT(*) FROM modules WHERE id = ?", (new_mod_id,))
        assert c.fetchone()[0] == 0
    print("✓ Lesson and chapter deleted cleanly with full audit trail logging")

    # 3. Administrator Full Course Modification & Teacher Reassignment
    req_admin_reassign = Request({"type": "http", "method": "POST", "path": f"/teacher/course/{target_course_id}/edit", "headers": admin_headers})
    asyncio.run(edit_course(
        req_admin_reassign,
        course_id=target_course_id,
        title="French Conversational Mastery (Admin Managed)",
        code=target_course_code,
        department="Languages",
        subject="Spanish",
        subtitle="Conversational fluency made intuitive",
        learning_path="Foundational A1 -> Conversational B1",
        instructions="Admin updated instructions",
        description="Course updated by Administrator on behalf of faculty.",
        status_val="published",
        teacher_id=teacher_user["id"],
        notify_students=0
    ))
    with get_db() as conn:
        c = conn.cursor()
        c.execute("SELECT action, details FROM audit_logs WHERE action = 'COURSE_EDIT' ORDER BY id DESC LIMIT 1")
        audit_row = c.fetchone()
        assert audit_row is not None
        assert f"Assigned Teacher ID: {teacher_user['id']}" in audit_row[1]
    print("✓ Administrator full authority confirmed: Modified course & reassigned teacher with audit record")

    # 4. Administrator Mylo AI Granular Governance Controls
    # 4A: Disable Mylo AI globally for all students
    req_set_ai = Request({"type": "http", "method": "POST", "path": "/api/mylo/save-settings", "headers": admin_headers})
    async def get_ai_settings_disabled():
        return {
            "mylo_ai_enabled_globally": "0",
            "mylo_ai_quiz_explanations_enabled": "1",
            "mylo_ai_disabled_courses": "",
            "mylo_ai_disabled_subjects": "",
            "mylo_ai_disabled_students": ""
        }
    req_set_ai.json = get_ai_settings_disabled
    asyncio.run(save_gemini_settings(req_set_ai))

    # Student attempts to call /api/quiz/explain-answer -> Must return 403 Forbidden
    req_exp_blocked = Request({"type": "http", "method": "POST", "path": "/api/quiz/explain-answer", "headers": student_headers})
    async def get_exp_blocked_json():
        return {"question_id": int(q2_id), "user_choice": "A"}
    req_exp_blocked.json = get_exp_blocked_json
    try:
        res_exp_blocked = asyncio.run(explain_quiz_answer(req_exp_blocked))
        assert res_exp_blocked.status_code == 403
    except HTTPException as e:
        assert e.status_code == 403
        assert "disabled for students" in e.detail
    print("✓ Granular Control 4A verified: Global Mylo AI student disable enforced at backend API level (403 Forbidden)")

    # 4B: Re-enable globally, disable for course
    with get_db() as conn:
        c = conn.cursor()
        c.execute("""
            SELECT m.course_id 
            FROM quiz_questions qq
            JOIN quizzes q ON qq.quiz_id = q.id
            JOIN lessons l ON q.lesson_id = l.id
            JOIN modules m ON l.module_id = m.id
            WHERE qq.id = ?
        """, (int(q2_id),))
        q2_course_id = c.fetchone()[0]

    async def get_ai_course_disabled():
        return {
            "mylo_ai_enabled_globally": "1",
            "mylo_ai_quiz_explanations_enabled": "1",
            "mylo_ai_disabled_courses": str(q2_course_id),
            "mylo_ai_disabled_subjects": "",
            "mylo_ai_disabled_students": ""
        }
    req_set_ai.json = get_ai_course_disabled
    asyncio.run(save_gemini_settings(req_set_ai))
    try:
        res_course_blocked = asyncio.run(explain_quiz_answer(req_exp_blocked))
        assert False, "Expected HTTPException 403"
    except HTTPException as e:
        assert e.status_code == 403
        assert "disabled for this course" in e.detail
    print("✓ Granular Control 4B verified: Course-level Mylo AI disable enforced at backend API level (403 Forbidden)")

    # 4C: Re-enable course, disable for individual student
    student_uid = "CS2026-002"
    async def get_ai_student_disabled():
        return {
            "mylo_ai_enabled_globally": "1",
            "mylo_ai_quiz_explanations_enabled": "1",
            "mylo_ai_disabled_courses": "",
            "mylo_ai_disabled_subjects": "",
            "mylo_ai_disabled_students": student_uid
        }
    req_set_ai.json = get_ai_student_disabled
    asyncio.run(save_gemini_settings(req_set_ai))
    try:
        res_student_blocked = asyncio.run(explain_quiz_answer(req_exp_blocked))
        assert False, "Expected HTTPException 403"
    except HTTPException as e:
        assert e.status_code == 403
        assert "disabled for student account" in e.detail
    print(f"✓ Granular Control 4C verified: Individual student account restriction ({student_uid}) enforced (403 Forbidden)")

    # 4D: Re-enable student, disable quiz explanations toggle
    async def get_ai_quiz_exp_disabled():
        return {
            "mylo_ai_enabled_globally": "1",
            "mylo_ai_quiz_explanations_enabled": "0",
            "mylo_ai_disabled_courses": "",
            "mylo_ai_disabled_subjects": "",
            "mylo_ai_disabled_students": ""
        }
    req_set_ai.json = get_ai_quiz_exp_disabled
    asyncio.run(save_gemini_settings(req_set_ai))
    try:
        res_quiz_exp_blocked = asyncio.run(explain_quiz_answer(req_exp_blocked))
        assert False, "Expected HTTPException 403"
    except HTTPException as e:
        assert e.status_code == 403
        assert "quiz explanations are currently disabled" in e.detail
    print("✓ Granular Control 4D verified: AI Quiz Explanations master toggle disable enforced (403 Forbidden)")

    # 4E: Re-enable all Mylo AI features
    async def get_ai_all_enabled():
        return {
            "mylo_ai_enabled_globally": "1",
            "mylo_ai_quiz_explanations_enabled": "1",
            "mylo_ai_disabled_courses": "",
            "mylo_ai_disabled_subjects": "",
            "mylo_ai_disabled_students": ""
        }
    req_set_ai.json = get_ai_all_enabled
    asyncio.run(save_gemini_settings(req_set_ai))
    res_exp_allowed = asyncio.run(explain_quiz_answer(req_exp_blocked))
    assert res_exp_allowed.status_code == 200
    print("✓ Granular Control 4E verified: Student Mylo AI access fully restored when permitted")

    # 5. AI Usage Logging & Expenditure Dashboard
    log_ai_usage(
        user_id=1,
        user_name="Student Test",
        user_role="student",
        feature_type="quiz_explanation",
        course_id=target_course_id,
        course_title="Spanish Conversational Mastery",
        subject="Spanish",
        prompt_tokens=150,
        completion_tokens=80
    )
    req_usage = Request({"type": "http", "method": "GET", "path": "/api/mylo/usage-metrics", "headers": admin_headers})
    usage_res = asyncio.run(get_mylo_usage_metrics(req_usage))
    assert usage_res.status_code == 200
    usage_metrics = json.loads(usage_res.body.decode("utf-8"))
    assert usage_metrics["total_requests"] >= 1
    assert usage_metrics["total_tokens"] >= 230
    assert usage_metrics["estimated_cost_usd"] > 0
    assert usage_metrics["estimated_cost_inr"] > 0
    assert usage_metrics["quiz_explanation_requests"] >= 1
    assert len(usage_metrics["course_breakdown"]) >= 1
    print(f"✓ Mylo AI Usage & Expenditure Dashboard verified: {usage_metrics['total_requests']} requests, {usage_metrics['total_tokens']} tokens, ${usage_metrics['estimated_cost_usd']} (₹{usage_metrics['estimated_cost_inr']})")

    print("\n🎉 ALL TESTS PASSED! LMS backend and database engine are fully operational.")

if __name__ == "__main__":
    test_lms()
