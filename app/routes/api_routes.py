from fastapi import APIRouter, Request, HTTPException, Header, Query
from fastapi.responses import JSONResponse
from app.database import (
    get_db, get_system_settings, update_system_settings,
    get_user_notifications, mark_notification_read, mark_all_notifications_read
)
from app.auth import get_current_user
from datetime import datetime
import time

router = APIRouter()

# ==========================================
# 1. LIVE STUDENT ACTIVITY HEARTBEAT
# ==========================================

@router.post("/api/activity/heartbeat")
async def activity_heartbeat(request: Request):
    """
    Called periodically (e.g. every 60s) by active student/user browser sessions.
    Maintains real-time live activity tracking based on authentic user engagement.
    """
    user = get_current_user(request)
    if not user:
        return JSONResponse({"status": "unauthenticated"}, status_code=200)

    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET last_active_at = CURRENT_TIMESTAMP WHERE id = ?", (user["id"],))

    return JSONResponse({"status": "active", "timestamp": int(time.time())})

# ==========================================
# 2. NOTIFICATION CENTRE API
# ==========================================

@router.get("/api/notifications")
async def fetch_user_notifications(request: Request):
    user = get_current_user(request)
    if not user:
        return JSONResponse({"unread_count": 0, "notifications": []})

    unread_count, notifications = get_user_notifications(user["id"], limit=30)
    return JSONResponse({
        "unread_count": unread_count,
        "notifications": notifications
    })

@router.post("/api/notifications/{notification_id}/read")
async def mark_single_read(request: Request, notification_id: int):
    user = get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Unauthorized")
    mark_notification_read(notification_id, user["id"])
    return JSONResponse({"status": "success", "id": notification_id})

@router.post("/api/notifications/read-all")
async def mark_all_read(request: Request):
    user = get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Unauthorized")
    mark_all_notifications_read(user["id"])
    return JSONResponse({"status": "success"})

# ==========================================
# 3. POWER BI & EXTERNAL REPORTING REST API
# ==========================================

def verify_powerbi_auth(request: Request, x_api_key: str = Header(None), api_key: str = Query(None)):
    token = ""
    if isinstance(x_api_key, str) and x_api_key:
        token = x_api_key
    elif isinstance(api_key, str) and api_key:
        token = api_key
    elif request.headers.get("x-api-key"):
        token = request.headers.get("x-api-key")
    elif request.query_params.get("api_key"):
        token = request.query_params.get("api_key")
    elif request.headers.get("Authorization"):
        token = request.headers.get("Authorization", "").replace("Bearer ", "").strip()

    settings = get_system_settings()
    configured_key = settings.get("powerbi_api_key", "").strip()

    if not configured_key or token != configured_key:
        raise HTTPException(status_code=401, detail="Invalid or missing Power BI API Key. Access denied.")

    # Record successful external synchronisation timestamp
    update_system_settings({"powerbi_last_sync_at": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")})
    return True

@router.get("/api/v1/reporting/students")
async def reporting_students(
    request: Request,
    limit: int = 500,
    offset: int = 0
):
    verify_powerbi_auth(request)
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT 
                u.id, u.user_id, u.full_name, u.guardian_name, u.department, u.school_name,
                u.udise_code, u.block, u.district, u.state, u.pincode, u.last_active_at, u.created_at,
                (SELECT COUNT(*) FROM enrollments WHERE user_id = u.id) as enrolled_courses_count,
                (SELECT COUNT(*) FROM enrollments WHERE user_id = u.id AND completed_at IS NOT NULL) as completed_courses_count,
                (SELECT ROUND(AVG(score_percent), 1) FROM quiz_attempts WHERE user_id = u.id) as avg_quiz_score
            FROM users u
            WHERE u.role = 'student'
            ORDER BY u.id ASC
            LIMIT ? OFFSET ?
        """, (limit, offset))
        students = [dict(r) for r in cursor.fetchall()]

    return JSONResponse({
        "status": "success",
        "count": len(students),
        "limit": limit,
        "offset": offset,
        "data": students
    })

@router.get("/api/v1/reporting/subjects")
async def reporting_subjects(request: Request):
    verify_powerbi_auth(request)
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT 
                COALESCE(c.subject, c.department) as subject_name,
                COUNT(DISTINCT c.id) as total_courses,
                COUNT(DISTINCT e.user_id) as unique_students,
                COUNT(e.id) as total_enrollments,
                COUNT(DISTINCT CASE WHEN u.last_active_at >= datetime('now', '-5 minutes') THEN e.user_id END) as live_students_now,
                COUNT(DISTINCT CASE WHEN e.completed_at IS NOT NULL THEN e.user_id END) as completed_students,
                ROUND(AVG(qa.score_percent), 1) as avg_quiz_score
            FROM courses c
            LEFT JOIN enrollments e ON c.id = e.course_id
            LEFT JOIN users u ON e.user_id = u.id
            LEFT JOIN modules m ON c.id = m.course_id
            LEFT JOIN lessons l ON m.id = l.module_id
            LEFT JOIN quizzes q ON l.id = q.lesson_id
            LEFT JOIN quiz_attempts qa ON q.id = qa.quiz_id AND qa.user_id = e.user_id
            WHERE c.status != 'deleted'
            GROUP BY COALESCE(c.subject, c.department)
            ORDER BY subject_name ASC
        """)
        subjects = [dict(r) for r in cursor.fetchall()]

    return JSONResponse({"status": "success", "count": len(subjects), "data": subjects})

@router.get("/api/v1/reporting/courses")
async def reporting_courses(request: Request):
    verify_powerbi_auth(request)
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT 
                c.id, c.code, c.title, COALESCE(c.subject, c.department) as subject, c.department,
                c.status, c.is_published, c.created_at, u.full_name as teacher_name,
                (SELECT COUNT(*) FROM enrollments WHERE course_id = c.id) as enrolled_count,
                (SELECT COUNT(*) FROM enrollments WHERE course_id = c.id AND completed_at IS NOT NULL) as completed_count,
                (SELECT COUNT(*) FROM lessons l JOIN modules m ON l.module_id = m.id WHERE m.course_id = c.id) as lesson_count
            FROM courses c
            JOIN users u ON c.teacher_id = u.id
            WHERE c.status != 'deleted'
            ORDER BY c.title ASC
        """)
        courses = [dict(r) for r in cursor.fetchall()]

    return JSONResponse({"status": "success", "count": len(courses), "data": courses})

@router.get("/api/v1/reporting/enrollments")
async def reporting_enrollments(request: Request, limit: int = 1000, offset: int = 0):
    verify_powerbi_auth(request)
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT 
                e.id as enrollment_id, e.user_id, u.user_id as student_code, u.full_name as student_name,
                c.id as course_id, c.code as course_code, c.title as course_title,
                COALESCE(c.subject, c.department) as subject,
                e.enrolled_at, e.completed_at
            FROM enrollments e
            JOIN users u ON e.user_id = u.id
            JOIN courses c ON e.course_id = c.id
            ORDER BY e.enrolled_at DESC
            LIMIT ? OFFSET ?
        """, (limit, offset))
        enrollments = [dict(r) for r in cursor.fetchall()]

    return JSONResponse({"status": "success", "count": len(enrollments), "data": enrollments})

@router.get("/api/v1/reporting/resources")
async def reporting_resources(request: Request):
    verify_powerbi_auth(request)
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT 
                l.id as lesson_id, l.title as lesson_title, l.content_type, l.duration_minutes,
                m.title as module_title, c.code as course_code, c.title as course_title,
                COALESCE(c.subject, c.department) as subject
            FROM lessons l
            JOIN modules m ON l.module_id = m.id
            JOIN courses c ON m.course_id = c.id
            ORDER BY c.id, m.position, l.position ASC
        """)
        resources = [dict(r) for r in cursor.fetchall()]

    return JSONResponse({"status": "success", "count": len(resources), "data": resources})

@router.get("/api/v1/reporting/quiz-attempts")
async def reporting_quiz_attempts(request: Request, limit: int = 1000, offset: int = 0):
    verify_powerbi_auth(request)
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT 
                qa.id as attempt_id, qa.user_id, u.user_id as student_code, u.full_name as student_name,
                c.code as course_code, COALESCE(c.subject, c.department) as subject,
                l.title as assessment_title, qa.score_percent, qa.passed,
                qa.time_taken_seconds, qa.attempted_at
            FROM quiz_attempts qa
            JOIN users u ON qa.user_id = u.id
            JOIN quizzes q ON qa.quiz_id = q.id
            JOIN lessons l ON q.lesson_id = l.id
            JOIN modules m ON l.module_id = m.id
            JOIN courses c ON m.course_id = c.id
            ORDER BY qa.attempted_at DESC
            LIMIT ? OFFSET ?
        """, (limit, offset))
        attempts = [dict(r) for r in cursor.fetchall()]

    return JSONResponse({"status": "success", "count": len(attempts), "data": attempts})

@router.get("/api/v1/reporting/engagement")
async def reporting_engagement(request: Request):
    verify_powerbi_auth(request)
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT 
                COALESCE(c.subject, c.department) as subject,
                COUNT(DISTINCT lp.user_id) as engaged_students,
                SUM(lp.watched_seconds) as total_watch_seconds,
                SUM(CASE WHEN lp.is_completed = 1 THEN 1 ELSE 0 END) as total_completed_lessons,
                COUNT(qa.id) as total_quiz_attempts
            FROM courses c
            JOIN modules m ON c.id = m.course_id
            JOIN lessons l ON m.id = l.module_id
            LEFT JOIN lesson_progress lp ON l.id = lp.lesson_id
            LEFT JOIN quizzes q ON l.id = q.lesson_id
            LEFT JOIN quiz_attempts qa ON q.id = qa.quiz_id
            GROUP BY COALESCE(c.subject, c.department)
        """)
        engagement = [dict(r) for r in cursor.fetchall()]

    return JSONResponse({"status": "success", "count": len(engagement), "data": engagement})

# ==========================================
# 4. CHATBOT, SUPPORT QUERIES & HELP DESK API
# ==========================================

from app.gemini_service import answer_support_query, test_gemini_connection
from app.database import create_notification, log_audit
import uuid

@router.post("/api/queries/create")
async def create_query(request: Request):
    """
    Submits a new query from Student or Teacher Chatbot.
    Rules:
      - Student queries: visibility = 'teachers_and_admin' (visible to Teachers and Admin)
      - Teacher queries: visibility = 'admin_only' (visible ONLY to Admin)
    """
    user = get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Please log in to submit a query.")

    try:
        body = await request.json()
    except Exception:
        form = await request.form()
        body = dict(form)

    subject = str(body.get("subject", "")).strip()
    message = str(body.get("message", "")).strip()
    category = str(body.get("category", "General Query")).strip()
    course_id = body.get("course_id")
    course_title = str(body.get("course_title", "")).strip() if body.get("course_title") else None

    if not subject or not message:
        raise HTTPException(status_code=400, detail="Both Subject and Query Message are required.")

    # Determine visibility based on user role as required
    if user["role"] == "teacher":
        visibility = "admin_only"
    else:
        visibility = "teachers_and_admin"

    ticket_id = f"TKT-{datetime.now().strftime('%y%m')}-{uuid.uuid4().hex[:4].upper()}"

    # Generate Gemini AI answer
    ai_response = answer_support_query(
        ticket_id=ticket_id,
        user_name=user["full_name"],
        user_role=user["role"],
        subject=subject,
        message=message,
        course_title=course_title
    )

    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO support_queries (
                ticket_id, user_id, user_role, user_name, user_email,
                course_id, course_title, subject, category, message,
                ai_response, status, visibility
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'open', ?)
        """, (
            ticket_id, user["user_id"], user["role"], user["full_name"], user.get("email"),
            course_id, course_title, subject, category, message,
            ai_response, visibility
        ))

        # Collect Admin IDs
        cursor.execute("SELECT id FROM users WHERE role = 'department_admin'")
        admin_ids = [a["id"] for a in cursor.fetchall()]

        # If student query, collect course teacher ID
        teacher_id = None
        if user["role"] == "student" and course_id:
            cursor.execute("SELECT teacher_id FROM courses WHERE id = ?", (course_id,))
            t_row = cursor.fetchone()
            if t_row:
                teacher_id = t_row["teacher_id"]

    # Alert Admin (outside first connection)
    for aid in admin_ids:
        create_notification(
            aid,
            f"New {user['role'].capitalize()} Query #{ticket_id}",
            f"{user['full_name']} raised: '{subject}'. Immediate Gemini AI answer delivered.",
            "/department?tab=queries",
            "system"
        )

    # Alert Course Teacher if applicable
    if teacher_id:
        create_notification(
            teacher_id,
            f"Student Query #{ticket_id} ({course_title or 'Course'})",
            f"{user['full_name']} asked: '{subject}'.",
            "/teacher",
            "course"
        )

    return JSONResponse({
        "status": "success",
        "ticket_id": ticket_id,
        "ai_response": ai_response,
        "visibility": visibility,
        "message": "Query registered successfully."
    })

@router.get("/api/queries/my")
async def get_my_queries(request: Request):
    """Returns queries raised by the logged in student or teacher."""
    user = get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Unauthorized")

    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT * FROM support_queries 
            WHERE user_id = ? 
            ORDER BY created_at DESC 
            LIMIT 50
        """, (user["user_id"],))
        rows = [dict(r) for r in cursor.fetchall()]

    return JSONResponse({"status": "success", "count": len(rows), "data": rows})

@router.get("/api/queries/feed")
async def get_queries_feed(request: Request, status_filter: str = Query("all")):
    """
    Returns queries based on strict role authorization:
      - Admin: Sees ALL queries (both student & teacher).
      - Teacher: Sees ONLY student queries (visibility == 'teachers_and_admin') and their own.
      - Student: Sees ONLY their own.
    """
    user = get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Unauthorized")

    with get_db() as conn:
        cursor = conn.cursor()
        query_sql = "SELECT * FROM support_queries WHERE "
        params = []

        if user["role"] == "department_admin":
            query_sql += "1=1 "
        elif user["role"] == "teacher":
            query_sql += "(visibility = 'teachers_and_admin' OR user_id = ?) "
            params.append(user["user_id"])
        else:
            query_sql += "user_id = ? "
            params.append(user["user_id"])

        if status_filter in ["open", "replied", "resolved"]:
            query_sql += "AND status = ? "
            params.append(status_filter)

        query_sql += "ORDER BY created_at DESC LIMIT 100"
        cursor.execute(query_sql, tuple(params))
        queries = [dict(r) for r in cursor.fetchall()]

    return JSONResponse({"status": "success", "count": len(queries), "data": queries})

@router.post("/api/queries/reply")
async def reply_to_query(request: Request):
    """
    Allows Admin to reply to any query, and Teachers to reply to student queries.
    """
    user = get_current_user(request)
    if not user or user["role"] not in ["department_admin", "teacher"]:
        raise HTTPException(status_code=403, detail="Unauthorized to reply to queries.")

    try:
        body = await request.json()
    except Exception:
        form = await request.form()
        body = dict(form)

    ticket_id = str(body.get("ticket_id", "")).strip()
    reply_text = str(body.get("reply_text", "")).strip()
    new_status = str(body.get("status", "replied")).strip()

    if not ticket_id or not reply_text:
        raise HTTPException(status_code=400, detail="Ticket ID and Reply Text are required.")

    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM support_queries WHERE ticket_id = ?", (ticket_id,))
        ticket = cursor.fetchone()
        if not ticket:
            raise HTTPException(status_code=404, detail="Ticket not found.")

        # Teacher cannot reply to teacher private queries
        if user["role"] == "teacher" and ticket["visibility"] == "admin_only":
            raise HTTPException(status_code=403, detail="Teacher queries are private to the Administrator.")

        cursor.execute("""
            UPDATE support_queries 
            SET admin_reply = ?, replied_by = ?, replied_at = CURRENT_TIMESTAMP, status = ?
            WHERE ticket_id = ?
        """, (reply_text, f"{user['full_name']} ({user['role'].replace('_', ' ')})", new_status, ticket_id))

        # Retrieve submitter ID
        cursor.execute("SELECT id FROM users WHERE user_id = ?", (ticket["user_id"],))
        sub_user = cursor.fetchone()
        sub_id = sub_user["id"] if sub_user else None

    # Notify outside transaction
    if sub_id:
        create_notification(
            sub_id,
            f"Reply to Ticket #{ticket_id}",
            f"{user['full_name']} responded: '{reply_text[:80]}...'",
            "/profile",
            "system"
        )

    return JSONResponse({
        "status": "success",
        "message": "Official reply submitted successfully.",
        "ticket_id": ticket_id
    })

# ==========================================
# 5. GEMINI AI CONFIGURATION & TESTING API
# ==========================================

@router.post("/api/gemini/save-settings")
async def save_gemini_settings(request: Request):
    """Saves Gemini AI configuration from Governance / Settings."""
    user = get_current_user(request)
    if not user or user["role"] != "department_admin":
        raise HTTPException(status_code=403, detail="Only Department Admin can configure Gemini AI.")

    try:
        body = await request.json()
    except Exception:
        form = await request.form()
        body = dict(form)

    api_key = str(body.get("gemini_api_key", "")).strip()
    model = str(body.get("gemini_model", "gemini-2.5-flash")).strip()
    auto_reply = "1" if body.get("gemini_auto_reply") in [True, "1", "true", "on"] else "0"
    enabled = "1" if body.get("gemini_enabled") in [True, "1", "true", "on"] else "0"

    settings = {
        "gemini_api_key": api_key,
        "gemini_model": model,
        "gemini_auto_reply": auto_reply,
        "gemini_enabled": enabled
    }
    update_system_settings(settings)
    log_audit(user["id"], "UPDATE_GEMINI_SETTINGS", "system_settings", "gemini", f"Updated Gemini AI settings: model={model}, enabled={enabled}")

    return JSONResponse({"status": "success", "message": "Gemini AI settings saved successfully."})

@router.post("/api/gemini/test")
async def test_gemini(request: Request):
    """Tests Gemini connection with provided or saved API key."""
    user = get_current_user(request)
    if not user or user["role"] != "department_admin":
        raise HTTPException(status_code=403, detail="Unauthorized.")

    try:
        body = await request.json()
    except Exception:
        form = await request.form()
        body = dict(form)

    api_key = str(body.get("api_key", "")).strip()
    model = str(body.get("model", "gemini-2.5-flash")).strip()

    if not api_key:
        curr_settings = get_system_settings()
        api_key = curr_settings.get("gemini_api_key", "").strip()

    res = test_gemini_connection(api_key, model=model)
    return JSONResponse(res)
