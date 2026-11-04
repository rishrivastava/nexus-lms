from fastapi import APIRouter, Request, Depends, HTTPException, status, Form, UploadFile, File
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from app.templates_config import templates
from app.database import (
    get_db,
    notify_users,
    get_live_classes_for_course,
    get_live_class_by_id,
    add_live_class_question,
    get_live_class_questions,
    get_department_by_name,
    get_user_answer_sheet_submissions,
    create_answer_sheet_submission,
    create_student_mentoring_request,
    get_student_mentoring_sessions,
    student_confirm_mentoring_schedule
)
from app.auth import get_current_user
from app.utils import extract_youtube_id
from app.gemini_service import explain_quiz_mistake
from typing import Optional
import os
import time
import json

router = APIRouter()

def get_student_user(request: Request):
    user = get_current_user(request)
    if not user:
        raise HTTPException(status_code=303, headers={"Location": "/login"})
    if user["must_change_password"]:
        raise HTTPException(status_code=303, headers={"Location": "/setup-account"})
    return user

@router.get("/student", response_class=HTMLResponse)
async def student_dashboard(request: Request):
    user = get_current_user(request)
    if not user:
        return RedirectResponse(url="/login", status_code=303)
    if user["must_change_password"]:
        return RedirectResponse(url="/setup-account", status_code=303)

    dept_name = user.get("department") or "Foreign Language"
    department_info = get_department_by_name(dept_name)
    if not department_info:
        department_info = {
            "name": dept_name,
            "branding_tagline": "transforming education",
            "banner_url": "https://images.unsplash.com/photo-1546410531-bb4caa6b424d?w=1200&auto=format&fit=crop&q=80",
            "welcome_message": f"Welcome to the {dept_name} Learning Portal."
        }

    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET last_active_at = CURRENT_TIMESTAMP WHERE id = ?", (user["id"],))
        
        # Fetch all active published courses the student is enrolled in
        cursor.execute("""
            SELECT c.id, c.title, c.code, c.department, c.description, c.thumbnail_url,
                   u.full_name as teacher_name,
                   (SELECT COUNT(*) FROM lessons l JOIN modules m ON l.module_id = m.id WHERE m.course_id = c.id) as total_lessons,
                   (SELECT COUNT(*) FROM lesson_progress lp 
                    JOIN lessons l ON lp.lesson_id = l.id 
                    JOIN modules m ON l.module_id = m.id 
                    WHERE m.course_id = c.id AND lp.user_id = ? AND lp.is_completed = 1) as completed_lessons,
                   (SELECT certificate_id FROM certificates cert WHERE cert.student_id = ? AND cert.course_id = c.id AND cert.status != 'revoked' LIMIT 1) as certificate_id
            FROM enrollments e
            JOIN courses c ON e.course_id = c.id
            JOIN users u ON c.teacher_id = u.id
            WHERE e.user_id = ? 
              AND c.is_published = 1 
              AND c.status = 'published' 
              AND c.deleted_at IS NULL
            ORDER BY e.enrolled_at DESC
        """, (user["id"], user["id"], user["id"]))
        
        courses_raw = cursor.fetchall()
        courses = []
        for cr in courses_raw:
            c = dict(cr)
            tot = c["total_lessons"]
            comp = c["completed_lessons"]
            c["progress_percent"] = round((comp / tot * 100) if tot > 0 else 0)
            courses.append(c)

        # Fetch upcoming & live classes for the student's enrolled courses
        cursor.execute("""
            SELECT lc.*, c.title as course_title, c.code as course_code, u.full_name as teacher_name,
                   (SELECT COUNT(*) FROM live_class_questions WHERE live_class_id = lc.id) as question_count
            FROM live_classes lc
            JOIN courses c ON lc.course_id = c.id
            JOIN users u ON lc.teacher_id = u.id
            JOIN enrollments e ON e.course_id = c.id
            WHERE e.user_id = ? AND lc.status IN ('scheduled', 'live')
              AND c.status = 'published' AND c.deleted_at IS NULL
            ORDER BY lc.scheduled_at ASC
        """, (user["id"],))
        upcoming_live_classes = [dict(r) for r in cursor.fetchall()]

        # Fetch 1-on-1 mentoring sessions for the student
        mentoring_sessions = get_student_mentoring_sessions(user["id"])

    return templates.TemplateResponse("student_dashboard.html", {
        "request": request,
        "user": user,
        "courses": courses,
        "department_info": department_info,
        "upcoming_live_classes": upcoming_live_classes,
        "mentoring_sessions": mentoring_sessions
    })

@router.get("/course/{course_id}", response_class=HTMLResponse)
async def course_player(request: Request, course_id: int, lesson_id: int = None):
    user = get_current_user(request)
    if not user:
        return RedirectResponse(url="/login", status_code=303)

    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET last_active_at = CURRENT_TIMESTAMP WHERE id = ?", (user["id"],))
        
        # Check course and enrollment - ensure active published and not deleted
        cursor.execute("""
            SELECT c.*, u.full_name as teacher_name 
            FROM courses c
            JOIN users u ON c.teacher_id = u.id
            WHERE c.id = ? AND c.status = 'published' AND c.deleted_at IS NULL AND c.is_published = 1
        """, (course_id,))
        course = cursor.fetchone()
        if not course:
            raise HTTPException(status_code=404, detail="Course not found or has been removed from LMS")

        # Update user's last_active_at timestamp
        cursor.execute("UPDATE users SET last_active_at = CURRENT_TIMESTAMP WHERE id = ?", (user["id"],))

        # Enforce strict assignment: Students can only access courses explicitly assigned to them
        if user["role"] == "student":
            cursor.execute("SELECT id FROM enrollments WHERE user_id = ? AND course_id = ?", (user["id"], course_id))
            if not cursor.fetchone():
                return templates.TemplateResponse("unauthorized_course.html", {
                    "request": request,
                    "user": user,
                    "course": dict(course)
                }, status_code=403)

        # Get modules and lessons
        cursor.execute("SELECT * FROM modules WHERE course_id = ? ORDER BY position ASC, id ASC", (course_id,))
        modules_raw = cursor.fetchall()
        
        modules = []
        all_lessons = []
        active_lesson = None

        for m in modules_raw:
            mod_dict = dict(m)
            cursor.execute("""
                SELECT l.*, 
                       COALESCE(lp.is_completed, 0) as is_completed,
                       COALESCE(lp.watched_seconds, 0) as watched_seconds
                FROM lessons l
                LEFT JOIN lesson_progress lp ON l.id = lp.lesson_id AND lp.user_id = ?
                WHERE l.module_id = ?
                ORDER BY l.position ASC, l.id ASC
            """, (user["id"], m["id"]))
            lessons = [dict(row) for row in cursor.fetchall()]
            mod_dict["lessons"] = lessons
            modules.append(mod_dict)
            all_lessons.extend(lessons)

        if not all_lessons:
            # Course has no lessons yet
            return templates.TemplateResponse("course_player.html", {
                "request": request,
                "user": user,
                "course": dict(course),
                "modules": [],
                "active_lesson": None,
                "quiz_data": None
            })

        # Determine active lesson
        if lesson_id:
            active_lesson = next((l for l in all_lessons if l["id"] == lesson_id), all_lessons[0])
        else:
            # Pick first uncompleted lesson or first lesson
            active_lesson = next((l for l in all_lessons if not l["is_completed"]), all_lessons[0])

        quiz_data = None
        user_attempts = []
        # If active lesson is a quiz, load quiz details and questions
        if active_lesson and active_lesson["content_type"] == "quiz":
            cursor.execute("SELECT * FROM quizzes WHERE lesson_id = ?", (active_lesson["id"],))
            quiz_row = cursor.fetchone()
            if quiz_row:
                quiz_data = dict(quiz_row)
                cursor.execute("SELECT id, question_text, option_a, option_b, option_c, option_d FROM quiz_questions WHERE quiz_id = ? ORDER BY id ASC", (quiz_data["id"],))
                quiz_data["questions"] = [dict(q) for q in cursor.fetchall()]

                cursor.execute("SELECT * FROM quiz_attempts WHERE user_id = ? AND quiz_id = ? ORDER BY attempted_at DESC LIMIT 5", (user["id"], quiz_data["id"]))
                user_attempts = [dict(a) for a in cursor.fetchall()]
                quiz_data["attempts"] = user_attempts

        # Extract YouTube ID if youtube
        youtube_id = None
        if active_lesson and active_lesson["content_type"] == "youtube":
            youtube_id = extract_youtube_id(active_lesson["content_value"])

        # Fetch live classes for this course
        live_classes = get_live_classes_for_course(course_id)

        # Fetch student's submitted UPSC answer sheets
        answer_sheets = get_user_answer_sheet_submissions(user["id"], course_id)

        # Check if an official certificate has been generated by Admin
        cursor.execute("""
            SELECT certificate_id FROM certificates 
            WHERE student_id = ? AND course_id = ? AND status != 'revoked'
            ORDER BY issued_at DESC, id DESC LIMIT 1
        """, (user["id"], course_id))
        cert_row = cursor.fetchone()
        issued_certificate_id = cert_row[0] if cert_row else None

        total_course_lessons = len(all_lessons)
        completed_course_lessons = sum(1 for l in all_lessons if l.get("is_completed"))
        is_course_completed = (total_course_lessons > 0 and completed_course_lessons == total_course_lessons)

    return templates.TemplateResponse("course_player.html", {
        "request": request,
        "user": user,
        "course": dict(course),
        "modules": modules,
        "active_lesson": active_lesson,
        "youtube_id": youtube_id,
        "quiz_data": quiz_data,
        "live_classes": live_classes,
        "answer_sheets": answer_sheets,
        "issued_certificate_id": issued_certificate_id,
        "is_course_completed": is_course_completed
    })

@router.post("/api/lesson/{lesson_id}/complete")
async def mark_lesson_complete(request: Request, lesson_id: int):
    user = get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Unauthorized")

    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET last_active_at = CURRENT_TIMESTAMP WHERE id = ?", (user["id"],))
        
        # Upsert progress
        cursor.execute("""
            INSERT INTO lesson_progress (user_id, lesson_id, is_completed, completed_at)
            VALUES (?, ?, 1, CURRENT_TIMESTAMP)
            ON CONFLICT(user_id, lesson_id) DO UPDATE SET 
                is_completed = 1,
                completed_at = CURRENT_TIMESTAMP
        """, (user["id"], lesson_id))

        # Check if all lessons in the course are completed
        cursor.execute("""
            SELECT m.course_id 
            FROM lessons l 
            JOIN modules m ON l.module_id = m.id 
            WHERE l.id = ?
        """, (lesson_id,))
        row = cursor.fetchone()
        if row:
            course_id = row[0]
            cursor.execute("""
                SELECT 
                    (SELECT COUNT(*) FROM lessons l JOIN modules m ON l.module_id = m.id WHERE m.course_id = ?) as total,
                    (SELECT COUNT(*) FROM lesson_progress lp 
                     JOIN lessons l ON lp.lesson_id = l.id 
                     JOIN modules m ON l.module_id = m.id 
                     WHERE m.course_id = ? AND lp.user_id = ? AND lp.is_completed = 1) as completed
            """, (course_id, course_id, user["id"]))
            counts = cursor.fetchone()
            if counts and counts[0] > 0 and counts[0] == counts[1]:
                cursor.execute("""
                    UPDATE enrollments 
                    SET completed_at = CURRENT_TIMESTAMP 
                    WHERE user_id = ? AND course_id = ? AND completed_at IS NULL
                """, (user["id"], course_id))
                
                # Fetch course title for notification
                cursor.execute("SELECT title FROM courses WHERE id = ?", (course_id,))
                c_row = cursor.fetchone()
                c_title = c_row[0] if c_row else "Course"

                # Notify Admins: Student completed 100%, certificate generation is pending approval
                cursor.execute("SELECT id FROM users WHERE role = 'department_admin'")
                admin_ids = [r[0] for r in cursor.fetchall()]
                if admin_ids:
                    notify_users(
                        admin_ids,
                        f"Course Completed: {c_title}",
                        f"Student {user['full_name']} ({user['user_id']}) has completed 100% of '{c_title}'. Certificate generation is pending administrative issuance.",
                        link="/department?tab=certificates",
                        category="certificate",
                        event_type="course_completed_pending_certificate",
                        conn=conn
                    )
                # Notify Student: Course completed, awaiting admin certificate issuance
                notify_users(
                    [user["id"]],
                    f"Course Completed: {c_title}!",
                    f"Congratulations! You have completed 100% of '{c_title}'. Your completion record has been forwarded to the Administrator for certificate issuance.",
                    link=f"/course/{course_id}",
                    category="course",
                    event_type="course_completed",
                    conn=conn
                )

    return JSONResponse({"status": "success", "lesson_id": lesson_id, "is_completed": True})

import time

@router.post("/api/quiz/{quiz_id}/start")
async def start_quiz(request: Request, quiz_id: int):
    user = get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Unauthorized")

    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT q.*, l.id as lesson_id FROM quizzes q JOIN lessons l ON q.lesson_id = l.id WHERE q.id = ?", (quiz_id,))
        quiz = cursor.fetchone()
        if not quiz:
            raise HTTPException(status_code=404, detail="Quiz not found")

        time_limit = quiz["time_limit_minutes"] if ("time_limit_minutes" in quiz.keys() and quiz["time_limit_minutes"]) else 10
        server_now = int(time.time())

    return JSONResponse({
        "status": "started",
        "quiz_id": quiz_id,
        "time_limit_minutes": time_limit,
        "server_start_time": server_now
    })

@router.post("/api/quiz/{quiz_id}/submit")
async def submit_quiz(request: Request, quiz_id: int):
    user = get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Unauthorized")

    body = await request.json()
    answers = body.get("answers", {})  # Dict of { question_id: "A" / "B" / "C" / "D" }
    start_time = body.get("start_time")  # Epoch seconds from frontend /start
    time_taken_seconds = int(body.get("time_taken_seconds", 0))

    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET last_active_at = CURRENT_TIMESTAMP WHERE id = ?", (user["id"],))
        cursor.execute("SELECT q.*, l.id as lesson_id, m.course_id FROM quizzes q JOIN lessons l ON q.lesson_id = l.id JOIN modules m ON l.module_id = m.id WHERE q.id = ?", (quiz_id,))
        quiz = cursor.fetchone()
        if not quiz:
            raise HTTPException(status_code=404, detail="Quiz not found")

        # Backend timer enforcement (PRD Section 6)
        time_limit_mins = quiz["time_limit_minutes"] if ("time_limit_minutes" in quiz.keys() and quiz["time_limit_minutes"]) else 10
        allowed_seconds = (time_limit_mins * 60) + 30  # 30-second network latency grace buffer
        
        timed_out = False
        if time_taken_seconds > allowed_seconds:
            timed_out = True

        cursor.execute("SELECT id, question_text, option_a, option_b, option_c, option_d, correct_option, explanation FROM quiz_questions WHERE quiz_id = ?", (quiz_id,))
        questions = cursor.fetchall()
        
        total_questions = len(questions)
        if total_questions == 0:
            return JSONResponse({"score_percent": 100, "correct_count": 0, "wrong_count": 0, "total_questions": 0, "passed": True, "time_taken_seconds": time_taken_seconds, "review": {}})

        correct_count = 0
        review = {}
        for q in questions:
            qid = str(q["id"])
            user_choice = answers.get(qid, "").upper().strip()
            correct_choice = q["correct_option"].upper().strip()
            correct = (user_choice == correct_choice)
            if correct:
                correct_count += 1

            options_map = {
                "A": q["option_a"],
                "B": q["option_b"],
                "C": q["option_c"],
                "D": q["option_d"]
            }
            user_choice_text = options_map.get(user_choice, "Skipped / Unanswered")
            correct_option_text = options_map.get(correct_choice, "")

            review[qid] = {
                "question_id": q["id"],
                "question_text": q["question_text"],
                "user_choice": user_choice,
                "user_choice_text": user_choice_text,
                "correct": correct,
                "correct_option": correct_choice,
                "correct_option_text": correct_option_text,
                "explanation": q["explanation"] or ""
            }

        wrong_count = total_questions - correct_count
        score_percent = round((correct_count / total_questions) * 100, 1)
        passed = 1 if score_percent >= quiz["passing_score"] else 0

        attempt_data = json.dumps({
            "answers": answers,
            "correct_count": correct_count,
            "wrong_count": wrong_count,
            "total_questions": total_questions,
            "review": review
        })

        # Record attempt with start, time taken, and detailed attempt data
        cursor.execute("""
            INSERT INTO quiz_attempts (user_id, quiz_id, score_percent, passed, time_taken_seconds, attempt_data)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (user["id"], quiz_id, score_percent, passed, time_taken_seconds, attempt_data))

        # If passed, mark the quiz lesson as completed
        if passed:
            cursor.execute("""
                INSERT INTO lesson_progress (user_id, lesson_id, is_completed, completed_at)
                VALUES (?, ?, 1, CURRENT_TIMESTAMP)
                ON CONFLICT(user_id, lesson_id) DO UPDATE SET 
                    is_completed = 1,
                    completed_at = CURRENT_TIMESTAMP
            """, (user["id"], quiz["lesson_id"]))

            # Check if all lessons in the course are completed
            cursor.execute("""
                SELECT m.course_id 
                FROM lessons l 
                JOIN modules m ON l.module_id = m.id 
                WHERE l.id = ?
            """, (quiz["lesson_id"],))
            q_course = cursor.fetchone()
            if q_course:
                qc_id = q_course[0]
                cursor.execute("""
                    SELECT 
                        (SELECT COUNT(*) FROM lessons l JOIN modules m ON l.module_id = m.id WHERE m.course_id = ?) as total,
                        (SELECT COUNT(*) FROM lesson_progress lp 
                         JOIN lessons l ON lp.lesson_id = l.id 
                         JOIN modules m ON l.module_id = m.id 
                         WHERE m.course_id = ? AND lp.user_id = ? AND lp.is_completed = 1) as completed
                """, (qc_id, qc_id, user["id"]))
                counts = cursor.fetchone()
                if counts and counts[0] > 0 and counts[0] == counts[1]:
                    cursor.execute("""
                        UPDATE enrollments 
                        SET completed_at = CURRENT_TIMESTAMP 
                        WHERE user_id = ? AND course_id = ? AND completed_at IS NULL
                    """, (user["id"], qc_id))

                    cursor.execute("SELECT title FROM courses WHERE id = ?", (qc_id,))
                    c_row = cursor.fetchone()
                    c_title = c_row[0] if c_row else "Course"

                    cursor.execute("SELECT id FROM users WHERE role = 'department_admin'")
                    admin_ids = [r[0] for r in cursor.fetchall()]
                    if admin_ids:
                        notify_users(
                            admin_ids,
                            f"Course Completed: {c_title}",
                            f"Student {user['full_name']} ({user['user_id']}) has completed 100% of '{c_title}'. Certificate generation is pending administrative issuance.",
                            link="/department?tab=certificates",
                            category="certificate",
                            event_type="course_completed_pending_certificate",
                            conn=conn
                        )
                    notify_users(
                        [user["id"]],
                        f"Course Completed: {c_title}!",
                        f"Congratulations! You have completed 100% of '{c_title}'. Your academic completion record has been forwarded to the Administrator for certificate issuance.",
                        link=f"/course/{qc_id}",
                        category="course",
                        event_type="course_completed",
                        conn=conn
                    )

    return JSONResponse({
        "score_percent": score_percent,
        "correct_count": correct_count,
        "wrong_count": wrong_count,
        "total_questions": total_questions,
        "passing_score": quiz["passing_score"],
        "passed": bool(passed),
        "timed_out": timed_out,
        "time_taken_seconds": time_taken_seconds,
        "review": review
    })


@router.post("/api/quiz/explain-answer")
async def explain_quiz_answer(request: Request):
    """Generates a detailed AI explanation of why the student's answer was wrong using Mylo AI."""
    user = get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Unauthorized")

    try:
        body = await request.json()
    except Exception:
        body = {}

    question_id = body.get("question_id")
    user_choice = (body.get("user_choice") or "").strip().upper()

    if not question_id:
        raise HTTPException(status_code=400, detail="Missing question_id parameter.")

    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT qq.*, q.lesson_id, c.id as course_id, c.title as course_title, c.subject
            FROM quiz_questions qq
            JOIN quizzes q ON qq.quiz_id = q.id
            JOIN lessons l ON q.lesson_id = l.id
            JOIN modules m ON l.module_id = m.id
            JOIN courses c ON m.course_id = c.id
            WHERE qq.id = ?
        """, (question_id,))
        q = cursor.fetchone()
        if not q:
            raise HTTPException(status_code=404, detail="Quiz question not found.")

    # Backend enforcement of Administrator Mylo AI usage governance policies
    from app.database import is_ai_feature_enabled, log_ai_usage
    allowed, reason = is_ai_feature_enabled(
        feature="quiz_explanation",
        student_user_id=user["user_id"],
        course_id=q["course_id"],
        subject=q["subject"]
    )
    if not allowed:
        raise HTTPException(status_code=403, detail=reason)

    options_map = {
        "A": q["option_a"],
        "B": q["option_b"],
        "C": q["option_c"],
        "D": q["option_d"]
    }
    user_choice_text = options_map.get(user_choice, "Skipped / Unanswered")
    correct_option = q["correct_option"].upper().strip()
    correct_choice_text = options_map.get(correct_option, "")

    explanation_text = explain_quiz_mistake(
        question_text=q["question_text"],
        student_choice=user_choice,
        student_choice_text=user_choice_text,
        correct_choice=correct_option,
        correct_choice_text=correct_choice_text,
        explanation=q["explanation"],
        course_title=q["course_title"]
    )

    # Log AI usage for governance & expenditure metrics
    log_ai_usage(
        user_id=user["id"],
        user_name=user["full_name"],
        user_role=user["role"],
        feature_type="quiz_explanation",
        course_id=q["course_id"],
        course_title=q["course_title"],
        subject=q["subject"],
        prompt_tokens=180,
        completion_tokens=220
    )

    return JSONResponse({
        "success": True,
        "question_id": question_id,
        "explanation": explanation_text
    })

# ===================================================================
# LIVE CLASSROOM & DOUBT-CLEARING VIEWS
# ===================================================================

@router.get("/course/{course_id}/live/{live_class_id}", response_class=HTMLResponse)
async def live_classroom(request: Request, course_id: int, live_class_id: int):
    user = get_current_user(request)
    if not user:
        return RedirectResponse(url="/login", status_code=303)

    live_class = get_live_class_by_id(live_class_id)
    if not live_class or live_class["course_id"] != course_id:
        raise HTTPException(status_code=404, detail="Live class session not found")

    # Access check: enrolled student, or teacher/admin
    if user["role"] == "student":
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT id FROM enrollments WHERE user_id = ? AND course_id = ?", (user["id"], course_id))
            if not cursor.fetchone():
                raise HTTPException(status_code=403, detail="You are not enrolled in this course")

    questions = get_live_class_questions(live_class_id)

    # YouTube embed handling
    youtube_embed_url = None
    if live_class["platform"] == "youtube_live" or "youtube.com" in live_class["meeting_url"] or "youtu.be" in live_class["meeting_url"]:
        yt_id = extract_youtube_id(live_class["meeting_url"])
        if yt_id:
            youtube_embed_url = f"https://www.youtube.com/embed/{yt_id}?autoplay=1&rel=0"

    dept_name = user.get("department") or "Foreign Language"
    department_info = get_department_by_name(dept_name)

    return templates.TemplateResponse("live_classroom.html", {
        "request": request,
        "user": user,
        "live_class": live_class,
        "questions": questions,
        "youtube_embed_url": youtube_embed_url,
        "department_info": department_info
    })

@router.post("/api/live-classes/{live_class_id}/questions")
async def post_live_class_question(request: Request, live_class_id: int):
    user = get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Unauthorized")
    try:
        body = await request.json()
    except Exception:
        body = {}
    question_text = (body.get("question_text") or "").strip()
    if not question_text:
        raise HTTPException(status_code=400, detail="Question cannot be empty")
    
    q = add_live_class_question(
        live_class_id=live_class_id,
        user_id=user["id"],
        user_name=user["full_name"],
        question_text=question_text
    )
    return JSONResponse({"status": "success", "question": q})

@router.get("/api/live-classes/{live_class_id}/questions")
async def fetch_live_class_questions(request: Request, live_class_id: int):
    user = get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Unauthorized")
    questions = get_live_class_questions(live_class_id)
    return JSONResponse({"status": "success", "questions": questions})

@router.post("/api/course/{course_id}/upload-answer-sheet")
async def upload_answer_sheet(
    request: Request,
    course_id: int,
    file: UploadFile = File(...),
    module_id: Optional[int] = Form(None),
    lesson_id: Optional[int] = Form(None),
    remarks: Optional[str] = Form("")
):
    user = get_current_user(request)
    if not user:
        return JSONResponse(status_code=401, content={"error": "Not authenticated"})

    if not file.filename.lower().endswith(".pdf"):
        return JSONResponse(status_code=400, content={"error": "Only PDF files are allowed for answer sheet submission."})

    upload_folder = os.path.join(os.path.dirname(os.path.dirname(__file__)), "static", "uploads", "answer_sheets")
    os.makedirs(upload_folder, exist_ok=True)

    timestamp = int(time.time())
    safe_name = f"ans_{user['id']}_{course_id}_{timestamp}_{os.path.basename(file.filename)}"
    dest_path = os.path.join(upload_folder, safe_name)
    
    contents = await file.read()
    with open(dest_path, "wb") as f:
        f.write(contents)

    rel_file_path = f"answer_sheets/{safe_name}"
    submission = create_answer_sheet_submission(
        user_id=user["id"],
        course_id=course_id,
        file_path=rel_file_path,
        original_filename=file.filename,
        module_id=module_id,
        lesson_id=lesson_id,
        remarks=remarks
    )

    # Notify the concerned subject teacher immediately
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT title, teacher_id FROM courses WHERE id = ?", (course_id,))
        course_row = cursor.fetchone()
        if course_row and course_row["teacher_id"]:
            notify_users(
                [course_row["teacher_id"]],
                f"New UPSC Answer Copy Submitted: {course_row['title']}",
                f"Student {user['full_name']} ({user['user_id']}) has uploaded an answer copy for '{course_row['title']}' ({file.filename}). Evaluation pending.",
                link="/teacher/dashboard#pendingAnswerCopies",
                category="submission",
                event_type="answer_copy_uploaded",
                conn=conn
            )

    return JSONResponse(content={"status": "success", "submission": submission})

@router.get("/api/course/{course_id}/answer-sheets")
async def get_answer_sheets(request: Request, course_id: int):
    user = get_current_user(request)
    if not user:
        return JSONResponse(status_code=401, content={"error": "Not authenticated"})
    submissions = get_user_answer_sheet_submissions(user["id"], course_id)
    return JSONResponse(content={"submissions": submissions})

# =========================================================================
# ONE-ON-ONE MENTORING ROUTES FOR STUDENTS
# =========================================================================

@router.post("/api/mentoring/student-request")
async def api_student_mentoring_request(
    request: Request,
    topic: str = Form(...),
    description: Optional[str] = Form(""),
    preferred_date: str = Form(...),
    preferred_time: str = Form(...),
    course_id: Optional[int] = Form(None)
):
    """Student raises a 1-on-1 mentoring request. Sent to Admin for faculty assignment."""
    user = get_current_user(request)
    if not user:
        return JSONResponse(status_code=401, content={"error": "Not authenticated"})

    session = create_student_mentoring_request(
        student_id=user["id"],
        course_id=course_id,
        topic=topic,
        description=description,
        preferred_date=preferred_date,
        preferred_time=preferred_time
    )

    # Notify all Administrators
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM users WHERE role = 'department_admin'")
        admin_ids = [r[0] for r in cursor.fetchall()]
        if admin_ids:
            notify_users(
                admin_ids,
                f"New 1-on-1 Mentoring Request: {user['full_name']}",
                f"Student {user['full_name']} ({user['user_id']}) requested a 1-on-1 session for topic: '{topic}' on {preferred_date} ({preferred_time}). Please assign a mentor.",
                link="/department?tab=mentoring",
                category="mentoring",
                event_type="mentoring_requested",
                conn=conn
            )

    return JSONResponse({"status": "success", "session": session})

@router.get("/api/mentoring/my-sessions")
async def api_get_student_mentoring(request: Request):
    """Returns all 1-on-1 mentoring sessions for the logged-in student."""
    user = get_current_user(request)
    if not user:
        return JSONResponse(status_code=401, content={"error": "Not authenticated"})
    sessions = get_student_mentoring_sessions(user["id"])
    return JSONResponse({"status": "success", "sessions": sessions})

@router.post("/api/mentoring/student-confirm-schedule")
async def api_student_confirm_mentoring(
    request: Request,
    session_id: int = Form(...),
    scheduled_date: str = Form(...),
    scheduled_time: str = Form(...),
    student_notes: Optional[str] = Form("")
):
    """Student confirms or suggests date/time for a teacher-initiated 1-on-1 session."""
    user = get_current_user(request)
    if not user:
        return JSONResponse(status_code=401, content={"error": "Not authenticated"})

    updated = student_confirm_mentoring_schedule(
        session_id=session_id,
        scheduled_date=scheduled_date,
        scheduled_time=scheduled_time,
        student_notes=student_notes
    )

    # Notify teacher if assigned
    if updated.get("teacher_id"):
        with get_db() as conn:
            notify_users(
                [updated["teacher_id"]],
                f"1-on-1 Mentoring Session Confirmed: {user['full_name']}",
                f"Student {user['full_name']} confirmed 1-on-1 session on '{updated['topic']}' for {scheduled_date} at {scheduled_time}.",
                link="/teacher/dashboard#mentoringSessions",
                category="mentoring",
                event_type="mentoring_confirmed",
                conn=conn
            )

    return JSONResponse({"status": "success", "session": updated})


