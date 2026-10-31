from fastapi import APIRouter, Request, Form, UploadFile, File, HTTPException, status, Response
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from app.templates_config import templates
from app.database import get_db, UPLOAD_DIR, log_audit, notify_users
from app.auth import get_current_user
from app.gemini_service import generate_ai_quiz
import os
import shutil
import uuid
import io
import csv
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from typing import Optional

router = APIRouter()

def require_teacher_or_admin(request: Request):
    user = get_current_user(request)
    if not user:
        raise HTTPException(status_code=303, headers={"Location": "/login"})
    if user["role"] not in ["teacher", "department_admin"]:
        raise HTTPException(status_code=403, detail="Only teachers or administrators can access this area.")
    return user

@router.get("/teacher", response_class=HTMLResponse)
async def teacher_dashboard(request: Request):
    user = require_teacher_or_admin(request)
    
    with get_db() as conn:
        cursor = conn.cursor()
        
        # If department admin, can view all courses; if teacher, their courses
        if user["role"] == "department_admin":
            cursor.execute("""
                SELECT c.*, u.full_name as teacher_name,
                       (SELECT COUNT(*) FROM enrollments WHERE course_id = c.id) as enrolled_count,
                       (SELECT COUNT(*) FROM lessons l JOIN modules m ON l.module_id = m.id WHERE m.course_id = c.id) as lesson_count
                FROM courses c
                JOIN users u ON c.teacher_id = u.id
                ORDER BY c.created_at DESC
            """)
        else:
            cursor.execute("""
                SELECT c.*, u.full_name as teacher_name,
                       (SELECT COUNT(*) FROM enrollments WHERE course_id = c.id) as enrolled_count,
                       (SELECT COUNT(*) FROM lessons l JOIN modules m ON l.module_id = m.id WHERE m.course_id = c.id) as lesson_count
                FROM courses c
                JOIN users u ON c.teacher_id = u.id
                WHERE c.teacher_id = ?
                ORDER BY c.created_at DESC
            """, (user["id"],))
            
        courses = [dict(c) for c in cursor.fetchall()]

        # Student queries visible to teachers (visibility == 'teachers_and_admin')
        cursor.execute("""
            SELECT * FROM support_queries 
            WHERE visibility = 'teachers_and_admin' 
            ORDER BY created_at DESC 
            LIMIT 50
        """)
        student_queries = [dict(q) for q in cursor.fetchall()]
        open_student_queries = sum(1 for q in student_queries if q["status"] == "open")

    return templates.TemplateResponse("teacher_dashboard.html", {
        "request": request,
        "user": user,
        "courses": courses,
        "student_queries": student_queries,
        "open_student_queries": open_student_queries
    })

@router.post("/teacher/course/create")
async def create_course(
    request: Request,
    title: str = Form(...),
    code: str = Form(...),
    department: str = Form(...),
    description: str = Form(...),
    subject: str = Form(None),
    thumbnail_url: str = Form(None)
):
    user = require_teacher_or_admin(request)
    
    thumb = thumbnail_url.strip() if thumbnail_url else "https://images.unsplash.com/photo-1516321318423-f06f85e504b3?w=800&auto=format&fit=crop&q=60"
    subj = subject.strip() if subject and subject.strip() else department.strip()

    with get_db() as conn:
        cursor = conn.cursor()
        try:
            cursor.execute("""
                INSERT INTO courses (title, code, department, subject, description, thumbnail_url, teacher_id, is_published, status)
                VALUES (?, ?, ?, ?, ?, ?, ?, 1, 'published')
            """, (title.strip(), code.strip().upper(), department.strip(), subj, description.strip(), thumb, user["id"]))
            course_id = cursor.lastrowid
            log_audit(user["id"], "COURSE_CREATE", "courses", str(course_id), f"Created course {title} ({code})")
        except Exception as e:
            if "UNIQUE constraint failed: courses.code" in str(e):
                raise HTTPException(status_code=400, detail="A course with this code already exists.")
            raise e

    return RedirectResponse(url=f"/teacher/course/{course_id}", status_code=303)

@router.post("/teacher/course/{course_id}/edit")
async def edit_course(
    request: Request,
    course_id: int,
    title: str = Form(...),
    code: str = Form(...),
    department: str = Form(...),
    subject: str = Form(None),
    description: str = Form(...),
    thumbnail_url: str = Form(None),
    status_val: str = Form("published"),
    notify_students: int = Form(0)
):
    user = require_teacher_or_admin(request)
    
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM courses WHERE id = ?", (course_id,))
        course = cursor.fetchone()
        if not course:
            raise HTTPException(status_code=404, detail="Course not found")

        if user["role"] != "department_admin" and course["teacher_id"] != user["id"]:
            raise HTTPException(status_code=403, detail="Permission denied")

        thumb = thumbnail_url.strip() if thumbnail_url else course["thumbnail_url"]
        subj = subject.strip() if subject and subject.strip() else department.strip()
        is_pub = 1 if status_val == "published" else (2 if status_val == "archived" else 0)

        cursor.execute("""
            UPDATE courses 
            SET title = ?, code = ?, department = ?, subject = ?, description = ?, thumbnail_url = ?, is_published = ?, status = ?
            WHERE id = ?
        """, (title.strip(), code.strip().upper(), department.strip(), subj, description.strip(), thumb, is_pub, status_val, course_id))

        log_audit(user["id"], "COURSE_EDIT", "courses", str(course_id), f"Edited course details for {title}")

        if notify_students:
            cursor.execute("SELECT user_id FROM enrollments WHERE course_id = ?", (course_id,))
            enrolled_ids = [r[0] for r in cursor.fetchall()]
            notify_users(enrolled_ids, f"Course Update: {title}", f"The course details and learning materials for '{title}' have been updated.", f"/course/{course_id}", "course", "content_published")

    return RedirectResponse(url=f"/teacher/course/{course_id}?saved=1", status_code=303)

@router.post("/teacher/course/{course_id}/archive")
async def archive_course(request: Request, course_id: int):
    user = require_teacher_or_admin(request)
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM courses WHERE id = ?", (course_id,))
        course = cursor.fetchone()
        if not course:
            raise HTTPException(status_code=404, detail="Course not found")

        if user["role"] != "department_admin" and course["teacher_id"] != user["id"]:
            raise HTTPException(status_code=403, detail="Permission denied")

        cursor.execute("UPDATE courses SET is_published = 2, status = 'archived', archived_at = CURRENT_TIMESTAMP WHERE id = ?", (course_id,))
        
        # Notify enrolled students
        cursor.execute("SELECT user_id FROM enrollments WHERE course_id = ?", (course_id,))
        enrolled_ids = [r[0] for r in cursor.fetchall()]
        notify_users(enrolled_ids, f"Course Archived: {course['title']}", f"The course '{course['title']}' has been archived by the department.", None, "course", "course_status_changed")
        
        log_audit(user["id"], "COURSE_ARCHIVE", "courses", str(course_id), f"Archived course {course['title']} ({len(enrolled_ids)} enrolled students affected)")

    return RedirectResponse(url="/department?tab=courses&course_archived=1", status_code=303)

@router.post("/teacher/course/{course_id}/unpublish")
async def unpublish_course(request: Request, course_id: int):
    user = require_teacher_or_admin(request)
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM courses WHERE id = ?", (course_id,))
        course = cursor.fetchone()
        if not course:
            raise HTTPException(status_code=404, detail="Course not found")

        if user["role"] != "department_admin" and course["teacher_id"] != user["id"]:
            raise HTTPException(status_code=403, detail="Permission denied")

        cursor.execute("UPDATE courses SET is_published = 0, status = 'draft' WHERE id = ?", (course_id,))
        log_audit(user["id"], "COURSE_UNPUBLISH", "courses", str(course_id), f"Unpublished course {course['title']} to draft")

    return RedirectResponse(url=f"/teacher/course/{course_id}?unpublished=1", status_code=303)

@router.post("/teacher/course/{course_id}/delete")
async def delete_course(
    request: Request,
    course_id: int,
    deletion_mode: str = Form("delete") # 'archive', 'unpublish', 'delete'
):
    user = require_teacher_or_admin(request)
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM courses WHERE id = ?", (course_id,))
        course = cursor.fetchone()
        if not course:
            raise HTTPException(status_code=404, detail="Course not found")

        if user["role"] != "department_admin" and course["teacher_id"] != user["id"]:
            raise HTTPException(status_code=403, detail="Permission denied")

        cursor.execute("SELECT user_id FROM enrollments WHERE course_id = ?", (course_id,))
        enrolled_ids = [r[0] for r in cursor.fetchall()]

        if deletion_mode == "archive":
            cursor.execute("UPDATE courses SET is_published = 2, status = 'archived', archived_at = CURRENT_TIMESTAMP WHERE id = ?", (course_id,))
            notify_users(enrolled_ids, f"Course Archived: {course['title']}", f"The course '{course['title']}' has been archived by the department.", None, "course", "course_status_changed")
            log_audit(user["id"], "COURSE_ARCHIVE", "courses", str(course_id), f"Archived course {course['title']} ({len(enrolled_ids)} students)")
        elif deletion_mode == "unpublish":
            cursor.execute("UPDATE courses SET is_published = 0, status = 'draft' WHERE id = ?", (course_id,))
            notify_users(enrolled_ids, f"Course Unpublished: {course['title']}", f"The course '{course['title']}' has been temporarily unpublished.", None, "course", "course_status_changed")
            log_audit(user["id"], "COURSE_UNPUBLISH", "courses", str(course_id), f"Unpublished course {course['title']} to draft")
        else:
            # Soft delete to preserve audit & analytics history without breaking foreign keys
            cursor.execute("UPDATE courses SET is_published = 0, status = 'deleted', deleted_at = CURRENT_TIMESTAMP WHERE id = ?", (course_id,))
            notify_users(enrolled_ids, f"Course Removed: {course['title']}", f"The course '{course['title']}' has been removed from your active curriculum.", None, "course", "course_status_changed")
            log_audit(user["id"], "COURSE_DELETE", "courses", str(course_id), f"Deleted course {course['title']} ({len(enrolled_ids)} enrolled students affected)")

    return RedirectResponse(url="/department?tab=courses&course_deleted=1", status_code=303)

@router.get("/api/course/{course_id}/enrolled-count")
async def get_course_enrolled_count(request: Request, course_id: int):
    user = require_teacher_or_admin(request)
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id, title, code, (SELECT COUNT(*) FROM enrollments WHERE course_id = ?) as count FROM courses WHERE id = ?", (course_id, course_id))
        row = cursor.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Course not found")
        return JSONResponse({"course_id": row["id"], "title": row["title"], "code": row["code"], "enrolled_count": row["count"]})

@router.get("/teacher/course/{course_id}", response_class=HTMLResponse)
async def course_editor(request: Request, course_id: int):
    user = require_teacher_or_admin(request)
    
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM courses WHERE id = ?", (course_id,))
        course = cursor.fetchone()
        if not course:
            raise HTTPException(status_code=404, detail="Course not found")
            
        # Verify ownership unless admin
        if user["role"] != "department_admin" and course["teacher_id"] != user["id"]:
            raise HTTPException(status_code=403, detail="You do not have permission to edit this course.")

        # Get modules and lessons
        cursor.execute("SELECT * FROM modules WHERE course_id = ? ORDER BY position ASC, id ASC", (course_id,))
        modules_raw = cursor.fetchall()
        
        # If course has no modules, auto-create Module 1 so lessons can always be added seamlessly
        if not modules_raw:
            cursor.execute("INSERT INTO modules (course_id, title, position) VALUES (?, 'Module 1: General Lessons', 1)", (course_id,))
            cursor.execute("SELECT * FROM modules WHERE course_id = ? ORDER BY position ASC, id ASC", (course_id,))
            modules_raw = cursor.fetchall()
        
        modules = []
        for m in modules_raw:
            mod_dict = dict(m)
            cursor.execute("""
                SELECT l.*, q.id as quiz_id, q.passing_score,
                       (SELECT COUNT(*) FROM quiz_questions WHERE quiz_id = q.id) as question_count
                FROM lessons l
                LEFT JOIN quizzes q ON l.id = q.lesson_id
                WHERE l.module_id = ?
                ORDER BY l.position ASC, l.id ASC
            """, (m["id"],))
            mod_dict["lessons"] = [dict(l) for l in cursor.fetchall()]
            modules.append(mod_dict)

        cursor.execute("SELECT value FROM system_settings WHERE key = 'allow_teacher_ai_quiz'")
        ai_quiz_row = cursor.fetchone()
        allow_teacher_ai_quiz = ai_quiz_row[0] if ai_quiz_row else "1"

    return templates.TemplateResponse("course_editor.html", {
        "request": request,
        "user": user,
        "course": dict(course),
        "modules": modules,
        "allow_teacher_ai_quiz": allow_teacher_ai_quiz
    })

@router.post("/teacher/course/{course_id}/module")
async def add_module(request: Request, course_id: int, title: str = Form(...)):
    user = require_teacher_or_admin(request)
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT MAX(position) FROM modules WHERE course_id = ?", (course_id,))
        max_pos = cursor.fetchone()[0] or 0
        cursor.execute("INSERT INTO modules (course_id, title, position) VALUES (?, ?, ?)", (course_id, title.strip(), max_pos + 1))
    return RedirectResponse(url=f"/teacher/course/{course_id}", status_code=303)

@router.get("/teacher/module/{module_id}/lesson/youtube")
async def get_youtube_lesson_redirect(request: Request, module_id: int):
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT course_id FROM modules WHERE id = ?", (module_id,))
        row = cursor.fetchone()
        if row:
            return RedirectResponse(url=f"/teacher/course/{row[0]}", status_code=303)
    return RedirectResponse(url="/teacher", status_code=303)

@router.get("/teacher/module/{module_id}/lesson/pdf")
async def get_pdf_lesson_redirect(request: Request, module_id: int):
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT course_id FROM modules WHERE id = ?", (module_id,))
        row = cursor.fetchone()
        if row:
            return RedirectResponse(url=f"/teacher/course/{row[0]}", status_code=303)
    return RedirectResponse(url="/teacher", status_code=303)

@router.get("/teacher/module/{module_id}/lesson/quiz")
async def get_quiz_lesson_redirect(request: Request, module_id: int):
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT course_id FROM modules WHERE id = ?", (module_id,))
        row = cursor.fetchone()
        if row:
            return RedirectResponse(url=f"/teacher/course/{row[0]}", status_code=303)
    return RedirectResponse(url="/teacher", status_code=303)

@router.post("/teacher/course/{course_id}/lesson/youtube")
@router.post("/teacher/course/{course_id}")
async def add_course_level_youtube_lesson(
    request: Request,
    course_id: int,
    title: str = Form(...),
    youtube_url: str = Form(...),
    duration_minutes: int = Form(10),
    module_id: int = Form(None)
):
    require_teacher_or_admin(request)
    with get_db() as conn:
        cursor = conn.cursor()
        target_mod_id = module_id
        if not target_mod_id:
            cursor.execute("SELECT id FROM modules WHERE course_id = ? ORDER BY position ASC, id ASC LIMIT 1", (course_id,))
            mod_row = cursor.fetchone()
            if mod_row:
                target_mod_id = mod_row[0]
            else:
                cursor.execute("INSERT INTO modules (course_id, title, position) VALUES (?, 'Module 1: General Lessons', 1)", (course_id,))
                target_mod_id = cursor.lastrowid

        cursor.execute("SELECT MAX(position) FROM lessons WHERE module_id = ?", (target_mod_id,))
        max_pos = cursor.fetchone()[0] or 0
        cursor.execute("""
            INSERT INTO lessons (module_id, title, content_type, content_value, position, duration_minutes)
            VALUES (?, ?, 'youtube', ?, ?, ?)
        """, (target_mod_id, title.strip(), youtube_url.strip(), max_pos + 1, duration_minutes))

        cursor.execute("SELECT user_id FROM enrollments WHERE course_id = ?", (course_id,))
        enrolled_ids = [r[0] for r in cursor.fetchall()]
        notify_users(enrolled_ids, f"New Lecture Video: {title.strip()}", "A new video lecture has been added to your curriculum.", f"/course/{course_id}", "course", "content_published", conn=conn)

    return RedirectResponse(url=f"/teacher/course/{course_id}", status_code=303)

@router.post("/teacher/module/{module_id}/lesson/youtube")
async def add_youtube_lesson(
    request: Request,
    module_id: int,
    course_id: int = Form(...),
    title: str = Form(...),
    youtube_url: str = Form(...),
    duration_minutes: int = Form(10)
):
    require_teacher_or_admin(request)
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT MAX(position) FROM lessons WHERE module_id = ?", (module_id,))
        max_pos = cursor.fetchone()[0] or 0
        cursor.execute("""
            INSERT INTO lessons (module_id, title, content_type, content_value, position, duration_minutes)
            VALUES (?, ?, 'youtube', ?, ?, ?)
        """, (module_id, title.strip(), youtube_url.strip(), max_pos + 1, duration_minutes))

        # Notify enrolled students
        cursor.execute("SELECT user_id FROM enrollments WHERE course_id = ?", (course_id,))
        enrolled_ids = [r[0] for r in cursor.fetchall()]
        notify_users(enrolled_ids, f"New Lecture Video: {title.strip()}", f"A new video lecture has been added to your curriculum.", f"/course/{course_id}", "course", "content_published", conn=conn)

    return RedirectResponse(url=f"/teacher/course/{course_id}", status_code=303)

@router.post("/teacher/course/{course_id}/lesson/pdf")
async def add_course_level_pdf_lesson(
    request: Request,
    course_id: int,
    title: str = Form(...),
    pdf_file: UploadFile = File(...),
    duration_minutes: int = Form(15),
    module_id: int = Form(None)
):
    require_teacher_or_admin(request)
    ext = os.path.splitext(pdf_file.filename)[1].lower()
    if ext != ".pdf":
        raise HTTPException(status_code=400, detail="Only PDF files are supported.")
        
    safe_filename = f"{uuid.uuid4().hex}_{pdf_file.filename}"
    file_path = os.path.join(UPLOAD_DIR, safe_filename)
    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(pdf_file.file, buffer)

    with get_db() as conn:
        cursor = conn.cursor()
        target_mod_id = module_id
        if not target_mod_id:
            cursor.execute("SELECT id FROM modules WHERE course_id = ? ORDER BY position ASC, id ASC LIMIT 1", (course_id,))
            mod_row = cursor.fetchone()
            if mod_row:
                target_mod_id = mod_row[0]
            else:
                cursor.execute("INSERT INTO modules (course_id, title, position) VALUES (?, 'Module 1: General Lessons', 1)", (course_id,))
                target_mod_id = cursor.lastrowid

        cursor.execute("SELECT MAX(position) FROM lessons WHERE module_id = ?", (target_mod_id,))
        max_pos = cursor.fetchone()[0] or 0
        cursor.execute("""
            INSERT INTO lessons (module_id, title, content_type, content_value, position, duration_minutes)
            VALUES (?, ?, 'pdf', ?, ?, ?)
        """, (target_mod_id, title.strip(), safe_filename, max_pos + 1, duration_minutes))

        cursor.execute("SELECT user_id FROM enrollments WHERE course_id = ?", (course_id,))
        enrolled_ids = [r[0] for r in cursor.fetchall()]
        notify_users(enrolled_ids, f"New Reading Material: {title.strip()}", "A new PDF study document has been uploaded.", f"/course/{course_id}", "course", "content_published", conn=conn)

    return RedirectResponse(url=f"/teacher/course/{course_id}", status_code=303)

@router.post("/teacher/module/{module_id}/lesson/pdf")
async def add_pdf_lesson(
    request: Request,
    module_id: int,
    course_id: int = Form(...),
    title: str = Form(...),
    pdf_file: UploadFile = File(...),
    duration_minutes: int = Form(15)
):
    require_teacher_or_admin(request)
    
    # Save PDF securely
    ext = os.path.splitext(pdf_file.filename)[1].lower()
    if ext != ".pdf":
        raise HTTPException(status_code=400, detail="Only PDF files are supported.")
        
    safe_filename = f"{uuid.uuid4().hex}_{pdf_file.filename}"
    file_path = os.path.join(UPLOAD_DIR, safe_filename)
    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(pdf_file.file, buffer)

    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT MAX(position) FROM lessons WHERE module_id = ?", (module_id,))
        max_pos = cursor.fetchone()[0] or 0
        cursor.execute("""
            INSERT INTO lessons (module_id, title, content_type, content_value, position, duration_minutes)
            VALUES (?, ?, 'pdf', ?, ?, ?)
        """, (module_id, title.strip(), safe_filename, max_pos + 1, duration_minutes))

        # Notify enrolled students
        cursor.execute("SELECT user_id FROM enrollments WHERE course_id = ?", (course_id,))
        enrolled_ids = [r[0] for r in cursor.fetchall()]
        notify_users(enrolled_ids, f"New Reading Material: {title.strip()}", f"A new PDF study document has been uploaded.", f"/course/{course_id}", "course", "content_published", conn=conn)

    return RedirectResponse(url=f"/teacher/course/{course_id}", status_code=303)

@router.post("/teacher/module/{module_id}/lesson/quiz")
async def add_quiz_lesson(
    request: Request,
    module_id: int,
    course_id: int = Form(...),
    title: str = Form(...),
    passing_score: int = Form(70),
    duration_minutes: int = Form(10)
):
    require_teacher_or_admin(request)
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT MAX(position) FROM lessons WHERE module_id = ?", (module_id,))
        max_pos = cursor.fetchone()[0] or 0
        cursor.execute("""
            INSERT INTO lessons (module_id, title, content_type, content_value, position, duration_minutes)
            VALUES (?, ?, 'quiz', 'Interactive Quiz', ?, ?)
        """, (module_id, title.strip(), max_pos + 1, duration_minutes))
        lesson_id = cursor.lastrowid
        
        cursor.execute("""
            INSERT INTO quizzes (lesson_id, passing_score, time_limit_minutes)
            VALUES (?, ?, ?)
        """, (lesson_id, passing_score, duration_minutes))

        # Notify enrolled students
        cursor.execute("SELECT user_id FROM enrollments WHERE course_id = ?", (course_id,))
        enrolled_ids = [r[0] for r in cursor.fetchall()]
        notify_users(enrolled_ids, f"New Timed Assessment: {title.strip()}", f"A new {duration_minutes}-minute quiz assessment is now available.", f"/course/{course_id}", "quiz", "quiz_published", conn=conn)

    return RedirectResponse(url=f"/teacher/course/{course_id}", status_code=303)

@router.post("/teacher/quiz/{quiz_id}/question")
async def add_quiz_question(
    request: Request,
    quiz_id: int,
    course_id: int = Form(...),
    question_text: str = Form(...),
    option_a: str = Form(...),
    option_b: str = Form(...),
    option_c: str = Form(...),
    option_d: str = Form(...),
    correct_option: str = Form(...),
    explanation: str = Form(None)
):
    require_teacher_or_admin(request)
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO quiz_questions (quiz_id, question_text, option_a, option_b, option_c, option_d, correct_option, explanation)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            quiz_id,
            question_text.strip(),
            option_a.strip(),
            option_b.strip(),
            option_c.strip(),
            option_d.strip(),
            correct_option.strip().upper(),
            explanation.strip() if explanation else ""
        ))
    return RedirectResponse(url=f"/teacher/course/{course_id}", status_code=303)


# =========================================================================
# SPREADSHEET & GEMINI AI QUIZ CREATION
# =========================================================================

def parse_quiz_spreadsheet(file_bytes: bytes, filename: str) -> list:
    """Parses .xlsx, .xls, or .csv and extracts list of question dictionaries."""
    filename_lower = (filename or "").lower()
    raw_rows = []
    
    if filename_lower.endswith(".xlsx") or filename_lower.endswith(".xls"):
        wb = openpyxl.load_workbook(io.BytesIO(file_bytes), data_only=True)
        sheet = wb.active
        for row in sheet.iter_rows(values_only=True):
            if any(cell is not None and str(cell).strip() != "" for cell in row):
                raw_rows.append([str(c).strip() if c is not None else "" for c in row])
    else: # assume CSV
        try:
            text = file_bytes.decode("utf-8-sig")
        except UnicodeDecodeError:
            text = file_bytes.decode("latin1", errors="replace")
        reader = csv.reader(io.StringIO(text))
        for row in reader:
            if any(cell.strip() != "" for cell in row):
                raw_rows.append([cell.strip() for cell in row])

    if not raw_rows:
        raise ValueError("Uploaded file is empty.")

    header = [c.lower() for c in raw_rows[0]]
    def find_col(aliases, default_idx=None):
        for idx, col in enumerate(header):
            for a in aliases:
                if a in col:
                    return idx
        return default_idx

    q_idx = find_col(["question", "prompt", "item"], default_idx=0)
    opt_a_idx = find_col(["option a", "opt a", "choice a", "option_a"], default_idx=1)
    opt_b_idx = find_col(["option b", "opt b", "choice b", "option_b"], default_idx=2)
    opt_c_idx = find_col(["option c", "opt c", "choice c", "option_c"], default_idx=3)
    opt_d_idx = find_col(["option d", "opt d", "choice d", "option_d"], default_idx=4)
    ans_idx = find_col(["correct", "answer", "key", "solution"], default_idx=5)
    exp_idx = find_col(["explanation", "note", "rationale", "reason"], default_idx=6)

    is_header = any(keyword in " ".join(header) for keyword in ["question", "option", "choice", "correct", "answer"])
    data_rows = raw_rows[1:] if is_header else raw_rows

    questions = []
    for r in data_rows:
        def get_val(idx):
            return r[idx].strip() if (idx is not None and idx < len(r)) else ""

        q_text = get_val(q_idx)
        opt_a = get_val(opt_a_idx)
        opt_b = get_val(opt_b_idx)
        opt_c = get_val(opt_c_idx)
        opt_d = get_val(opt_d_idx)
        ans = get_val(ans_idx).upper()
        exp = get_val(exp_idx)

        if ans not in ["A", "B", "C", "D"]:
            if ans in ["1", "OPTION A", "OPT A"] or (ans and ans.lower() == opt_a.lower()):
                ans = "A"
            elif ans in ["2", "OPTION B", "OPT B"] or (ans and ans.lower() == opt_b.lower()):
                ans = "B"
            elif ans in ["3", "OPTION C", "OPT C"] or (ans and ans.lower() == opt_c.lower()):
                ans = "C"
            elif ans in ["4", "OPTION D", "OPT D"] or (ans and ans.lower() == opt_d.lower()):
                ans = "D"
            else:
                ans = "A"

        if q_text and (opt_a or opt_b):
            if not opt_c: opt_c = "None of the above"
            if not opt_d: opt_d = "All of the above"
            questions.append({
                "question_text": q_text,
                "option_a": opt_a,
                "option_b": opt_b,
                "option_c": opt_c,
                "option_d": opt_d,
                "correct_option": ans,
                "explanation": exp
            })

    return questions


@router.get("/teacher/quiz/template/download")
async def download_quiz_template(request: Request, format: str = "xlsx"):
    """Provides a downloadable sample template for quiz uploads in .xlsx or .csv format."""
    require_teacher_or_admin(request)
    
    sample_rows = [
        ["What is the Spanish word for 'Water'?", "Agua", "Fuego", "Tierra", "Aire", "A", "'Agua' is the standard Spanish translation of 'water'."],
        ["Which of the following is the German word for 'Thank you'?", "Bitte", "Danke", "Guten Tag", "Hallo", "B", "'Danke' expresses gratitude in German."],
        ["In French, which is the correct definite article for feminine singular nouns?", "Le", "Les", "La", "Un", "C", "'La' is the singular feminine article (e.g., la pomme)."],
        ["What does the Spanish phrase '¿Cómo estás?' mean in English?", "What time is it?", "How are you?", "Where are you going?", "How much is it?", "B", "'¿Cómo estás?' is the informal way to ask 'How are you?'."],
        ["Which verb means 'to be' in French?", "Avoir", "Faire", "Être", "Aller", "C", "'Être' is the fundamental French verb for 'to be'."]
    ]
    
    if format.lower() == "csv":
        out = io.StringIO()
        writer = csv.writer(out)
        writer.writerow(["Question", "Option A", "Option B", "Option C", "Option D", "Correct Option", "Explanation"])
        for r in sample_rows:
            writer.writerow(r)
        csv_bytes = "\ufeff" + out.getvalue()
        return Response(
            content=csv_bytes.encode("utf-8"),
            media_type="text/csv",
            headers={"Content-Disposition": 'attachment; filename="nexus_lms_quiz_template.csv"'}
        )
    else:
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Quiz Template"
        
        headers = ["Question", "Option A", "Option B", "Option C", "Option D", "Correct Option", "Explanation"]
        ws.append(headers)
        
        header_fill = PatternFill(start_color="1E293B", end_color="1E293B", fill_type="solid")
        header_font = Font(name="Calibri", size=11, bold=True, color="FFFFFF")
        align_center = Alignment(horizontal="center", vertical="center", wrap_text=True)
        align_left = Alignment(horizontal="left", vertical="center", wrap_text=True)
        
        for col_idx, col_name in enumerate(headers, 1):
            cell = ws.cell(row=1, column=col_idx)
            cell.fill = header_fill
            cell.font = header_font
            cell.alignment = align_center if col_name == "Correct Option" else align_left
        
        for r in sample_rows:
            ws.append(r)
            
        for row in ws.iter_rows(min_row=2, max_row=len(sample_rows)+1):
            for cell in row:
                cell.font = Font(name="Calibri", size=10)
                if cell.column == 6:
                    cell.alignment = Alignment(horizontal="center", vertical="center")
                    cell.font = Font(name="Calibri", size=10, bold=True)
                else:
                    cell.alignment = Alignment(horizontal="left", vertical="center")
                    
        col_widths = {"A": 45, "B": 22, "C": 22, "D": 22, "E": 22, "F": 16, "G": 45}
        for col_letter, width in col_widths.items():
            ws.column_dimensions[col_letter].width = width
            
        out = io.BytesIO()
        wb.save(out)
        out.seek(0)
        
        return Response(
            content=out.getvalue(),
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": 'attachment; filename="nexus_lms_quiz_template.xlsx"'}
        )


async def upload_spreadsheet_quiz(
    request: Request,
    file: UploadFile = File(...),
    title: Optional[str] = None,
    passing_score: int = 70,
    duration_minutes: int = 10,
    module_id: Optional[int] = None,
    course_id: Optional[int] = None
):
    """Parses an uploaded .xlsx, .xls, or .csv spreadsheet and generates a full quiz lesson with questions."""
    user = require_teacher_or_admin(request)
    
    # Handle Form parameter defaults if invoked directly
    if hasattr(module_id, "default"):
        module_id = None
    elif module_id is not None:
        try:
            module_id = int(module_id)
        except (ValueError, TypeError):
            module_id = None

    if hasattr(course_id, "default"):
        course_id = None
    elif course_id is not None:
        try:
            course_id = int(course_id)
        except (ValueError, TypeError):
            course_id = None

    if hasattr(title, "default"):
        title = None

    if hasattr(passing_score, "default"):
        passing_score = 70
    else:
        passing_score = int(passing_score)

    if hasattr(duration_minutes, "default"):
        duration_minutes = 10
    else:
        duration_minutes = int(duration_minutes)

    path_params = request.path_params
    if not course_id and "course_id" in path_params:
        course_id = int(path_params["course_id"])
    if not module_id and "module_id" in path_params:
        module_id = int(path_params["module_id"])
        
    with get_db() as conn:
        cursor = conn.cursor()
        
        if not course_id and module_id:
            cursor.execute("SELECT course_id FROM modules WHERE id = ?", (module_id,))
            m_row = cursor.fetchone()
            if m_row:
                course_id = m_row[0]
                
        if not course_id:
            raise HTTPException(status_code=400, detail="Invalid course identifier.")
            
        if not module_id:
            cursor.execute("SELECT id FROM modules WHERE course_id = ? ORDER BY position ASC LIMIT 1", (course_id,))
            m_row = cursor.fetchone()
            if m_row:
                module_id = m_row[0]
            else:
                cursor.execute("INSERT INTO modules (course_id, title, position) VALUES (?, 'Module 1: Assessments', 1)", (course_id,))
                module_id = cursor.lastrowid

    file_bytes = await file.read()
    try:
        parsed_questions = parse_quiz_spreadsheet(file_bytes, file.filename)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to parse spreadsheet quiz: {str(e)}")

    if not parsed_questions:
        raise HTTPException(status_code=400, detail="No valid questions found in file. Please ensure columns: Question, Option A, Option B, Option C, Option D, Correct Option.")

    final_title = title.strip() if (title and title.strip()) else os.path.splitext(file.filename)[0].replace("_", " ").title()

    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT MAX(position) FROM lessons WHERE module_id = ?", (module_id,))
        max_pos = cursor.fetchone()[0] or 0
        
        cursor.execute("""
            INSERT INTO lessons (module_id, title, content_type, content_value, position, duration_minutes)
            VALUES (?, ?, 'quiz', 'Interactive Quiz', ?, ?)
        """, (module_id, final_title, max_pos + 1, duration_minutes))
        lesson_id = cursor.lastrowid
        
        cursor.execute("""
            INSERT INTO quizzes (lesson_id, passing_score, time_limit_minutes)
            VALUES (?, ?, ?)
        """, (lesson_id, passing_score, duration_minutes))
        quiz_id = cursor.lastrowid
        
        for q in parsed_questions:
            cursor.execute("""
                INSERT INTO quiz_questions (quiz_id, question_text, option_a, option_b, option_c, option_d, correct_option, explanation)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                quiz_id,
                q["question_text"],
                q["option_a"],
                q["option_b"],
                q["option_c"],
                q["option_d"],
                q["correct_option"],
                q["explanation"]
            ))

        cursor.execute("SELECT user_id FROM enrollments WHERE course_id = ?", (course_id,))
        enrolled_ids = [r[0] for r in cursor.fetchall()]
        notify_users(
            enrolled_ids,
            f"New Quiz Assessment: {final_title}",
            f"A new assessment with {len(parsed_questions)} questions has been published.",
            f"/course/{course_id}",
            "quiz",
            "quiz_published",
            conn=conn
        )
        log_audit(user["id"], "UPLOAD_QUIZ_SPREADSHEET", "quizzes", str(quiz_id), f"Created quiz '{final_title}' with {len(parsed_questions)} questions via {file.filename}", conn=conn)

    return RedirectResponse(url=f"/teacher/course/{course_id}?msg=quiz_uploaded", status_code=303)


@router.post("/teacher/course/{course_id}/quiz/upload")
async def upload_course_spreadsheet_quiz(
    request: Request,
    course_id: int,
    file: UploadFile = File(...),
    title: Optional[str] = Form(None),
    passing_score: int = Form(70),
    duration_minutes: int = Form(10),
    module_id: Optional[int] = Form(None)
):
    return await upload_spreadsheet_quiz(
        request=request, file=file, title=title, passing_score=passing_score,
        duration_minutes=duration_minutes, module_id=module_id, course_id=course_id
    )


@router.post("/teacher/module/{module_id}/quiz/upload")
async def upload_module_spreadsheet_quiz(
    request: Request,
    module_id: int,
    file: UploadFile = File(...),
    title: Optional[str] = Form(None),
    passing_score: int = Form(70),
    duration_minutes: int = Form(10),
    course_id: Optional[int] = Form(None)
):
    return await upload_spreadsheet_quiz(
        request=request, file=file, title=title, passing_score=passing_score,
        duration_minutes=duration_minutes, module_id=module_id, course_id=course_id
    )


async def ai_generate_quiz(
    request: Request,
    topic: str,
    num_questions: int = 5,
    difficulty: str = "Medium",
    passing_score: int = 70,
    duration_minutes: int = 10,
    module_id: Optional[int] = None,
    course_id: Optional[int] = None
):
    """Automatically generates an interactive quiz from a curriculum topic using Gemini AI."""
    user = require_teacher_or_admin(request)
    
    if hasattr(module_id, "default"):
        module_id = None
    elif module_id is not None:
        try:
            module_id = int(module_id)
        except (ValueError, TypeError):
            module_id = None

    if hasattr(course_id, "default"):
        course_id = None
    elif course_id is not None:
        try:
            course_id = int(course_id)
        except (ValueError, TypeError):
            course_id = None

    if hasattr(num_questions, "default"):
        num_questions = 5
    else:
        num_questions = int(num_questions)

    if hasattr(difficulty, "default"):
        difficulty = "Medium"

    if hasattr(passing_score, "default"):
        passing_score = 70
    else:
        passing_score = int(passing_score)

    if hasattr(duration_minutes, "default"):
        duration_minutes = 10
    else:
        duration_minutes = int(duration_minutes)
    
    # Administrator governance check
    with get_db() as conn:
        cursor = conn.cursor()
        if user["role"] == "teacher":
            cursor.execute("SELECT value FROM system_settings WHERE key = 'allow_teacher_ai_quiz'")
            row = cursor.fetchone()
            allowed = row[0] if row else "1"
            if allowed != "1":
                raise HTTPException(status_code=403, detail="Gemini AI Quiz Generation is currently disabled for teachers by the administrator.")

    path_params = request.path_params
    if not course_id and "course_id" in path_params:
        course_id = int(path_params["course_id"])
    if not module_id and "module_id" in path_params:
        module_id = int(path_params["module_id"])
        
    with get_db() as conn:
        cursor = conn.cursor()
        if not course_id and module_id:
            cursor.execute("SELECT course_id FROM modules WHERE id = ?", (module_id,))
            m_row = cursor.fetchone()
            if m_row:
                course_id = m_row[0]
                
        if not course_id:
            raise HTTPException(status_code=400, detail="Invalid course identifier.")

        cursor.execute("SELECT title FROM courses WHERE id = ?", (course_id,))
        c_row = cursor.fetchone()
        course_title = c_row[0] if c_row else "Foreign Language Learning"

        if not module_id:
            cursor.execute("SELECT id FROM modules WHERE course_id = ? ORDER BY position ASC LIMIT 1", (course_id,))
            m_row = cursor.fetchone()
            if m_row:
                module_id = m_row[0]
            else:
                cursor.execute("INSERT INTO modules (course_id, title, position) VALUES (?, 'Module 1: Assessments', 1)", (course_id,))
                module_id = cursor.lastrowid

    generated_quiz = generate_ai_quiz(
        topic=topic.strip(),
        num_questions=max(1, min(int(num_questions), 20)),
        difficulty=difficulty.strip(),
        course_title=course_title
    )
    
    quiz_title = generated_quiz.get("title") or f"{topic.strip().title()} Assessment"
    questions = generated_quiz.get("questions", [])
    if not questions:
        raise HTTPException(status_code=500, detail="Failed to generate questions with AI. Please try again.")

    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT MAX(position) FROM lessons WHERE module_id = ?", (module_id,))
        max_pos = cursor.fetchone()[0] or 0
        
        cursor.execute("""
            INSERT INTO lessons (module_id, title, content_type, content_value, position, duration_minutes)
            VALUES (?, ?, 'quiz', 'Interactive Quiz', ?, ?)
        """, (module_id, quiz_title, max_pos + 1, duration_minutes))
        lesson_id = cursor.lastrowid
        
        cursor.execute("""
            INSERT INTO quizzes (lesson_id, passing_score, time_limit_minutes)
            VALUES (?, ?, ?)
        """, (lesson_id, passing_score, duration_minutes))
        quiz_id = cursor.lastrowid
        
        for q in questions:
            cursor.execute("""
                INSERT INTO quiz_questions (quiz_id, question_text, option_a, option_b, option_c, option_d, correct_option, explanation)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                quiz_id,
                q["question_text"],
                q["option_a"],
                q["option_b"],
                q["option_c"],
                q["option_d"],
                q["correct_option"],
                q["explanation"]
            ))

        cursor.execute("SELECT user_id FROM enrollments WHERE course_id = ?", (course_id,))
        enrolled_ids = [r[0] for r in cursor.fetchall()]
        notify_users(
            enrolled_ids,
            f"New AI-Generated Quiz: {quiz_title}",
            f"A new interactive quiz on '{topic}' ({len(questions)} questions) is ready for you.",
            f"/course/{course_id}",
            "quiz",
            "quiz_published",
            conn=conn
        )
        log_audit(user["id"], "AI_GENERATE_QUIZ", "quizzes", str(quiz_id), f"Auto-generated quiz '{quiz_title}' ({len(questions)} questions) on topic '{topic}' using Gemini AI", conn=conn)

    return RedirectResponse(url=f"/teacher/course/{course_id}?msg=ai_quiz_generated", status_code=303)


@router.post("/teacher/course/{course_id}/quiz/ai-generate")
async def ai_generate_course_quiz(
    request: Request,
    course_id: int,
    topic: str = Form(...),
    num_questions: int = Form(5),
    difficulty: str = Form("Medium"),
    passing_score: int = Form(70),
    duration_minutes: int = Form(10),
    module_id: Optional[int] = Form(None)
):
    return await ai_generate_quiz(
        request=request, course_id=course_id, module_id=module_id,
        topic=topic, num_questions=num_questions, difficulty=difficulty,
        passing_score=passing_score, duration_minutes=duration_minutes
    )


@router.post("/teacher/module/{module_id}/quiz/ai-generate")
async def ai_generate_module_quiz(
    request: Request,
    module_id: int,
    topic: str = Form(...),
    num_questions: int = Form(5),
    difficulty: str = Form("Medium"),
    passing_score: int = Form(70),
    duration_minutes: int = Form(10),
    course_id: Optional[int] = Form(None)
):
    return await ai_generate_quiz(
        request=request, course_id=course_id, module_id=module_id,
        topic=topic, num_questions=num_questions, difficulty=difficulty,
        passing_score=passing_score, duration_minutes=duration_minutes
    )
