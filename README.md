# Nexus LMS - Enterprise Departmental Learning Management System

A modern, responsive, web-based Learning Management System (LMS) built with **FastAPI**, **SQLite**, and **Tailwind CSS**, designed for departments, colleges, universities, schools, training academies, and state educational programs.

The system is architected to effortlessly support at least **6,000+ students**, featuring centralized student management, identity deduplication, course-based isolation, timed assessments, customizable governance permissions, and full administrative audit logging.

---

## 🌟 Key Architecture & Product Capabilities

### 1. Department Administrator Profile and Branding
- **Prominent Department Identity:** Customizable department name, institution name, tagline, cover banner image, custom logo, primary and secondary brand colors, and contact info (email, phone, office).
- **Displayed Department Name Decoupling:** Changing the displayed department name updates the branding dynamically without altering underlying database identifiers, user permissions, course ownership, or student records.
- **Institutional Typography Engine:** Curated selection of professional fonts:
  - **Outfit** (Modern Geometric - Default)
  - **Poppins** (Clean Academic)
  - **Inter** (Enterprise Standard)
  - **Noto Sans Devanagari** (Full Hindi & Bilingual Indian Language Support)
  - **Merriweather** (Classic Editorial Serif)
- **Administrator Personal Profile:** The HOD can customize their personal profile (full name, designation, official email, and profile photo avatar).
- **Identity Change Governance & Audit History:** Requires explicit administrator confirmation for identity updates and writes immutable chronological records to the audit trail.

---

### 2. Three Main Analytics Dashboard Sections

The system features three dedicated primary analytics dashboard sections in the main navigation, computed directly from live database records:

#### Dashboard 1: Overview Dashboard (Consolidated LMS View)
Consolidates real-time institutional metrics across 12 primary KPI cards:
1. **Total Registered Students** (Global Student Pool)
2. **Total Active Student Accounts** (Learners who have updated temporary passwords)
3. **Total Enrolled Students** (Unique learners assigned to active courses)
4. **Total Teachers / Faculty**
5. **Total Subjects** (Academic streams)
6. **Total Courses** (Published curricula)
7. **Total Course Enrolments** (Total seat allocations across all cohorts)
8. **Average Quiz Score (%)** (Calculated across all knowledge checks)
9. **Average Time Spent on LMS** (Hours/minutes computed from video watch progress & reading time)
10. **Total Learning Resources** (Sum of PDF documents, YouTube lectures, and quizzes)
11. **Overall Course Completion Rate (%)** (Completed courses vs total enrolments)
12. **Students Active Right Now** (Real-time active pulse within the &le; 5-minute heartbeat window)

**Below the KPI Cards:**
- **Student Registration Trends:** Monthly registration breakdown.
- **Top-Performing Subjects:** Ranked by average quiz score.
- **Subjects Requiring Academic Attention:** Highlighting low completion or low average scores.
- **Interactive Scope Filters:** Scope analytics by District or School.
- **Clickable Drill-Downs:** Clicking KPI cards immediately navigates to the detailed view.

#### Dashboard 2: Subject Participation Dashboard
Compares student enrolment, engagement, and academic performance across subjects:
- **Subject-Wise Comparison Matrix:**
  - Subject Name
  - Courses under Subject
  - Total Unique Students Enrolled
  - Total Course Enrolments
  - Students Active Right Now (&le; 5 min)
  - Students Active in Selected Period (24h)
  - Average Quiz Score (%)
  - Average Learning Time Spent per Student
  - Overall Course Completion Rate (%)
  - Total Quiz Attempts Count
  - Not Started Count (Enrolled with 0 lessons finished and 0 quiz attempts)
- **Subject Drill-Down Navigation:**
  - **Top 10 Students Ranking Table:** Displays rank, student ID, name, guardian, school, district, average score %, completion %, and learning time. **Enforces minimum 1 quiz attempt requirement** (unattempted students are strictly excluded).
  - **Bottom 10 Students Ranking Table:** Identifies students requiring remediation (min 1 attempt requirement).
  - **Unattempted Students List:** Enrolled students who have not attempted any assessment quizzes.
  - **Not Started Students List:** Enrolled students with zero activity.
  - **Download Subject CSV:** One-click CSV export of subject participation and performance records.

#### Dashboard 3: Subject Content Dashboard
Hierarchical matrix of all learning content by subject:
- Subject Name & total estimated learning duration
- Courses under subject with instructor name and publication status
- Number of curriculum modules and lessons per course
- Resource counts: PDF documents, YouTube video lectures, Timed Quizzes
- Assessment depth: Total question count per quiz
- Quick Management Shortcuts: Edit curriculum, preview student view, and archive/delete courses.

---

### 3. Power BI & External Analytics REST API Integration
Dedicated **Integrations & Data Export** panel in settings:
- **Live Sync Indicator:** Tracks external queries and records the latest timestamp in `powerbi_last_sync_at`.
- **API Key Management:** One-click generation and rotation of secure REST API keys with audit logging.
- **Power BI / Power Query (M Query) Connector Snippet:**
  ```powerquery
  let
      Source = Json.Document(Web.Contents("http://127.0.0.1:8000/api/v1/reporting/students", [
          Headers=[#"X-API-Key"="YOUR_API_KEY"]
      ])),
      data = Source[data],
      table = Table.FromRecords(data)
  in
      table
  ```
- **Documented Authenticated REST Endpoints (`X-API-Key` or `?api_key=`):**
  - `GET /api/v1/reporting/students`: Paginated student roster, demographics, UDISE codes, progress.
  - `GET /api/v1/reporting/subjects`: Subject-wise enrolment, live learners, quiz score averages.
  - `GET /api/v1/reporting/courses`: Course catalog, instructor, modules, and lesson counts.
  - `GET /api/v1/reporting/enrollments`: Course assignments, timestamps, completion states.
  - `GET /api/v1/reporting/resources`: Lesson modules, PDF documents, and YouTube videos.
  - `GET /api/v1/reporting/quiz-attempts`: Knowledge check attempts, scores, and pass/fail states.
  - `GET /api/v1/reporting/engagement`: Watch times, completed lessons, and interaction metrics.

---

### 4. Course Modification, Archival & Soft Deletion
- **Course Settings Editor:** Modify course title, course code, subject stream, description, estimated duration, and publication status.
- **Deletion Workflow with Warning Banner:**
  Displays a warning with the count of enrolled students affected and offers 3 choices:
  1. **Archive Course (Preferred):** Hides course from student dashboards, preserves all student quiz scores, learning logs, and audit trail.
  2. **Unpublish Course:** Reverts course to draft status.
  3. **Permanently Delete Course:** Soft deletes course (`status = 'deleted'`) while keeping student accounts in the Global Student Pool safe.
- **Automated Student Notifications:** Optional toggle to notify all enrolled students when a course is archived, unpublished, or modified.

---

### 5. Notification Centre for All Users
- **Navbar Bell Icon:** Displays live unread count badge and opens an interactive notification drawer.
- **Notification Inbox:** View recent notifications with timestamps, mark single items as read, or mark all as read.
- **Automated Event Triggers:**
  - Course assignment / enrolment
  - New content added (PDF document, YouTube video, Timed Quiz)
  - Course status changed (archived or deleted)
  - New faculty member added
- **Administrator Policy Governance:** Toggle notification triggers in `notification_settings` to suppress specific notification events institution-wide.

---

### 6. Real-Time Live Student Tracking
- **Heartbeat Engine:** Active browser sessions dispatch an asynchronous heartbeat ping every 60 seconds (`POST /api/activity/heartbeat`).
- **Live Active Indicator:** Students who interacted within the last 5 minutes are flagged as "Active Right Now" with a pulsating indicator.

---

### 7. Global Student Pool & Dual-Layer Duplicate Prevention Engine
- **Permanent Identity vs Course Enrolment:** Every student has exactly one permanent record in the centralized Global Student Pool (`STU-YYYY-XXXXXX`).
- **Duplicate Prevention Criteria:** Strict normalization and matching on **Student Name + Father/Guardian Name**.
- **Normalization Pipeline:**
  1. Unicode NFKD normalization and diacritic removal.
  2. Lowercase conversion.
  3. Trimming and collapsing of whitespace.
- **Single Student Registration Workflow:** Real-time duplicate validation warns if the student already exists and offers one-click enrolment into courses without duplicating records.
- **Administrative Conflict Review:** When two genuine individuals share names, staff can flag the record for HOD review.
- **Bulk Spreadsheet Import (.csv & .xlsx):** Validates in-file and database duplicates, auto-enrols existing students into specified courses, and generates downloadable rejected row reports.

---

## 🚀 Running the Application

### Start Command
```bash
cd /Users/rocket/.gemini/antigravity/scratch/lms
./start.sh
```
The server runs at: **[http://127.0.0.1:8000](http://127.0.0.1:8000)**

### Running Unit & Integration Tests
```bash
cd /Users/rocket/.gemini/antigravity/scratch/lms
./venv/bin/python3 test_app.py
```

---

## 🔑 Default Provisioned Accounts

| Role | User ID / Login | Default Password | Primary Dashboard |
| :--- | :--- | :--- | :--- |
| **Department Head / Admin** | `DEPT-HEAD` | `admin123` | `/department` |
| **Teacher / Faculty** | `T-ALAN` | `teacher123` | `/teacher` |
| **Student** | `CS2026-002` | `welcome123` *(prompts password setup)* | `/student` |

---

## 📋 Spreadsheets & Bulk Import Format

Upload files via the **Import Students (CSV / Excel)** modal.

Expected headers:
```csv
Serial NO. (UNIQUE NO.),STUDENT NAME,FATHER'/GUARDIAN, NAME,SCHOOL NAME,UDISE CODE,BLOCK,DISTRICT,STATE,PINCODE,COURSE
```
Sample Row:
```csv
KA-2026-101,Aarav Kumar,Ramesh Kumar,Govt Model High School,29280100101,North Block,Bengaluru,Karnataka,560001,CS-201
```
