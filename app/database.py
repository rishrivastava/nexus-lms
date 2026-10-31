import sqlite3
import os
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

        # Default system branding and settings
        default_settings = {
            "platform_name": "Nexus LMS",
            "platform_tagline": "Language learning made easy",
            "institution_name": "Leadership Boulevard Pvt Ltd",
            "department_name": "Foreign Language",
            "department_tagline": "Pioneering in Language Teaching",
            "brand_color": "#1e3a8a",
            "secondary_brand_color": "#0284c7",
            "welcome_message": "Welcome to the Foreign Language Learning Portal. Master world languages with curated modules, interactive videos, and speaking practice.",
            "login_help_text": "Enter your User ID / Serial Number and password to access your portal.",
            "login_user_id_placeholder": "e.g. Serial Number or ID",
            "login_button_text": "Sign In",
            "login_footer_text": "Accredited Foreign Language Learning Portal",
            "logo_icon": "fa-language",
            "logo_image_url": "",
            "department_banner_url": "",
            "contact_email": "info@fl4schools.com",
            "contact_phone": "+91 9540594033",
            "contact_office": "Mumbai",
            "branding_text": "Accredited Academic Portal for Foreign Language Learning.",
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

        # Always cleanse any legacy IIT, Science or Computer Science from system settings
        cursor.execute("UPDATE system_settings SET value = 'Leadership Boulevard Pvt Ltd' WHERE value LIKE '%Indian Institute%'")
        cursor.execute("UPDATE system_settings SET value = 'Foreign Language' WHERE value LIKE '%Computer Science%'")
        cursor.execute("UPDATE system_settings SET value = 'Language learning made easy' WHERE key = 'platform_tagline' OR value LIKE '%Departmental Learning%'")
        cursor.execute("UPDATE system_settings SET value = 'Pioneering in Language Teaching' WHERE value LIKE '%Pioneering Innovation%'")
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

def update_system_settings(settings: dict):
    with get_db() as conn:
        cursor = conn.cursor()
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

def notify_users(user_ids: list, title: str, message: str, link_url: str = None, category: str = "general", event_type: str = None, conn=None):
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
        return dict(cursor.fetchone())
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
        return dict(cursor.fetchone())

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


