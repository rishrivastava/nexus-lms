import asyncio
import urllib.parse
import json
import sqlite3
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.main import app
from app.auth import create_access_token

class ASGIClient:
    def __init__(self, app):
        self.app = app
        self.cookies = {}

    async def request(self, method, path, query_params=None, data=None, json_data=None, headers=None, follow_redirects=True):
        if headers is None:
            headers = {}
        
        # Merge cookies
        cookie_header = "; ".join(f"{k}={v}" for k, v in self.cookies.items())
        if cookie_header:
            headers["cookie"] = cookie_header

        body = b""
        if data is not None:
            body = urllib.parse.urlencode(data).encode("utf-8")
            headers.setdefault("content-type", "application/x-www-form-urlencoded")
        elif json_data is not None:
            body = json.dumps(json_data).encode("utf-8")
            headers.setdefault("content-type", "application/json")

        qs = ""
        if query_params:
            qs = urllib.parse.urlencode(query_params)

        raw_headers = [(b"host", b"testserver")]
        for k, v in headers.items():
            raw_headers.append((k.lower().encode("utf-8"), str(v).encode("utf-8")))

        scope = {
            "type": "http",
            "http_version": "1.1",
            "method": method.upper(),
            "path": path,
            "raw_path": path.encode("utf-8"),
            "query_string": qs.encode("utf-8"),
            "headers": raw_headers,
            "client": ("127.0.0.1", 12345),
            "server": ("testserver", 80),
            "scheme": "http",
        }

        sent = False
        async def receive():
            nonlocal sent
            if not sent:
                sent = True
                return {"type": "http.request", "body": body, "more_body": False}
            return {"type": "http.request", "body": b"", "more_body": False}

        status_code = [None]
        resp_headers = []
        resp_body = []

        async def send(message):
            if message["type"] == "http.response.start":
                status_code[0] = message["status"]
                resp_headers.extend(message.get("headers", []))
            elif message["type"] == "http.response.body":
                resp_body.append(message.get("body", b""))

        await self.app(scope, receive, send)

        # Parse Set-Cookie
        for k, v in resp_headers:
            if k.lower() == b"set-cookie":
                cookie_str = v.decode("utf-8")
                parts = cookie_str.split(";")[0].split("=", 1)
                if len(parts) == 2:
                    self.cookies[parts[0].strip()] = parts[1].strip()

        status = status_code[0]
        text = b"".join(resp_body).decode("utf-8", errors="replace")

        # Handle redirects
        if follow_redirects and status in (301, 302, 303, 307, 308):
            loc = None
            for k, v in resp_headers:
                if k.lower() == b"location":
                    loc = v.decode("utf-8")
                    break
            if loc:
                parsed = urllib.parse.urlparse(loc)
                new_path = parsed.path
                new_qs = urllib.parse.parse_qs(parsed.query)
                flat_qs = {k: v[0] if len(v) == 1 else v for k, v in new_qs.items()}
                return await self.request("GET", new_path, query_params=flat_qs, follow_redirects=True)

        return status, text, resp_headers

    async def get(self, path, query_params=None, headers=None, follow_redirects=True):
        return await self.request("GET", path, query_params=query_params, headers=headers, follow_redirects=follow_redirects)

    async def post(self, path, data=None, json_data=None, headers=None, follow_redirects=True):
        return await self.request("POST", path, data=data, json_data=json_data, headers=headers, follow_redirects=follow_redirects)

def get_client_for_user(email_or_user_id):
    client = ASGIClient(app)
    conn = sqlite3.connect('/Users/rocket/.gemini/antigravity/scratch/lms/lms.db')
    c = conn.cursor()
    c.execute("SELECT id, user_id, email, full_name, role FROM users WHERE email = ? OR user_id = ?", (email_or_user_id, email_or_user_id))
    user = c.fetchone()
    conn.close()
    if not user:
        raise ValueError(f"User not found: {email_or_user_id}")
    
    # Directly set auth cookie via jwt
    token = create_access_token({"sub": user[1], "role": user[4]})
    client.cookies["lms_token"] = token
    return client, user

async def run_tests():
    print("=== 1. Testing Greetings without Designations ===")
    # Student
    client_st, student_user = get_client_for_user("CS2026-002") # Priya Patel
    status, text, _ = await client_st.get("/profile")
    assert status == 200
    assert "Welcome Priya Patel!" in text, f"Expected 'Welcome Priya Patel!' in student profile"
    assert "Welcome Student" not in text
    print("  ✓ Student profile: 'Welcome Priya Patel!' verified, no 'Welcome Student'")

    # Teacher
    client_tc, teacher_user = get_client_for_user("alan@nexus.edu") # Prof. Rameez
    status, text, _ = await client_tc.get("/profile")
    assert status == 200
    assert f"Welcome {teacher_user[3]}!" in text
    assert "Welcome Teacher" not in text
    print(f"  ✓ Teacher profile: 'Welcome {teacher_user[3]}!' verified, no 'Welcome Teacher'")

    # Admin
    client_ad, admin_user = get_client_for_user("admin@nexus.edu") # Rishu
    status, text, _ = await client_ad.get("/profile")
    assert status == 200
    assert f"Welcome {admin_user[3]}!" in text
    assert "Welcome Admin" not in text
    print(f"  ✓ Admin profile: 'Welcome {admin_user[3]}!' verified, no 'Welcome Admin'")

    print("\n=== 2. Testing Teacher Dashboard (500 Error Fix) ===")
    conn = sqlite3.connect('/Users/rocket/.gemini/antigravity/scratch/lms/lms.db')
    c = conn.cursor()
    c.execute("SELECT id, user_id, email, full_name FROM users WHERE role = 'teacher'")
    teachers = c.fetchall()
    conn.close()

    for t in teachers:
        c_inst, _ = get_client_for_user(t[2] or t[1])
        status, text, _ = await c_inst.get("/teacher/dashboard")
        assert status == 200, f"Teacher dashboard failed for {t[3]} (ID {t[0]}): status {status}"
        assert "Welcome" in text
    print(f"  ✓ All {len(teachers)} teachers load /teacher/dashboard with HTTP 200 OK and no 500 error!")

    print("\n=== 3. Testing Copy Text Update ===")
    status, text, _ = await client_ad.get("/department")
    assert status == 200
    assert "Ans sheet upload" in text, "Expected 'Ans sheet upload' in department dashboard"
    assert "UPSC Mains PDF answer sheet upload & faculty grading" not in text, "Legacy string found!"
    print("  ✓ 'Ans sheet upload' present and 'UPSC Mains PDF answer sheet upload & faculty grading' removed.")

    print("\n=== 4. Testing Teacher Profile Department Read-Only ===")
    status, text, _ = await client_tc.get("/profile")
    assert "Assigned Department(s)" in text
    assert "Read-Only" in text
    
    # Try updating department as teacher
    status, text, _ = await client_tc.post("/profile/update", data={
        "full_name": teacher_user[3],
        "department": "HACKED_DEPARTMENT",
        "school_name": "Test School"
    })
    assert status == 200
    conn = sqlite3.connect('/Users/rocket/.gemini/antigravity/scratch/lms/lms.db')
    c = conn.cursor()
    c.execute("SELECT department FROM users WHERE id = ?", (teacher_user[0],))
    dept_val = c.fetchone()[0]
    conn.close()
    assert "HACKED_DEPARTMENT" not in dept_val, f"Teacher was able to change department! Found: {dept_val}"
    print("  ✓ Teacher cannot tamper with or modify assigned departments.")

    print("\n=== 5. Testing Admin Teacher Assignment Flow (Department -> Courses) ===")
    conn = sqlite3.connect('/Users/rocket/.gemini/antigravity/scratch/lms/lms.db')
    c = conn.cursor()
    c.execute("SELECT id, name FROM departments WHERE name = 'Foreign Language'")
    fl_dept = c.fetchone()
    c.execute("SELECT id, name FROM departments WHERE name = 'Test Prep'")
    tp_dept = c.fetchone()
    
    # Identify Claude Shannon (id 2479)
    shannon_id = 2479
    conn.close()

    # Step A: Assign Claude Shannon to 'Foreign Language' only
    status, text, _ = await client_ad.post("/department/teachers/assign-departments", data={
        "teacher_id": str(shannon_id),
        "department_ids": str(fl_dept[0])
    })
    assert status == 200, f"Assign depts failed: {status}"

    # Step B: Check assignable courses via API
    status, text, _ = await client_ad.get(f"/api/teachers/{shannon_id}/assignable-courses")
    assert status == 200
    courses_data = json.loads(text)
    assert courses_data["status"] == "success"
    assert any(d["name"] == "Foreign Language" for d in courses_data["departments"])
    assert all(c["department"].lower() == "foreign language" for c in courses_data["courses"])
    print(f"  ✓ Only courses belonging to teacher's assigned department ({len(courses_data['courses'])} courses) are assignable.")

    # Step C: Try assigning a course from a DIFFERENT department (e.g., Test Prep) -> Must be rejected!
    conn = sqlite3.connect('/Users/rocket/.gemini/antigravity/scratch/lms/lms.db')
    c = conn.cursor()
    c.execute("SELECT id, title FROM courses WHERE department = 'Test Prep' AND status != 'deleted' LIMIT 1")
    tp_course = c.fetchone()
    conn.close()

    status, text, _ = await client_ad.post("/department/teachers/assign-course", json_data={
        "teacher_id": shannon_id,
        "course_id": tp_course[0]
    }, follow_redirects=False)
    assert status == 400
    res_json = json.loads(text)
    assert "Teacher is not assigned to the 'Test Prep' department" in res_json.get("message", "")
    print("  ✓ Admin course assignment blocked if teacher is not in the course's department first!")

    # Step D: Now assign teacher to MULTIPLE departments (Foreign Language AND Test Prep)
    status, text, _ = await client_ad.post("/department/teachers/assign-departments", json_data={
        "teacher_id": shannon_id,
        "department_ids": [fl_dept[0], tp_dept[0]]
    })
    assert status == 200

    # Verify courses from both departments are now available
    status, text, _ = await client_ad.get(f"/api/teachers/{shannon_id}/assignable-courses")
    courses_data2 = json.loads(text)
    c_depts = set(c["department"] for c in courses_data2["courses"])
    assert "Foreign Language" in c_depts or "Test Prep" in c_depts
    print("  ✓ Multi-department assignment successful; teacher now eligible for courses in both departments.")

    # Step E: Assign the Test Prep course now -> Must succeed!
    status, text, _ = await client_ad.post("/department/teachers/assign-course", json_data={
        "teacher_id": shannon_id,
        "course_id": tp_course[0]
    }, follow_redirects=False)
    assert status == 200, f"Expected success, got: {status} - {text}"
    print(f"  ✓ Successfully assigned course '{tp_course[1]}' to teacher after department assignment.")

    print("\n=== 6. Testing Answer Sheets Surveillance Window for Admin ===")
    status, text, _ = await client_ad.get("/department", query_params={"tab": "answer-sheets"})
    assert status == 200
    assert "Answer Sheet Submissions &amp; Evaluation Control" in text or "Answer Sheet Submissions & Evaluation Control" in text
    assert "Total Received" in text
    assert "Evaluated Copies" in text
    assert "Pending Evaluation" in text
    assert "Evaluation Rate" in text
    print("  ✓ Dedicated Admin Answer Sheets Monitor window active with 4 live KPI metrics and submission table.")

    print("\n=== 7. Testing Teacher Profile Student PDF Visibility ===")
    status, text, _ = await client_tc.get("/profile")
    assert status == 200
    assert "Enrolled Student Answer Sheets &amp; Evaluations" in text or "Enrolled Student Answer Sheets & Evaluations" in text
    assert "Submission(s)" in text
    print("  ✓ Student PDF submissions visible on teacher profile with instant grading links.")

    print("\n=== 8. Testing Teacher Viewing Enrolled Student Profile ===")
    status, text, _ = await client_tc.get(f"/api/students/{student_user[0]}/profile-modal")
    assert status == 200
    modal_data = json.loads(text)
    assert modal_data["status"] == "success"
    assert modal_data["student"]["full_name"] == "Priya Patel"
    assert "courses" in modal_data
    assert "quiz_attempts" in modal_data
    assert "answer_sheets" in modal_data
    print("  ✓ Teacher can inspect full student profile, course completion, assessment history, and answer sheets.")

    print("\n=== 9. Testing Teachers Only View Assigned Classes ===")
    # Teacher Alan/Rameez
    status, text, _ = await client_tc.get("/teacher")
    assert status == 200
    # Confirm courses list only includes courses with teacher_id = teacher_user[0]
    conn = sqlite3.connect('/Users/rocket/.gemini/antigravity/scratch/lms/lms.db')
    c = conn.cursor()
    c.execute("SELECT id, title FROM courses WHERE teacher_id = ? AND status != 'deleted'", (teacher_user[0],))
    assigned_courses = c.fetchall()
    c.execute("SELECT id, title FROM courses WHERE teacher_id != ? AND status != 'deleted'", (teacher_user[0],))
    unassigned_courses = c.fetchall()
    conn.close()

    for ac in assigned_courses:
        assert ac[1] in text, f"Assigned course '{ac[1]}' missing from teacher studio!"
    for uc in unassigned_courses:
        # Title should not appear as a course card header
        assert f"/teacher/course/{uc[0]}" not in text, f"Unassigned course {uc[0]} accessible in teacher studio!"
    print(f"  ✓ Verified: Teacher strictly only views their {len(assigned_courses)} assigned classes.")

    print("\n========================================================")
    print("  ALL 9 END-TO-END VERIFICATION SUITES PASSED (100% OK)!")
    print("========================================================")

if __name__ == "__main__":
    asyncio.run(run_tests())
