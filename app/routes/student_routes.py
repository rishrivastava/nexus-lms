from fastapi import APIRouter, Request, Depends, HTTPException, status, Form
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from app.templates_config import templates
from app.database import get_db
from app.auth import get_current_user
from app.utils import extract_youtube_id
from app.gemini_service import explain_quiz_mistake
import os
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

    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET last_active_at = CURRENT_TIMESTAMP WHERE id = ?", (user["id"],))
        
        # Fetch all courses the student is enrolled in
        cursor.execute("""
            SELECT c.id, c.title, c.code, c.department, c.description, c.thumbnail_url,
                   u.full_name as teacher_name,
                   (SELECT COUNT(*) FROM lessons l JOIN modules m ON l.module_id = m.id WHERE m.course_id = c.id) as total_lessons,
                   (SELECT COUNT(*) FROM lesson_progress lp 
                    JOIN lessons l ON lp.lesson_id = l.id 
                    JOIN modules m ON l.module_id = m.id 
                    WHERE m.course_id = c.id AND lp.user_id = ? AND lp.is_completed = 1) as completed_lessons
            FROM enrollments e
            JOIN courses c ON e.course_id = c.id
            JOIN users u ON c.teacher_id = u.id
            WHERE e.user_id = ? AND c.is_published = 1
        """, (user["id"], user["id"]))
        
        courses_raw = cursor.fetchall()
        courses = []
        for cr in courses_raw:
            c = dict(cr)
            tot = c["total_lessons"]
            comp = c["completed_lessons"]
            c["progress_percent"] = round((comp / tot * 100) if tot > 0 else 0)
            courses.append(c)

    return templates.TemplateResponse("student_dashboard.html", {
        "request": request,
        "user": user,
        "courses": courses
    })

@router.get("/course/{course_id}", response_class=HTMLResponse)
async def course_player(request: Request, course_id: int, lesson_id: int = None):
    user = get_current_user(request)
    if not user:
        return RedirectResponse(url="/login", status_code=303)

    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET last_active_at = CURRENT_TIMESTAMP WHERE id = ?", (user["id"],))
        
        # Check course and enrollment
        cursor.execute("""
            SELECT c.*, u.full_name as teacher_name 
            FROM courses c
            JOIN users u ON c.teacher_id = u.id
            WHERE c.id = ?
        """, (course_id,))
        course = cursor.fetchone()
        if not course:
            raise HTTPException(status_code=404, detail="Course not found")

        # Update user's last_active_at timestamp
        cursor.execute("UPDATE users SET last_active_at = CURRENT_TIMESTAMP WHERE id = ?", (user["id"],))

        # Enforce strict assignment: Students can only access courses assigned to them
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

    return templates.TemplateResponse("course_player.html", {
        "request": request,
        "user": user,
        "course": dict(course),
        "modules": modules,
        "active_lesson": active_lesson,
        "youtube_id": youtube_id,
        "quiz_data": quiz_data
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
    """Generates a detailed AI explanation of why the student's answer was wrong using Gemini AI."""
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
            SELECT qq.*, q.lesson_id, c.title as course_title 
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

    return JSONResponse({
        "success": True,
        "question_id": question_id,
        "explanation": explanation_text
    })
