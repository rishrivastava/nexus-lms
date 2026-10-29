from fastapi import APIRouter, Request, Form, UploadFile, File, HTTPException, status
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from app.templates_config import templates
from app.database import get_db, UPLOAD_DIR, log_audit, notify_users
from app.auth import get_current_user
import os
import shutil
import uuid

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

    return templates.TemplateResponse("teacher_dashboard.html", {
        "request": request,
        "user": user,
        "courses": courses
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

    return templates.TemplateResponse("course_editor.html", {
        "request": request,
        "user": user,
        "course": dict(course),
        "modules": modules
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
        notify_users(enrolled_ids, f"New Lecture Video: {title.strip()}", f"A new video lecture has been added to your curriculum.", f"/course/{course_id}", "course", "content_published")

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
        notify_users(enrolled_ids, f"New Reading Material: {title.strip()}", f"A new PDF study document has been uploaded.", f"/course/{course_id}", "course", "content_published")

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
        notify_users(enrolled_ids, f"New Timed Assessment: {title.strip()}", f"A new {duration_minutes}-minute quiz assessment is now available.", f"/course/{course_id}", "quiz", "quiz_published")

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
