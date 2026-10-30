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
            position INTEGER DEFAULT 1,
            FOREIGN KEY (course_id) REFERENCES courses(id) ON DELETE CASCADE
        );
        """)
        
        # 4. Lessons (Video, PDF, or Quiz)
        # content_type: 'youtube', 'pdf', 'quiz'
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS lessons (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            module_id INTEGER NOT NULL,
            title TEXT NOT NULL,
            content_type TEXT NOT NULL,                -- 'youtube', 'pdf', 'quiz'
            content_value TEXT,                        -- YouTube URL/ID or uploaded PDF filename or instructions
            position INTEGER DEFAULT 1,
            duration_minutes INTEGER DEFAULT 10,
            FOREIGN KEY (module_id) REFERENCES modules(id) ON DELETE CASCADE
        );
        """)
        
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
            ai_response TEXT,                           -- instant Gemini AI response
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

        # Default system branding and settings
        default_settings = {
            "platform_name": "Nexus LMS",
            "platform_tagline": "Foreign Language Learning Portal",
            "institution_name": "Leadership Boulevard Pvt Ltd",
            "department_name": "Foreign Language",
            "department_tagline": "Pioneering in Language Teaching",
            "brand_color": "#1e3a8a",
            "secondary_brand_color": "#0284c7",
            "welcome_message": "Welcome to the Foreign Language Learning Portal. Master world languages with curated modules, interactive videos, and speaking practice.",
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
            "gemini_enabled": "1"
        }
        for k, v in default_settings.items():
            cursor.execute("INSERT OR IGNORE INTO system_settings (key, value) VALUES (?, ?)", (k, v))

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

def notify_users(user_ids: list, title: str, message: str, link_url: str = None, category: str = "general", event_type: str = None):
    if not user_ids:
        return
    try:
        with get_db() as conn:
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

