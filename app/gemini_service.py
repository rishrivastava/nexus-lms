import os
import json
import urllib.request
import urllib.error
from app.database import get_system_settings

def get_gemini_config() -> dict:
    settings = get_system_settings()
    api_key = settings.get("gemini_api_key", "").strip() or os.environ.get("GEMINI_API_KEY", "").strip()
    model = settings.get("gemini_model", "gemini-2.5-flash").strip() or "gemini-2.5-flash"
    auto_reply = settings.get("gemini_auto_reply", "1") == "1"
    enabled = settings.get("gemini_enabled", "1") == "1"
    return {
        "api_key": api_key,
        "model": model,
        "auto_reply": auto_reply,
        "enabled": enabled
    }

def call_gemini_api(prompt: str, system_instruction: str = None, model: str = "gemini-2.5-flash", api_key: str = None) -> str:
    """Calls Google Gemini API using native HTTP request (Zero external dependencies)."""
    if not api_key:
        conf = get_gemini_config()
        api_key = conf["api_key"]
        model = conf["model"]

    if not api_key:
        return None

    endpoint = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
    
    payload = {
        "contents": [
            {
                "parts": [{"text": prompt}]
            }
        ],
        "generationConfig": {
            "temperature": 0.4,
            "maxOutputTokens": 800
        }
    }

    if system_instruction:
        payload["systemInstruction"] = {
            "parts": [{"text": system_instruction}]
        }

    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        endpoint,
        data=data,
        headers={"Content-Type": "application/json"}
    )

    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            if resp.status == 200:
                result = json.loads(resp.read().decode("utf-8"))
                candidates = result.get("candidates", [])
                if candidates and "content" in candidates[0]:
                    parts = candidates[0]["content"].get("parts", [])
                    if parts and "text" in parts[0]:
                        return parts[0]["text"].strip()
    except Exception as e:
        print(f"[Gemini Service Error]: {e}")
        return None

    return None

def answer_support_query(ticket_id: str, user_name: str, user_role: str, subject: str, message: str, course_title: str = None) -> str:
    """Generates an immediate AI response for student/teacher chatbot queries."""
    conf = get_gemini_config()
    
    # Try calling live Gemini API if key is present
    if conf["api_key"] and conf["enabled"]:
        system_prompt = (
            "You are the official AI Academic Assistant for Nexus LMS / FL4School. "
            "You provide clear, accurate, friendly, and structured responses to students and faculty. "
            "Provide helpful answers, step-by-step guidance, or explanations. "
            "Remind them that their question has also been logged with the Department Administrator/Faculty for review."
        )
        user_prompt = (
            f"User: {user_name} ({user_role.capitalize()})\n"
            f"Course: {course_title or 'General Platform Inquiry'}\n"
            f"Topic: {subject}\n"
            f"Message: {message}\n\n"
            "Please provide a helpful, encouraging, and concise response."
        )
        ai_resp = call_gemini_api(user_prompt, system_instruction=system_prompt, model=conf["model"], api_key=conf["api_key"])
        if ai_resp:
            return ai_resp

    # Intelligent fallback when Gemini API key is pending or network is isolated
    if user_role == "student":
        return (
            f"Hello {user_name}! 🎓\n\n"
            f"Thank you for reaching out regarding '{subject}'. "
            f"I have registered your inquiry under Ticket #{ticket_id}.\n\n"
            f"Our system has forwarded this query to your Course Teacher and Department Administrator. "
            f"They have received an instant alert and will respond to you directly here.\n\n"
            f"Tip: If this is about coursework in '{course_title or 'your enrolled course'}', "
            f"review the module learning materials or lecture notes while faculty prepares an official response!"
        )
    else:
        return (
            f"Hello Prof. {user_name}! 📋\n\n"
            f"Your faculty query regarding '{subject}' has been registered as Ticket #{ticket_id}.\n\n"
            f"As requested, teacher queries are strictly confidential and visible ONLY to the Department Administrator. "
            f"The Administrator has been alerted on their command center and will review your request shortly."
        )

def test_gemini_connection(api_key: str, model: str = "gemini-2.5-flash") -> dict:
    """Tests Gemini API key validity."""
    if not api_key or not api_key.strip():
        return {"success": False, "error": "API Key is required."}

    test_prompt = "Hello! Please confirm this API key is active by responding with: 'Gemini AI connection verified successfully!'"
    res = call_gemini_api(test_prompt, model=model, api_key=api_key.strip())
    if res:
        return {"success": True, "message": res}
    return {"success": False, "error": "Failed to connect to Google Gemini API. Please check your API key."}
