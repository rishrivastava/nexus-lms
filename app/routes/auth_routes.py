from fastapi import APIRouter, Request, Form, Response, Depends, HTTPException, status
from fastapi.responses import HTMLResponse, RedirectResponse
from app.templates_config import templates
from app.database import get_db
from app.auth import verify_password, hash_password, create_access_token, get_current_user
import os

router = APIRouter()

@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    user = get_current_user(request)
    if user:
        if user["must_change_password"]:
            return RedirectResponse(url="/setup-account", status_code=303)
        if user["role"] == "teacher":
            return RedirectResponse(url="/teacher", status_code=303)
        elif user["role"] == "department_admin":
            return RedirectResponse(url="/department", status_code=303)
        return RedirectResponse(url="/student", status_code=303)
    return templates.TemplateResponse("login.html", {"request": request, "error": None})

@router.post("/login")
async def login_action(
    request: Request,
    response: Response,
    user_id: str = Form(...),
    password: str = Form(...)
):
    user_id = user_id.strip()
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE user_id = ? COLLATE NOCASE", (user_id,))
        user = cursor.fetchone()

    if not user or not verify_password(password, user["password_hash"]):
        return templates.TemplateResponse("login.html", {
            "request": request,
            "error": "Invalid User ID or Password. Please check your credentials.",
            "user_id": user_id
        }, status_code=400)

    token = create_access_token({"sub": user["user_id"], "role": user["role"]})
    
    # Redirect based on status & role
    target_url = "/student"
    if user["must_change_password"]:
        target_url = "/setup-account"
    elif user["role"] == "teacher":
        target_url = "/teacher"
    elif user["role"] == "department_admin":
        target_url = "/department"

    redirect = RedirectResponse(url=target_url, status_code=303)
    redirect.set_cookie(
        key="lms_token",
        value=token,
        httponly=True,
        max_age=60 * 60 * 24 * 7,
        samesite="lax"
    )
    return redirect

@router.get("/setup-account", response_class=HTMLResponse)
async def setup_account_page(request: Request):
    user = get_current_user(request)
    if not user:
        return RedirectResponse(url="/login", status_code=303)
    return templates.TemplateResponse("setup_account.html", {"request": request, "user": user, "error": None})

@router.post("/setup-account")
async def setup_account_action(
    request: Request,
    new_password: str = Form(...),
    confirm_password: str = Form(...),
    email: str = Form(None)
):
    user = get_current_user(request)
    if not user:
        return RedirectResponse(url="/login", status_code=303)

    if len(new_password) < 6:
        return templates.TemplateResponse("setup_account.html", {
            "request": request, "user": user, "error": "Password must be at least 6 characters long."
        }, status_code=400)

    if new_password != confirm_password:
        return templates.TemplateResponse("setup_account.html", {
            "request": request, "user": user, "error": "Passwords do not match."
        }, status_code=400)

    email_clean = email.strip() if email else None
    new_hash = hash_password(new_password)

    with get_db() as conn:
        cursor = conn.cursor()
        try:
            cursor.execute("""
                UPDATE users 
                SET password_hash = ?, email = ?, must_change_password = 0 
                WHERE id = ?
            """, (new_hash, email_clean, user["id"]))
        except Exception as e:
            if "UNIQUE constraint failed: users.email" in str(e):
                return templates.TemplateResponse("setup_account.html", {
                    "request": request, "user": user, "error": "This email address is already connected to another account."
                }, status_code=400)
            raise e

    # Redirect to their appropriate destination
    dest = "/student"
    if user["role"] == "teacher":
        dest = "/teacher"
    elif user["role"] == "department_admin":
        dest = "/department"
        
    return RedirectResponse(url=dest, status_code=303)

@router.get("/logout")
async def logout():
    redirect = RedirectResponse(url="/login", status_code=303)
    redirect.delete_cookie("lms_token")
    return redirect

@router.get("/profile", response_class=HTMLResponse)
async def view_profile(request: Request):
    user = get_current_user(request)
    if not user:
        return RedirectResponse(url="/login", status_code=303)

    with get_db() as conn:
        cursor = conn.cursor()
        
        # Student specific profile data
        enrolled_courses = []
        quiz_history = []
        teacher_courses = []
        teacher_stats = {}

        if user["role"] == "student":
            cursor.execute("""
                SELECT c.id, c.title, c.code, c.department, e.enrolled_at, e.completed_at,
                       (SELECT COUNT(*) FROM lessons l JOIN modules m ON l.module_id = m.id WHERE m.course_id = c.id) as total_lessons,
                       (SELECT COUNT(*) FROM lesson_progress lp 
                        JOIN lessons l ON lp.lesson_id = l.id 
                        JOIN modules m ON l.module_id = m.id 
                        WHERE m.course_id = c.id AND lp.user_id = ? AND lp.is_completed = 1) as completed_lessons
                FROM enrollments e
                JOIN courses c ON e.course_id = c.id
                WHERE e.user_id = ?
                ORDER BY e.enrolled_at DESC
            """, (user["id"], user["id"]))
            for r in cursor.fetchall():
                c = dict(r)
                tot = c["total_lessons"]
                comp = c["completed_lessons"]
                c["progress_percent"] = round((comp / tot * 100) if tot > 0 else 0)
                enrolled_courses.append(c)

            cursor.execute("""
                SELECT qa.*, q.passing_score, l.title as lesson_title, c.title as course_title, c.code as course_code
                FROM quiz_attempts qa
                JOIN quizzes q ON qa.quiz_id = q.id
                JOIN lessons l ON q.lesson_id = l.id
                JOIN modules m ON l.module_id = m.id
                JOIN courses c ON m.course_id = c.id
                WHERE qa.user_id = ?
                ORDER BY qa.attempted_at DESC
                LIMIT 20
            """, (user["id"],))
            quiz_history = [dict(q) for q in cursor.fetchall()]

        elif user["role"] == "teacher":
            cursor.execute("""
                SELECT c.*,
                       (SELECT COUNT(*) FROM enrollments WHERE course_id = c.id) as enrolled_count
                FROM courses c
                WHERE c.teacher_id = ?
                ORDER BY c.created_at DESC
            """, (user["id"],))
            teacher_courses = [dict(c) for c in cursor.fetchall()]
            
            cursor.execute("""
                SELECT COUNT(DISTINCT e.user_id) 
                FROM enrollments e 
                JOIN courses c ON e.course_id = c.id 
                WHERE c.teacher_id = ?
            """, (user["id"],))
            teacher_stats["unique_students"] = cursor.fetchone()[0]
            teacher_stats["total_courses"] = len(teacher_courses)

    return templates.TemplateResponse("profile.html", {
        "request": request,
        "user": user,
        "enrolled_courses": enrolled_courses,
        "quiz_history": quiz_history,
        "teacher_courses": teacher_courses,
        "teacher_stats": teacher_stats,
        "saved": request.query_params.get("saved"),
        "error": request.query_params.get("error")
    })

@router.post("/profile/update")
async def update_profile(
    request: Request,
    full_name: str = Form(None),
    designation: str = Form(None),
    email: str = Form(None),
    current_password: str = Form(None),
    new_password: str = Form(None)
):
    user = get_current_user(request)
    if not user:
        return RedirectResponse(url="/login", status_code=303)

    clean_email = email.strip() if email else None
    
    with get_db() as conn:
        cursor = conn.cursor()

        # Full Name & Designation update (for Admin / Faculty)
        if full_name and full_name.strip():
            clean_name = full_name.strip()
            clean_desig = designation.strip() if designation and designation.strip() else user.get("designation")
            cursor.execute("""
                UPDATE users 
                SET full_name = ?, designation = ?
                WHERE id = ?
            """, (clean_name, clean_desig, user["id"]))
        
        # Password update if requested
        if new_password and new_password.strip():
            if not current_password or not verify_password(current_password.strip(), user["password_hash"]):
                return RedirectResponse(url="/profile?error=Incorrect+current+password", status_code=303)
            if len(new_password.strip()) < 6:
                return RedirectResponse(url="/profile?error=New+password+must+be+at+least+6+characters", status_code=303)
            new_hash = hash_password(new_password.strip())
            cursor.execute("UPDATE users SET password_hash = ? WHERE id = ?", (new_hash, user["id"]))

        # Email update
        if clean_email and clean_email != user["email"]:
            try:
                cursor.execute("UPDATE users SET email = ? WHERE id = ?", (clean_email, user["id"]))
            except Exception as e:
                if "UNIQUE constraint failed: users.email" in str(e):
                    return RedirectResponse(url="/profile?error=Email+already+in+use+by+another+account", status_code=303)
                raise e

    return RedirectResponse(url="/profile?saved=1", status_code=303)
