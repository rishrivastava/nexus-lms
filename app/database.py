import sqlite3
import os
from typing import Optional, Dict, Any, List
from contextlib import contextmanager

DB_PATH = os.environ.get("LMS_DB_PATH", os.path.join(os.path.dirname(os.path.dirname(__file__)), "lms.db"))
UPLOAD_DIR = os.path.join(os.path.dirname(__file__), "static", "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)

@contextmanager
def get_db():
    conn = sqlite3.connect(DB_PATH, timeout=30.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.execute("PRAGMA journal_mode = WAL;")
    conn.execute("PRAGMA busy_timeout = 30000;")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

def init_db():
    with get_db() as conn:
        cursor = conn.cursor()
        
        # 1. Users Table
        # Roles: 'student', 'teacher', 'department_admin'
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT UNIQUE NOT NULL,               -- e.g. "CS2026-001" or "T-JOHN"
            full_name TEXT NOT NULL,
            department TEXT NOT NULL,                  -- e.g. "Computer Science" or School/District
            email TEXT UNIQUE,                         -- Can be NULL initially
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT 'student',      -- 'student', 'teacher', 'department_admin'
            must_change_password INTEGER DEFAULT 1,    -- 1 = must reset on first login
            guardian_name TEXT,                        -- Father's / Guardian's name
            school_name TEXT,                          -- School Name
            udise_code TEXT,                           -- UDISE Code
            block TEXT,                                -- Block
            district TEXT,                             -- District
            state TEXT,                                -- State
            pincode TEXT,                              -- PIN Code
            last_active_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """)
        
        # Ensure new educational & duplicate prevention columns exist in already initialized DBs
        cursor.execute("PRAGMA table_info(users)")
        existing_cols = {row["name"] for row in cursor.fetchall()}
        new_cols = {
            "guardian_name": "TEXT",
            "school_name": "TEXT",
            "udise_code": "TEXT",
            "block": "TEXT",
            "district": "TEXT",
            "state": "TEXT",
            "pincode": "TEXT",
            "normalized_name": "TEXT",
            "normalized_guardian": "TEXT",
            "designation": "TEXT",
            "avatar_url": "TEXT",
            "phone": "TEXT",
            "bio": "TEXT",
            "last_active_at": "TIMESTAMP"
        }
        for col, col_type in new_cols.items():
            if col not in existing_cols:
                cursor.execute(f"ALTER TABLE users ADD COLUMN {col} {col_type}")
        cursor.execute("UPDATE users SET last_active_at = CURRENT_TIMESTAMP WHERE last_active_at IS NULL")

        # Create index on normalized names for fast duplicate detection
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_users_normalized ON users(normalized_name, normalized_guardian);")
        
        # 2. Courses Table
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS courses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            code TEXT UNIQUE NOT NULL,                 -- e.g. "CS101"
            department TEXT NOT NULL,
            subject TEXT,                              -- Subject grouping e.g. "Computer Science", "Mathematics"
            description TEXT,
            thumbnail_url TEXT,
            teacher_id INTEGER NOT NULL,
            is_published INTEGER DEFAULT 1,            -- 1 = published, 0 = draft, 2 = archived
            status TEXT DEFAULT 'published',           -- 'published', 'draft', 'archived', 'deleted'
            archived_at TIMESTAMP,
            deleted_at TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (teacher_id) REFERENCES users(id) ON DELETE CASCADE
        );
        """)

        # Migration check for courses new columns
        cursor.execute("PRAGMA table_info(courses)")
        course_cols = {row["name"] for row in cursor.fetchall()}
        course_new_cols = {
            "subject": "TEXT",
            "subtitle": "TEXT",
            "learning_path": "TEXT",
            "instructions": "TEXT",
            "status": "TEXT DEFAULT 'published'",
            "archived_at": "TIMESTAMP",
            "deleted_at": "TIMESTAMP"
        }
        for col, col_type in course_new_cols.items():
            if col not in course_cols:
                cursor.execute(f"ALTER TABLE courses ADD COLUMN {col} {col_type}")
        cursor.execute("UPDATE courses SET subject = department WHERE subject IS NULL OR subject = ''")
        cursor.execute("UPDATE courses SET status = 'published' WHERE status IS NULL OR status = ''")
        
        # 3. Modules (Chapters)
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS modules (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            course_id INTEGER NOT NULL,
            title TEXT NOT NULL,
            description TEXT,
            position INTEGER DEFAULT 1,
            FOREIGN KEY (course_id) REFERENCES courses(id) ON DELETE CASCADE
        );
        """)
        cursor.execute("PRAGMA table_info(modules)")
        mod_cols = {row["name"] for row in cursor.fetchall()}
        if "description" not in mod_cols:
            cursor.execute("ALTER TABLE modules ADD COLUMN description TEXT")
        
        # 4. Lessons (Video, PDF, or Quiz)
        # content_type: 'youtube', 'pdf', 'quiz'
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS lessons (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            module_id INTEGER NOT NULL,
            title TEXT NOT NULL,
            subtitle TEXT,
            description TEXT,
            content_type TEXT NOT NULL,                -- 'youtube', 'pdf', 'quiz'
            content_value TEXT,                        -- YouTube URL/ID or uploaded PDF filename or instructions
            position INTEGER DEFAULT 1,
            duration_minutes INTEGER DEFAULT 10,
            FOREIGN KEY (module_id) REFERENCES modules(id) ON DELETE CASCADE
        );
        """)
        cursor.execute("PRAGMA table_info(lessons)")
        les_cols = {row["name"] for row in cursor.fetchall()}
        if "subtitle" not in les_cols:
            cursor.execute("ALTER TABLE lessons ADD COLUMN subtitle TEXT")
        if "description" not in les_cols:
            cursor.execute("ALTER TABLE lessons ADD COLUMN description TEXT")
        
        # 5. Quizzes
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS quizzes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            lesson_id INTEGER UNIQUE NOT NULL,
            passing_score INTEGER DEFAULT 70,          -- Percentage needed to pass
            time_limit_minutes INTEGER DEFAULT 10,     -- Time limit enforced by backend
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (lesson_id) REFERENCES lessons(id) ON DELETE CASCADE
        );
        """)

        # Migration check for quizzes time_limit_minutes
        cursor.execute("PRAGMA table_info(quizzes)")
        q_cols = {row["name"] for row in cursor.fetchall()}
        if "time_limit_minutes" not in q_cols:
            cursor.execute("ALTER TABLE quizzes ADD COLUMN time_limit_minutes INTEGER DEFAULT 10")
        
        # 6. Quiz Questions & Options
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS quiz_questions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            quiz_id INTEGER NOT NULL,
            question_text TEXT NOT NULL,
            option_a TEXT NOT NULL,
            option_b TEXT NOT NULL,
            option_c TEXT NOT NULL,
            option_d TEXT NOT NULL,
            correct_option TEXT NOT NULL,              -- 'A', 'B', 'C', or 'D'
            explanation TEXT,
            FOREIGN KEY (quiz_id) REFERENCES quizzes(id) ON DELETE CASCADE
        );
        """)
        
        # 7. Student Enrollments
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS enrollments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            course_id INTEGER NOT NULL,
            enrolled_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            completed_at TIMESTAMP,
            UNIQUE(user_id, course_id),
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
            FOREIGN KEY (course_id) REFERENCES courses(id) ON DELETE CASCADE
        );
        """)
        
        # 8. Lesson Progress Tracking
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS lesson_progress (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            lesson_id INTEGER NOT NULL,
            is_completed INTEGER DEFAULT 0,
            watched_seconds INTEGER DEFAULT 0,
            completed_at TIMESTAMP,
            UNIQUE(user_id, lesson_id),
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
            FOREIGN KEY (lesson_id) REFERENCES lessons(id) ON DELETE CASCADE
        );
        """)
        
        # 9. Quiz Attempts & Scores
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS quiz_attempts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            quiz_id INTEGER NOT NULL,
            score_percent REAL NOT NULL,
            passed INTEGER NOT NULL,
            started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            time_taken_seconds INTEGER DEFAULT 0,
            attempted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
            FOREIGN KEY (quiz_id) REFERENCES quizzes(id) ON DELETE CASCADE
        );
        """)

        cursor.execute("PRAGMA table_info(quiz_attempts)")
        qa_cols = {row["name"] for row in cursor.fetchall()}
        if "started_at" not in qa_cols:
            cursor.execute("ALTER TABLE quiz_attempts ADD COLUMN started_at TIMESTAMP")
        if "time_taken_seconds" not in qa_cols:
            cursor.execute("ALTER TABLE quiz_attempts ADD COLUMN time_taken_seconds INTEGER DEFAULT 0")
        if "attempt_data" not in qa_cols:
            cursor.execute("ALTER TABLE quiz_attempts ADD COLUMN attempt_data TEXT")

        # 10. Audit Logs Table (Tracks administrative actions)
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS audit_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            action TEXT NOT NULL,
            entity_type TEXT NOT NULL,
            entity_id TEXT,
            details TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """)

        # 11. Dashboard Permissions & Widgets Configuration Table
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS dashboard_permissions (
            widget_key TEXT PRIMARY KEY,
            widget_title TEXT NOT NULL,
            allowed_roles TEXT NOT NULL,                -- Comma-separated: 'department_admin,teacher,student'
            is_enabled INTEGER DEFAULT 1
        );
        """)

        default_widgets = [
            ("kpi_cards", "Executive KPI Cards", "department_admin,teacher", 1),
            ("course_groups", "Course Cohorts & Learning Analytics", "department_admin,teacher", 1),
            ("teacher_roster", "Faculty Workload Roster", "department_admin", 1),
            ("global_student_pool", "Global Student Pool Database", "department_admin,teacher", 1),
            ("branding_settings", "Custom Branding & Portal Configuration", "department_admin", 1),
            ("audit_logs", "Administrative Security & Audit Logs", "department_admin", 1)
        ]
        for wkey, wtitle, wroles, w_en in default_widgets:
            cursor.execute("""
                INSERT OR IGNORE INTO dashboard_permissions (widget_key, widget_title, allowed_roles, is_enabled)
                VALUES (?, ?, ?, ?)
            """, (wkey, wtitle, wroles, w_en))

        # 12. Student Duplicate Conflict Reviews Table
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS student_conflicts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_name TEXT NOT NULL,
            guardian_name TEXT NOT NULL,
            existing_user_id TEXT NOT NULL,
            requested_data TEXT,
            status TEXT DEFAULT 'pending',             -- 'pending', 'resolved', 'rejected'
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """)

        # 13. Notifications Table
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS notifications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            title TEXT NOT NULL,
            message TEXT NOT NULL,
            link_url TEXT,
            category TEXT DEFAULT 'general',           -- 'course', 'quiz', 'import', 'system', 'conflict'
            is_read INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        );
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_notifications_user ON notifications(user_id, is_read);")

        # 14. Notification Preferences Table
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS notification_settings (
            event_type TEXT PRIMARY KEY,
            event_title TEXT NOT NULL,
            is_enabled INTEGER DEFAULT 1,
            target_roles TEXT NOT NULL
        );
        """)
        default_notification_events = [
            ("course_assigned", "Course Enrolment / Assignment", 1, "student,teacher"),
            ("content_published", "New Content / Video / PDF Published", 1, "student"),
            ("quiz_published", "New Quiz Assessment Available", 1, "student"),
            ("course_status_changed", "Course Archived, Unpublished, or Deleted", 1, "student"),
            ("course_completed", "Student Completed Course", 1, "teacher,department_admin"),
            ("quiz_submitted", "Student Quiz Attempt Completed", 1, "teacher,department_admin"),
            ("faculty_created", "New Faculty Member Provisioned", 1, "department_admin"),
            ("import_completed", "Bulk Student Import Finished", 1, "department_admin")
        ]
        for ev_k, ev_t, ev_en, ev_roles in default_notification_events:
            cursor.execute("""
                INSERT OR IGNORE INTO notification_settings (event_type, event_title, is_enabled, target_roles)
                VALUES (?, ?, ?, ?)
            """, (ev_k, ev_t, ev_en, ev_roles))

        # 15. System Settings & Custom Branding
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS system_settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );
        """)

        # 16. Support Queries & Chatbot Tickets Table
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS support_queries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticket_id TEXT UNIQUE NOT NULL,             -- e.g. TKT-2026-0001
            user_id TEXT NOT NULL,                      -- student or teacher user_id
            user_role TEXT NOT NULL,                    -- 'student' or 'teacher'
            user_name TEXT NOT NULL,
            user_email TEXT,
            course_id INTEGER,                          -- optional, course context
            course_title TEXT,                          -- optional
            subject TEXT NOT NULL,                      -- query subject/topic
            category TEXT DEFAULT 'General',            -- 'Academic', 'Technical', 'General'
            message TEXT NOT NULL,                      -- original query text
            ai_response TEXT,                           -- instant Mylo AI response
            admin_reply TEXT,                           -- reply from admin or teacher
            replied_by TEXT,                            -- name/id of replier
            replied_at TIMESTAMP,
            status TEXT DEFAULT 'open',                 -- 'open', 'replied', 'resolved'
            visibility TEXT NOT NULL,                   -- 'teachers_and_admin' (for students), 'admin_only' (for teachers)
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_queries_user ON support_queries(user_id);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_queries_status ON support_queries(status);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_queries_visibility ON support_queries(visibility);")

        # 17. Mylo AI Usage Logs & Cost Tracking Table
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS ai_usage_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            user_name TEXT,
            user_role TEXT,
            course_id INTEGER,
            course_title TEXT,
            subject TEXT,
            feature_type TEXT NOT NULL,                 -- 'quiz_explanation', 'quiz_generation', 'chatbot'
            prompt_tokens INTEGER DEFAULT 0,
            completion_tokens INTEGER DEFAULT 0,
            total_tokens INTEGER DEFAULT 0,
            estimated_cost_usd REAL DEFAULT 0.0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_ai_logs_user ON ai_usage_logs(user_id);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_ai_logs_course ON ai_usage_logs(course_id);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_ai_logs_feature ON ai_usage_logs(feature_type);")

        # 18. Verified Certificates Table with Unique ID & QR Verification
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS certificates (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            certificate_id TEXT UNIQUE NOT NULL,               -- e.g. "LBPL-2026-000001"
            student_id INTEGER NOT NULL,                       -- FK to users.id
            student_name TEXT NOT NULL,
            student_uid TEXT NOT NULL,                         -- e.g. "CS2026-002"
            course_id INTEGER NOT NULL,                        -- FK to courses.id
            course_name TEXT NOT NULL,
            course_code TEXT,
            issued_by TEXT NOT NULL DEFAULT 'Leadership Boulevard Pvt Ltd',
            issued_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            status TEXT NOT NULL DEFAULT 'verified',           -- 'verified', 'revoked', 'reissued'
            revoked_at TIMESTAMP,
            revocation_reason TEXT,
            reissued_from_id TEXT,
            reissued_to_id TEXT,
            qr_code_data_uri TEXT,
            verification_url TEXT,
            verification_count INTEGER DEFAULT 0,
            last_verified_at TIMESTAMP,
            completion_date TEXT,
            grade_score REAL DEFAULT 100.0,
            FOREIGN KEY (student_id) REFERENCES users(id),
            FOREIGN KEY (course_id) REFERENCES courses(id)
        );
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_cert_id ON certificates(certificate_id);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_cert_student ON certificates(student_id);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_cert_course ON certificates(course_id);")

        # 18. Departments Table (Bucketing for isolated sub-environments)
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS departments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL,                  -- e.g. "Foreign Language", "Test Prep"
            code TEXT UNIQUE NOT NULL,                  -- e.g. "FOREIGN_LANG", "TEST_PREP"
            description TEXT,
            banner_url TEXT,
            branding_tagline TEXT DEFAULT 'transforming education',
            welcome_message TEXT,
            ans_writing_enabled INTEGER DEFAULT 1,      -- 1 = Answer Writing Enabled, 0 = Disabled
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """)

        # Migration check: ensure ans_writing_enabled column exists in departments
        cursor.execute("PRAGMA table_info(departments)")
        dept_existing_cols = {row["name"] for row in cursor.fetchall()}
        if "ans_writing_enabled" not in dept_existing_cols:
            cursor.execute("ALTER TABLE departments ADD COLUMN ans_writing_enabled INTEGER DEFAULT 1")
            cursor.execute("UPDATE departments SET ans_writing_enabled = 0 WHERE name = 'Foreign Language'")
            cursor.execute("UPDATE departments SET ans_writing_enabled = 1 WHERE name IN ('Test Prep', 'UPSC Coaching')")

        # Seed initial core departments (Foreign Language and Test Prep)
        cursor.execute("""
        INSERT OR IGNORE INTO departments (name, code, description, banner_url, branding_tagline, welcome_message, ans_writing_enabled)
        VALUES 
        ('Foreign Language', 'FOREIGN_LANG', 'World Languages, Linguistic Proficiency & Conversational Fluency', 'https://images.unsplash.com/photo-1546410531-bb4caa6b424d?w=1200&auto=format&fit=crop&q=80', 'transforming education', 'Welcome to the Foreign Language Learning Portal. Master world languages with curated modules, interactive videos, and speaking practice.', 0),
        ('Test Prep', 'TEST_PREP', 'Standardized Exam Preparation, Mock Drills & Competitive Testing', 'https://images.unsplash.com/photo-1434030216411-0b793f4b4173?w=1200&auto=format&fit=crop&q=80', 'transforming education', 'Welcome to the Test Prep Portal. Accelerate your performance with targeted practice tests, analytics, and instructor-led strategies.', 1)
        """)

        # 19. Live Classes & Sessions Table
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS live_classes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            course_id INTEGER NOT NULL,
            teacher_id INTEGER NOT NULL,
            title TEXT NOT NULL,
            description TEXT,
            platform TEXT NOT NULL DEFAULT 'zoom',      -- 'zoom', 'google_meet', 'youtube_live', 'teams'
            meeting_url TEXT NOT NULL,
            meeting_id TEXT,
            meeting_passcode TEXT,
            scheduled_at TIMESTAMP NOT NULL,
            duration_minutes INTEGER DEFAULT 60,
            status TEXT DEFAULT 'scheduled',            -- 'scheduled', 'live', 'completed', 'cancelled'
            recording_url TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (course_id) REFERENCES courses(id) ON DELETE CASCADE,
            FOREIGN KEY (teacher_id) REFERENCES users(id) ON DELETE CASCADE
        );
        """)

        # 20. Live Class Interactive Q&A / Doubt Table
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS live_class_questions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            live_class_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            user_name TEXT NOT NULL,
            question_text TEXT NOT NULL,
            is_answered INTEGER DEFAULT 0,
            answer_text TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (live_class_id) REFERENCES live_classes(id) ON DELETE CASCADE,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        );
        """)

        # 21. UPSC Mains PDF Answer Sheet Submissions Table
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS answer_sheet_submissions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            course_id INTEGER NOT NULL,
            module_id INTEGER,
            lesson_id INTEGER,
            file_path TEXT NOT NULL,
            original_filename TEXT NOT NULL,
            remarks TEXT,
            status TEXT DEFAULT 'pending',
            marks_awarded REAL,
            max_marks REAL DEFAULT 20.0,
            feedback TEXT,
            evaluated_by INTEGER,
            evaluated_at TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
            FOREIGN KEY (course_id) REFERENCES courses(id) ON DELETE CASCADE,
            FOREIGN KEY (module_id) REFERENCES modules(id) ON DELETE SET NULL,
            FOREIGN KEY (lesson_id) REFERENCES lessons(id) ON DELETE SET NULL,
            FOREIGN KEY (evaluated_by) REFERENCES users(id) ON DELETE SET NULL
        );
        """)

        # 22. One-on-One Mentoring Sessions Table (Student-Initiated & Teacher-Initiated)
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS mentoring_sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            initiator_role TEXT NOT NULL,       -- 'student' or 'teacher'
            student_id INTEGER NOT NULL,
            teacher_id INTEGER,                 -- Assigned by admin if student-initiated, or teacher who initiated
            course_id INTEGER,
            topic TEXT NOT NULL,
            description TEXT,
            preferred_date TEXT,
            preferred_time TEXT,
            scheduled_date TEXT,
            scheduled_time TEXT,
            meeting_link TEXT,
            status TEXT DEFAULT 'pending_admin_assignment', -- 'pending_admin_assignment', 'pending_student_schedule', 'scheduled', 'completed', 'cancelled'
            student_notes TEXT,
            teacher_notes TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (student_id) REFERENCES users(id) ON DELETE CASCADE,
            FOREIGN KEY (teacher_id) REFERENCES users(id) ON DELETE SET NULL,
            FOREIGN KEY (course_id) REFERENCES courses(id) ON DELETE SET NULL
        );
        """)

        # Default system branding and settings
        default_settings = {
            "platform_name": "LEAD Group",
            "platform_tagline": "transforming education",
            "institution_name": "Leadership Boulevard Pvt Ltd",
            "department_name": "Foreign Language",
            "department_tagline": "transforming education",
            "brand_color": "#1e3a8a",
            "secondary_brand_color": "#0284c7",
            "welcome_message": "Welcome to the Learning Portal. Master your curriculum with curated modules, interactive videos, and live doubts.",
            "login_help_text": "Enter your User ID / Serial Number and password to access your portal.",
            "login_user_id_placeholder": "e.g. Serial Number or ID",
            "login_button_text": "Sign In",
            "login_footer_text": "Leadership Boulevard Pvt Ltd • transforming education",
            "logo_icon": "fa-graduation-cap",
            "logo_image_url": "/static/images/lead_group_logo.png",
            "department_banner_url": "",
            "contact_email": "info@fl4schools.com",
            "contact_phone": "+91 9540594033",
            "contact_office": "Mumbai",
            "branding_text": "Leadership Boulevard Pvt Ltd • transforming education",
            "font_family": "outfit",
            "powerbi_api_key": "pbi_live_9a7f82b3d1e4c5a6b7c8d9e0f1a2b3c4",
            "powerbi_last_sync_at": "",
            "live_inactivity_minutes": "5",
            "accreditation_badge": "Accredited Academic Portal",
            "gemini_api_key": "",
            "gemini_model": "gemini-2.5-flash",
            "gemini_auto_reply": "1",
            "gemini_enabled": "1",
            "allow_teacher_ai_quiz": "1",
            "teacher_can_generate_quiz": "1",
            "mylo_ai_students_enabled": "1",
            "mylo_ai_chatbot_enabled": "1",
            "mylo_ai_enabled_globally": "1",
            "mylo_ai_quiz_explanations_enabled": "1",
            "mylo_ai_disabled_courses": "",
            "mylo_ai_disabled_subjects": "",
            "mylo_ai_disabled_students": "",
            "mylo_ai_quiz_explanations_disabled_courses": ""
        }
        for k, v in default_settings.items():
            cursor.execute("INSERT OR IGNORE INTO system_settings (key, value) VALUES (?, ?)", (k, v))

        # Always cleanse any legacy titles, learning made easy, or engineering references
        cursor.execute("UPDATE system_settings SET value = 'LEAD Group' WHERE key = 'platform_name'")
        cursor.execute("UPDATE system_settings SET value = '/static/images/lead_group_logo.png' WHERE key = 'logo_image_url'")
        cursor.execute("UPDATE system_settings SET value = 'transforming education' WHERE key IN ('platform_tagline', 'department_tagline')")
        cursor.execute("UPDATE system_settings SET value = 'Foreign Language' WHERE key = 'department_name' AND (value = 'transforming education' OR value LIKE '%learning made easy%' OR value LIKE '%Computer Science%')")
        cursor.execute("UPDATE system_settings SET value = 'Leadership Boulevard Pvt Ltd' WHERE value LIKE '%Indian Institute%'")
        cursor.execute("UPDATE system_settings SET value = 'info@fl4schools.com' WHERE value LIKE '%cse@institution.edu%'")
        cursor.execute("UPDATE system_settings SET value = 'Mumbai' WHERE value LIKE '%Computing Annex%'")

        # Ensure user department matches current department_name where still default Computer Science or NULL
        cursor.execute("SELECT value FROM system_settings WHERE key = 'department_name'")
        dept_row = cursor.fetchone()
        if dept_row and dept_row[0]:
            cursor.execute("UPDATE users SET department = ? WHERE department = 'Computer Science' OR department IS NULL OR department LIKE '%Engineering%'", (dept_row[0],))

def get_system_settings() -> dict:
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT key, value FROM system_settings")
        rows = cursor.fetchall()
        return {r["key"]: r["value"] for r in rows}

def update_system_settings(settings: dict, conn=None):
    if conn:
        cursor = conn.cursor()
        for k, v in settings.items():
            cursor.execute("""
                INSERT INTO system_settings (key, value) VALUES (?, ?)
                ON CONFLICT(key) DO UPDATE SET value = ?
            """, (k, str(v), str(v)))
    else:
        with get_db() as c:
            cursor = c.cursor()
            for k, v in settings.items():
                cursor.execute("""
                    INSERT INTO system_settings (key, value) VALUES (?, ?)
                    ON CONFLICT(key) DO UPDATE SET value = ?
                """, (k, str(v), str(v)))

def get_dashboard_permissions() -> list:
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM dashboard_permissions ORDER BY widget_key ASC")
        return [dict(r) for r in cursor.fetchall()]

def update_dashboard_permissions(permissions: dict):
    with get_db() as conn:
        cursor = conn.cursor()
        for key, conf in permissions.items():
            cursor.execute("""
                UPDATE dashboard_permissions 
                SET allowed_roles = ?, is_enabled = ?
                WHERE widget_key = ?
            """, (conf.get("allowed_roles", ""), conf.get("is_enabled", 1), key))

def log_audit(user_id: int, action: str, entity_type: str, entity_id: str, details: str, conn=None):
    try:
        if conn is not None:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO audit_logs (user_id, action, entity_type, entity_id, details)
                VALUES (?, ?, ?, ?, ?)
            """, (user_id, action, entity_type, str(entity_id), details))
        else:
            with get_db() as c_conn:
                cursor = c_conn.cursor()
                cursor.execute("""
                    INSERT INTO audit_logs (user_id, action, entity_type, entity_id, details)
                    VALUES (?, ?, ?, ?, ?)
                """, (user_id, action, entity_type, str(entity_id), details))
    except Exception as e:
        print(f"Error logging audit action: {e}")

# ==========================================
# NOTIFICATION ENGINE HELPERS
# ==========================================

def create_notification(user_id: int, title: str, message: str, link_url: str = None, category: str = "general", event_type: str = None, conn=None):
    try:
        if conn is not None:
            cursor = conn.cursor()
            if event_type:
                cursor.execute("SELECT is_enabled FROM notification_settings WHERE event_type = ?", (event_type,))
                row = cursor.fetchone()
                if row and row["is_enabled"] == 0:
                    return None  # Event notification suppressed by admin policy
            cursor.execute("""
                INSERT INTO notifications (user_id, title, message, link_url, category)
                VALUES (?, ?, ?, ?, ?)
            """, (user_id, title, message, link_url, category))
        else:
            with get_db() as c_conn:
                cursor = c_conn.cursor()
                if event_type:
                    cursor.execute("SELECT is_enabled FROM notification_settings WHERE event_type = ?", (event_type,))
                    row = cursor.fetchone()
                    if row and row["is_enabled"] == 0:
                        return None  # Event notification suppressed by admin policy
                cursor.execute("""
                    INSERT INTO notifications (user_id, title, message, link_url, category)
                    VALUES (?, ?, ?, ?, ?)
                """, (user_id, title, message, link_url, category))
    except Exception as e:
        print(f"Error creating notification: {e}")

def notify_users(user_ids: list, title: str, message: str, link_url: str = None, category: str = "general", event_type: str = None, conn=None, link: str = None):
    if link is not None and link_url is None:
        link_url = link
    if not user_ids:
        return
    try:
        if conn is not None:
            cursor = conn.cursor()
            if event_type:
                cursor.execute("SELECT is_enabled FROM notification_settings WHERE event_type = ?", (event_type,))
                row = cursor.fetchone()
                if row and row["is_enabled"] == 0:
                    return  # Suppressed by admin policy
            for uid in user_ids:
                cursor.execute("""
                    INSERT INTO notifications (user_id, title, message, link_url, category)
                    VALUES (?, ?, ?, ?, ?)
                """, (uid, title, message, link_url, category))
        else:
            with get_db() as c_conn:
                cursor = c_conn.cursor()
                if event_type:
                    cursor.execute("SELECT is_enabled FROM notification_settings WHERE event_type = ?", (event_type,))
                    row = cursor.fetchone()
                    if row and row["is_enabled"] == 0:
                        return  # Suppressed by admin policy
                for uid in user_ids:
                    cursor.execute("""
                        INSERT INTO notifications (user_id, title, message, link_url, category)
                        VALUES (?, ?, ?, ?, ?)
                    """, (uid, title, message, link_url, category))
    except Exception as e:
        print(f"Error notifying multiple users: {e}")

def get_user_notifications(user_id: int, limit: int = 30) -> tuple:
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM notifications WHERE user_id = ? AND is_read = 0", (user_id,))
        unread_count = cursor.fetchone()[0]
        cursor.execute("""
            SELECT * FROM notifications 
            WHERE user_id = ? 
            ORDER BY created_at DESC 
            LIMIT ?
        """, (user_id, limit))
        notifications = [dict(r) for r in cursor.fetchall()]
        return unread_count, notifications

def mark_notification_read(notification_id: int, user_id: int):
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE notifications SET is_read = 1 WHERE id = ? AND user_id = ?", (notification_id, user_id))

def mark_all_notifications_read(user_id: int):
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE notifications SET is_read = 1 WHERE user_id = ?", (user_id,))

def get_notification_settings() -> list:
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM notification_settings ORDER BY event_type ASC")
        return [dict(r) for r in cursor.fetchall()]

def update_notification_settings(settings: dict):
    with get_db() as conn:
        cursor = conn.cursor()
        for k, v in settings.items():
            is_en = 1 if v.get("is_enabled") else 0
            cursor.execute("UPDATE notification_settings SET is_enabled = ? WHERE event_type = ?", (is_en, k))


# ==========================================
# MYLO AI USAGE LOGGING & GOVERNANCE HELPERS
# ==========================================

def is_ai_feature_enabled(feature: str, student_user_id: str = None, course_id: int = None, subject: str = None) -> tuple:
    """
    Checks if a student / course / subject has access to Mylo AI features.
    Returns (allowed: bool, reason: str).
    """
    settings = get_system_settings()

    # 1. Global Student Mylo AI toggle
    if settings.get("mylo_ai_enabled_globally", "1") == "0":
        return False, "Mylo AI access is currently disabled for students by the administrator."

    # 2. Individual student blacklist
    disabled_students = [s.strip().lower() for s in settings.get("mylo_ai_disabled_students", "").split(",") if s.strip()]
    if student_user_id and student_user_id.strip().lower() in disabled_students:
        return False, f"Mylo AI access is disabled for student account '{student_user_id}' by administrative policy."

    # 3. Subject-wise blacklist
    disabled_subjects = [s.strip().lower() for s in settings.get("mylo_ai_disabled_subjects", "").split(",") if s.strip()]
    if subject and subject.strip().lower() in disabled_subjects:
        return False, f"Mylo AI is disabled for subject '{subject}' by administrative policy."

    # 4. Course-wise blacklist
    disabled_courses = [c.strip() for c in settings.get("mylo_ai_disabled_courses", "").split(",") if c.strip()]
    if course_id and str(course_id) in disabled_courses:
        return False, "Mylo AI is disabled for this course by administrative policy."

    # 5. Feature-specific master controls (Students, Teachers, Chatbot)
    if feature == "quiz_explanation":
        if settings.get("mylo_ai_students_enabled", settings.get("mylo_ai_quiz_explanations_enabled", "1")) == "0":
            return False, "Mylo AI quiz explanations are currently disabled by the administrator."

        disabled_exp_courses = [c.strip() for c in settings.get("mylo_ai_quiz_explanations_disabled_courses", "").split(",") if c.strip()]
        if course_id and str(course_id) in disabled_exp_courses:
            return False, "Mylo AI quiz explanations are disabled for this course by administrative policy."
    elif feature == "quiz_generation":
        if settings.get("teacher_can_generate_quiz", settings.get("allow_teacher_ai_quiz", "1")) == "0":
            return False, "Mylo AI quiz generation for teachers is currently disabled by the administrator."
    elif feature == "chatbot":
        if settings.get("mylo_ai_chatbot_enabled", settings.get("gemini_auto_reply", "1")) == "0":
            return False, "Mylo AI chatbot responses are currently disabled by the administrator."

    return True, "Allowed"

def log_ai_usage(user_id: int, user_name: str, user_role: str, feature_type: str, course_id: int = None, course_title: str = None, subject: str = None, prompt_tokens: int = 150, completion_tokens: int = 250):
    """Logs Mylo AI token consumption and estimated API expenditure."""
    try:
        total_tokens = prompt_tokens + completion_tokens
        # Gemini / Mylo 2.5 Flash pricing: approx $0.075 per 1M input tokens, $0.30 per 1M output tokens
        cost_usd = round((prompt_tokens * 0.000000075) + (completion_tokens * 0.0000003), 6)
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO ai_usage_logs (user_id, user_name, user_role, course_id, course_title, subject, feature_type, prompt_tokens, completion_tokens, total_tokens, estimated_cost_usd)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (user_id, user_name, user_role, course_id, course_title, subject, feature_type, prompt_tokens, completion_tokens, total_tokens, cost_usd))
    except Exception as e:
        print(f"Error logging Mylo AI usage: {e}")

def get_ai_usage_metrics() -> dict:
    """Computes comprehensive Mylo AI usage, breakdowns, and cost analytics."""
    with get_db() as conn:
        cursor = conn.cursor()
        
        # Overall totals
        cursor.execute("""
            SELECT COUNT(*) as total_requests,
                   COALESCE(SUM(total_tokens), 0) as total_tokens,
                   COALESCE(SUM(estimated_cost_usd), 0.0) as total_cost_usd
            FROM ai_usage_logs
        """)
        totals = dict(cursor.fetchone())
        totals["total_cost_inr"] = round(totals["total_cost_usd"] * 84.5, 2)
        totals["total_cost_usd"] = round(totals["total_cost_usd"], 4)

        # Feature breakdown
        cursor.execute("""
            SELECT feature_type, COUNT(*) as count, COALESCE(SUM(total_tokens), 0) as tokens
            FROM ai_usage_logs
            GROUP BY feature_type
        """)
        feature_breakdown = {r["feature_type"]: dict(r) for r in cursor.fetchall()}

        # Course-wise usage
        cursor.execute("""
            SELECT course_id, COALESCE(course_title, 'General / Unassigned') as title,
                   COUNT(*) as requests, COALESCE(SUM(total_tokens), 0) as tokens,
                   COALESCE(SUM(estimated_cost_usd), 0.0) as cost_usd
            FROM ai_usage_logs
            GROUP BY course_id, course_title
            ORDER BY requests DESC LIMIT 10
        """)
        course_usage = [dict(r) for r in cursor.fetchall()]

        # Subject-wise usage
        cursor.execute("""
            SELECT COALESCE(subject, 'General') as subject,
                   COUNT(*) as requests, COALESCE(SUM(total_tokens), 0) as tokens
            FROM ai_usage_logs
            GROUP BY subject
            ORDER BY requests DESC LIMIT 10
        """)
        subject_usage = [dict(r) for r in cursor.fetchall()]

        # Student-wise usage leaderboard
        cursor.execute("""
            SELECT user_id, user_name, user_role,
                   COUNT(*) as requests, COALESCE(SUM(total_tokens), 0) as tokens
            FROM ai_usage_logs
            WHERE user_role = 'student'
            GROUP BY user_id, user_name, user_role
            ORDER BY requests DESC LIMIT 10
        """)
        student_usage = [dict(r) for r in cursor.fetchall()]

        # Recent 25 requests log
        cursor.execute("""
            SELECT * FROM ai_usage_logs ORDER BY created_at DESC LIMIT 25
        """)
        recent_logs = [dict(r) for r in cursor.fetchall()]

        return {
            "totals": totals,
            "total_requests": totals["total_requests"],
            "total_tokens": totals["total_tokens"],
            "prompt_tokens": totals["total_tokens"] // 2,
            "completion_tokens": totals["total_tokens"] // 2,
            "estimated_cost_usd": totals["total_cost_usd"],
            "estimated_cost_inr": totals["total_cost_inr"],
            "quiz_explanation_requests": feature_breakdown.get("quiz_explanation", {}).get("count", 0),
            "chatbot_requests": feature_breakdown.get("chatbot", {}).get("count", 0),
            "feature_breakdown": feature_breakdown,
            "course_breakdown": course_usage,
            "course_usage": course_usage,
            "subject_usage": subject_usage,
            "student_breakdown": student_usage,
            "student_usage": student_usage,
            "recent_logs": recent_logs
        }


# ===================================================================
# UNIQUE CERTIFICATE ID & QR-BASED VERIFICATION MANAGEMENT
# ===================================================================

_LAST_CERT_SEQ = 0

def generate_unique_certificate_id(conn=None) -> str:
    """
    Generates a structured, guaranteed unique certificate ID.
    Format: LBPL-YYYY-000001 (e.g. LBPL-2026-000001)
    """
    global _LAST_CERT_SEQ
    from datetime import datetime
    year = datetime.now().year
    prefix = f"LBPL-{year}-"
    should_close = False
    if conn is None:
        conn = sqlite3.connect(DB_PATH)
        should_close = True
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT certificate_id FROM certificates WHERE certificate_id LIKE ? ORDER BY id DESC LIMIT 1", (f"{prefix}%",))
        row = cursor.fetchone()
        db_seq = 0
        if row and row[0]:
            try:
                db_seq = int(row[0].split("-")[-1])
            except Exception:
                cursor.execute("SELECT COUNT(*) FROM certificates")
                db_seq = cursor.fetchone()[0] or 0
        else:
            cursor.execute("SELECT COUNT(*) FROM certificates")
            db_seq = cursor.fetchone()[0] or 0

        seq = max(db_seq + 1, _LAST_CERT_SEQ + 1)
        _LAST_CERT_SEQ = seq
        return f"{prefix}{seq:06d}"
    finally:
        if should_close:
            conn.close()

def generate_qr_code_base64(data: str) -> str:
    """
    Generates a high-contrast, scannable QR code embedded as a Base64 PNG data URI.
    """
    import io
    import base64
    import qrcode

    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=8,
        border=2,
    )
    qr.add_data(data)
    qr.make(fit=True)
    img = qr.make_image(fill_color="#0f172a", back_color="#ffffff")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode("utf-8")

def issue_certificate(student_id: int, course_id: int, admin_user_id: int = None, completion_date: str = None, grade_score: float = None, conn=None) -> dict:
    """
    Automatically generates and permanently registers an authentic certificate for a student in a course.
    Embeds a unique certificate ID (LBPL-YYYY-000001) and scannable verification QR code.
    """
    from datetime import datetime
    should_close = False
    if conn is None:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        should_close = True
    try:
        cursor = conn.cursor()
        # Fetch student details (accepts either user integer ID or string user_id like 'CS2026-002')
        if isinstance(student_id, str) and not student_id.isdigit():
            cursor.execute("SELECT id, user_id, full_name FROM users WHERE user_id = ?", (student_id,))
        else:
            cursor.execute("SELECT id, user_id, full_name FROM users WHERE id = ?", (int(student_id),))
        student = cursor.fetchone()
        if not student:
            raise ValueError(f"Student '{student_id}' not found in database")

        # Fetch course details
        cursor.execute("SELECT id, title, code FROM courses WHERE id = ?", (course_id,))
        course = cursor.fetchone()
        if not course:
            raise ValueError(f"Course #{course_id} not found in database")

        # Check if an active verified certificate already exists for this student & course
        cursor.execute("SELECT * FROM certificates WHERE student_id = ? AND course_id = ? AND status = 'verified'", (student["id"], course["id"]))
        existing = cursor.fetchone()
        if existing:
            return dict(existing)

        cert_id = generate_unique_certificate_id(conn=conn)
        verification_url = f"/verify/{cert_id}"
        qr_code_data_uri = generate_qr_code_base64(verification_url)
        comp_date = completion_date or datetime.now().strftime("%B %d, %Y")

        cursor.execute("""
            INSERT INTO certificates (
                certificate_id, student_id, student_name, student_uid,
                course_id, course_name, course_code, issued_by,
                status, qr_code_data_uri, verification_url, completion_date, grade_score
            ) VALUES (?, ?, ?, ?, ?, ?, ?, 'Leadership Boulevard Pvt Ltd', 'verified', ?, ?, ?, ?)
        """, (
            cert_id, student["id"], student["full_name"], student["user_id"],
            course["id"], course["title"], course["code"],
            qr_code_data_uri, verification_url, comp_date, grade_score or 100.0
        ))
        new_row_id = cursor.lastrowid
        conn.commit()

        if admin_user_id:
            log_audit(admin_user_id, "CERTIFICATE_ISSUE", "certificates", str(new_row_id), f"Issued certificate {cert_id} for student {student['full_name']} in course {course['title']}", conn=conn)

        cursor.execute("SELECT * FROM certificates WHERE id = ?", (new_row_id,))
        cert_dict = dict(cursor.fetchone())
        cert_dict["course_title"] = cert_dict.get("course_name", "")
        return cert_dict
    finally:
        if should_close:
            conn.close()

def get_certificate_by_id(certificate_id: str, conn=None) -> dict:
    """Retrieves a certificate record by its unique Certificate ID."""
    should_close = False
    if conn is None:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        should_close = True
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM certificates WHERE certificate_id = ? COLLATE NOCASE", (certificate_id.strip(),))
        row = cursor.fetchone()
        return dict(row) if row else None
    finally:
        if should_close:
            conn.close()

def verify_certificate(certificate_id: str, increment_count: bool = True) -> dict:
    """
    Public verification method: checks validity, increments scan counter, and returns certificate details.
    """
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM certificates WHERE certificate_id = ? COLLATE NOCASE", (certificate_id.strip(),))
        row = cursor.fetchone()
        if not row:
            return None
        cert = dict(row)
        if increment_count and cert["status"] == "verified":
            cursor.execute("UPDATE certificates SET verification_count = verification_count + 1, last_verified_at = CURRENT_TIMESTAMP WHERE id = ?", (cert["id"],))
            cert["verification_count"] += 1
        return cert

def revoke_certificate(certificate_id: str, reason: str = None, admin_user_id: int = None) -> bool:
    """
    Revokes an issued certificate. Revocation immediately takes effect across public verification.
    """
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM certificates WHERE certificate_id = ? COLLATE NOCASE", (certificate_id.strip(),))
        row = cursor.fetchone()
        if not row:
            return False
        cert = dict(row)
        rev_reason = reason.strip() if reason and reason.strip() else "Revoked by Administrator"
        cursor.execute("UPDATE certificates SET status = 'revoked', revoked_at = CURRENT_TIMESTAMP, revocation_reason = ? WHERE id = ?", (rev_reason, cert["id"]))
        if admin_user_id:
            log_audit(admin_user_id, "CERTIFICATE_REVOKE", "certificates", str(cert["id"]), f"Revoked certificate {certificate_id}. Reason: {rev_reason}", conn=conn)
        return True

def reissue_certificate(old_certificate_id: str, admin_user_id: int = None) -> dict:
    """
    Reissues a certificate with a new unique certificate ID and QR code,
    while archiving the previous record to maintain a permanent audit trail.
    """
    from datetime import datetime
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM certificates WHERE certificate_id = ? COLLATE NOCASE", (old_certificate_id.strip(),))
        row = cursor.fetchone()
        if not row:
            raise ValueError(f"Certificate {old_certificate_id} not found")
        old_cert = dict(row)

        new_cert_id = generate_unique_certificate_id(conn=conn)
        verification_url = f"/verify/{new_cert_id}"
        qr_code_data_uri = generate_qr_code_base64(verification_url)
        comp_date = old_cert["completion_date"] or datetime.now().strftime("%B %d, %Y")

        # Mark old certificate as revoked / reissued
        cursor.execute("""
            UPDATE certificates 
            SET status = 'revoked', revoked_at = CURRENT_TIMESTAMP, 
                revocation_reason = 'Reissued with new Certificate ID', reissued_to_id = ? 
            WHERE id = ?
        """, (new_cert_id, old_cert["id"]))

        # Create new certificate
        cursor.execute("""
            INSERT INTO certificates (
                certificate_id, student_id, student_name, student_uid,
                course_id, course_name, course_code, issued_by,
                status, reissued_from_id, qr_code_data_uri, verification_url, completion_date, grade_score
            ) VALUES (?, ?, ?, ?, ?, ?, ?, 'Leadership Boulevard Pvt Ltd', 'verified', ?, ?, ?, ?, ?)
        """, (
            new_cert_id, old_cert["student_id"], old_cert["student_name"], old_cert["student_uid"],
            old_cert["course_id"], old_cert["course_name"], old_cert["course_code"],
            old_cert["certificate_id"], qr_code_data_uri, verification_url, comp_date, old_cert["grade_score"]
        ))
        new_row_id = cursor.lastrowid

        if admin_user_id:
            log_audit(admin_user_id, "CERTIFICATE_REISSUE", "certificates", str(new_row_id), f"Reissued certificate {old_certificate_id} -> {new_cert_id} for {old_cert['student_name']}", conn=conn)

        cursor.execute("SELECT * FROM certificates WHERE id = ?", (new_row_id,))
        cert_dict = dict(cursor.fetchone())
        cert_dict["course_title"] = cert_dict.get("course_name", "")
        return cert_dict

def list_certificates(status: str = None, search: str = None) -> list:
    """Returns a list of all certificate records with optional status and search filtering."""
    with get_db() as conn:
        cursor = conn.cursor()
        query = "SELECT * FROM certificates WHERE 1=1"
        params = []
        if status and status != "all":
            query += " AND status = ?"
            params.append(status)
        if search and search.strip():
            s = f"%{search.strip()}%"
            query += " AND (certificate_id LIKE ? OR student_name LIKE ? OR course_name LIKE ? OR student_uid LIKE ?)"
            params.extend([s, s, s, s])
        query += " ORDER BY id DESC"
        cursor.execute(query, tuple(params))
        return [dict(r) for r in cursor.fetchall()]

def get_student_certificates(student_id: int) -> list:
    """Retrieves all valid or earned certificates belonging to a specific student."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT * FROM certificates 
            WHERE student_id = ? 
            ORDER BY id DESC
        """, (student_id,))
        return [dict(r) for r in cursor.fetchall()]

# ===================================================================
# AUTOMATED CERTIFICATE ISSUANCE ENGINE
# ===================================================================

def auto_issue_certificates_for_course(course_id: int = None, admin_user_id: int = None) -> list:
    """
    Automates certificate generation for all students who have completed 100% of a course.
    If course_id is None, checks across all active courses.
    Returns list of newly issued certificates.
    """
    newly_issued = []
    with get_db() as conn:
        cursor = conn.cursor()
        
        # Query target courses
        if course_id:
            cursor.execute("SELECT id, title, code FROM courses WHERE id = ? AND status != 'deleted'", (course_id,))
        else:
            cursor.execute("SELECT id, title, code FROM courses WHERE status != 'deleted'")
        courses = [dict(c) for c in cursor.fetchall()]

        for c in courses:
            cid = c["id"]
            # Count total lessons in course
            cursor.execute("""
                SELECT COUNT(*) FROM lessons l 
                JOIN modules m ON l.module_id = m.id 
                WHERE m.course_id = ?
            """, (cid,))
            total_lessons = cursor.fetchone()[0] or 0

            if total_lessons == 0:
                continue

            # Find all enrolled students who finished all lessons
            cursor.execute("""
                SELECT u.id as student_id, u.user_id, u.full_name,
                       (SELECT COUNT(*) FROM lesson_progress lp 
                        JOIN lessons l ON lp.lesson_id = l.id 
                        JOIN modules m ON l.module_id = m.id 
                        WHERE m.course_id = ? AND lp.user_id = u.id AND lp.is_completed = 1) as completed_count
                FROM enrollments e
                JOIN users u ON e.user_id = u.id
                WHERE e.course_id = ? AND u.role = 'student'
            """, (cid, cid))
            enrolled = cursor.fetchall()

            for student in enrolled:
                comp = student["completed_count"]
                if comp >= total_lessons:
                    # Check if student already has a verified certificate for this course
                    cursor.execute("""
                        SELECT id FROM certificates 
                        WHERE student_id = ? AND course_id = ? AND status = 'verified'
                    """, (student["student_id"], cid))
                    if not cursor.fetchone():
                        cert = issue_certificate(
                            student_id=student["student_id"],
                            course_id=cid,
                            admin_user_id=admin_user_id,
                            grade_score=100.0,
                            conn=conn
                        )
                        newly_issued.append(cert)

    return newly_issued

# ===================================================================
# MULTI-DEPARTMENT BUCKETS MANAGEMENT
# ===================================================================

def get_all_departments(conn=None) -> list:
    """Returns all department records with teacher, student, and course counts."""
    should_close = False
    if conn is None:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        should_close = True
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT d.*,
                   (SELECT COUNT(*) FROM users WHERE role = 'teacher' AND department = d.name) as teachers_count,
                   (SELECT COUNT(*) FROM users WHERE role = 'student' AND department = d.name) as students_count,
                   (SELECT COUNT(*) FROM courses WHERE department = d.name AND status != 'deleted') as courses_count
            FROM departments d
            ORDER BY d.id ASC
        """)
        return [dict(r) for r in cursor.fetchall()]
    finally:
        if should_close:
            conn.close()

def get_department_by_name(name: str, conn=None) -> dict:
    """Retrieves department branding and banner by name."""
    should_close = False
    if conn is None:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        should_close = True
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM departments WHERE name = ? COLLATE NOCASE", (name.strip(),))
        row = cursor.fetchone()
        if row:
            return dict(row)
        # Default fallback
        return {
            "name": name,
            "code": name.upper().replace(" ", "_"),
            "description": f"{name} Academic Department",
            "banner_url": "https://images.unsplash.com/photo-1546410531-bb4caa6b424d?w=1200&auto=format&fit=crop&q=80",
            "branding_tagline": "transforming education",
            "welcome_message": f"Welcome to the {name} Portal.",
            "ans_writing_enabled": 0 if name == "Foreign Language" else 1
        }
    finally:
        if should_close:
            conn.close()

def create_department(name: str, code: str = None, description: str = "", banner_url: str = "", tagline: str = "transforming education", welcome_message: str = "", ans_writing_enabled: int = 1) -> dict:
    """Creates a new isolated department bucket or updates existing."""
    clean_name = name.strip()
    clean_code = code.strip().upper().replace(" ", "_") if code and code.strip() else clean_name.upper().replace(" ", "_")[:12]
    clean_banner = banner_url.strip() if banner_url and banner_url.strip() else "https://images.unsplash.com/photo-1434030216411-0b793f4b4173?w=1200&auto=format&fit=crop&q=80"
    clean_tagline = tagline.strip() if tagline and tagline.strip() else "transforming education"
    clean_welcome = welcome_message.strip() if welcome_message and welcome_message.strip() else f"Welcome to the {clean_name} Learning Portal."

    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM departments WHERE name = ? OR code = ?", (clean_name, clean_code))
        existing = cursor.fetchone()
        if existing:
            cursor.execute("""
                UPDATE departments 
                SET description = ?, banner_url = ?, branding_tagline = ?, welcome_message = ?, ans_writing_enabled = ?
                WHERE id = ?
            """, (description.strip() or existing["description"], clean_banner or existing["banner_url"], clean_tagline, clean_welcome, ans_writing_enabled, existing["id"]))
            cursor.execute("SELECT * FROM departments WHERE id = ?", (existing["id"],))
            return dict(cursor.fetchone())

        cursor.execute("""
            INSERT INTO departments (name, code, description, banner_url, branding_tagline, welcome_message, ans_writing_enabled)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (clean_name, clean_code, description.strip(), clean_banner, clean_tagline, clean_welcome, ans_writing_enabled))
        dept_id = cursor.lastrowid
        cursor.execute("SELECT * FROM departments WHERE id = ?", (dept_id,))
        return dict(cursor.fetchone())

def toggle_department_ans_writing(department_id: int, admin_user_id: int = None) -> dict:
    """Toggles the Answer Writing feature (Mains PDF answer sheets & evaluation) on/off for a department."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id, name, ans_writing_enabled FROM departments WHERE id = ?", (department_id,))
        dept = cursor.fetchone()
        if not dept:
            return None
        current_state = dept["ans_writing_enabled"] if dept["ans_writing_enabled"] is not None else 1
        new_state = 0 if current_state == 1 else 1
        cursor.execute("UPDATE departments SET ans_writing_enabled = ? WHERE id = ?", (new_state, department_id))
        if admin_user_id:
            status_label = "ENABLED" if new_state == 1 else "DISABLED"
            log_audit(admin_user_id, "TOGGLE_ANS_WRITING", "departments", str(department_id), f"Toggled Answer Writing feature for '{dept['name']}' to {status_label}", conn=conn)
        cursor.execute("SELECT * FROM departments WHERE id = ?", (department_id,))
        return dict(cursor.fetchone())

def is_ans_writing_enabled_for_course(course_id: int) -> bool:
    """Checks whether Answer Writing is enabled for the department of the given course."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT d.ans_writing_enabled
            FROM courses c
            JOIN departments d ON LOWER(c.department) = LOWER(d.name)
            WHERE c.id = ?
        """, (course_id,))
        row = cursor.fetchone()
        if row is not None and row[0] is not None:
            return bool(row[0])
        cursor.execute("SELECT department FROM courses WHERE id = ?", (course_id,))
        c_row = cursor.fetchone()
        if c_row and c_row["department"]:
            cursor.execute("SELECT ans_writing_enabled FROM departments WHERE name = ? COLLATE NOCASE", (c_row["department"].strip(),))
            d_row = cursor.fetchone()
            if d_row and d_row[0] is not None:
                return bool(d_row[0])
        return True

def is_ans_writing_enabled_for_department(dept_name: str) -> bool:
    """Checks whether Answer Writing is enabled for a given department name."""
    if not dept_name:
        return True
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT ans_writing_enabled FROM departments WHERE name = ? COLLATE NOCASE", (dept_name.strip(),))
        row = cursor.fetchone()
        if row is not None and row[0] is not None:
            return bool(row[0])
        return True

def assign_user_to_department(user_id: int, department_name: str, admin_user_id: int = None) -> bool:
    """Moves a student or teacher into a specific department bucket."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET department = ? WHERE id = ?", (department_name.strip(), user_id))
        if admin_user_id:
            log_audit(admin_user_id, "ASSIGN_DEPARTMENT", "users", str(user_id), f"Moved user #{user_id} into department '{department_name}'", conn=conn)
        return True

# ===================================================================
# LIVE CLASSES & DOUBT ENGINE
# ===================================================================

def get_live_classes_for_course(course_id: int) -> list:
    """Retrieves all scheduled, live, or completed classes for a course."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT lc.*, u.full_name as teacher_name, c.title as course_title, c.code as course_code,
                   (SELECT COUNT(*) FROM live_class_questions WHERE live_class_id = lc.id) as question_count
            FROM live_classes lc
            JOIN users u ON lc.teacher_id = u.id
            JOIN courses c ON lc.course_id = c.id
            WHERE lc.course_id = ?
            ORDER BY lc.scheduled_at ASC
        """, (course_id,))
        return [dict(r) for r in cursor.fetchall()]

def get_live_class_by_id(live_class_id: int) -> dict:
    """Retrieves full details of a specific live class session."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT lc.*, u.full_name as teacher_name, c.title as course_title, c.code as course_code
            FROM live_classes lc
            JOIN users u ON lc.teacher_id = u.id
            JOIN courses c ON lc.course_id = c.id
            WHERE lc.id = ?
        """, (live_class_id,))
        row = cursor.fetchone()
        return dict(row) if row else None

def create_live_class(
    course_id: int,
    teacher_id: int,
    title: str,
    meeting_url: str,
    scheduled_at: str,
    platform: str = "zoom",
    meeting_id: str = "",
    meeting_passcode: str = "",
    duration_minutes: int = 60,
    description: str = ""
) -> dict:
    """Creates a new live class entry for a course."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO live_classes (
                course_id, teacher_id, title, description, platform,
                meeting_url, meeting_id, meeting_passcode, scheduled_at, duration_minutes, status
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'scheduled')
        """, (
            course_id, teacher_id, title.strip(), description.strip(), platform.lower().strip(),
            meeting_url.strip(), meeting_id.strip(), meeting_passcode.strip(), scheduled_at.strip(), duration_minutes
        ))
        new_id = cursor.lastrowid
        cursor.execute("SELECT * FROM live_classes WHERE id = ?", (new_id,))
        return dict(cursor.fetchone())

def update_live_class_status(live_class_id: int, status: str) -> bool:
    """Updates live class status (e.g. 'scheduled', 'live', 'completed', 'cancelled')."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE live_classes SET status = ? WHERE id = ?", (status.strip().lower(), live_class_id))
        return True

def delete_live_class(live_class_id: int) -> bool:
    """Deletes a live class and its doubts."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM live_classes WHERE id = ?", (live_class_id,))
        return True

def add_live_class_question(live_class_id: int, user_id: int, user_name: str, question_text: str) -> dict:
    """Submits a real-time question or doubt in a live class session."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO live_class_questions (live_class_id, user_id, user_name, question_text)
            VALUES (?, ?, ?, ?)
        """, (live_class_id, user_id, user_name.strip(), question_text.strip()))
        qid = cursor.lastrowid
        cursor.execute("SELECT * FROM live_class_questions WHERE id = ?", (qid,))
        return dict(cursor.fetchone())

def get_live_class_questions(live_class_id: int) -> list:
    """Retrieves all student questions/doubts submitted in a live class."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT * FROM live_class_questions
            WHERE live_class_id = ?
            ORDER BY id ASC
        """, (live_class_id,))
        return [dict(r) for r in cursor.fetchall()]

def answer_live_class_question(question_id: int, answer_text: str) -> bool:
    """Marks a live class question as answered with optional explanation."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE live_class_questions
            SET is_answered = 1, answer_text = ?
            WHERE id = ?
        """, (answer_text.strip(), question_id))
        return True

def create_answer_sheet_submission(user_id: int, course_id: int, file_path: str, original_filename: str, module_id: Optional[int] = None, lesson_id: Optional[int] = None, remarks: Optional[str] = None) -> dict:
    """Records a student's uploaded PDF answer sheet for UPSC Mains evaluation."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO answer_sheet_submissions (user_id, course_id, module_id, lesson_id, file_path, original_filename, remarks)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (user_id, course_id, module_id, lesson_id, file_path, original_filename, (remarks or "").strip()))
        sid = cursor.lastrowid
        cursor.execute("""
            SELECT a.*, u.full_name as student_name, u.user_id as student_user_id, c.title as course_title
            FROM answer_sheet_submissions a
            JOIN users u ON a.user_id = u.id
            JOIN courses c ON a.course_id = c.id
            WHERE a.id = ?
        """, (sid,))
        return dict(cursor.fetchone())

def get_user_answer_sheet_submissions(user_id: int, course_id: int) -> list:
    """Returns all answer sheet submissions for a specific student in a course."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT a.*, c.title as course_title, m.title as module_title, l.title as lesson_title
            FROM answer_sheet_submissions a
            JOIN courses c ON a.course_id = c.id
            LEFT JOIN modules m ON a.module_id = m.id
            LEFT JOIN lessons l ON a.lesson_id = l.id
            WHERE a.user_id = ? AND a.course_id = ?
            ORDER BY a.created_at DESC
        """, (user_id, course_id))
        return [dict(r) for r in cursor.fetchall()]

def get_course_answer_sheet_submissions(course_id: int) -> list:
    """Returns all answer sheets submitted by students for a course (for faculty review)."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT a.*, u.full_name as student_name, u.user_id as student_user_id, u.email as student_email,
                   c.title as course_title, m.title as module_title, l.title as lesson_title,
                   evaluator.full_name as evaluator_name
            FROM answer_sheet_submissions a
            JOIN users u ON a.user_id = u.id
            JOIN courses c ON a.course_id = c.id
            LEFT JOIN modules m ON a.module_id = m.id
            LEFT JOIN lessons l ON a.lesson_id = l.id
            LEFT JOIN users evaluator ON a.evaluated_by = evaluator.id
            WHERE a.course_id = ?
            ORDER BY a.created_at DESC
        """, (course_id,))
        return [dict(r) for r in cursor.fetchall()]

def evaluate_answer_sheet_submission(submission_id: int, marks_awarded: float, max_marks: float, feedback: str, evaluated_by: int) -> bool:
    """Updates an answer sheet submission with evaluation marks and faculty feedback."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE answer_sheet_submissions
            SET marks_awarded = ?, max_marks = ?, feedback = ?, status = 'evaluated', evaluated_by = ?, evaluated_at = CURRENT_TIMESTAMP
            WHERE id = ?
        """, (marks_awarded, max_marks, feedback.strip(), evaluated_by, submission_id))
        return True

def get_teacher_pending_answer_sheets(teacher_id: int) -> list:
    """Returns all pending answer copy submissions for courses taught by a specific teacher."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT a.*, u.full_name as student_name, u.user_id as student_user_id, u.email as student_email,
                   c.title as course_title, c.code as course_code, m.title as module_title
            FROM answer_sheet_submissions a
            JOIN courses c ON a.course_id = c.id
            JOIN users u ON a.user_id = u.id
            LEFT JOIN modules m ON a.module_id = m.id
            WHERE c.teacher_id = ? AND a.status IN ('pending', 'submitted', 'under_review')
            ORDER BY a.created_at ASC
        """, (teacher_id,))
        return [dict(r) for r in cursor.fetchall()]

def complete_answer_sheet_evaluation(submission_id: int, marks_awarded: float, max_marks: float, feedback: str, evaluated_by: int) -> dict:
    """Evaluates and marks an answer sheet submission as completed with marks and feedback."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE answer_sheet_submissions
            SET marks_awarded = ?, max_marks = ?, feedback = ?, status = 'evaluated', evaluated_by = ?, evaluated_at = CURRENT_TIMESTAMP
            WHERE id = ?
        """, (marks_awarded, max_marks, feedback.strip(), evaluated_by, submission_id))
        cursor.execute("""
            SELECT a.*, u.full_name as student_name, u.user_id as student_user_id, c.title as course_title, c.teacher_id
            FROM answer_sheet_submissions a
            JOIN users u ON a.user_id = u.id
            JOIN courses c ON a.course_id = c.id
            WHERE a.id = ?
        """, (submission_id,))
        return dict(cursor.fetchone())

def get_completed_students_without_certificates() -> list:
    """
    Finds enrolled students who have completed 100% of a course, but do not yet have an authentic certificate issued by Admin.
    """
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT e.user_id, e.course_id, e.completed_at,
                   u.full_name as student_name, u.user_id as student_user_id, u.email as student_email,
                   c.title as course_title, c.code as course_code
            FROM enrollments e
            JOIN users u ON e.user_id = u.id
            JOIN courses c ON e.course_id = c.id
            WHERE c.status = 'published' AND c.deleted_at IS NULL
              AND (e.completed_at IS NOT NULL OR 
                  ((SELECT COUNT(*) FROM lessons l JOIN modules m ON l.module_id = m.id WHERE m.course_id = c.id) > 0 AND
                   (SELECT COUNT(*) FROM lessons l JOIN modules m ON l.module_id = m.id WHERE m.course_id = c.id) = 
                   (SELECT COUNT(*) FROM lesson_progress lp JOIN lessons l ON lp.lesson_id = l.id JOIN modules m ON l.module_id = m.id WHERE m.course_id = c.id AND lp.user_id = u.id AND lp.is_completed = 1)))
              AND NOT EXISTS (
                  SELECT 1 FROM certificates cert 
                  WHERE cert.student_id = e.user_id AND cert.course_id = e.course_id AND cert.status != 'revoked'
              )
            ORDER BY e.completed_at DESC, u.full_name ASC
        """)
        return [dict(r) for r in cursor.fetchall()]

# =========================================================================
# ONE-ON-ONE MENTORING SESSIONS HELPERS
# =========================================================================

def create_student_mentoring_request(student_id: int, course_id: Optional[int], topic: str, description: str, preferred_date: str, preferred_time: str) -> dict:
    """Student requests a 1-on-1 mentoring session; awaits Admin assignment of a faculty mentor."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO mentoring_sessions (initiator_role, student_id, course_id, topic, description, preferred_date, preferred_time, status)
            VALUES ('student', ?, ?, ?, ?, ?, ?, 'pending_admin_assignment')
        """, (student_id, course_id, topic.strip(), (description or "").strip(), preferred_date.strip(), preferred_time.strip()))
        sid = cursor.lastrowid
        cursor.execute("""
            SELECT ms.*, u.full_name as student_name, u.user_id as student_user_id, c.title as course_title
            FROM mentoring_sessions ms
            JOIN users u ON ms.student_id = u.id
            LEFT JOIN courses c ON ms.course_id = c.id
            WHERE ms.id = ?
        """, (sid,))
        return dict(cursor.fetchone())

def create_teacher_mentoring_request(teacher_id: int, student_id: int, course_id: Optional[int], topic: str, description: str, scheduled_date: str, scheduled_time: str) -> dict:
    """Teacher initiates a 1-on-1 mentoring session with a specific student; student confirms or suggests date/time."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO mentoring_sessions (initiator_role, student_id, teacher_id, course_id, topic, description, scheduled_date, scheduled_time, status)
            VALUES ('teacher', ?, ?, ?, ?, ?, ?, ?, 'pending_student_schedule')
        """, (student_id, teacher_id, course_id, topic.strip(), (description or "").strip(), scheduled_date.strip(), scheduled_time.strip()))
        sid = cursor.lastrowid
        cursor.execute("""
            SELECT ms.*, u.full_name as student_name, u.user_id as student_user_id, t.full_name as teacher_name, c.title as course_title
            FROM mentoring_sessions ms
            JOIN users u ON ms.student_id = u.id
            JOIN users t ON ms.teacher_id = t.id
            LEFT JOIN courses c ON ms.course_id = c.id
            WHERE ms.id = ?
        """, (sid,))
        return dict(cursor.fetchone())

def admin_assign_mentoring_teacher(session_id: int, teacher_id: int, scheduled_date: Optional[str] = None, scheduled_time: Optional[str] = None, meeting_link: Optional[str] = None) -> dict:
    """Admin assigns an expert faculty mentor to a student-initiated 1-on-1 session."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE mentoring_sessions
            SET teacher_id = ?,
                scheduled_date = COALESCE(?, preferred_date),
                scheduled_time = COALESCE(?, preferred_time),
                meeting_link = ?,
                status = 'scheduled',
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
        """, (teacher_id, scheduled_date, scheduled_time, (meeting_link or "https://meet.google.com/new"), session_id))
        cursor.execute("""
            SELECT ms.*, u.full_name as student_name, u.user_id as student_user_id, t.full_name as teacher_name, c.title as course_title
            FROM mentoring_sessions ms
            JOIN users u ON ms.student_id = u.id
            JOIN users t ON ms.teacher_id = t.id
            LEFT JOIN courses c ON ms.course_id = c.id
            WHERE ms.id = ?
        """, (session_id,))
        return dict(cursor.fetchone())

def student_confirm_mentoring_schedule(session_id: int, scheduled_date: str, scheduled_time: str, student_notes: Optional[str] = None) -> dict:
    """Student confirms or suggests date/time for a teacher-initiated 1-on-1 session."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE mentoring_sessions
            SET scheduled_date = ?,
                scheduled_time = ?,
                student_notes = ?,
                status = 'scheduled',
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
        """, (scheduled_date.strip(), scheduled_time.strip(), (student_notes or "").strip(), session_id))
        cursor.execute("""
            SELECT ms.*, u.full_name as student_name, u.user_id as student_user_id, t.full_name as teacher_name, c.title as course_title
            FROM mentoring_sessions ms
            JOIN users u ON ms.student_id = u.id
            LEFT JOIN users t ON ms.teacher_id = t.id
            LEFT JOIN courses c ON ms.course_id = c.id
            WHERE ms.id = ?
        """, (session_id,))
        return dict(cursor.fetchone())

def complete_mentoring_session(session_id: int, teacher_notes: Optional[str] = None) -> bool:
    """Marks a mentoring session as successfully completed with notes."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE mentoring_sessions
            SET status = 'completed',
                teacher_notes = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
        """, ((teacher_notes or "").strip(), session_id))
        return True

def get_student_mentoring_sessions(student_id: int) -> list:
    """Returns all mentoring sessions for a student."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT ms.*, t.full_name as teacher_name, t.email as teacher_email, c.title as course_title
            FROM mentoring_sessions ms
            LEFT JOIN users t ON ms.teacher_id = t.id
            LEFT JOIN courses c ON ms.course_id = c.id
            WHERE ms.student_id = ?
            ORDER BY ms.created_at DESC
        """, (student_id,))
        return [dict(r) for r in cursor.fetchall()]

def get_teacher_mentoring_sessions(teacher_id: int) -> list:
    """Returns all mentoring sessions assigned to or initiated by a teacher."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT ms.*, u.full_name as student_name, u.user_id as student_user_id, u.email as student_email, c.title as course_title
            FROM mentoring_sessions ms
            JOIN users u ON ms.student_id = u.id
            LEFT JOIN courses c ON ms.course_id = c.id
            WHERE ms.teacher_id = ?
            ORDER BY ms.created_at DESC
        """, (teacher_id,))
        return [dict(r) for r in cursor.fetchall()]

def get_admin_pending_mentoring_sessions() -> list:
    """Returns all student requests awaiting teacher assignment by admin, plus all scheduled sessions."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT ms.*, u.full_name as student_name, u.user_id as student_user_id, u.email as student_email,
                   t.full_name as teacher_name, c.title as course_title
            FROM mentoring_sessions ms
            JOIN users u ON ms.student_id = u.id
            LEFT JOIN users t ON ms.teacher_id = t.id
            LEFT JOIN courses c ON ms.course_id = c.id
            ORDER BY CASE WHEN ms.status = 'pending_admin_assignment' THEN 0 ELSE 1 END, ms.created_at DESC
        """)
        return [dict(r) for r in cursor.fetchall()]





