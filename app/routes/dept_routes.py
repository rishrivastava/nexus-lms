from fastapi import APIRouter, Request, Form, UploadFile, File, HTTPException, status
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse, Response, JSONResponse
from app.templates_config import templates
from app.database import (
    get_db, get_system_settings, update_system_settings, UPLOAD_DIR,
    log_audit, get_dashboard_permissions, update_dashboard_permissions,
    get_notification_settings, update_notification_settings
)
from app.auth import get_current_user, hash_password
from app.utils import normalize_name, generate_unique_student_id
import os
import csv
import io
import re
import json
import uuid
import shutil
import zipfile
import xml.etree.ElementTree as ET

router = APIRouter()

# Memory store for last import rejected report (downloadable by authorized users)
LAST_IMPORT_REJECTED = []

def require_dept_admin_or_teacher(request: Request):
    user = get_current_user(request)
    if not user:
        raise HTTPException(status_code=303, headers={"Location": "/login"})
    if user["role"] not in ["department_admin", "teacher", "dashboard_viewer"]:
        raise HTTPException(status_code=403, detail="Access reserved for Department Admins, Faculty, and Dashboard Viewers.")
    return user

def require_dept_admin(request: Request):
    user = get_current_user(request)
    if not user:
        raise HTTPException(status_code=303, headers={"Location": "/login"})
    if user["role"] != "department_admin":
        raise HTTPException(status_code=403, detail="Access reserved exclusively for Department Head / Administrator.")
    return user

def extract_field(row_dict: dict, *candidate_names) -> str:
    norm_map = {}
    for k, v in row_dict.items():
        if k:
            norm_k = re.sub(r'[^a-z0-9]', '', str(k).lower())
            norm_map[norm_k] = str(v).strip() if v is not None else ""
            
    for cand in candidate_names:
        norm_c = re.sub(r'[^a-z0-9]', '', cand.lower())
        if norm_c in norm_map and norm_map[norm_c]:
            return norm_map[norm_c]
    return ""

def parse_student_upload(contents: bytes, filename: str) -> list:
    """
    Robust parser supporting:
    1. Standard Excel (.xlsx) files via built-in zipfile/xml.
    2. CSV files encoded in UTF-8, UTF-16 (Excel Windows export), Latin-1, or CP1252.
    3. Auto-cleans NUL bytes (\x00) and auto-detects comma, semicolon, or tab delimiters.
    """
    rows = []

    # 1. Handle Excel .xlsx files directly
    if contents.startswith(b'PK\x03\x04') or (filename and filename.lower().endswith(('.xlsx', '.xlsm'))):
        try:
            z = zipfile.ZipFile(io.BytesIO(contents))
            shared = []
            if 'xl/sharedStrings.xml' in z.namelist():
                tree = ET.fromstring(z.read('xl/sharedStrings.xml'))
                ns = '{http://schemas.openxmlformats.org/spreadsheetml/2006/main}'
                for si in tree.findall(f'.//{ns}si'):
                    text = "".join(t.text or "" for t in si.findall(f'.//{ns}t'))
                    shared.append(text)
            
            # Find the primary worksheet
            sheet_name = 'xl/worksheets/sheet1.xml'
            for name in z.namelist():
                if name.startswith('xl/worksheets/sheet') and name.endswith('.xml'):
                    sheet_name = name
                    break
            
            sheet = ET.fromstring(z.read(sheet_name))
            ns = '{http://schemas.openxmlformats.org/spreadsheetml/2006/main}'
            raw_rows = []
            for row_el in sheet.findall(f'.//{ns}row'):
                row_vals = []
                for c in row_el.findall(f'.//{ns}c'):
                    t = c.get('t')
                    v = c.find(f'{ns}v')
                    val = v.text if v is not None else ""
                    if t == 's' and val.isdigit() and int(val) < len(shared):
                        val = shared[int(val)]
                    elif t == 'inlineStr':
                        it = c.find(f'.//{ns}t')
                        if it is not None and it.text:
                            val = it.text
                    row_vals.append(val.strip())
                if any(row_vals):
                    raw_rows.append(row_vals)
            
            if len(raw_rows) > 1:
                headers = raw_rows[0]
                for r in raw_rows[1:]:
                    row_dict = {}
                    for i, h in enumerate(headers):
                        if i < len(r):
                            row_dict[h] = r[i]
                    if row_dict:
                        rows.append(row_dict)
                return rows
        except Exception as e:
            print("Excel XLSX parsing fallback:", e)

    # 2. Handle Text / CSV / TSV files
    decoded_text = ""
    for enc in ['utf-8-sig', 'utf-16', 'utf-16-le', 'utf-16-be', 'latin-1', 'cp1252', 'utf-8']:
        try:
            cand = contents.decode(enc)
            if '\x00' in cand:
                cand = cand.replace('\x00', '')
            if cand.strip():
                decoded_text = cand
                break
        except Exception:
            continue

    if not decoded_text:
        decoded_text = contents.decode('utf-8', errors='ignore').replace('\x00', '')

    lines = [l.strip() for l in decoded_text.splitlines() if l.strip()]
    if not lines:
        return []

    # Detect delimiter
    first_line = lines[0]
    delimiter = ','
    if '\t' in first_line and first_line.count('\t') > first_line.count(','):
        delimiter = '\t'
    elif ';' in first_line and first_line.count(';') > first_line.count(','):
        delimiter = ';'

    reader = csv.DictReader(lines, delimiter=delimiter)
    for row in reader:
        if row and any(row.values()):
            rows.append(row)

    return rows

def format_time_duration(seconds: float) -> str:
    if seconds <= 0:
        return "0m"
    if seconds < 60:
        return f"{int(seconds)}s"
    if seconds < 3600:
        return f"{round(seconds / 60)} mins"
    hours = int(seconds // 3600)
    mins = int((seconds % 3600) // 60)
    return f"{hours}h {mins}m"

@router.get("/department", response_class=HTMLResponse)
async def department_dashboard(
    request: Request,
    department: str = None,
    subject: str = None,
    tab: str = "overview",
    date_range: str = "all"
):
    user = require_dept_admin_or_teacher(request)
    
    with get_db() as conn:
        cursor = conn.cursor()
        
        # 1. Available departments / districts / schools for filter
        cursor.execute("SELECT DISTINCT department FROM users WHERE role = 'student' ORDER BY department")
        departments = [r[0] for r in cursor.fetchall() if r[0]]
        
        cursor.execute("SELECT DISTINCT district FROM users WHERE role = 'student' AND district IS NOT NULL AND district != '' ORDER BY district")
        districts = [r[0] for r in cursor.fetchall()]

        cursor.execute("SELECT DISTINCT school_name FROM users WHERE role = 'student' AND school_name IS NOT NULL AND school_name != '' ORDER BY school_name")
        schools = [r[0] for r in cursor.fetchall()]

        # All published courses for assignment dropdown
        cursor.execute("SELECT id, title, code, department, subject FROM courses WHERE is_published = 1 AND status != 'deleted' ORDER BY title ASC")
        all_courses = [dict(c) for c in cursor.fetchall()]

        # All distinct subjects
        cursor.execute("""
            SELECT DISTINCT COALESCE(NULLIF(subject, ''), NULLIF(department, ''), 'General') as subj 
            FROM courses 
            WHERE status != 'deleted' 
            ORDER BY subj ASC
        """)
        all_subjects = [r[0] for r in cursor.fetchall() if r[0]]
        if not all_subjects:
            all_subjects = ["Computer Science", "General"]

        selected_dept = department if department and department != "all" else None
        active_subject = subject if subject and subject in all_subjects else all_subjects[0]

        dept_filter_sql = " AND (u.department = ? OR u.district = ? OR u.school_name = ?)" if selected_dept else ""
        dept_filter_params = [selected_dept, selected_dept, selected_dept] if selected_dept else []

        # ==========================================
        # DASHBOARD 1: 12 KPI CARDS (Consolidated LMS View)
        # ==========================================
        # 1. Total registered students
        cursor.execute(f"SELECT COUNT(*) FROM users u WHERE u.role = 'student'{dept_filter_sql}", dept_filter_params)
        total_students = cursor.fetchone()[0]

        # 2. Total active student accounts (have changed password)
        cursor.execute(f"SELECT COUNT(*) FROM users u WHERE u.role = 'student' AND u.must_change_password = 0{dept_filter_sql}", dept_filter_params)
        active_accounts = cursor.fetchone()[0]

        # 3. Total enrolled students across courses (unique)
        cursor.execute(f"SELECT COUNT(DISTINCT u.id) FROM users u JOIN enrollments e ON u.id = e.user_id WHERE u.role = 'student'{dept_filter_sql}", dept_filter_params)
        active_enrolled = cursor.fetchone()[0]

        # 4. Total teachers
        cursor.execute("SELECT COUNT(*) FROM users u WHERE u.role = 'teacher'")
        total_teachers = cursor.fetchone()[0]

        # 5. Total subjects
        total_subjects = len(all_subjects)

        # 6. Total courses
        cursor.execute("SELECT COUNT(*) FROM courses WHERE status != 'deleted'")
        total_courses = cursor.fetchone()[0]

        # 7. Total course enrolments
        cursor.execute(f"SELECT COUNT(e.id) FROM enrollments e JOIN users u ON e.user_id = u.id WHERE 1=1{dept_filter_sql}", dept_filter_params)
        total_course_enrollments = cursor.fetchone()[0]

        # 8. Average quiz score across all attempts
        cursor.execute(f"""
            SELECT 
                COALESCE(AVG(qa.score_percent), 0),
                COUNT(CASE WHEN qa.passed = 1 THEN 1 END),
                COUNT(CASE WHEN qa.passed = 0 THEN 1 END),
                COUNT(*)
            FROM quiz_attempts qa
            JOIN users u ON qa.user_id = u.id
            WHERE 1=1{dept_filter_sql}
        """, dept_filter_params)
        q_row = cursor.fetchone()
        avg_quiz_score = round(q_row[0], 1)
        quiz_passed_count = q_row[1]
        quiz_failed_count = q_row[2]
        quiz_total_attempts = q_row[3]
        quiz_pass_rate = round((quiz_passed_count / quiz_total_attempts * 100), 1) if quiz_total_attempts > 0 else 0.0

        # 9. Average time spent on LMS
        cursor.execute(f"""
            SELECT COALESCE(SUM(lp.watched_seconds), 0) + 
                   COALESCE(SUM(CASE WHEN lp.is_completed = 1 AND l.content_type != 'youtube' THEN l.duration_minutes * 60 ELSE 0 END), 0)
            FROM lesson_progress lp
            JOIN lessons l ON lp.lesson_id = l.id
            JOIN users u ON lp.user_id = u.id
            WHERE 1=1{dept_filter_sql}
        """, dept_filter_params)
        total_system_seconds = cursor.fetchone()[0] or 0
        avg_seconds_per_student = (total_system_seconds / active_enrolled) if active_enrolled > 0 else 0
        avg_learning_time_formatted = format_time_duration(avg_seconds_per_student)

        # 10. Total learning resources (modules and lessons)
        cursor.execute("""
            SELECT COUNT(*) 
            FROM lessons l 
            JOIN modules m ON l.module_id = m.id 
            JOIN courses c ON m.course_id = c.id 
            WHERE c.status != 'deleted'
        """)
        total_learning_resources = cursor.fetchone()[0]

        # 11. Overall course completion rate
        cursor.execute(f"""
            SELECT COUNT(*) 
            FROM enrollments e 
            JOIN users u ON e.user_id = u.id 
            WHERE e.completed_at IS NOT NULL{dept_filter_sql}
        """, dept_filter_params)
        total_course_completions = cursor.fetchone()[0]
        overall_completion_rate = round((total_course_completions / total_course_enrollments * 100), 1) if total_course_enrollments > 0 else 0.0

        # 12. Students active right now (last 5 minutes)
        cursor.execute(f"""
            SELECT COUNT(DISTINCT u.id) 
            FROM users u 
            WHERE u.role = 'student' AND u.last_active_at >= datetime('now', '-5 minutes'){dept_filter_sql}
        """, dept_filter_params)
        live_students_now = cursor.fetchone()[0]

        # Total lesson views / completed
        cursor.execute(f"""
            SELECT COUNT(*) 
            FROM lesson_progress lp 
            JOIN users u ON lp.user_id = u.id 
            WHERE lp.is_completed = 1{dept_filter_sql}
        """, dept_filter_params)
        total_lesson_views = cursor.fetchone()[0]

        # ==========================================
        # OVERVIEW TRENDS & TOP/BOTTOM SUBJECTS
        # ==========================================
        cursor.execute(f"""
            SELECT strftime('%Y-%m', u.created_at) as month_label, COUNT(*) as reg_count
            FROM users u
            WHERE u.role = 'student'{dept_filter_sql}
            GROUP BY month_label
            ORDER BY month_label ASC
            LIMIT 6
        """, dept_filter_params)
        registration_trends = [dict(r) for r in cursor.fetchall()]

        # ==========================================
        # DASHBOARD 2: SUBJECT PARTICIPATION & COMPARISON TABLE
        # ==========================================
        subject_participation_table = []
        for subj in all_subjects:
            cursor.execute("""
                SELECT 
                    COUNT(DISTINCT c.id) as courses_count,
                    COUNT(DISTINCT e.user_id) as unique_students,
                    COUNT(e.id) as total_enrollments,
                    COUNT(DISTINCT CASE WHEN u.last_active_at >= datetime('now', '-5 minutes') THEN e.user_id END) as live_students_now,
                    COUNT(DISTINCT CASE WHEN u.last_active_at >= datetime('now', '-24 hours') THEN e.user_id END) as active_period_students,
                    COUNT(DISTINCT CASE WHEN e.completed_at IS NOT NULL THEN e.user_id END) as completed_students,
                    COALESCE(ROUND(AVG(qa.score_percent), 1), 0.0) as avg_quiz_score,
                    COUNT(qa.id) as total_quiz_attempts,
                    COALESCE(SUM(lp.watched_seconds), 0) + 
                    COALESCE(SUM(CASE WHEN lp.is_completed = 1 AND l.content_type != 'youtube' THEN l.duration_minutes * 60 ELSE 0 END), 0) as subj_learning_seconds
                FROM courses c
                LEFT JOIN enrollments e ON c.id = e.course_id
                LEFT JOIN users u ON e.user_id = u.id
                LEFT JOIN modules m ON c.id = m.course_id
                LEFT JOIN lessons l ON m.id = l.module_id
                LEFT JOIN lesson_progress lp ON l.id = lp.lesson_id AND lp.user_id = e.user_id
                LEFT JOIN quizzes q ON l.id = q.lesson_id
                LEFT JOIN quiz_attempts qa ON q.id = qa.quiz_id AND qa.user_id = e.user_id
                WHERE COALESCE(NULLIF(c.subject, ''), NULLIF(c.department, ''), 'General') = ? AND c.status != 'deleted'
            """, (subj,))
            s_row = dict(cursor.fetchone())
            u_st = s_row["unique_students"]
            tot_en = s_row["total_enrollments"]
            comp_st = s_row["completed_students"]
            s_row["subject_name"] = subj
            s_row["completion_rate"] = round((comp_st / tot_en * 100), 1) if tot_en > 0 else 0.0
            
            subj_sec = s_row["subj_learning_seconds"]
            avg_st_sec = (subj_sec / u_st) if u_st > 0 else 0
            s_row["avg_time_str"] = format_time_duration(avg_st_sec)

            # Enrolled students who haven't started (0 completed lessons and 0 quiz attempts)
            cursor.execute("""
                SELECT COUNT(DISTINCT e.user_id)
                FROM enrollments e
                JOIN courses c ON e.course_id = c.id
                WHERE COALESCE(NULLIF(c.subject, ''), NULLIF(c.department, ''), 'General') = ? AND c.status != 'deleted'
                  AND e.user_id NOT IN (
                      SELECT DISTINCT lp.user_id 
                      FROM lesson_progress lp 
                      JOIN lessons l ON lp.lesson_id = l.id 
                      JOIN modules m ON l.module_id = m.id 
                      JOIN courses c2 ON m.course_id = c2.id 
                      WHERE COALESCE(NULLIF(c2.subject, ''), NULLIF(c2.department, ''), 'General') = ? AND lp.is_completed = 1
                  )
                  AND e.user_id NOT IN (
                      SELECT DISTINCT qa.user_id 
                      FROM quiz_attempts qa 
                      JOIN quizzes q ON qa.quiz_id = q.id 
                      JOIN lessons l ON q.lesson_id = l.id 
                      JOIN modules m ON l.module_id = m.id 
                      JOIN courses c2 ON m.course_id = c2.id 
                      WHERE COALESCE(NULLIF(c2.subject, ''), NULLIF(c2.department, ''), 'General') = ?
                  )
            """, (subj, subj, subj))
            s_row["not_started_count"] = cursor.fetchone()[0]

            subject_participation_table.append(s_row)

        top_performing_subjects = sorted(subject_participation_table, key=lambda s: s["avg_quiz_score"], reverse=True)[:3]
        attention_subjects = sorted(subject_participation_table, key=lambda s: (s["completion_rate"], s["avg_quiz_score"]))[:3]

        # ==========================================
        # SUBJECT DRILL-DOWN: TOP 10, BOTTOM 10, UNATTEMPTED, NOT STARTED
        # ==========================================
        # Top 10 ranking table (Minimum 1 quiz attempt required!)
        cursor.execute("""
            SELECT 
                u.id, u.user_id, u.full_name, COALESCE(u.guardian_name, '') as guardian_name,
                COALESCE(u.school_name, '') as school_name, COALESCE(u.district, '') as district,
                ROUND(AVG(qa.score_percent), 1) as avg_score,
                COUNT(qa.id) as attempts_count,
                (SELECT COUNT(*) FROM enrollments e2 JOIN courses c2 ON e2.course_id = c2.id WHERE e2.user_id = u.id AND COALESCE(NULLIF(c2.subject, ''), NULLIF(c2.department, ''), 'General') = ? AND c2.status != 'deleted') as courses_enrolled,
                (SELECT COUNT(*) FROM enrollments e2 JOIN courses c2 ON e2.course_id = c2.id WHERE e2.user_id = u.id AND e2.completed_at IS NOT NULL AND COALESCE(NULLIF(c2.subject, ''), NULLIF(c2.department, ''), 'General') = ? AND c2.status != 'deleted') as courses_completed,
                (SELECT COALESCE(SUM(lp.watched_seconds), 0) + 
                        COALESCE(SUM(CASE WHEN lp.is_completed = 1 AND l.content_type != 'youtube' THEN l.duration_minutes * 60 ELSE 0 END), 0)
                 FROM lesson_progress lp
                 JOIN lessons l ON lp.lesson_id = l.id
                 JOIN modules m ON l.module_id = m.id
                 JOIN courses c2 ON m.course_id = c2.id
                 WHERE lp.user_id = u.id AND COALESCE(NULLIF(c2.subject, ''), NULLIF(c2.department, ''), 'General') = ? AND c2.status != 'deleted') as learning_seconds
            FROM users u
            JOIN quiz_attempts qa ON u.id = qa.user_id
            JOIN quizzes q ON qa.quiz_id = q.id
            JOIN lessons l ON q.lesson_id = l.id
            JOIN modules m ON l.module_id = m.id
            JOIN courses c ON m.course_id = c.id
            WHERE COALESCE(NULLIF(c.subject, ''), NULLIF(c.department, ''), 'General') = ? AND c.status != 'deleted'
            GROUP BY u.id
            HAVING attempts_count >= 1
            ORDER BY avg_score DESC, learning_seconds DESC
            LIMIT 10
        """, (active_subject, active_subject, active_subject, active_subject))
        top_10_students = []
        for idx, r in enumerate(cursor.fetchall(), 1):
            d = dict(r)
            d["rank"] = idx
            en = d["courses_enrolled"]
            comp = d["courses_completed"]
            d["completion_rate"] = round((comp / en * 100), 1) if en > 0 else 0.0
            d["time_spent_str"] = format_time_duration(d["learning_seconds"])
            top_10_students.append(d)

        # Bottom 10 ranking table (Minimum 1 quiz attempt required!)
        cursor.execute("""
            SELECT 
                u.id, u.user_id, u.full_name, COALESCE(u.guardian_name, '') as guardian_name,
                COALESCE(u.school_name, '') as school_name, COALESCE(u.district, '') as district,
                ROUND(AVG(qa.score_percent), 1) as avg_score,
                COUNT(qa.id) as attempts_count,
                (SELECT COUNT(*) FROM enrollments e2 JOIN courses c2 ON e2.course_id = c2.id WHERE e2.user_id = u.id AND COALESCE(NULLIF(c2.subject, ''), NULLIF(c2.department, ''), 'General') = ? AND c2.status != 'deleted') as courses_enrolled,
                (SELECT COUNT(*) FROM enrollments e2 JOIN courses c2 ON e2.course_id = c2.id WHERE e2.user_id = u.id AND e2.completed_at IS NOT NULL AND COALESCE(NULLIF(c2.subject, ''), NULLIF(c2.department, ''), 'General') = ? AND c2.status != 'deleted') as courses_completed,
                (SELECT COALESCE(SUM(lp.watched_seconds), 0) + 
                        COALESCE(SUM(CASE WHEN lp.is_completed = 1 AND l.content_type != 'youtube' THEN l.duration_minutes * 60 ELSE 0 END), 0)
                 FROM lesson_progress lp
                 JOIN lessons l ON lp.lesson_id = l.id
                 JOIN modules m ON l.module_id = m.id
                 JOIN courses c2 ON m.course_id = c2.id
                 WHERE lp.user_id = u.id AND COALESCE(NULLIF(c2.subject, ''), NULLIF(c2.department, ''), 'General') = ? AND c2.status != 'deleted') as learning_seconds
            FROM users u
            JOIN quiz_attempts qa ON u.id = qa.user_id
            JOIN quizzes q ON qa.quiz_id = q.id
            JOIN lessons l ON q.lesson_id = l.id
            JOIN modules m ON l.module_id = m.id
            JOIN courses c ON m.course_id = c.id
            WHERE COALESCE(NULLIF(c.subject, ''), NULLIF(c.department, ''), 'General') = ? AND c.status != 'deleted'
            GROUP BY u.id
            HAVING attempts_count >= 1
            ORDER BY avg_score ASC, learning_seconds ASC
            LIMIT 10
        """, (active_subject, active_subject, active_subject, active_subject))
        bottom_10_students = []
        for idx, r in enumerate(cursor.fetchall(), 1):
            d = dict(r)
            d["rank"] = idx
            en = d["courses_enrolled"]
            comp = d["courses_completed"]
            d["completion_rate"] = round((comp / en * 100), 1) if en > 0 else 0.0
            d["time_spent_str"] = format_time_duration(d["learning_seconds"])
            bottom_10_students.append(d)

        # Unattempted students in this subject (enrolled, but 0 quiz attempts)
        cursor.execute("""
            SELECT DISTINCT
                u.id, u.user_id, u.full_name, COALESCE(u.guardian_name, '') as guardian_name,
                COALESCE(u.school_name, '') as school_name, COALESCE(u.district, '') as district
            FROM users u
            JOIN enrollments e ON u.id = e.user_id
            JOIN courses c ON e.course_id = c.id
            WHERE COALESCE(NULLIF(c.subject, ''), NULLIF(c.department, ''), 'General') = ? AND c.status != 'deleted'
              AND u.id NOT IN (
                  SELECT DISTINCT qa.user_id 
                  FROM quiz_attempts qa
                  JOIN quizzes q ON qa.quiz_id = q.id
                  JOIN lessons l ON q.lesson_id = l.id
                  JOIN modules m ON l.module_id = m.id
                  JOIN courses c2 ON m.course_id = c2.id
                  WHERE COALESCE(NULLIF(c2.subject, ''), NULLIF(c2.department, ''), 'General') = ?
              )
            ORDER BY u.full_name ASC
            LIMIT 50
        """, (active_subject, active_subject))
        unattempted_students = [dict(r) for r in cursor.fetchall()]

        # Not started students in this subject (enrolled, 0 completed lessons, 0 quiz attempts)
        cursor.execute("""
            SELECT DISTINCT
                u.id, u.user_id, u.full_name, COALESCE(u.guardian_name, '') as guardian_name,
                COALESCE(u.school_name, '') as school_name, COALESCE(u.district, '') as district
            FROM users u
            JOIN enrollments e ON u.id = e.user_id
            JOIN courses c ON e.course_id = c.id
            WHERE COALESCE(NULLIF(c.subject, ''), NULLIF(c.department, ''), 'General') = ? AND c.status != 'deleted'
              AND u.id NOT IN (
                  SELECT DISTINCT lp.user_id 
                  FROM lesson_progress lp 
                  JOIN lessons l ON lp.lesson_id = l.id 
                  JOIN modules m ON l.module_id = m.id 
                  JOIN courses c2 ON m.course_id = c2.id 
                  WHERE COALESCE(NULLIF(c2.subject, ''), NULLIF(c2.department, ''), 'General') = ? AND lp.is_completed = 1
              )
              AND u.id NOT IN (
                  SELECT DISTINCT qa.user_id 
                  FROM quiz_attempts qa 
                  JOIN quizzes q ON qa.quiz_id = q.id 
                  JOIN lessons l ON q.lesson_id = l.id 
                  JOIN modules m ON l.module_id = m.id 
                  JOIN courses c2 ON m.course_id = c2.id 
                  WHERE COALESCE(NULLIF(c2.subject, ''), NULLIF(c2.department, ''), 'General') = ?
              )
            ORDER BY u.full_name ASC
            LIMIT 50
        """, (active_subject, active_subject, active_subject))
        not_started_students = [dict(r) for r in cursor.fetchall()]

        # ==========================================
        # DASHBOARD 3: SUBJECT CONTENT MATRIX
        # ==========================================
        cursor.execute("""
            SELECT 
                c.id, c.code, c.title, COALESCE(NULLIF(c.subject, ''), NULLIF(c.department, ''), 'General') as subject,
                c.status, c.is_published, u.full_name as teacher_name,
                (SELECT COUNT(*) FROM modules WHERE course_id = c.id) as modules_count,
                (SELECT COUNT(*) FROM lessons l JOIN modules m ON l.module_id = m.id WHERE m.course_id = c.id) as lessons_count,
                (SELECT COUNT(*) FROM lessons l JOIN modules m ON l.module_id = m.id WHERE m.course_id = c.id AND l.content_type = 'pdf') as pdf_count,
                (SELECT COUNT(*) FROM lessons l JOIN modules m ON l.module_id = m.id WHERE m.course_id = c.id AND l.content_type = 'youtube') as video_count,
                (SELECT COUNT(*) FROM lessons l JOIN modules m ON l.module_id = m.id WHERE m.course_id = c.id AND l.content_type = 'quiz') as quiz_count,
                (SELECT COUNT(*) FROM quiz_questions qq JOIN quizzes q ON qq.quiz_id = q.id JOIN lessons l ON q.lesson_id = l.id JOIN modules m ON l.module_id = m.id WHERE m.course_id = c.id) as questions_count,
                (SELECT COALESCE(SUM(l.duration_minutes), 0) FROM lessons l JOIN modules m ON l.module_id = m.id WHERE m.course_id = c.id) as total_duration_minutes
            FROM courses c
            JOIN users u ON c.teacher_id = u.id
            WHERE c.status != 'deleted'
            ORDER BY c.title ASC
        """)
        all_content_courses = [dict(r) for r in cursor.fetchall()]
        subject_content_tree = {}
        for subj in all_subjects:
            subj_courses = [c for c in all_content_courses if c["subject"] == subj]
            total_mod = sum(c["modules_count"] for c in subj_courses)
            total_les = sum(c["lessons_count"] for c in subj_courses)
            total_pdf = sum(c["pdf_count"] for c in subj_courses)
            total_vid = sum(c["video_count"] for c in subj_courses)
            total_q = sum(c["quiz_count"] for c in subj_courses)
            total_quest = sum(c["questions_count"] for c in subj_courses)
            total_dur = sum(c["total_duration_minutes"] for c in subj_courses)
            subject_content_tree[subj] = {
                "subject_name": subj,
                "courses": subj_courses,
                "courses_count": len(subj_courses),
                "modules_count": total_mod,
                "lessons_count": total_les,
                "pdf_count": total_pdf,
                "video_count": total_vid,
                "quiz_count": total_q,
                "questions_count": total_quest,
                "duration_minutes": total_dur,
                "duration_str": format_time_duration(total_dur * 60)
            }

        # Courses Breakdown (existing feature for cohort management)
        cursor.execute("""
            SELECT 
                c.id, c.title, c.code, COALESCE(NULLIF(c.subject, ''), NULLIF(c.department, ''), 'General') as subject, c.department,
                c.status, c.is_published,
                u.full_name as teacher_name,
                (SELECT COUNT(*) FROM enrollments WHERE course_id = c.id) as enrolled_count,
                (SELECT COUNT(*) FROM enrollments WHERE course_id = c.id AND completed_at IS NOT NULL) as completed_count,
                (SELECT COUNT(*) FROM lessons l JOIN modules m ON l.module_id = m.id WHERE m.course_id = c.id) as lesson_count,
                (SELECT COUNT(DISTINCT e.user_id) 
                 FROM enrollments e 
                 JOIN users u2 ON e.user_id = u2.id 
                 WHERE e.course_id = c.id AND u2.last_active_at >= datetime('now', '-5 minutes')) as live_students_count,
                (SELECT COALESCE(SUM(lp.watched_seconds), 0) + 
                        COALESCE(SUM(CASE WHEN lp.is_completed = 1 AND l.content_type != 'youtube' THEN l.duration_minutes * 60 ELSE 0 END), 0)
                 FROM lesson_progress lp
                 JOIN lessons l ON lp.lesson_id = l.id
                 JOIN modules m ON l.module_id = m.id
                 JOIN enrollments e ON lp.user_id = e.user_id AND e.course_id = c.id
                 WHERE m.course_id = c.id) as total_course_learning_seconds,
                (SELECT COALESCE(AVG(qa.score_percent), 0) FROM quiz_attempts qa 
                 JOIN quizzes q ON qa.quiz_id = q.id 
                 JOIN lessons l ON q.lesson_id = l.id 
                 JOIN modules m ON l.module_id = m.id 
                 WHERE m.course_id = c.id) as avg_quiz_score
            FROM courses c
            JOIN users u ON c.teacher_id = u.id
            WHERE c.status != 'deleted'
            ORDER BY c.created_at DESC
        """)
        courses_raw = cursor.fetchall()
        course_breakdown = []
        for cr in courses_raw:
            c = dict(cr)
            enrolled = c["enrolled_count"]
            completed = c["completed_count"]
            c["completion_rate"] = round((completed / enrolled * 100), 1) if enrolled > 0 else 0.0
            c["avg_quiz_score"] = round(c["avg_quiz_score"], 1)
            total_sec = c["total_course_learning_seconds"]
            avg_sec = (total_sec / enrolled) if enrolled > 0 else 0
            c["avg_learning_time"] = format_time_duration(avg_sec)

            cursor.execute("""
                SELECT u.id as user_id_int, u.user_id, u.full_name, u.school_name, u.district, u.last_active_at, e.completed_at,
                       (SELECT COUNT(*) FROM lesson_progress lp 
                        JOIN lessons l ON lp.lesson_id = l.id 
                        JOIN modules m ON l.module_id = m.id 
                        WHERE m.course_id = ? AND lp.user_id = u.id AND lp.is_completed = 1) as course_lessons_completed
                FROM enrollments e
                JOIN users u ON e.user_id = u.id
                WHERE e.course_id = ?
                ORDER BY u.full_name ASC
            """, (c["id"], c["id"]))
            c["group_students"] = [dict(s) for s in cursor.fetchall()]
            course_breakdown.append(c)

        # Faculty list
        cursor.execute("""
            SELECT 
                u.id, u.user_id, u.full_name, u.department, u.email, u.designation, u.avatar_url, u.must_change_password, u.created_at,
                (SELECT COUNT(*) FROM courses WHERE teacher_id = u.id AND status != 'deleted') as courses_count,
                (SELECT COUNT(DISTINCT e.user_id) FROM enrollments e JOIN courses c ON e.course_id = c.id WHERE c.teacher_id = u.id AND c.status != 'deleted') as total_students_taught
            FROM users u
            WHERE u.role = 'teacher'
            ORDER BY u.full_name ASC
        """)
        teachers_list = [dict(t) for t in cursor.fetchall()]

        # Students Roster Table
        query = f"""
            SELECT 
                u.id as user_id_int,
                u.user_id,
                u.full_name,
                u.department,
                u.email,
                u.must_change_password,
                u.last_active_at,
                COALESCE(u.guardian_name, '') as guardian_name,
                COALESCE(u.school_name, '') as school_name,
                COALESCE(u.udise_code, '') as udise_code,
                COALESCE(u.block, '') as block,
                COALESCE(u.district, '') as district,
                COALESCE(u.state, '') as state,
                COALESCE(u.pincode, '') as pincode,
                COUNT(DISTINCT e.course_id) as enrolled_courses_count,
                COUNT(DISTINCT CASE WHEN e.completed_at IS NOT NULL THEN e.course_id END) as completed_courses_count,
                (SELECT GROUP_CONCAT(c.code, ', ') FROM enrollments e2 JOIN courses c ON e2.course_id = c.id WHERE e2.user_id = u.id AND c.status != 'deleted') as assigned_course_codes,
                (SELECT COUNT(*) FROM lesson_progress lp WHERE lp.user_id = u.id AND lp.is_completed = 1) as completed_lessons_count,
                (SELECT COALESCE(AVG(qa.score_percent), 0) FROM quiz_attempts qa WHERE qa.user_id = u.id) as avg_quiz_score
            FROM users u
            LEFT JOIN enrollments e ON u.id = e.user_id
            WHERE u.role = 'student'{dept_filter_sql}
            GROUP BY u.id
            ORDER BY u.user_id ASC
        """
        cursor.execute(query, dept_filter_params)
        student_rows = [dict(r) for r in cursor.fetchall()]
        for s in student_rows:
            s["avg_quiz_score"] = round(s["avg_quiz_score"], 1)

        # Branding & Integrations Settings
        branding = get_system_settings()

        # Admin user profile data
        cursor.execute("SELECT id, user_id, full_name, email, designation, avatar_url, role, department FROM users WHERE id = ?", (user["id"],))
        admin_profile = dict(cursor.fetchone() or user)

        # Dashboard Permissions & Widgets
        cursor.execute("SELECT * FROM dashboard_permissions ORDER BY widget_key ASC")
        dashboard_permissions = [dict(p) for p in cursor.fetchall()]

        # Notification Settings
        notification_settings = get_notification_settings()

        # Recent Audit Logs
        cursor.execute("""
            SELECT al.*, u.full_name as user_name, u.role as user_role
            FROM audit_logs al
            LEFT JOIN users u ON al.user_id = u.id
            ORDER BY al.created_at DESC
            LIMIT 50
        """)
        audit_logs = [dict(a) for a in cursor.fetchall()]

        # Student Conflicts
        cursor.execute("""
            SELECT sc.*, u.full_name as existing_name
            FROM student_conflicts sc
            LEFT JOIN users u ON sc.existing_user_id = u.user_id
            ORDER BY sc.created_at DESC
        """)
        student_conflicts = [dict(c) for c in cursor.fetchall()]

        # Support & Chatbot Queries
        cursor.execute("SELECT * FROM support_queries ORDER BY created_at DESC LIMIT 100")
        all_queries = [dict(q) for q in cursor.fetchall()]
        open_queries_count = sum(1 for q in all_queries if q["status"] == "open")

        # General Dashboard Accounts (Dashboard Viewers)
        cursor.execute("""
            SELECT id, user_id, full_name, email, department, designation, created_at, last_active_at
            FROM users
            WHERE role = 'dashboard_viewer'
            ORDER BY created_at DESC
        """)
        dashboard_viewers = [dict(v) for v in cursor.fetchall()]

    return templates.TemplateResponse("department_dashboard.html", {
        "request": request,
        "user": user,
        "admin_profile": admin_profile,
        "active_tab": tab,
        "date_range": date_range,
        "departments": departments,
        "districts": districts,
        "schools": schools,
        "selected_dept": selected_dept,
        "all_courses": all_courses,
        "all_subjects": all_subjects,
        "active_subject": active_subject,
        # Executive 12 KPIs
        "kpi_total_students": total_students,
        "kpi_active_accounts": active_accounts,
        "kpi_enrolled_students": active_enrolled,
        "kpi_total_teachers": total_teachers,
        "kpi_total_subjects": total_subjects,
        "kpi_total_courses": total_courses,
        "kpi_total_enrollments": total_course_enrollments,
        "kpi_avg_quiz_score": avg_quiz_score,
        "kpi_avg_time_spent": avg_learning_time_formatted,
        "kpi_total_resources": total_learning_resources,
        "kpi_completion_rate": overall_completion_rate,
        "kpi_live_students_now": live_students_now,
        # Legacy/helper aliases
        "total_students": total_students,
        "active_enrolled": active_enrolled,
        "total_teachers": total_teachers,
        "total_courses": total_courses,
        "total_course_completions": total_course_completions,
        "total_lesson_views": total_lesson_views,
        "avg_quiz_score": avg_quiz_score,
        "quiz_passed_count": quiz_passed_count,
        "quiz_failed_count": quiz_failed_count,
        "quiz_total_attempts": quiz_total_attempts,
        "quiz_pass_rate": quiz_pass_rate,
        # Overview Trends
        "registration_trends": registration_trends,
        "top_performing_subjects": top_performing_subjects,
        "attention_subjects": attention_subjects,
        # Subject Participation Dashboard
        "subject_participation_table": subject_participation_table,
        "top_10_students": top_10_students,
        "bottom_10_students": bottom_10_students,
        "unattempted_students": unattempted_students,
        "not_started_students": not_started_students,
        # Subject Content Dashboard
        "subject_content_tree": subject_content_tree,
        # Integrations & Governance
        "course_breakdown": course_breakdown,
        "teachers": teachers_list,
        "dashboard_viewers": dashboard_viewers,
        "students": student_rows,
        "branding": branding,
        "dashboard_permissions": dashboard_permissions,
        "notification_settings": notification_settings,
        "audit_logs": audit_logs,
        "student_conflicts": student_conflicts,
        "all_queries": all_queries,
        "open_queries_count": open_queries_count,
        "last_rejected_count": len(LAST_IMPORT_REJECTED)
    })

@router.post("/department/courses/assign")
async def assign_course_to_students(
    request: Request,
    course_id: int = Form(...),
    student_ids: str = Form(""),
    school_filter: str = Form("")
):
    """Allows Teachers, Admins, or Department Heads to assign specific courses to students."""
    user = require_dept_admin_or_teacher(request)
    
    assigned_count = 0
    with get_db() as conn:
        cursor = conn.cursor()
        
        # Verify course exists
        cursor.execute("SELECT id, title FROM courses WHERE id = ?", (course_id,))
        course = cursor.fetchone()
        if not course:
            raise HTTPException(status_code=404, detail="Course not found")

        # 1. Assign by comma-separated student IDs or user_ids
        if student_ids and student_ids.strip():
            raw_ids = [i.strip() for i in student_ids.replace("\n", ",").replace(";", ",").split(",") if i.strip()]
            for uid in raw_ids:
                cursor.execute("SELECT id FROM users WHERE (user_id = ? OR id = ?) AND role = 'student'", (uid, uid))
                st = cursor.fetchone()
                if st:
                    cursor.execute("INSERT OR IGNORE INTO enrollments (user_id, course_id) VALUES (?, ?)", (st["id"], course_id))
                    assigned_count += 1

        # 2. Assign by entire School / District batch
        if school_filter and school_filter.strip() and school_filter != "all":
            clean_school = school_filter.strip()
            cursor.execute("""
                SELECT id FROM users 
                WHERE (school_name = ? OR district = ? OR department = ?) AND role = 'student'
            """, (clean_school, clean_school, clean_school))
            batch_students = cursor.fetchall()
            for st in batch_students:
                cursor.execute("INSERT OR IGNORE INTO enrollments (user_id, course_id) VALUES (?, ?)", (st["id"], course_id))
                assigned_count += 1

    return RedirectResponse(url=f"/department?tab=courses&assigned={assigned_count}", status_code=303)

@router.post("/department/courses/unassign")
async def unassign_course_from_student(
    request: Request,
    course_id: int = Form(...),
    user_id: int = Form(...)
):
    require_dept_admin_or_teacher(request)
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM enrollments WHERE user_id = ? AND course_id = ?", (user_id, course_id))
    return RedirectResponse(url="/department?tab=courses&unassigned=1", status_code=303)

@router.post("/department/teachers/add")
async def add_teacher(
    request: Request,
    user_id: str = Form(...),
    full_name: str = Form(...),
    department: str = Form(...),
    email: str = Form(None),
    temporary_password: str = Form("teacher123")
):
    require_dept_admin(request)
    
    clean_uid = user_id.strip()
    clean_name = full_name.strip()
    clean_dept = department.strip()
    clean_email = email.strip() if email else None
    pass_hash = hash_password(temporary_password.strip())

    with get_db() as conn:
        cursor = conn.cursor()
        try:
            cursor.execute("""
                INSERT INTO users (user_id, full_name, department, email, password_hash, role, must_change_password)
                VALUES (?, ?, ?, ?, ?, 'teacher', 1)
            """, (clean_uid, clean_name, clean_dept, clean_email, pass_hash))
        except Exception as e:
            if "UNIQUE constraint failed: users.user_id" in str(e):
                raise HTTPException(status_code=400, detail=f"A faculty member with ID '{clean_uid}' already exists.")
            if "UNIQUE constraint failed: users.email" in str(e):
                raise HTTPException(status_code=400, detail=f"Email '{clean_email}' is already associated with an account.")
            raise e

    return RedirectResponse(url="/department?tab=teachers&teacher_added=1", status_code=303)

@router.post("/department/teachers/delete/{teacher_user_id}")
async def delete_teacher(request: Request, teacher_user_id: str):
    admin = require_dept_admin(request)
    clean_uid = teacher_user_id.strip()
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id, full_name FROM users WHERE user_id = ? AND role = 'teacher'", (clean_uid,))
        t = cursor.fetchone()
        if t:
            cursor.execute("DELETE FROM users WHERE id = ?", (t["id"],))
            log_audit(admin["id"], "DELETE_TEACHER", "users", clean_uid, f"Deleted faculty member {t['full_name']} ({clean_uid})", conn=conn)
    return RedirectResponse(url="/department?tab=teachers&teacher_deleted=1", status_code=303)

@router.post("/department/viewers/add")
async def add_dashboard_viewer(
    request: Request,
    user_id: str = Form(...),
    full_name: str = Form(...),
    email: str = Form(None),
    password: str = Form("viewer123")
):
    admin = require_dept_admin(request)
    clean_uid = user_id.strip()
    clean_name = full_name.strip()
    clean_email = email.strip() if email and email.strip() else None
    pass_hash = hash_password(password.strip())
    
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT value FROM system_settings WHERE key = 'department_name'")
        dept_row = cursor.fetchone()
        dept_name = dept_row[0] if dept_row and dept_row[0] else "Department Administration"
        
        try:
            cursor.execute("""
                INSERT INTO users (user_id, full_name, department, email, password_hash, role, must_change_password)
                VALUES (?, ?, ?, ?, ?, 'dashboard_viewer', 0)
            """, (clean_uid, clean_name, dept_name, clean_email, pass_hash))
            log_audit(admin["id"], "ADD_VIEWER", "users", clean_uid, f"Created Dashboard Viewer account {clean_name} ({clean_uid})", conn=conn)
        except Exception as e:
            if "UNIQUE constraint failed: users.user_id" in str(e):
                return RedirectResponse(url=f"/department?tab=teachers&error=User+ID+'{clean_uid}'+already+exists", status_code=303)
            if "UNIQUE constraint failed: users.email" in str(e):
                return RedirectResponse(url=f"/department?tab=teachers&error=Email+'{clean_email}'+already+in+use", status_code=303)
            raise e

    return RedirectResponse(url="/department?tab=teachers&viewer_added=1", status_code=303)

@router.post("/department/viewers/delete/{viewer_user_id}")
async def delete_dashboard_viewer(request: Request, viewer_user_id: str):
    admin = require_dept_admin(request)
    clean_uid = viewer_user_id.strip()
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM users WHERE user_id = ? AND role = 'dashboard_viewer'", (clean_uid,))
        log_audit(admin["id"], "DELETE_VIEWER", "users", clean_uid, f"Deleted Dashboard Viewer account {clean_uid}", conn=conn)
    return RedirectResponse(url="/department?tab=teachers&viewer_deleted=1", status_code=303)

@router.post("/department/settings/update")
async def update_branding_settings(
    request: Request,
    platform_name: str = Form(...),
    platform_tagline: str = Form(""),
    department_name: str = Form(""),
    institution_name: str = Form(...),
    accreditation_badge: str = Form("Accredited Academic Portal"),
    department_tagline: str = Form(""),
    admin_full_name: str = Form(None),
    admin_designation: str = Form(None),
    admin_email: str = Form(None),
    brand_color: str = Form("#4f46e5"),
    secondary_brand_color: str = Form("#0ea5e9"),
    font_family: str = Form("Outfit"),
    contact_email: str = Form(""),
    contact_phone: str = Form(""),
    contact_office: str = Form(""),
    branding_text: str = Form(""),
    welcome_message: str = Form(""),
    logo_icon: str = Form("fa-graduation-cap"),
    logo_image_url: str = Form(""),
    banner_image_url: str = Form(""),
    confirm_identity: str = Form("0"),
    logo_file: UploadFile = File(None),
    banner_file: UploadFile = File(None)
):
    user = require_dept_admin(request)
    
    final_logo_url = logo_image_url.strip() if isinstance(logo_image_url, str) else ""
    final_banner_url = banner_image_url.strip() if isinstance(banner_image_url, str) else ""

    # Logo file upload
    if isinstance(logo_file, UploadFile) and logo_file.filename:
        ext = os.path.splitext(logo_file.filename)[1].lower()
        if ext in [".png", ".jpg", ".jpeg", ".svg", ".webp", ".ico"]:
            safe_logo_name = f"logo_{uuid.uuid4().hex[:8]}{ext}"
            file_path = os.path.join(UPLOAD_DIR, safe_logo_name)
            with open(file_path, "wb") as buffer:
                shutil.copyfileobj(logo_file.file, buffer)
            final_logo_url = f"/static/uploads/{safe_logo_name}"

    # Banner / cover file upload
    if isinstance(banner_file, UploadFile) and banner_file.filename:
        ext = os.path.splitext(banner_file.filename)[1].lower()
        if ext in [".png", ".jpg", ".jpeg", ".svg", ".webp"]:
            safe_banner_name = f"banner_{uuid.uuid4().hex[:8]}{ext}"
            file_path = os.path.join(UPLOAD_DIR, safe_banner_name)
            with open(file_path, "wb") as buffer:
                shutil.copyfileobj(banner_file.file, buffer)
            final_banner_url = f"/static/uploads/{safe_banner_name}"

    settings = {
        "platform_name": platform_name.strip(),
        "platform_tagline": platform_tagline.strip() if platform_tagline else (department_tagline.strip() if department_tagline else "Department Portal"),
        "department_name": department_name.strip() if department_name.strip() else platform_name.strip(),
        "institution_name": institution_name.strip(),
        "accreditation_badge": accreditation_badge.strip() if accreditation_badge else "Accredited Academic Portal",
        "department_tagline": department_tagline.strip(),
        "brand_color": brand_color.strip(),
        "secondary_brand_color": secondary_brand_color.strip() if secondary_brand_color else "#0ea5e9",
        "font_family": font_family.strip() if font_family else "Outfit",
        "contact_email": contact_email.strip(),
        "contact_phone": contact_phone.strip(),
        "contact_office": contact_office.strip(),
        "branding_text": branding_text.strip(),
        "welcome_message": welcome_message.strip(),
        "logo_icon": logo_icon.strip(),
        "logo_image_url": final_logo_url,
        "department_banner_url": final_banner_url
    }
    update_system_settings(settings)

    # Administrator Name, Designation & Email Update (Directly from Governance Form)
    if isinstance(admin_full_name, str) and admin_full_name.strip():
        clean_admin_name = admin_full_name.strip()
        clean_desig = admin_designation.strip() if isinstance(admin_designation, str) and admin_designation.strip() else (user.get("designation") or "department head")
        clean_admin_email = admin_email.strip() if isinstance(admin_email, str) and admin_email.strip() else user["email"]
        norm_admin = normalize_name(clean_admin_name)
        with get_db() as conn:
            c = conn.cursor()
            c.execute("""
                UPDATE users 
                SET full_name = ?, designation = ?, email = ?, normalized_name = ?
                WHERE id = ?
            """, (clean_admin_name, clean_desig, clean_admin_email, norm_admin, user["id"]))

    # Audit log
    log_audit(
        user["id"],
        "UPDATE_GOVERNANCE_BRANDING",
        "system_settings",
        "branding",
        f"Updated department governance: Name='{settings['department_name']}', Institution='{settings['institution_name']}', Admin='{admin_full_name or user['full_name']}', Designation='{admin_designation or user.get('designation', '')}'"
    )
    
    return RedirectResponse(url="/department?tab=governance&saved=1", status_code=303)

@router.post("/department/profile/update")
async def update_admin_personal_profile(
    request: Request,
    full_name: str = Form(...),
    designation: str = Form(""),
    avatar_url: str = Form(""),
    email: str = Form(""),
    avatar_file: UploadFile = File(None)
):
    """Allows Department Administrator to edit their personal profile fields."""
    user = require_dept_admin(request)
    
    clean_name = full_name.strip()
    clean_desig = designation.strip()
    clean_email = email.strip() if email.strip() else None
    final_avatar = avatar_url.strip() if avatar_url else ""

    if isinstance(avatar_file, UploadFile) and avatar_file.filename:
        ext = os.path.splitext(avatar_file.filename)[1].lower()
        if ext in [".png", ".jpg", ".jpeg", ".svg", ".webp"]:
            safe_avatar_name = f"avatar_{uuid.uuid4().hex[:8]}{ext}"
            file_path = os.path.join(UPLOAD_DIR, safe_avatar_name)
            with open(file_path, "wb") as buffer:
                shutil.copyfileobj(avatar_file.file, buffer)
            final_avatar = f"/static/uploads/{safe_avatar_name}"

    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE users 
            SET full_name = ?, designation = ?, email = ?, avatar_url = ?, normalized_name = ?
            WHERE id = ?
        """, (clean_name, clean_desig, clean_email, final_avatar, normalize_name(clean_name), user["id"]))

    log_audit(
        user["id"],
        "UPDATE_PROFILE",
        "users",
        str(user["id"]),
        f"Admin updated personal profile: Name='{clean_name}', Designation='{clean_desig}'"
    )

    return RedirectResponse(url="/department?tab=governance&profile_saved=1", status_code=303)

@router.post("/department/powerbi/generate-key")
async def generate_powerbi_key(request: Request):
    """Generates and rotates the Power BI & External Analytics API Key."""
    user = require_dept_admin(request)
    new_key = f"pbi_live_{uuid.uuid4().hex}"
    update_system_settings({"powerbi_api_key": new_key})
    
    log_audit(
        user["id"],
        "GENERATE_POWERBI_KEY",
        "system_settings",
        "powerbi_api_key",
        "Rotated and issued new Power BI / External Analytics API access key"
    )
    
    return RedirectResponse(url="/department?tab=integrations&key_generated=1", status_code=303)

@router.post("/department/notifications/settings")
async def update_notifications_settings_route(request: Request):
    """Updates notification delivery triggers and administrator preferences."""
    user = require_dept_admin(request)
    form_data = await request.form()
    
    settings = get_notification_settings()
    updated = {}
    for s in settings:
        k = s["event_type"]
        is_checked = 1 if form_data.get(f"notify_{k}") == "1" else 0
        updated[k] = {"is_enabled": is_checked}
        
    update_notification_settings(updated)
    
    log_audit(
        user["id"],
        "UPDATE_NOTIFICATION_SETTINGS",
        "notification_settings",
        "all",
        "Updated system-wide notification event triggers"
    )
    
    return RedirectResponse(url="/department?tab=integrations&notifications_saved=1", status_code=303)

@router.get("/department/export-subject-csv")
async def export_subject_csv(request: Request, subject: str = None):
    """Exports Subject Participation & Academic Performance metrics to CSV."""
    require_dept_admin_or_teacher(request)
    
    with get_db() as conn:
        cursor = conn.cursor()
        subj_filter = "WHERE COALESCE(NULLIF(c.subject, ''), NULLIF(c.department, ''), 'General') = ?" if subject and subject != "all" else "WHERE 1=1"
        params = [subject] if subject and subject != "all" else []
        
        cursor.execute(f"""
            SELECT 
                COALESCE(NULLIF(c.subject, ''), NULLIF(c.department, ''), 'General') as "SUBJECT NAME",
                COUNT(DISTINCT c.id) as "COURSES COUNT",
                COUNT(DISTINCT e.user_id) as "UNIQUE STUDENTS ENROLLED",
                COUNT(e.id) as "TOTAL ENROLLMENTS",
                COUNT(DISTINCT CASE WHEN u.last_active_at >= datetime('now', '-5 minutes') THEN e.user_id END) as "LIVE STUDENTS (5M)",
                COUNT(DISTINCT CASE WHEN u.last_active_at >= datetime('now', '-24 hours') THEN e.user_id END) as "ACTIVE TODAY",
                COALESCE(ROUND(AVG(qa.score_percent), 1), 0.0) as "AVG QUIZ SCORE (%)",
                COUNT(qa.id) as "QUIZ ATTEMPTS",
                COUNT(DISTINCT CASE WHEN e.completed_at IS NOT NULL THEN e.user_id END) as "STUDENTS COMPLETED"
            FROM courses c
            LEFT JOIN enrollments e ON c.id = e.course_id
            LEFT JOIN users u ON e.user_id = u.id
            LEFT JOIN modules m ON c.id = m.course_id
            LEFT JOIN lessons l ON m.id = l.module_id
            LEFT JOIN quizzes q ON l.id = q.lesson_id
            LEFT JOIN quiz_attempts qa ON q.id = qa.quiz_id AND qa.user_id = e.user_id
            {subj_filter} AND c.status != 'deleted'
            GROUP BY COALESCE(NULLIF(c.subject, ''), NULLIF(c.department, ''), 'General')
            ORDER BY 1 ASC
        """, params)
        rows = cursor.fetchall()
        
    output = io.StringIO()
    writer = csv.writer(output)
    if rows:
        writer.writerow(rows[0].keys())
        for r in rows:
            writer.writerow(list(r))
    else:
        writer.writerow(["No Subject Participation Records Available"])
        
    output.seek(0)
    filename = f"Subject_Participation_Report_{subject or 'All'}.csv"
    return Response(
        content=output.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )

@router.get("/department/export-csv")
async def export_department_csv(request: Request, department: str = None):
    require_dept_admin_or_teacher(request)
    
    with get_db() as conn:
        cursor = conn.cursor()
        
        dept_filter = " AND (u.department = ? OR u.district = ? OR u.school_name = ?)" if department and department != "all" else ""
        params = [department, department, department] if department and department != "all" else []

        cursor.execute(f"""
            SELECT 
                u.user_id as "Serial NO. (UNIQUE NO.)",
                u.full_name as "STUDENT NAME",
                COALESCE(u.guardian_name, '') as "FATHER'/GUARDIAN NAME",
                COALESCE(u.school_name, '') as "SCHOOL NAME",
                COALESCE(u.udise_code, '') as "UDISE CODE",
                COALESCE(u.block, '') as "BLOCK",
                COALESCE(u.district, '') as "DISTRICT",
                COALESCE(u.state, '') as "STATE",
                COALESCE(u.pincode, '') as "PINCODE",
                COALESCE((SELECT GROUP_CONCAT(c.code, '; ') FROM enrollments e JOIN courses c ON e.course_id = c.id WHERE e.user_id = u.id), 'None') as "ASSIGNED COURSES",
                COALESCE(u.email, 'Not Linked') as "EMAIL",
                CASE WHEN u.must_change_password = 1 THEN 'Temporary Password' ELSE 'Active' END as "ACCOUNT STATUS",
                COUNT(DISTINCT e.course_id) as "COURSES ENROLLED",
                COUNT(DISTINCT CASE WHEN e.completed_at IS NOT NULL THEN e.course_id END) as "COURSES COMPLETED",
                (SELECT COUNT(*) FROM lesson_progress lp WHERE lp.user_id = u.id AND lp.is_completed = 1) as "LESSONS FINISHED",
                ROUND((SELECT COALESCE(AVG(qa.score_percent), 0) FROM quiz_attempts qa WHERE qa.user_id = u.id), 1) as "AVG QUIZ SCORE (%)"
            FROM users u
            LEFT JOIN enrollments e ON u.id = e.user_id
            WHERE u.role = 'student'{dept_filter}
            GROUP BY u.id
            ORDER BY u.user_id ASC
        """, params)
        
        rows = cursor.fetchall()
        
    output = io.StringIO()
    writer = csv.writer(output)
    
    if rows:
        writer.writerow(rows[0].keys())
        for row in rows:
            writer.writerow(list(row))
    else:
        writer.writerow(["No student data available"])

    output.seek(0)
    dept_label = department if department and department != "all" else "All_Districts"
    filename = f"LMS_Student_Roster_{dept_label}.csv"
    
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )

@router.get("/department/download-sample-csv")
async def download_sample_csv():
    """Provides a ready-to-use CSV template matching the required headers including COURSE."""
    output = io.StringIO()
    writer = csv.writer(output)
    
    headers = [
        "Serial NO. (UNIQUE NO.)",
        "STUDENT NAME",
        "FATHER'/GUARDIAN, NAME",
        "SCHOOL NAME",
        "UDISE CODE",
        "BLOCK",
        "DISTRICT",
        "STATE",
        "PINCODE",
        "COURSE"
    ]
    sample_rows = [
        ["KA-2026-101", "Aarav Kumar", "Ramesh Kumar", "Govt Model High School", "29280100101", "North Block", "Bengaluru", "Karnataka", "560001", "CS-201"],
        ["KA-2026-102", "Priya Sharma", "Sunil Sharma", "Govt Girls High School", "29280100102", "South Block", "Bengaluru", "Karnataka", "560002", "CS-201"],
        ["KA-2026-103", "Rohan Mehta", "Deepak Mehta", "St Xavier Model School", "29280100103", "East Block", "Mysuru", "Karnataka", "570001", "CS-201"]
    ]
    writer.writerow(headers)
    for r in sample_rows:
        writer.writerow(r)
        
    output.seek(0)
    return Response(
        content=output.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=Sample_Student_Import_Template.csv"}
    )

@router.get("/department/download-rejected-report")
async def download_rejected_report():
    """Generates a downloadable CSV of all rejected rows and duplicates from the most recent import."""
    global LAST_IMPORT_REJECTED
    output = io.StringIO()
    writer = csv.writer(output)
    
    if LAST_IMPORT_REJECTED:
        headers = list(LAST_IMPORT_REJECTED[0].keys())
        writer.writerow(headers)
        for r in LAST_IMPORT_REJECTED:
            writer.writerow([r.get(h, "") for h in headers])
    else:
        writer.writerow(["Notice"])
        writer.writerow(["No rejected or duplicate records found in the last import session."])
        
    output.seek(0)
    return Response(
        content=output.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=Student_Import_Rejected_Report.csv"}
    )

@router.post("/department/import-students")
async def import_students_csv(
    request: Request,
    file: UploadFile = File(...),
    default_password: str = Form("welcome123")
):
    global LAST_IMPORT_REJECTED
    user = require_dept_admin_or_teacher(request)
    
    contents = await file.read()
    if not contents or len(contents) == 0:
        return RedirectResponse(url="/department?tab=students&error=Empty+file+uploaded", status_code=303)

    rows = parse_student_upload(contents, file.filename or "")
    if not rows:
        return RedirectResponse(url="/department?tab=students&error=No+records+found+in+file", status_code=303)

    default_hash = hash_password(default_password.strip())
    imported_count = 0
    existing_enrolled_count = 0
    duplicates_skipped_count = 0
    rejected_rows = []
    seen_in_file = set()

    with get_db() as conn:
        cursor = conn.cursor()
        
        # Pre-cache courses for fast code / title matching
        cursor.execute("SELECT id, code, title FROM courses")
        course_map = {}
        for c in cursor.fetchall():
            course_map[re.sub(r'[^a-z0-9]', '', c["code"].lower())] = c["id"]
            course_map[re.sub(r'[^a-z0-9]', '', c["title"].lower())] = c["id"]
        
        for row in rows:
            uid = extract_field(row, "Serial NO. (UNIQUE NO.)", "Serial NO.", "Serial No", "UNIQUE NO.", "student_id", "ID", "Serial No.")
            name = extract_field(row, "STUDENT NAME", "Student Name", "name", "full_name")
            guardian = extract_field(row, "FATHER'/GUARDIAN, NAME", "FATHER'/GUARDIAN", "FATHER/GUARDIAN", "Father's Name", "Guardian Name", "father_name", "guardian_name")
            school = extract_field(row, "SCHOOL NAME", "School Name", "school_name", "school")
            udise = extract_field(row, "UDISE CODE", "UDISE Code", "udise_code", "udise")
            block = extract_field(row, "BLOCK", "Block", "block")
            district = extract_field(row, "DISTRICT", "District", "district")
            state = extract_field(row, "STATE", "State", "state")
            pincode = extract_field(row, "PINCODE", "Pincode", "PIN CODE", "Pin Code", "pin")
            course_val = extract_field(row, "COURSE", "Course", "COURSE CODE", "Course Code", "COURSES", "Subject", "COURSE NAME")
            
            # Validation 1: Student Name required
            if not name:
                r_dict = dict(row)
                r_dict["Rejection Reason"] = "Missing required Student Name"
                rejected_rows.append(r_dict)
                continue

            # Validation 2: Father / Guardian Name required for duplicate check
            if not guardian:
                r_dict = dict(row)
                r_dict["Rejection Reason"] = "Missing Father/Guardian Name (required for duplicate prevention)"
                rejected_rows.append(r_dict)
                continue

            norm_name = normalize_name(name)
            norm_guardian = normalize_name(guardian)
            dedup_pair = (norm_name, norm_guardian)

            # Validation 3: Check duplicate within the uploaded file
            if dedup_pair in seen_in_file:
                r_dict = dict(row)
                r_dict["Rejection Reason"] = f"In-file duplicate: Student '{name}' with Guardian '{guardian}' appears multiple times in upload"
                rejected_rows.append(r_dict)
                duplicates_skipped_count += 1
                continue
            seen_in_file.add(dedup_pair)

            dept = district if district else (school if school else user["department"])

            # Validation 4: Check if student already exists in Global Student Pool
            cursor.execute("""
                SELECT id, user_id, full_name, guardian_name 
                FROM users 
                WHERE (normalized_name = ? AND normalized_guardian = ?) OR (user_id = ? AND user_id != '')
            """, (norm_name, norm_guardian, uid if uid else ""))
            existing_student = cursor.fetchone()

            if existing_student:
                # Student already exists in the Global Student Pool!
                # If course is specified, enrol the existing student into the course (PRD Section 3)
                if course_val:
                    course_tokens = re.split(r'[,;]+', course_val)
                    enrolled_in_any = False
                    for c_tok in course_tokens:
                        clean_tok = re.sub(r'[^a-z0-9]', '', c_tok.lower())
                        matched_c_id = course_map.get(clean_tok)
                        if matched_c_id:
                            cursor.execute("INSERT OR IGNORE INTO enrollments (user_id, course_id) VALUES (?, ?)", (existing_student["id"], matched_c_id))
                            enrolled_in_any = True
                    if enrolled_in_any:
                        existing_enrolled_count += 1
                    else:
                        r_dict = dict(row)
                        r_dict["Rejection Reason"] = f"Existing student in Global Pool (ID: {existing_student['user_id']}) - specified course '{course_val}' not found"
                        rejected_rows.append(r_dict)
                        duplicates_skipped_count += 1
                else:
                    r_dict = dict(row)
                    r_dict["Rejection Reason"] = f"Student already exists in Global Student Pool (Existing Student ID: {existing_student['user_id']})"
                    rejected_rows.append(r_dict)
                    duplicates_skipped_count += 1
                continue

            # If student does not exist: generate ID if not provided
            if not uid:
                uid = generate_unique_student_id(cursor)

            try:
                cursor.execute("""
                    INSERT INTO users (
                        user_id, full_name, department, email, password_hash, role, must_change_password,
                        guardian_name, school_name, udise_code, block, district, state, pincode,
                        normalized_name, normalized_guardian
                    )
                    VALUES (?, ?, ?, NULL, ?, 'student', 1, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (uid, name, dept, default_hash, guardian, school, udise, block, district, state, pincode, norm_name, norm_guardian))
                
                new_user_id = cursor.lastrowid
                
                # Check for course assignment from upload
                if course_val:
                    course_tokens = re.split(r'[,;]+', course_val)
                    for c_tok in course_tokens:
                        clean_tok = re.sub(r'[^a-z0-9]', '', c_tok.lower())
                        matched_c_id = course_map.get(clean_tok)
                        if matched_c_id:
                            cursor.execute("INSERT OR IGNORE INTO enrollments (user_id, course_id) VALUES (?, ?)", (new_user_id, matched_c_id))
                
                imported_count += 1
            except Exception as e:
                r_dict = dict(row)
                r_dict["Rejection Reason"] = f"Database insertion error: {str(e)}"
                rejected_rows.append(r_dict)
                duplicates_skipped_count += 1

        LAST_IMPORT_REJECTED = rejected_rows
        log_audit(user["id"], "STUDENT_IMPORT", "users", None, f"Imported: {imported_count}, Existing Enrolled: {existing_enrolled_count}, Duplicates: {duplicates_skipped_count}, Rejected: {len(rejected_rows)}")

    return RedirectResponse(
        url=f"/department?tab=students&imported={imported_count}&existing={existing_enrolled_count}&duplicates={duplicates_skipped_count}&rejected={len(rejected_rows)}",
        status_code=303
    )

@router.post("/department/students/register-single")
async def register_single_student(
    request: Request,
    full_name: str = Form(...),
    guardian_name: str = Form(""),
    school_name: str = Form(""),
    udise_code: str = Form(""),
    block: str = Form(""),
    district: str = Form(""),
    state: str = Form(""),
    pincode: str = Form(""),
    email: str = Form(""),
    course_id: int = Form(0),
    custom_student_id: str = Form(""),
    flag_conflict: int = Form(0),
    default_password: str = Form("welcome123")
):
    """
    Workflow A & B:
    Teacher or Admin enters student's name and optional guardian name.
    System checks the Global Student Pool.
    If student exists: displays existing student ID with option to enrol.
    If conflict flagged: submits for administrative conflict review.
    If student does not exist: creates new permanent student record and enrols in course.
    """
    user = require_dept_admin_or_teacher(request)
    
    clean_name = full_name.strip()
    clean_guardian = guardian_name.strip() if guardian_name and guardian_name.strip() else "Not specified"
    
    if not clean_name:
        return RedirectResponse(url="/department?tab=students&error=Student+Full+Name+is+required", status_code=303)
        
    norm_name = normalize_name(clean_name)
    norm_guardian = normalize_name(clean_guardian)
    
    with get_db() as conn:
        cursor = conn.cursor()
        
        # Check duplicate
        cursor.execute("""
            SELECT id, user_id, full_name, guardian_name, school_name, district
            FROM users
            WHERE normalized_name = ? AND normalized_guardian = ?
        """, (norm_name, norm_guardian))
        existing = cursor.fetchone()
        
        if existing and not flag_conflict:
            # Student already exists!
            # If user specified a course, enrol the existing student into the course
            if course_id > 0:
                cursor.execute("INSERT OR IGNORE INTO enrollments (user_id, course_id) VALUES (?, ?)", (existing["id"], course_id))
                log_audit(user["id"], "ENROLL_EXISTING", "users", existing["user_id"], f"Enrolled existing student {existing['user_id']} into course ID {course_id}", conn=conn)
                return RedirectResponse(
                    url=f"/department?tab=students&msg=Student+already+exists+in+Global+Pool+(ID:+{existing['user_id']}).+Successfully+added+to+selected+course.",
                    status_code=303
                )
            else:
                return RedirectResponse(
                    url=f"/department?tab=students&existing_id={existing['user_id']}&existing_name={existing['full_name']}&warning=duplicate_found",
                    status_code=303
                )

        if existing and flag_conflict:
            # User asserts genuine different student sharing names -> flag for administrative review
            cursor.execute("""
                INSERT INTO student_conflicts (student_name, guardian_name, existing_user_id, requested_data)
                VALUES (?, ?, ?, ?)
            """, (clean_name, clean_guardian, existing["user_id"], json.dumps({
                "school": school_name, "district": district, "course_id": course_id, "registered_by": user["full_name"]
            })))
            log_audit(user["id"], "FLAG_CONFLICT", "student_conflicts", existing["user_id"], f"Conflict flagged for {clean_name} / {clean_guardian}", conn=conn)
            return RedirectResponse(
                url="/department?tab=students&msg=Student+record+flagged+for+Administrative+Conflict+Review.+Department+Head+will+review.",
                status_code=303
            )

        # Check if custom_student_id is specified and already exists
        if custom_student_id.strip():
            cursor.execute("SELECT id FROM users WHERE user_id = ?", (custom_student_id.strip(),))
            if cursor.fetchone():
                return RedirectResponse(url=f"/department?tab=students&error=Student+Login+ID+'{custom_student_id.strip()}'+already+taken.+Please+choose+another.", status_code=303)

        # Create new student record
        new_uid = custom_student_id.strip() if custom_student_id.strip() else generate_unique_student_id(cursor)
        dept = district.strip() if district.strip() else (school_name.strip() if school_name.strip() else user["department"])
        default_hash = hash_password(default_password.strip())
        
        cursor.execute("""
            INSERT INTO users (
                user_id, full_name, department, email, password_hash, role, must_change_password,
                guardian_name, school_name, udise_code, block, district, state, pincode,
                normalized_name, normalized_guardian
            )
            VALUES (?, ?, ?, ?, ?, 'student', 1, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            new_uid, clean_name, dept, email.strip() if email.strip() else None,
            default_hash, clean_guardian, school_name.strip(), udise_code.strip(),
            block.strip(), district.strip(), state.strip(), pincode.strip(),
            norm_name, norm_guardian
        ))
        new_id = cursor.lastrowid
        
        if course_id > 0:
            cursor.execute("INSERT OR IGNORE INTO enrollments (user_id, course_id) VALUES (?, ?)", (new_id, course_id))
            
        log_audit(user["id"], "REGISTER_STUDENT", "users", new_uid, f"Registered new student {clean_name} (ID: {new_uid})", conn=conn)

    return RedirectResponse(url=f"/department?tab=students&registered_id={new_uid}", status_code=303)

@router.post("/department/students/delete-all")
async def delete_all_students(request: Request):
    admin = require_dept_admin(request)
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id, user_id FROM users WHERE role = 'student'")
        students = cursor.fetchall()
        count = len(students)
        if count > 0:
            student_int_ids = [s["id"] for s in students]
            student_str_ids = [s["user_id"] for s in students]
            int_ph = ",".join("?" for _ in student_int_ids)
            str_ph = ",".join("?" for _ in student_str_ids)
            
            cursor.execute(f"DELETE FROM enrollments WHERE user_id IN ({int_ph})", student_int_ids)
            cursor.execute(f"DELETE FROM lesson_progress WHERE user_id IN ({int_ph})", student_int_ids)
            cursor.execute(f"DELETE FROM quiz_attempts WHERE user_id IN ({int_ph})", student_int_ids)
            cursor.execute(f"DELETE FROM support_queries WHERE user_id IN ({str_ph})", student_str_ids)
            cursor.execute("DELETE FROM student_conflicts")
            cursor.execute("DELETE FROM users WHERE role = 'student'")
            
            log_audit(admin["id"], "DELETE_ALL_STUDENTS", "users", "ALL", f"Deleted all {count} registered students and associated learning data.", conn=conn)

    return RedirectResponse(url=f"/department?tab=students&deleted_all=1&count={count}", status_code=303)

@router.post("/department/students/delete/{student_user_id}")
async def delete_single_student(request: Request, student_user_id: str):
    admin = require_dept_admin(request)
    clean_uid = student_user_id.strip()
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id, full_name FROM users WHERE user_id = ? AND role = 'student'", (clean_uid,))
        st = cursor.fetchone()
        if st:
            st_id = st["id"]
            st_name = st["full_name"]
            cursor.execute("DELETE FROM enrollments WHERE user_id = ?", (st_id,))
            cursor.execute("DELETE FROM lesson_progress WHERE user_id = ?", (st_id,))
            cursor.execute("DELETE FROM quiz_attempts WHERE user_id = ?", (st_id,))
            cursor.execute("DELETE FROM support_queries WHERE user_id = ?", (clean_uid,))
            cursor.execute("DELETE FROM users WHERE id = ?", (st_id,))
            log_audit(admin["id"], "DELETE_STUDENT", "users", clean_uid, f"Deleted student record {st_name} ({clean_uid})", conn=conn)

    return RedirectResponse(url=f"/department?tab=students&student_deleted={clean_uid}", status_code=303)

@router.get("/api/students/check-duplicate")
async def api_check_duplicate(name: str, guardian: str):
    """Real-time duplicate check endpoint for interactive frontend validation."""
    norm_n = normalize_name(name)
    norm_g = normalize_name(guardian)
    if not norm_n or not norm_g:
        return JSONResponse({"exists": False})
        
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, user_id, full_name, guardian_name, school_name, district
            FROM users
            WHERE normalized_name = ? AND normalized_guardian = ?
        """, (norm_n, norm_g))
        row = cursor.fetchone()
        if row:
            return JSONResponse({
                "exists": True,
                "student": {
                    "id": row["id"],
                    "user_id": row["user_id"],
                    "full_name": row["full_name"],
                    "guardian_name": row["guardian_name"],
                    "school_name": row["school_name"] or "",
                    "district": row["district"] or ""
                }
            })
    return JSONResponse({"exists": False})

@router.post("/department/permissions/update")
async def update_permissions_route(request: Request):
    """Allows Administrator / HOD to configure dashboard widgets and role access without changing source code."""
    user = require_dept_admin(request)
    form_data = await request.form()
    
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT widget_key FROM dashboard_permissions")
        keys = [r[0] for r in cursor.fetchall()]
        
        for k in keys:
            is_en = 1 if form_data.get(f"enable_{k}") == "1" else 0
            roles_list = form_data.getlist(f"roles_{k}")
            allowed_roles = ",".join(roles_list) if roles_list else "department_admin"
            cursor.execute("""
                UPDATE dashboard_permissions
                SET is_enabled = ?, allowed_roles = ?
                WHERE widget_key = ?
            """, (is_en, allowed_roles, k))
            
        log_audit(user["id"], "UPDATE_PERMISSIONS", "dashboard_permissions", "all", "Updated dashboard widget permissions")

    return RedirectResponse(url="/department?tab=governance&permissions_saved=1", status_code=303)

@router.post("/department/conflicts/resolve")
async def resolve_student_conflict(
    request: Request,
    conflict_id: int = Form(...),
    action: str = Form(...)  # 'approve' or 'reject'
):
    user = require_dept_admin(request)
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM student_conflicts WHERE id = ?", (conflict_id,))
        conflict = cursor.fetchone()
        if not conflict:
            raise HTTPException(status_code=404, detail="Conflict not found")
            
        if action == "approve":
            # Admin verifies it is a genuine separate student
            req_data = json.loads(conflict["requested_data"] or "{}")
            new_uid = generate_unique_student_id(cursor)
            norm_n = normalize_name(conflict["student_name"])
            norm_g = normalize_name(conflict["guardian_name"])
            default_hash = hash_password("welcome123")
            cursor.execute("""
                INSERT INTO users (
                    user_id, full_name, department, password_hash, role, must_change_password,
                    guardian_name, school_name, district, normalized_name, normalized_guardian
                )
                VALUES (?, ?, ?, ?, 'student', 1, ?, ?, ?, ?, ?)
            """, (
                new_uid, conflict["student_name"], req_data.get("district") or user["department"],
                default_hash, conflict["guardian_name"], req_data.get("school", ""),
                req_data.get("district", ""), norm_n, norm_g + " [verified_distinct]"
            ))
            new_id = cursor.lastrowid
            if req_data.get("course_id"):
                cursor.execute("INSERT OR IGNORE INTO enrollments (user_id, course_id) VALUES (?, ?)", (new_id, int(req_data["course_id"])))
            cursor.execute("UPDATE student_conflicts SET status = 'resolved' WHERE id = ?", (conflict_id,))
            log_audit(user["id"], "RESOLVE_CONFLICT", "users", new_uid, f"Approved distinct student identity {conflict['student_name']} (ID: {new_uid})")
        else:
            cursor.execute("UPDATE student_conflicts SET status = 'rejected' WHERE id = ?", (conflict_id,))
            log_audit(user["id"], "REJECT_CONFLICT", "student_conflicts", str(conflict_id), f"Rejected conflict claim for {conflict['student_name']}")

    return RedirectResponse(url="/department?tab=students&conflict_resolved=1", status_code=303)
