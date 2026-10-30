import os
from app.database import init_db, get_db, UPLOAD_DIR
from app.auth import hash_password

def seed_data():
    init_db()
    with get_db() as conn:
        cursor = conn.cursor()
        
        # Check if already seeded
        cursor.execute("SELECT COUNT(*) FROM users")
        if cursor.fetchone()[0] > 0:
            print("Database already contains data. Skipping seed.")
            return

        print("Seeding initial LMS data...")
        
        # 1. Insert Department Head / Admin
        admin_pass = hash_password("admin123")
        cursor.execute("""
            INSERT INTO users (user_id, full_name, department, email, password_hash, role, must_change_password)
            VALUES (?, ?, ?, ?, ?, ?, 0)
        """, ("DEPT-HEAD", "Academic Director", "Foreign Language", "head@fl4schools.com", admin_pass, "department_admin"))
        
        # 2. Insert Teacher
        teacher_pass = hash_password("teacher123")
        cursor.execute("""
            INSERT INTO users (user_id, full_name, department, email, password_hash, role, must_change_password)
            VALUES (?, ?, ?, ?, ?, ?, 0)
        """, ("T-ALAN", "Prof. Claire Dubois", "Foreign Language", "claire.dubois@fl4schools.com", teacher_pass, "teacher"))
        teacher_id = cursor.lastrowid
        
        # 3. Insert Students (with default temporary passwords and must_change_password = 1)
        student_pass = hash_password("welcome123")
        students = [
            ("CS2026-001", "Aarav Sharma", "Foreign Language"),
            ("CS2026-002", "Priya Patel", "Foreign Language"),
            ("CS2026-003", "Rohan Mehta", "Foreign Language"),
            ("CS2026-004", "Ananya Verma", "Foreign Language"),
            ("CS2026-005", "Devansh Rao", "Foreign Language")
        ]
        
        student_ids = []
        for uid, name, dept in students:
            cursor.execute("""
                INSERT INTO users (user_id, full_name, department, email, password_hash, role, must_change_password)
                VALUES (?, ?, ?, NULL, ?, 'student', 1)
            """, (uid, name, dept, student_pass))
            student_ids.append(cursor.lastrowid)

        # 4. Insert Course
        cursor.execute("""
            INSERT INTO courses (title, code, department, subject, description, thumbnail_url, teacher_id, is_published)
            VALUES (?, ?, ?, ?, ?, ?, ?, 1)
        """, (
            "French A1: Beginner French & Fundamentals",
            "FR-101",
            "Foreign Language",
            "French",
            "Learn the fundamentals of French: alphabet, greetings, essential vocabulary, and foundational sentence structure.",
            "https://images.unsplash.com/photo-1502602898657-3e91760cbb34?w=800&auto=format&fit=crop&q=60",
            teacher_id
        ))
        course_id = cursor.lastrowid

        # 5. Insert Modules & Lessons
        # Module 1
        cursor.execute("""
            INSERT INTO modules (course_id, title, position)
            VALUES (?, ?, 1)
        """, (course_id, "Module 1: Salutations et Les Bases (Greetings & Basics)"))
        mod1_id = cursor.lastrowid

        # Lesson 1: YouTube video
        cursor.execute("""
            INSERT INTO lessons (module_id, title, content_type, content_value, position, duration_minutes)
            VALUES (?, ?, 'youtube', ?, 1, 15)
        """, (mod1_id, "Learn French in 15 Minutes - French Basics for Beginners", "https://www.youtube.com/watch?v=ujDtm0hZyII"))

        # Lesson 2: PDF Document
        sample_pdf_path = os.path.join(UPLOAD_DIR, "French_A1_Beginner_Grammar_and_Vocabulary.pdf")
        if not os.path.exists(sample_pdf_path):
            with open(sample_pdf_path, "w") as f:
                f.write("%PDF-1.4\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n3 0 obj<</Type/Page/MediaBox[0 0 612 792]/Parent 2 0 R/Resources<<>>>>endobj\nxref\n0 4\n0000000000 65535 f \n0000000009 00000 n \n0000000052 00000 n \n0000000101 00000 n \ntrailer<</Size 4/Root 1 0 R>>\nstartxref\n178\n%%EOF\n")
        
        cursor.execute("""
            INSERT INTO lessons (module_id, title, content_type, content_value, position, duration_minutes)
            VALUES (?, ?, 'pdf', ?, 2, 15)
        """, (mod1_id, "Study Guide: French Greetings, Pronouns & Everyday Vocabulary", "French_A1_Beginner_Grammar_and_Vocabulary.pdf"))

        # Lesson 3: Quiz
        cursor.execute("""
            INSERT INTO lessons (module_id, title, content_type, content_value, position, duration_minutes)
            VALUES (?, ?, 'quiz', ?, 3, 10)
        """, (mod1_id, "Knowledge Check: French Greetings & Essentials", "Test your understanding of French greetings, pronouns, and numbers."))
        quiz_lesson_id = cursor.lastrowid

        cursor.execute("""
            INSERT INTO quizzes (lesson_id, passing_score)
            VALUES (?, 70)
        """, (quiz_lesson_id,))
        quiz_id = cursor.lastrowid

        # Quiz Questions
        questions = [
            (
                quiz_id,
                "Which French greeting means 'Good morning' or 'Hello'?",
                "Au revoir",
                "Bonjour",
                "Merci",
                "Bonne nuit",
                "B",
                "Bonjour is the standard French greeting meaning Good morning or Hello."
            ),
            (
                quiz_id,
                "How do you say 'Thank you very much' in French?",
                "De rien",
                "S'il vous plaît",
                "Merci beaucoup",
                "Enchanté",
                "C",
                "Merci beaucoup translates directly to 'Thank you very much'."
            ),
            (
                quiz_id,
                "What does the phrase 'Comment vous appelez-vous ?' mean?",
                "Where do you live?",
                "What is your name?",
                "How old are you?",
                "How are you?",
                "B",
                "'Comment vous appelez-vous ?' is the polite way to ask for someone's name."
            )
        ]
        cursor.executemany("""
            INSERT INTO quiz_questions (quiz_id, question_text, option_a, option_b, option_c, option_d, correct_option, explanation)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, questions)

        # 6. Enroll students into this course
        for s_id in student_ids:
            cursor.execute("INSERT INTO enrollments (user_id, course_id) VALUES (?, ?)", (s_id, course_id))

        # Give student 1 some demo progress
        cursor.execute("""
            INSERT INTO lesson_progress (user_id, lesson_id, is_completed, watched_seconds, completed_at)
            VALUES (?, ?, 1, 720, CURRENT_TIMESTAMP)
        """, (student_ids[0], 1))
        
        cursor.execute("""
            INSERT INTO quiz_attempts (user_id, quiz_id, score_percent, passed)
            VALUES (?, ?, 100.0, 1)
        """, (student_ids[0], quiz_id))

        print("Seeding completed successfully!")

if __name__ == "__main__":
    seed_data()
