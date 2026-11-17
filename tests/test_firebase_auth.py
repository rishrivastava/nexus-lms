import asyncio
import json
import sqlite3
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from tests.test_e2e_features import ASGIClient, get_client_for_user
from app.main import app

async def run_firebase_tests():
    print("=== Testing Firebase Authentication Pipeline ===")
    client = ASGIClient(app)

    # 1. Test GET /api/auth/firebase-config
    status, text, _ = await client.get("/api/auth/firebase-config")
    assert status == 200, f"Expected 200 for config, got {status}"
    config = json.loads(text)
    assert "enabled" in config
    assert "projectId" in config
    print("  ✓ GET /api/auth/firebase-config returned valid public config")

    # 2. Test Firebase Login for existing Admin (admin@nexus.edu)
    status, text, headers = await client.post("/api/auth/firebase-login", json_data={
        "email": "admin@nexus.edu",
        "name": "Admin Rishu",
        "firebase_uid": "fb_uid_admin_test_123",
        "provider_id": "google.com",
        "photo_url": "https://example.com/avatar.jpg"
    })
    assert status == 200, f"Expected 200 for admin login, got {status}: {text}"
    resp = json.loads(text)
    assert resp["status"] == "success"
    assert resp["redirect_url"] == "/department"
    assert resp["user"]["role"] == "department_admin"
    assert "lms_token" in client.cookies
    print("  ✓ Firebase Login for Admin successful (redirected to /department)")

    # 3. Test Firebase Login for existing Teacher (alan@nexus.edu)
    teacher_client = ASGIClient(app)
    status, text, _ = await teacher_client.post("/api/auth/firebase-login", json_data={
        "email": "alan@nexus.edu",
        "name": "Prof. Rameez",
        "firebase_uid": "fb_uid_teacher_test_456",
        "provider_id": "google.com"
    })
    assert status == 200
    resp = json.loads(text)
    assert resp["status"] == "success"
    assert resp["redirect_url"] == "/teacher"
    assert resp["user"]["role"] == "teacher"
    assert "lms_token" in teacher_client.cookies
    print("  ✓ Firebase Login for Teacher successful (redirected to /teacher)")

    # 4. Test Firebase Login for existing Student (student@nexus.edu -> CS2026-002)
    student_client = ASGIClient(app)
    status, text, _ = await student_client.post("/api/auth/firebase-login", json_data={
        "email": "student@nexus.edu",
        "name": "Priya Patel",
        "firebase_uid": "fb_uid_student_test_789",
        "provider_id": "google.com"
    })
    assert status == 200
    resp = json.loads(text)
    assert resp["status"] == "success"
    assert resp["redirect_url"] == "/student"
    assert resp["user"]["role"] == "student"
    print("  ✓ Firebase Login for Student successful (redirected to /student)")

    # 5. Test Auto-Provisioning for Brand New Learner
    new_email = "rohit.sharma.test2026@gmail.com"
    new_client = ASGIClient(app)
    status, text, _ = await new_client.post("/api/auth/firebase-login", json_data={
        "email": new_email,
        "name": "Rohit Sharma",
        "firebase_uid": "fb_uid_new_learner_999",
        "provider_id": "google.com",
        "photo_url": "https://example.com/rohit.jpg"
    })
    assert status == 200
    resp = json.loads(text)
    assert resp["status"] == "success"
    assert resp["redirect_url"] == "/student"
    assert resp["user"]["role"] == "student"
    assert resp["user"]["full_name"] == "Rohit Sharma"
    
    # Verify user exists in database with firebase_uid
    conn = sqlite3.connect('/Users/rocket/.gemini/antigravity/scratch/lms/lms.db')
    c = conn.cursor()
    c.execute("SELECT id, user_id, full_name, email, role, firebase_uid FROM users WHERE email = ?", (new_email,))
    row = c.fetchone()
    conn.close()
    assert row is not None, "New student was not inserted into database!"
    assert row[5] == "fb_uid_new_learner_999", "Firebase UID not stored!"
    print("  ✓ Auto-provisioned new student account via Firebase (ST- ID, role=student, firebase_uid linked)")

    # 6. Verify new student can view profile using the issued lms_token
    status, prof_text, _ = await new_client.get("/profile")
    assert status == 200
    assert "Welcome Rohit Sharma!" in prof_text
    print("  ✓ Newly provisioned student successfully accesses /profile with 'Welcome Rohit Sharma!'")

    # 7. Test Admin updating Firebase settings via POST /department/firebase/settings
    admin_client, _ = get_client_for_user("admin@nexus.edu")
    status, text, headers = await admin_client.post("/department/firebase/settings", data={
        "firebase_auth_enabled": "1",
        "firebase_project_id": "nexus-prod-12345",
        "firebase_api_key": "AIzaSyTestKey98765",
        "firebase_auth_domain": "nexus-prod-12345.firebaseapp.com",
        "firebase_app_id": "1:987654321:web:abcdef1234"
    }, follow_redirects=False)
    assert status in (200, 303)
    
    # Verify settings persisted in DB
    conn = sqlite3.connect('/Users/rocket/.gemini/antigravity/scratch/lms/lms.db')
    c = conn.cursor()
    c.execute("SELECT value FROM system_settings WHERE key = 'firebase_project_id'")
    proj_val = c.fetchone()[0]
    c.execute("SELECT value FROM system_settings WHERE key = 'firebase_api_key'")
    key_val = c.fetchone()[0]
    conn.close()
    assert proj_val == "nexus-prod-12345"
    assert key_val == "AIzaSyTestKey98765"
    print("  ✓ Admin updated and persisted Firebase settings in system_settings")

    # 8. Verify public config now reflects new settings
    status, text, _ = await client.get("/api/auth/firebase-config")
    updated_config = json.loads(text)
    assert updated_config["projectId"] == "nexus-prod-12345"
    assert updated_config["apiKey"] == "AIzaSyTestKey98765"
    print("  ✓ Public Firebase config accurately reflects newly configured credentials")

    # 9. Test Login Page loads with Firebase UI (using unauthenticated client)
    unauth_client = ASGIClient(app)
    status, login_html, _ = await unauth_client.get("/login")
    assert status == 200
    assert "Sign in with Google" in login_html
    assert "firebase-app-compat.js" in login_html
    assert "btnFirebaseGoogle" in login_html
    print("  ✓ Login page renders Google (Firebase) sign-in button & Firebase SDK compat scripts")

    print("\n========================================================")
    print("  ALL FIREBASE AUTHENTICATION TESTS PASSED (100% OK)!")
    print("========================================================")

if __name__ == "__main__":
    asyncio.run(run_firebase_tests())
