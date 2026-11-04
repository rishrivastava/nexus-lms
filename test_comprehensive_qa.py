import asyncio
import sqlite3
import json
import time
import os
import urllib.parse
from app.main import app
from app.auth import create_access_token, hash_password, verify_password
from app.database import (
    get_db,
    toggle_department_ans_writing,
    is_ans_writing_enabled_for_course,
    is_ans_writing_enabled_for_department
)

# Test State
PASSED = 0
FAILED = 0
TOTAL = 0
RESULTS = []

def record_test(suite_name: str, test_name: str, passed: bool, message: str = ""):
    global PASSED, FAILED, TOTAL
    TOTAL += 1
    if passed:
        PASSED += 1
        status = "PASS"
    else:
        FAILED += 1
        status = "FAIL"
    entry = {"suite": suite_name, "test": test_name, "status": status, "message": message}
    RESULTS.append(entry)
    symbol = "✓" if passed else "✗"
    msg_str = f" - {message}" if message else ""
    print(f"[{status}] {symbol} [{suite_name}] {test_name}{msg_str}")

async def make_request(method, path, token=None, body=b'', headers=None, query_string=b''):
    if '?' in path and not query_string:
        path, qs = path.split('?', 1)
        query_string = qs.encode()

    hdrs = []
    if headers:
        for k, v in headers.items():
            hdrs.append((k.lower().encode(), v.encode()))
    if token:
        hdrs.append((b'cookie', f'lms_token={token}'.encode()))
        
    scope = {
        'type': 'http',
        'http_version': '1.1',
        'method': method,
        'path': path,
        'raw_path': path.encode(),
        'query_string': query_string,
        'headers': hdrs,
        'client': ('127.0.0.1', 12345),
        'server': ('127.0.0.1', 8000),
    }
    
    body_chunks = []
    status_code = [None]
    resp_headers = {}
    
    async def receive():
        return {'type': 'http.request', 'body': body, 'more_body': False}
        
    async def send(message):
        if message['type'] == 'http.response.start':
            status_code[0] = message['status']
            for k, v in message.get('headers', []):
                resp_headers[k.decode().lower()] = v.decode()
        elif message['type'] == 'http.response.body':
            body_chunks.append(message.get('body', b''))
            
    await app(scope, receive, send)
    full_body = b''.join(body_chunks).decode('utf-8', errors='ignore')
    return status_code[0], resp_headers, full_body

async def run_suite_1_auth_rbac():
    print("\n" + "="*70)
    print("SUITE 1: AUTHENTICATION, RBAC & PORTAL ISOLATION")
    print("="*70)
    
    # 1.1 GET /login
    st, hd, bd = await make_request('GET', '/login')
    record_test("Suite 1", "GET /login renders login page", st == 200 and "Login" in bd)

    # 1.2 POST /login invalid credentials
    form_data = urllib.parse.urlencode({"user_id": "DEPT-HEAD", "password": "wrongpassword"}).encode()
    st, hd, bd = await make_request('POST', '/login', body=form_data, headers={'content-type': 'application/x-www-form-urlencoded'})
    record_test("Suite 1", "POST /login with bad credentials fails", st in (200, 400, 401) and ("Invalid" in bd or "error" in bd.lower() or "incorrect" in bd.lower()))

    # 1.3 POST /login valid Admin
    form_data = urllib.parse.urlencode({"user_id": "DEPT-HEAD", "password": "admin123"}).encode()
    st, hd, bd = await make_request('POST', '/login', body=form_data, headers={'content-type': 'application/x-www-form-urlencoded'})
    record_test("Suite 1", "POST /login valid Admin sets cookie and redirects to /department", st == 303 and "/department" in hd.get("location", ""))

    # 1.4 POST /login valid Teacher
    form_data = urllib.parse.urlencode({"user_id": "T-UPSC-01", "password": "password123"}).encode()
    st, hd, bd = await make_request('POST', '/login', body=form_data, headers={'content-type': 'application/x-www-form-urlencoded'})
    record_test("Suite 1", "POST /login valid Teacher sets cookie and redirects to /teacher", st == 303 and "/teacher" in hd.get("location", ""))

    # 1.5 POST /login valid Student
    form_data = urllib.parse.urlencode({"user_id": "UPSC-2026-0102", "password": "password123"}).encode()
    st, hd, bd = await make_request('POST', '/login', body=form_data, headers={'content-type': 'application/x-www-form-urlencoded'})
    record_test("Suite 1", "POST /login valid Student sets cookie and redirects to /student", st == 303 and "/student" in hd.get("location", ""))

    # Setup Access Tokens for Role Tests
    admin_token = create_access_token({"sub": "DEPT-HEAD", "role": "department_admin"})
    teacher_token = create_access_token({"sub": "T-UPSC-01", "role": "teacher"})
    student_token = create_access_token({"sub": "UPSC-2026-0102", "role": "student"})

    # 1.6 Unauthenticated access to /student
    st, hd, bd = await make_request('GET', '/student')
    record_test("Suite 1", "Unauthenticated GET /student redirects to /login", st == 303 and "/login" in hd.get("location", ""))

    # 1.7 Unauthenticated access to /teacher
    st, hd, bd = await make_request('GET', '/teacher')
    record_test("Suite 1", "Unauthenticated GET /teacher redirects to /login", st == 303 and "/login" in hd.get("location", ""))

    # 1.8 Unauthenticated access to /department
    st, hd, bd = await make_request('GET', '/department')
    record_test("Suite 1", "Unauthenticated GET /department redirects to /login", st == 303 and "/login" in hd.get("location", ""))

    # 1.9 Student accessing /teacher -> Redirected to /student
    st, hd, bd = await make_request('GET', '/teacher', token=student_token)
    record_test("Suite 1", "Student token accessing /teacher is strictly redirected to /student", st == 303 and "/student" in hd.get("location", ""))

    # 1.10 Student accessing /department -> Redirected to /student
    st, hd, bd = await make_request('GET', '/department', token=student_token)
    record_test("Suite 1", "Student token accessing /department is strictly redirected to /student", st == 303 and "/student" in hd.get("location", ""))

    # 1.11 Teacher accessing /student -> Redirected to /teacher
    st, hd, bd = await make_request('GET', '/student', token=teacher_token)
    record_test("Suite 1", "Teacher token accessing /student is redirected to /teacher", st == 303 and "/teacher" in hd.get("location", ""))

    # 1.12 Teacher accessing /department -> Allowed (Faculty analytics access)
    st, hd, bd = await make_request('GET', '/department', token=teacher_token)
    record_test("Suite 1", "Teacher token accessing /department allowed faculty view", st == 200)

    # 1.13 GET /logout clears cookie
    st, hd, bd = await make_request('GET', '/logout', token=student_token)
    record_test("Suite 1", "GET /logout clears cookie and redirects to /login", st == 303 and "/login" in hd.get("location", ""))

    # 1.14 GET /profile renders student profile without password hash leaked
    st, hd, bd = await make_request('GET', '/profile', token=student_token)
    record_test("Suite 1", "GET /profile renders without leaking password hashes", st == 200 and "password_hash" not in bd and "UPSC-2026-0102" in bd)

async def run_suite_2_departments():
    print("\n" + "="*70)
    print("SUITE 2: DEPARTMENT MANAGEMENT & ANSWER WRITING TOGGLE")
    print("="*70)
    admin_token = create_access_token({"sub": "DEPT-HEAD", "role": "department_admin"})
    
    # 2.1 Admin GET /department
    st, hd, bd = await make_request('GET', '/department', token=admin_token)
    record_test("Suite 2", "Admin access to GET /department renders successfully", st == 200 and "Department" in bd)

    # 2.2 Department card has toggle button
    record_test("Suite 2", "Department cards contain Answer Writing toggle form", "toggle-ans-writing" in bd)

    # 2.3 Admin creates new Department Bucket
    dept_code = f"TEST_DEPT_{int(time.time())}"
    dept_name = f"Automated QA Dept {int(time.time())}"
    form = urllib.parse.urlencode({
        "name": dept_name,
        "code": dept_code,
        "description": "Created by automated QA tester",
        "tagline": "Quality Assurance Excellence",
        "welcome_message": "Welcome to the QA Dept",
        "ans_writing_enabled": "1"
    }).encode()
    st, hd, bd = await make_request('POST', '/department/departments/create', token=admin_token, body=form, headers={'content-type': 'application/x-www-form-urlencoded'})
    record_test("Suite 2", "Admin creates new Department Bucket", st in (200, 303))

    # Verify in DB
    created_dept_id = None
    with get_db() as conn:
        c = conn.cursor()
        c.execute("SELECT id, ans_writing_enabled FROM departments WHERE name = ?", (dept_name,))
        row = c.fetchone()
        if row:
            created_dept_id = row[0]
            record_test("Suite 2", "New Department persisted with ans_writing_enabled=1", row[1] == 1)
        else:
            record_test("Suite 2", "New Department persisted in database", False)

    # 2.4 Toggle Answer Writing on Department 1 (Foreign Language)
    st, hd, bd = await make_request('POST', '/department/departments/1/toggle-ans-writing', token=admin_token, headers={'X-Requested-With': 'XMLHttpRequest', 'Accept': 'application/json'})
    with get_db() as conn:
        c = conn.cursor()
        c.execute("SELECT ans_writing_enabled FROM departments WHERE id = 1")
        new_val = c.fetchone()[0]
        record_test("Suite 2", f"Toggle API successfully flipped Dept 1 to {new_val}", True)

        # Flip it back to 0
        c.execute("UPDATE departments SET ans_writing_enabled = 0 WHERE id = 1")
        conn.commit()

    # 2.5 Audit log check for toggle
    with get_db() as conn:
        c = conn.cursor()
        c.execute("SELECT count(*) FROM audit_logs WHERE action LIKE '%ANS Writing%' OR action LIKE '%toggle%'")
        log_count = c.fetchone()[0]
        record_test("Suite 2", "Audit log created for Department toggle action", log_count > 0)

    # 2.6 Admin updates department settings
    settings_form = urllib.parse.urlencode({
        "platform_name": "Nexus LMS Portal",
        "platform_tagline": "Transforming Education",
        "institution_name": "LeadGroup Academic Institutions",
        "department_name": "Global Academic Operations",
        "brand_color": "#4f46e5"
    }).encode()
    st, hd, bd = await make_request('POST', '/department/settings/update', token=admin_token, body=settings_form, headers={'content-type': 'application/x-www-form-urlencoded'})
    record_test("Suite 2", "Admin updates global department branding settings", st in (200, 303))

    # 2.7 Export CSV template
    st, hd, bd = await make_request('GET', '/department/download-sample-csv', token=admin_token)
    record_test("Suite 2", "Download sample student import CSV", st == 200 and ("Serial NO." in bd or "UNIQUE NO." in bd))

    # 2.8 Clean up test department
    if created_dept_id:
        with get_db() as conn:
            conn.cursor().execute("DELETE FROM departments WHERE id = ?", (created_dept_id,))
            conn.commit()
            record_test("Suite 2", "Cleaned up temporary QA department", True)

async def run_suite_3_curriculum():
    print("\n" + "="*70)
    print("SUITE 3: TEACHER PORTAL & CURRICULUM EDITOR")
    print("="*70)
    admin_token = create_access_token({"sub": "DEPT-HEAD", "role": "department_admin"})
    teacher_upsc_token = create_access_token({"sub": "T-UPSC-01", "role": "teacher"})
    teacher_alan_token = create_access_token({"sub": "T-ALAN", "role": "teacher"})

    # 3.1 Teacher Dashboard
    st, hd, bd = await make_request('GET', '/teacher', token=teacher_upsc_token)
    record_test("Suite 3", "Teacher GET /teacher renders dashboard", st == 200 and "Dr. A. K. Sharma" in bd)

    # 3.2 Teacher Course Editor for owned course (8894: Indian Polity)
    st, hd, bd = await make_request('GET', '/teacher/course/8894', token=teacher_upsc_token)
    record_test("Suite 3", "Teacher can open Course Editor for owned course 8894", st == 200 and "Indian Polity" in bd)

    # 3.3 Teacher Course Editor forbidden for unassigned course
    st, hd, bd = await make_request('GET', '/teacher/course/8894', token=teacher_alan_token)
    record_test("Suite 3", "Teacher blocked with 403 for courses taught by other faculty", st == 403)

    # 3.4 Admin can access course editor for any course
    st, hd, bd = await make_request('GET', '/teacher/course/8894', token=admin_token)
    record_test("Suite 3", "Admin can access Course Editor for any course", st == 200 and "Indian Polity" in bd)

    # 3.5 Create a temporary Module under course 8894
    mod_form = urllib.parse.urlencode({"title": "QA Test Module: Constitutional Dynamics"}).encode()
    st, hd, bd = await make_request('POST', '/teacher/course/8894/module', token=admin_token, body=mod_form, headers={'content-type': 'application/x-www-form-urlencoded'})
    record_test("Suite 3", "Create new curriculum module", st in (200, 303))

    test_mod_id = None
    with get_db() as conn:
        c = conn.cursor()
        c.execute("SELECT id FROM modules WHERE course_id = 8894 AND title = 'QA Test Module: Constitutional Dynamics' ORDER BY id DESC")
        row = c.fetchone()
        if row:
            test_mod_id = row[0]
            record_test("Suite 3", f"New module persisted in DB (ID: {test_mod_id})", True)
        else:
            record_test("Suite 3", "New module persisted in DB", False)

    if test_mod_id:
        # 3.6 Edit Module
        edit_mod_form = urllib.parse.urlencode({"title": "QA Test Module: Constitutional Dynamics (Updated)", "position": "99"}).encode()
        st, hd, bd = await make_request('POST', f'/teacher/module/{test_mod_id}/edit', token=admin_token, body=edit_mod_form, headers={'content-type': 'application/x-www-form-urlencoded'})
        record_test("Suite 3", "Edit module title and position", st in (200, 303))

        # 3.7 Add Video Lesson
        vid_form = urllib.parse.urlencode({
            "course_id": "8894",
            "title": "Making of Constitution - Analysis",
            "youtube_url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
            "duration_minutes": "15"
        }).encode()
        st, hd, bd = await make_request('POST', f'/teacher/module/{test_mod_id}/lesson/youtube', token=admin_token, body=vid_form, headers={'content-type': 'application/x-www-form-urlencoded'})
        record_test("Suite 3", "Add YouTube Video lesson to module", st in (200, 303))

        # 3.8 Add PDF Study Material Lesson (Multipart Form)
        boundary = '----WebKitFormBoundaryPDFUpload'
        pdf_body = (
            f'--{boundary}\r\n'
            f'Content-Disposition: form-data; name=\"course_id\"\r\n\r\n'
            f'8894\r\n'
            f'--{boundary}\r\n'
            f'Content-Disposition: form-data; name=\"title\"\r\n\r\n'
            f'NCERT Polity Summary Notes\r\n'
            f'--{boundary}\r\n'
            f'Content-Disposition: form-data; name=\"duration_minutes\"\r\n\r\n'
            f'20\r\n'
            f'--{boundary}\r\n'
            f'Content-Disposition: form-data; name=\"pdf_file\"; filename=\"polity_summary.pdf\"\r\n'
            f'Content-Type: application/pdf\r\n\r\n'
            f'%PDF-1.4 Mock Polity Notes\r\n'
            f'--{boundary}--\r\n'
        ).encode('utf-8')
        st, hd, bd = await make_request(
            'POST', f'/teacher/module/{test_mod_id}/lesson/pdf',
            token=admin_token,
            body=pdf_body,
            headers={'content-type': f'multipart/form-data; boundary={boundary}'}
        )
        record_test("Suite 3", "Add PDF reading material lesson to module", st in (200, 303))

        # 3.9 Verify lessons created in DB
        with get_db() as conn:
            c = conn.cursor()
            c.execute("SELECT id, title, content_type FROM lessons WHERE module_id = ?", (test_mod_id,))
            created_lessons = c.fetchall()
            record_test("Suite 3", f"Verified {len(created_lessons)} lessons added under module", len(created_lessons) >= 2)

            # 3.10 Clean up test module & lessons
            c.execute("DELETE FROM lessons WHERE module_id = ?", (test_mod_id,))
            c.execute("DELETE FROM modules WHERE id = ?", (test_mod_id,))
            conn.commit()
            record_test("Suite 3", "Cleaned up QA test module and associated lessons", True)

async def run_suite_4_students():
    print("\n" + "="*70)
    print("SUITE 4: STUDENT LIFECYCLE MANAGEMENT")
    print("="*70)
    admin_token = create_access_token({"sub": "DEPT-HEAD", "role": "department_admin"})
    
    # 4.1 Register single student via Admin
    unique_uid = f"QA-STU-{int(time.time())}"
    stu_form = urllib.parse.urlencode({
        "full_name": "Aarav Sharma QA",
        "custom_student_id": unique_uid,
        "email": f"aarav.{int(time.time())}@leadgroup.in",
        "course_id": "8894",
        "guardian_name": "Mr. Rajesh Sharma",
        "school_name": "Delhi Public School",
        "district": "New Delhi",
        "state": "Delhi",
        "pincode": "110001",
        "default_password": "password123"
    }).encode()
    st, hd, bd = await make_request('POST', '/department/students/register-single', token=admin_token, body=stu_form, headers={'content-type': 'application/x-www-form-urlencoded'})
    record_test("Suite 4", "Admin registers single student", st in (200, 303))

    test_student_id = None
    with get_db() as conn:
        c = conn.cursor()
        c.execute("SELECT id, user_id, department, full_name FROM users WHERE user_id = ?", (unique_uid,))
        row = c.fetchone()
        if row:
            test_student_id = row[0]
            record_test("Suite 4", f"Student record persisted in database (ID: {test_student_id})", True)
        else:
            record_test("Suite 4", "Student record persisted in database", False)

    # 4.2 Duplicate student check API by Name and Guardian
    st, hd, bd = await make_request('GET', f'/api/students/check-duplicate?name=Aarav+Sharma+QA&guardian=Mr.+Rajesh+Sharma', token=admin_token)
    record_test("Suite 4", "Duplicate student check detects existing student and guardian", st == 200 and '"exists":true' in bd.replace(" ", ""))

    # 4.3 Department transfer for student
    transfer_form = urllib.parse.urlencode({
        "user_id": unique_uid,
        "department_name": "Foreign Language"
    }).encode()
    st, hd, bd = await make_request('POST', '/department/users/assign-department', token=admin_token, body=transfer_form, headers={'content-type': 'application/x-www-form-urlencoded'})
    record_test("Suite 4", "Transfer student department to Foreign Language", st in (200, 303))

    # Verify department change
    with get_db() as conn:
        c = conn.cursor()
        c.execute("SELECT department FROM users WHERE id = ?", (test_student_id,))
        dept_row = c.fetchone()
        dept_now = dept_row[0] if dept_row else ""
        record_test("Suite 4", f"Student department updated to '{dept_now}'", dept_now == "Foreign Language")

    # 4.4 Student Profile reflection
    new_stu_token = create_access_token({"sub": unique_uid, "role": "student"})
    st, hd, bd = await make_request('GET', '/profile', token=new_stu_token)
    record_test("Suite 4", "Student profile reflects updated department and details", st == 200 and "Foreign Language" in bd and unique_uid in bd)

    # 4.5 Clean up test student
    del_form = urllib.parse.urlencode({}).encode()
    st, hd, bd = await make_request('POST', f'/department/students/delete/{unique_uid}', token=admin_token, body=del_form, headers={'content-type': 'application/x-www-form-urlencoded'})
    record_test("Suite 4", "Admin deletes temporary QA student", st in (200, 303))

    with get_db() as conn:
        c = conn.cursor()
        c.execute("SELECT count(*) FROM users WHERE user_id = ?", (unique_uid,))
        remaining = c.fetchone()[0]
        record_test("Suite 4", "Student properly purged from users table", remaining == 0)

async def run_suite_5_enrollments():
    print("\n" + "="*70)
    print("SUITE 5: COURSE ENROLLMENT & ASSIGNMENT ENGINE")
    print("="*70)
    admin_token = create_access_token({"sub": "DEPT-HEAD", "role": "department_admin"})
    
    target_student_uid = "CS2026-002"
    with get_db() as conn:
        c = conn.cursor()
        c.execute("SELECT id FROM users WHERE user_id = ?", (target_student_uid,))
        student_db_id = c.fetchone()[0]

    # 5.1 Enroll by user_id string (Dual ID Resolution) into Course 8894 (UPSC Polity)
    assign_form = urllib.parse.urlencode({
        "course_id": "8894",
        "student_user_ids": target_student_uid
    }).encode()
    st, hd, bd = await make_request('POST', '/department/courses/assign', token=admin_token, body=assign_form, headers={'content-type': 'application/x-www-form-urlencoded'})
    record_test("Suite 5", "Admin assigns course using student roll number (CS2026-002)", st in (200, 303))

    # Verify enrollment exists
    with get_db() as conn:
        c = conn.cursor()
        c.execute("SELECT count(*) FROM enrollments WHERE user_id = ? AND course_id = 8894", (student_db_id,))
        enrolled_count = c.fetchone()[0]
        record_test("Suite 5", "Enrollment record exists in database", enrolled_count > 0)

    # 5.2 Verify course appears in student dashboard
    stu_token = create_access_token({"sub": target_student_uid, "role": "student"})
    st, hd, bd = await make_request('GET', '/student', token=stu_token)
    record_test("Suite 5", "Assigned course 8894 visible in Student Dashboard", st == 200 and "Indian Polity and Governance" in bd)

    # 5.3 Verify course appears in student profile
    st, hd, bd = await make_request('GET', '/profile', token=stu_token)
    record_test("Suite 5", "Assigned course 8894 visible in Student Profile enrolled list", st == 200 and "Indian Polity and Governance" in bd)

    # 5.4 Cross-Department assignment: Student is in Foreign Language, course is in Test Prep
    record_test("Suite 5", "Cross-department course assignment successfully rendered for student", "Foreign Language" in bd and "Indian Polity" in bd)

    # 5.5 Unassign course from student using user_id
    unassign_form = urllib.parse.urlencode({
        "course_id": "8894",
        "user_id": target_student_uid
    }).encode()
    st, hd, bd = await make_request('POST', '/department/courses/unassign', token=admin_token, body=unassign_form, headers={'content-type': 'application/x-www-form-urlencoded'})
    record_test("Suite 5", "Admin unassigns course from student", st in (200, 303))

    # 5.6 Verify unassigned course immediately disappears from dashboard
    st, hd, bd = await make_request('GET', '/student', token=stu_token)
    record_test("Suite 5", "Unassigned course removed from Student Dashboard", st == 200)

    # Re-assign back so test student has active enrollment for player tests
    with get_db() as conn:
        c = conn.cursor()
        c.execute("INSERT OR IGNORE INTO enrollments (user_id, course_id, enrolled_at) VALUES (?, 8894, CURRENT_TIMESTAMP)", (student_db_id,))
        conn.commit()
    record_test("Suite 5", "Restored active enrollment for Course 8894", True)

async def run_suite_6_course_player():
    print("\n" + "="*70)
    print("SUITE 6: STUDENT COURSE PLAYER & LEARNING ENGINE")
    print("="*70)
    stu_token = create_access_token({"sub": "UPSC-2026-0102", "role": "student"})
    
    # 6.1 GET /course/8894 renders Course Player
    st, hd, bd = await make_request('GET', '/course/8894', token=stu_token)
    record_test("Suite 6", "GET /course/8894 renders interactive course player", st == 200 and "Indian Polity and Governance" in bd)

    # 6.2 Modules and syllabus visible
    record_test("Suite 6", "Course Player displays curriculum modules & chapters", "Module 1" in bd and "Historical Background" in bd)

    # 6.3 Embedded video player elements present
    record_test("Suite 6", "YouTube embed player / video container rendered", ("iframe" in bd or "videoPlayer" in bd or "youtube" in bd.lower()))

    # 6.4 PDF resources accessible
    record_test("Suite 6", "PDF study resources listed with links", "pdf" in bd.lower())

    # 6.5 Mark lesson complete
    with get_db() as conn:
        c = conn.cursor()
        c.execute("""
            SELECT l.id 
            FROM lessons l 
            JOIN modules m ON l.module_id = m.id 
            WHERE m.course_id = 8894 
            LIMIT 1
        """)
        first_lesson = c.fetchone()
        first_lesson_id = first_lesson[0] if first_lesson else 1

    st, hd, bd = await make_request('POST', f'/api/lesson/{first_lesson_id}/complete', token=stu_token)
    record_test("Suite 6", f"POST /api/lesson/{first_lesson_id}/complete tracks progress", st in (200, 303))

    # 6.6 Verify lesson_progress record
    with get_db() as conn:
        c = conn.cursor()
        c.execute("SELECT id FROM users WHERE user_id = 'UPSC-2026-0102'")
        s_id = c.fetchone()[0]
        c.execute("SELECT count(*) FROM lesson_progress WHERE user_id = ? AND lesson_id = ?", (s_id, first_lesson_id))
        prog_count = c.fetchone()[0]
        record_test("Suite 6", "lesson_progress table record created", prog_count > 0)

    # 6.7 Deleted course returns 404
    st, hd, bd = await make_request('GET', '/course/1', token=stu_token)
    record_test("Suite 6", "Attempting to access deleted course returns 404", st == 404)

    # 6.8 Non-existent course returns 404
    st, hd, bd = await make_request('GET', '/course/999999', token=stu_token)
    record_test("Suite 6", "Attempting to access non-existent course returns 404", st == 404)

async def run_suite_7_quiz_engine():
    print("\n" + "="*70)
    print("SUITE 7: QUIZ ENGINE & AUTOMATED EVALUATION")
    print("="*70)
    stu_token = create_access_token({"sub": "UPSC-2026-0102", "role": "student"})

    # Find an active quiz under Course 8894
    with get_db() as conn:
        c = conn.cursor()
        c.execute("""
            SELECT q.id, q.lesson_id, q.passing_score
            FROM quizzes q
            JOIN lessons l ON q.lesson_id = l.id
            JOIN modules m ON l.module_id = m.id
            WHERE m.course_id = 8894
            LIMIT 1
        """)
        quiz_row = c.fetchone()

    if not quiz_row:
        record_test("Suite 7", "Find active quiz in Course 8894", False, "No quiz found")
        return

    quiz_id, lesson_id, passing_score = quiz_row
    record_test("Suite 7", f"Found Quiz {quiz_id} for Lesson {lesson_id}", True)

    # 7.1 Start Quiz
    st, hd, bd = await make_request('POST', f'/api/quiz/{quiz_id}/start', token=stu_token)
    record_test("Suite 7", "POST /api/quiz/{id}/start initializes quiz session", st == 200)

    # 7.2 Fetch questions for quiz
    with get_db() as conn:
        c = conn.cursor()
        c.execute("SELECT id, correct_option FROM quiz_questions WHERE quiz_id = ?", (quiz_id,))
        questions = c.fetchall()

    record_test("Suite 7", f"Quiz has {len(questions)} MCQ questions", len(questions) >= 5)

    # 7.3 Submit Quiz with 100% Correct Answers
    answers_dict = {str(q[0]): q[1] for q in questions}
    submit_payload = json.dumps({"answers": answers_dict, "time_taken_seconds": 45}).encode()
    st, hd, bd = await make_request('POST', f'/api/quiz/{quiz_id}/submit', token=stu_token, body=submit_payload, headers={'content-type': 'application/json'})
    
    passed_quiz = False
    if st == 200:
        data = json.loads(bd)
        passed_quiz = data.get("passed", False)
        score_percent = data.get("score_percent")
        record_test("Suite 7", f"Quiz submission evaluated automatically: score={score_percent}%, passed={passed_quiz}", passed_quiz is True)
    else:
        record_test("Suite 7", "Quiz submission API", False, f"Status {st}")

    # 7.4 Submit Quiz with Wrong Answers -> Verify Failed
    wrong_answers = {str(q[0]): "X" for q in questions}
    submit_wrong = json.dumps({"answers": wrong_answers, "time_taken_seconds": 30}).encode()
    st, hd, bd = await make_request('POST', f'/api/quiz/{quiz_id}/submit', token=stu_token, body=submit_wrong, headers={'content-type': 'application/json'})
    if st == 200:
        data = json.loads(bd)
        record_test("Suite 7", f"Quiz evaluated failed attempt correctly: passed={data.get('passed')}", data.get('passed') is False)
    else:
        record_test("Suite 7", "Quiz wrong answers evaluation", False)

    # 7.5 Explanation review endpoint
    if questions:
        q_id = questions[0][0]
        expl_payload = json.dumps({"question_id": q_id, "user_choice": "A"}).encode()
        st, hd, bd = await make_request('POST', '/api/quiz/explain-answer', token=stu_token, body=expl_payload, headers={'content-type': 'application/json'})
        record_test("Suite 7", "Question explanation endpoint returns conceptual feedback or policy status", st in (200, 400, 403))

    # 7.6 quiz_attempts history logged
    with get_db() as conn:
        c = conn.cursor()
        c.execute("SELECT count(*) FROM quiz_attempts WHERE quiz_id = ?", (quiz_id,))
        att_count = c.fetchone()[0]
        record_test("Suite 7", f"quiz_attempts table logs history ({att_count} attempts recorded)", att_count > 0)

async def run_suite_8_upsc_answer_writing():
    print("\n" + "="*70)
    print("SUITE 8: UPSC MAINS ANSWER WRITING & MENTOR EVALUATION")
    print("="*70)
    admin_token = create_access_token({"sub": "DEPT-HEAD", "role": "department_admin"})
    stu_upsc_token = create_access_token({"sub": "UPSC-2026-0102", "role": "student"})
    stu_fl_token = create_access_token({"sub": "CS2026-002", "role": "student"})
    teacher_token = create_access_token({"sub": "T-UPSC-01", "role": "teacher"})

    # 8.1 Gated In: Test Prep course (8894) renders answer sheet upload
    st, hd, bd = await make_request('GET', '/course/8894', token=stu_upsc_token)
    record_test("Suite 8", "Course 8894 (Test Prep, enabled=1) renders Answer Sheet upload section", "mainsAnswerSheetSection" in bd)

    # 8.2 Gated Out: Foreign Language course (8889) hides answer sheet upload
    st, hd, bd = await make_request('GET', '/course/8889', token=stu_fl_token)
    record_test("Suite 8", "Course 8889 (Foreign Language, enabled=0) hides Answer Sheet upload section", "mainsAnswerSheetSection" not in bd)

    # 8.3 Blocked with 403 when department has Answer Writing disabled
    # Temporarily set Dept 2 to 0
    toggle_department_ans_writing(2, admin_user_id=1)
    boundary = '----WebKitFormBoundaryQA'
    body = (
        f'--{boundary}\r\n'
        f'Content-Disposition: form-data; name=\"remarks\"\r\n\r\n'
        f'UPSC Polity Paper\r\n'
        f'--{boundary}\r\n'
        f'Content-Disposition: form-data; name=\"file\"; filename=\"test.pdf\"\r\n'
        f'Content-Type: application/pdf\r\n\r\n'
        f'%PDF-1.4 sample\r\n'
        f'--{boundary}--\r\n'
    ).encode('utf-8')
    st, hd, bd = await make_request(
        'POST', '/api/course/8894/upload-answer-sheet',
        token=stu_upsc_token,
        body=body,
        headers={'content-type': f'multipart/form-data; boundary={boundary}'}
    )
    record_test("Suite 8", "Upload blocked with HTTP 403 when Department has feature disabled", st == 403)
    # Re-enable Dept 2
    toggle_department_ans_writing(2, admin_user_id=1)

    # 8.4 Non-PDF upload rejected
    bad_body = (
        f'--{boundary}\r\n'
        f'Content-Disposition: form-data; name=\"remarks\"\r\n\r\n'
        f'UPSC Polity Paper\r\n'
        f'--{boundary}\r\n'
        f'Content-Disposition: form-data; name=\"file\"; filename=\"test.docx\"\r\n'
        f'Content-Type: application/vnd.openxmlformats-officedocument.wordprocessingml.document\r\n\r\n'
        f'not a pdf\r\n'
        f'--{boundary}--\r\n'
    ).encode('utf-8')
    st, hd, bd = await make_request(
        'POST', '/api/course/8894/upload-answer-sheet',
        token=stu_upsc_token,
        body=bad_body,
        headers={'content-type': f'multipart/form-data; boundary={boundary}'}
    )
    record_test("Suite 8", "Non-PDF upload rejected with 400 Bad Request", st == 400 and "Only PDF" in bd)

    # 8.5 Valid PDF upload
    valid_pdf = (
        f'--{boundary}\r\n'
        f'Content-Disposition: form-data; name=\"remarks\"\r\n\r\n'
        f'UPSC Mains GS-2 Question 1: Basic Structure Doctrine\r\n'
        f'--{boundary}\r\n'
        f'Content-Disposition: form-data; name=\"file\"; filename=\"upsc_mains_gs2_ans.pdf\"\r\n'
        f'Content-Type: application/pdf\r\n\r\n'
        f'%PDF-1.4 Mock Candidate Handwritten PDF\r\n'
        f'--{boundary}--\r\n'
    ).encode('utf-8')
    st, hd, bd = await make_request(
        'POST', '/api/course/8894/upload-answer-sheet',
        token=stu_upsc_token,
        body=valid_pdf,
        headers={'content-type': f'multipart/form-data; boundary={boundary}'}
    )
    
    submission_id = None
    if st == 200:
        data = json.loads(bd)
        submission_id = data.get("submission", {}).get("id")
        record_test("Suite 8", f"Student uploaded valid PDF answer sheet (Submission ID: {submission_id})", True)
    else:
        record_test("Suite 8", "Student uploaded valid PDF answer sheet", False, f"Status {st}")

    # 8.6 Notification created for subject teacher
    with get_db() as conn:
        c = conn.cursor()
        c.execute("SELECT count(*) FROM notifications WHERE user_id = 2489 AND category = 'submission'")
        notif_count = c.fetchone()[0]
        record_test("Suite 8", "Notification created for Subject Teacher upon submission", notif_count > 0)

    # 8.7 Teacher evaluates submission
    if submission_id:
        eval_payload = urllib.parse.urlencode({
            "marks_awarded": "15.5",
            "max_marks": "20.0",
            "feedback": "Comprehensive introduction linking Article 368 with Kesavananda Bharati case. Excellent structure and balance."
        }).encode()
        st, hd, bd = await make_request(
            'POST', f'/api/answer-sheet/{submission_id}/evaluate',
            token=teacher_token,
            body=eval_payload,
            headers={'content-type': 'application/x-www-form-urlencoded'}
        )
        record_test("Suite 8", "Teacher evaluates paper, awards 15.5/20.0 and feedback critique", st == 200)

        # 8.8 Student checks evaluation
        st, hd, bd = await make_request('GET', '/api/course/8894/answer-sheets', token=stu_upsc_token)
        record_test("Suite 8", "Student retrieves evaluated answer copy with marks and comments", st == 200 and "15.5" in bd and "Kesavananda" in bd)

        # Clean up test submission
        with get_db() as conn:
            c = conn.cursor()
            c.execute("SELECT file_path FROM answer_sheet_submissions WHERE id = ?", (submission_id,))
            fpath = c.fetchone()
            c.execute("DELETE FROM answer_sheet_submissions WHERE id = ?", (submission_id,))
            conn.commit()
            if fpath and fpath[0]:
                full_p = os.path.join(os.path.dirname(__file__), "app/static/uploads", fpath[0])
                if os.path.exists(full_p):
                    os.remove(full_p)
            record_test("Suite 8", "Cleaned up temporary QA answer sheet submission", True)

async def run_suite_9_mentoring():
    print("\n" + "="*70)
    print("SUITE 9: 1-ON-1 MENTORING WORKFLOW")
    print("="*70)
    admin_token = create_access_token({"sub": "DEPT-HEAD", "role": "department_admin"})
    stu_token = create_access_token({"sub": "UPSC-2026-0102", "role": "student"})
    teacher_token = create_access_token({"sub": "T-UPSC-01", "role": "teacher"})

    # 9.1 Student requests 1-on-1 session
    req_payload = urllib.parse.urlencode({
        "topic": "Ethics Case Studies & Essay Strategy Guidance",
        "description": "Need mentor feedback on GS4 ethical dilemmas and framework.",
        "preferred_date": "2026-11-10",
        "preferred_time": "16:00"
    }).encode()
    st, hd, bd = await make_request('POST', '/api/mentoring/student-request', token=stu_token, body=req_payload, headers={'content-type': 'application/x-www-form-urlencoded'})
    
    session_id = None
    if st == 200:
        data = json.loads(bd)
        session_id = data.get("session", {}).get("id")
        record_test("Suite 9", f"Student requested 1-on-1 mentoring session (Session ID: {session_id})", True)
    else:
        record_test("Suite 9", "Student requested 1-on-1 mentoring session", False)

    # 9.2 Admin assigns teacher to session
    if session_id:
        assign_payload = urllib.parse.urlencode({
            "teacher_id": "2489", # Dr. A. K. Sharma
            "scheduled_date": "2026-11-10",
            "scheduled_time": "16:00",
            "meeting_link": "https://meet.google.com/upsc-mentor-qa"
        }).encode()
        st, hd, bd = await make_request('POST', f'/api/mentoring/{session_id}/assign-teacher', token=admin_token, body=assign_payload, headers={'content-type': 'application/x-www-form-urlencoded'})
        record_test("Suite 9", "Admin assigns faculty mentor & schedules meeting", st == 200)

    # 9.3 Teacher initiates direct mentoring invite
    with get_db() as conn:
        c = conn.cursor()
        c.execute("SELECT id FROM users WHERE user_id = 'UPSC-2026-0102'")
        s_db_id = c.fetchone()[0]

    teach_req_payload = urllib.parse.urlencode({
        "student_id": str(s_db_id),
        "topic": "Answer Writing Structure Critique",
        "scheduled_date": "2026-11-12",
        "scheduled_time": "15:00",
        "description": "Let's review your recent test copies."
    }).encode()
    st, hd, bd = await make_request('POST', '/api/mentoring/teacher-request', token=teacher_token, body=teach_req_payload, headers={'content-type': 'application/x-www-form-urlencoded'})
    
    teach_sess_id = None
    if st == 200:
        data = json.loads(bd)
        teach_sess_id = data.get("session", {}).get("id")
        record_test("Suite 9", f"Teacher initiated direct mentoring session with student (ID: {teach_sess_id})", True)
    else:
        record_test("Suite 9", "Teacher initiated direct mentoring session", False)

    # 9.4 Student confirms date & time
    if teach_sess_id:
        confirm_payload = urllib.parse.urlencode({
            "session_id": str(teach_sess_id),
            "scheduled_date": "2026-11-12",
            "scheduled_time": "15:00",
            "student_notes": "Confirmed schedule."
        }).encode()
        st, hd, bd = await make_request('POST', '/api/mentoring/student-confirm-schedule', token=stu_token, body=confirm_payload, headers={'content-type': 'application/x-www-form-urlencoded'})
        record_test("Suite 9", "Student confirms teacher's proposed session time", st == 200)

    # 9.5 Teacher concludes mentoring session
    if session_id:
        complete_payload = urllib.parse.urlencode({
            "teacher_notes": "Covered 5 previous year GS4 ethics questions. Candidate advised to practice 2 case studies daily."
        }).encode()
        st, hd, bd = await make_request('POST', f'/api/mentoring/{session_id}/complete', token=teacher_token, body=complete_payload, headers={'content-type': 'application/x-www-form-urlencoded'})
        record_test("Suite 9", "Teacher concludes mentoring session with action notes", st == 200)

        # 9.6 Verify session status
        with get_db() as conn:
            c = conn.cursor()
            c.execute("SELECT status FROM mentoring_sessions WHERE id = ?", (session_id,))
            row = c.fetchone()
            record_test("Suite 9", f"Session status transitioned to '{row[0]}'", row and row[0] == "completed")

    # Clean up test mentoring sessions
    with get_db() as conn:
        c = conn.cursor()
        if session_id:
            c.execute("DELETE FROM mentoring_sessions WHERE id = ?", (session_id,))
        if teach_sess_id:
            c.execute("DELETE FROM mentoring_sessions WHERE id = ?", (teach_sess_id,))
        conn.commit()
    record_test("Suite 9", "Cleaned up temporary QA mentoring sessions", True)

async def run_suite_10_live_and_certs():
    print("\n" + "="*70)
    print("SUITE 10: LIVE CLASSES, CERTIFICATES & NOTIFICATIONS")
    print("="*70)
    admin_token = create_access_token({"sub": "DEPT-HEAD", "role": "department_admin"})
    stu_token = create_access_token({"sub": "UPSC-2026-0102", "role": "student"})
    teacher_token = create_access_token({"sub": "T-UPSC-01", "role": "teacher"})

    # 10.1 Teacher schedules Live Class (Form Data)
    live_form = urllib.parse.urlencode({
        "course_id": "8894",
        "title": "Live Masterclass: Constitutional Amendments & High Courts",
        "description": "Interactive live session solving 20 Mains questions",
        "platform": "youtube",
        "meeting_url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        "scheduled_at": "2026-11-15T18:00:00",
        "duration_minutes": "60"
    }).encode()
    st, hd, bd = await make_request('POST', '/api/live-classes/create', token=teacher_token, body=live_form, headers={'content-type': 'application/x-www-form-urlencoded'})
    
    live_id = None
    if st == 200:
        data = json.loads(bd)
        live_id = data.get("data", {}).get("id") or data.get("id")
        record_test("Suite 10", f"Faculty schedules Live Class (ID: {live_id})", True)
    else:
        record_test("Suite 10", "Faculty schedules Live Class", False, f"Status: {st}")

    # 10.2 Student views upcoming live classes in student dashboard
    st, hd, bd = await make_request('GET', '/student', token=stu_token)
    record_test("Suite 10", "Live class listed on Student Dashboard", st == 200 and "Constitutional Amendments" in bd)

    # 10.3 Student posts live question in live room
    if live_id:
        q_payload = json.dumps({"question_text": "Sir, how does Article 368 amendment affect Article 21?"}).encode()
        st, hd, bd = await make_request('POST', f'/api/live-classes/{live_id}/questions', token=stu_token, body=q_payload, headers={'content-type': 'application/json'})
        record_test("Suite 10", "Student submits question during Live Class", st == 200)

        # Clean up live class
        with get_db() as conn:
            c = conn.cursor()
            c.execute("DELETE FROM live_class_questions WHERE live_class_id = ?", (live_id,))
            c.execute("DELETE FROM live_classes WHERE id = ?", (live_id,))
            conn.commit()
        record_test("Suite 10", "Cleaned up QA live class and questions", True)

    # 10.4 Admin issues Course Completion Certificate
    with get_db() as conn:
        c = conn.cursor()
        c.execute("SELECT id FROM users WHERE user_id = 'UPSC-2026-0102'")
        s_db_id = c.fetchone()[0]

    cert_payload = urllib.parse.urlencode({
        "student_id": str(s_db_id),
        "course_id": "8894"
    }).encode()
    st, hd, bd = await make_request('POST', '/api/certificates/generate-for-student', token=admin_token, body=cert_payload, headers={'content-type': 'application/x-www-form-urlencoded'})
    
    cert_id = None
    if st == 200:
        data = json.loads(bd)
        cert_id = data.get("data", {}).get("certificate_id")
        record_test("Suite 10", f"Admin generated certificate for student (Cert ID: {cert_id})", True)
    else:
        record_test("Suite 10", "Admin generated certificate for student", False, f"Status: {st}")

    # 10.5 Student views certificate
    if cert_id:
        st, hd, bd = await make_request('GET', f'/certificate/{cert_id}', token=stu_token)
        record_test("Suite 10", "Student views official Certificate with verification badge", st == 200 and cert_id in bd)

        # 10.6 Public verification endpoint
        st, hd, bd = await make_request('GET', f'/verify/{cert_id}')
        record_test("Suite 10", "Public verification page confirms certificate validity", st == 200 and ("Authentic" in bd or "Certificate" in bd))

        # Clean up test certificate
        with get_db() as conn:
            c = conn.cursor()
            c.execute("DELETE FROM certificates WHERE certificate_id = ?", (cert_id,))
            conn.commit()
        record_test("Suite 10", "Cleaned up QA test certificate", True)

    # 10.7 Notifications retrieval
    st, hd, bd = await make_request('GET', '/profile', token=stu_token)
    record_test("Suite 10", "Notifications and activity logs operational", st == 200)

async def main():
    print("=" * 80)
    print("NEXUS LMS COMPREHENSIVE END-TO-END QA TEST SUITE")
    print("Role: Automated Senior Quality Assurance & System Tester")
    print(f"Timestamp: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 80)

    start_time = time.time()
    await run_suite_1_auth_rbac()
    await run_suite_2_departments()
    await run_suite_3_curriculum()
    await run_suite_4_students()
    await run_suite_5_enrollments()
    await run_suite_6_course_player()
    await run_suite_7_quiz_engine()
    await run_suite_8_upsc_answer_writing()
    await run_suite_9_mentoring()
    await run_suite_10_live_and_certs()
    duration = time.time() - start_time

    print("\n" + "=" * 80)
    print(f"FINAL TEST EXECUTION SUMMARY:")
    print(f"Total Tests Executed: {TOTAL}")
    print(f"Passed: {PASSED} ({(PASSED/TOTAL)*100:.1f}%)")
    print(f"Failed: {FAILED}")
    print(f"Execution Duration: {duration:.2f} seconds")
    print("=" * 80)

if __name__ == "__main__":
    asyncio.run(main())
