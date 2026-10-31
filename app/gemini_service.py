import os
import json
import ssl
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

def call_gemini_api(prompt: str, system_instruction: str = None, model: str = "gemini-2.5-flash", api_key: str = None, max_tokens: int = 1200) -> str:
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
            "maxOutputTokens": max_tokens
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

    ssl_ctx = None
    try:
        ssl_ctx = ssl.create_default_context()
    except Exception:
        ssl_ctx = ssl._create_unverified_context()

    try:
        try:
            with urllib.request.urlopen(req, timeout=15, context=ssl_ctx) as resp:
                if resp.status == 200:
                    result = json.loads(resp.read().decode("utf-8"))
                    candidates = result.get("candidates", [])
                    if candidates and "content" in candidates[0]:
                        parts = candidates[0]["content"].get("parts", [])
                        if parts and "text" in parts[0]:
                            return parts[0]["text"].strip()
        except urllib.error.URLError as url_err:
            if "CERTIFICATE_VERIFY_FAILED" in str(url_err) or "certificate verify failed" in str(url_err):
                unverified_ctx = ssl._create_unverified_context()
                with urllib.request.urlopen(req, timeout=15, context=unverified_ctx) as resp:
                    if resp.status == 200:
                        result = json.loads(resp.read().decode("utf-8"))
                        candidates = result.get("candidates", [])
                        if candidates and "content" in candidates[0]:
                            parts = candidates[0]["content"].get("parts", [])
                            if parts and "text" in parts[0]:
                                return parts[0]["text"].strip()
            else:
                raise url_err
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
            "You are the official Mylo AI Academic Assistant for Nexus LMS / FL4School. "
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

    # Intelligent fallback when Mylo AI API key is pending or network is isolated
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
    """Tests Mylo AI / Gemini API key validity."""
    if not api_key or not api_key.strip():
        return {"success": False, "error": "API Key is required."}

    test_prompt = "Hello! Please confirm this API key is active by responding with: 'Mylo AI connection verified successfully!'"
    res = call_gemini_api(test_prompt, model=model, api_key=api_key.strip())
    if res:
        return {"success": True, "message": res}
    return {"success": False, "error": "Failed to connect to Mylo AI / Google API. Please check your API key."}

def explain_quiz_mistake(
    question_text: str,
    student_choice: str,
    student_choice_text: str,
    correct_choice: str,
    correct_choice_text: str,
    explanation: str = None,
    course_title: str = None
) -> str:
    """Provides a supportive, detailed AI pedagogical explanation of why the student's answer was incorrect."""
    conf = get_gemini_config()
    
    if conf["api_key"] and conf["enabled"]:
        system_prompt = (
            "You are an encouraging, expert Language Teacher and AI Tutor for Nexus LMS powered by Mylo AI. "
            "A student answered a quiz question incorrectly. "
            "In 2-3 warm, clear paragraphs: "
            "1. Explain what Option (" + student_choice + ") '" + student_choice_text + "' actually means and why it does not fit here. "
            "2. Explain why Option (" + correct_choice + ") '" + correct_choice_text + "' is the grammatically and culturally correct answer. "
            "3. Offer a memorable learning tip or pattern rule so the student can easily recall this in the future."
        )
        user_prompt = (
            f"Course / Subject: {course_title or 'Foreign Language Learning'}\n"
            f"Question: {question_text}\n"
            f"Student Selected: Option {student_choice} ({student_choice_text})\n"
            f"Correct Answer: Option {correct_choice} ({correct_choice_text})\n"
            f"Reference Notes: {explanation or 'None'}\n\n"
            "Provide your encouraging pedagogical explanation."
        )
        ai_resp = call_gemini_api(user_prompt, system_instruction=system_prompt, model=conf["model"], api_key=conf["api_key"])
        if ai_resp:
            return ai_resp

    # Fallback explanation when Mylo AI API is offline / unconfigured
    fallback = (
        f"**Why Option {student_choice} ('{student_choice_text}') is not the right fit:**\n"
        f"In this context, '{student_choice_text}' does not satisfy the grammatical requirement or definition asked in the question.\n\n"
        f"**Why Option {correct_choice} ('{correct_choice_text}') is correct:**\n"
        f"{explanation or f'Option {correct_choice} correctly fulfills the standard sentence structure and vocabulary rule.'}\n\n"
        f"💡 **Mylo AI Tutor Study Tip:** Write down '{question_text}' alongside '{correct_choice_text}' in your language journal and review it before your next practice session!"
    )
    return fallback
    return fallback

def generate_ai_quiz(
    topic: str,
    num_questions: int = 5,
    difficulty: str = "Beginner",
    course_title: str = None
) -> dict:
    """Generates an academic quiz using Gemini AI or structured language generator."""
    conf = get_gemini_config()
    
    if conf["api_key"] and conf["enabled"]:
        system_prompt = (
            "You are an expert Foreign Language Curriculum Designer for Nexus LMS. "
            "Generate a high-quality educational quiz in valid JSON without any markdown code fences. "
            "Format: {\"title\": \"...\", \"description\": \"...\", \"questions\": [{\"question_text\": \"...\", \"option_a\": \"...\", \"option_b\": \"...\", \"option_c\": \"...\", \"option_d\": \"...\", \"correct_option\": \"A\", \"explanation\": \"...\"}]}"
        )
        user_prompt = (
            f"Course: {course_title or 'Foreign Language'}\n"
            f"Topic: {topic}\n"
            f"Difficulty Level: {difficulty}\n"
            f"Number of Questions: {num_questions}\n\n"
            "Ensure every question has 4 distinct options (A, B, C, D), a valid correct_option, and an instructive explanation."
        )
        raw_resp = call_gemini_api(user_prompt, system_instruction=system_prompt, model=conf["model"], api_key=conf["api_key"], max_tokens=2000)
        if raw_resp:
            cleaned = raw_resp.strip()
            if cleaned.startswith("```json"):
                cleaned = cleaned[7:]
            if cleaned.startswith("```"):
                cleaned = cleaned[3:]
            if cleaned.endswith("```"):
                cleaned = cleaned[:-3]
            try:
                data = json.loads(cleaned.strip())
                if "questions" in data and len(data["questions"]) > 0:
                    return data
            except Exception as e:
                print(f"[Gemini Quiz JSON Parse Error]: {e}")

    # Fallback generator tailored to requested topic
    return generate_fallback_quiz(topic, num_questions, difficulty)

def generate_fallback_quiz(topic: str, num_questions: int = 5, difficulty: str = "Beginner") -> dict:
    """Contextual question generator for language learning topics."""
    t_lower = topic.lower()
    
    if "spanish" in t_lower or "es" in t_lower:
        base_pool = [
            ("What is the Spanish translation for 'Good morning'?", "Buenas noches", "Buenos días", "Buenas tardes", "Hola", "B", "'Buenos días' is used in the morning until noon."),
            ("How do you say 'Please' in Spanish?", "Gracias", "De nada", "Por favor", "Perdón", "C", "'Por favor' translates to 'Please'."),
            ("Which pronoun corresponds to 'We' in Spanish?", "Ellos", "Tú", "Nosotros", "Ustedes", "C", "'Nosotros' is the first person plural pronoun (we)."),
            ("What does the verb 'Comer' mean?", "To drink", "To eat", "To sleep", "To speak", "B", "'Comer' means 'to eat' in Spanish."),
            ("Which word means 'Water' in Spanish?", "Agua", "Fuego", "Tierra", "Aire", "A", "'Agua' translates to 'water' in Spanish."),
            ("How do you ask 'Where is the bathroom?' in Spanish?", "¿Cómo estás?", "¿Dónde está el baño?", "¿Cuánto cuesta?", "¿Qué hora es?", "B", "'¿Dónde está el baño?' is the standard way to ask for the restroom."),
            ("What is the plural of 'el libro' (the book)?", "los libros", "las libros", "el libros", "los librose", "A", "Masculine nouns ending in a vowel take '-s' and article 'los'."),
            ("Which verb is used for permanent characteristics in Spanish?", "Estar", "Ser", "Tener", "Hacer", "B", "'Ser' is used for essential qualities, origin, and identity.")
        ]
    elif "german" in t_lower or "de" in t_lower:
        base_pool = [
            ("What is the German word for 'Thank you'?", "Bitte", "Danke", "Guten Tag", "Hallo", "B", "'Danke' means 'Thank you' in German."),
            ("How do you say 'Good evening' in German?", "Guten Morgen", "Gute Nacht", "Guten Abend", "Auf Wiedersehen", "C", "'Guten Abend' is used in the evening."),
            ("What is the definite article for masculine nouns in nominative case?", "Die", "Das", "Der", "Den", "C", "'Der' is the masculine nominative article in German."),
            ("What does the verb 'Sprechen' mean?", "To write", "To speak", "To read", "To listen", "B", "'Sprechen' means 'to speak'."),
            ("Which number is 'Zehn' in English?", "Five", "Ten", "Twelve", "Twenty", "B", "'Zehn' is the number 10 in German.")
        ]
    elif "verb" in t_lower or "grammar" in t_lower:
        base_pool = [
            ("Which tense is typically used to express habitual actions in the present?", "Present Simple", "Past Perfect", "Future Continuous", "Subjunctive", "A", "Present Simple describes routines, regular habits, and general facts."),
            ("What is an infinitive verb?", "A verb ending in -ed", "The base form of a verb preceded by 'to'", "A conjugated verb", "A past participle", "B", "The infinitive is the unconjugated base form of a verb."),
            ("What is an irregular verb?", "A verb that always takes -ed", "A verb whose conjugation does not follow regular rules", "A verb with no past tense", "An auxiliary verb", "B", "Irregular verbs have unique conjugation patterns."),
            ("Which form indicates a command or instruction?", "Indicative", "Conditional", "Imperative", "Interrogative", "C", "The imperative mood expresses direct commands and requests."),
            ("What is an auxiliary verb?", "A verb used with a main verb to express tense or mood", "A noun acting like a verb", "An adjective", "A preposition", "A", "Auxiliary verbs like 'be', 'have', and 'do' help form complex tenses.")
        ]
    else: # French / General Language
        base_pool = [
            ("Which French greeting means 'Good morning' or 'Hello'?", "Au revoir", "Bonjour", "Merci", "Bonne nuit", "B", "'Bonjour' is the daytime greeting in French."),
            ("How do you say 'Thank you very much' in French?", "De rien", "S'il vous plaît", "Merci beaucoup", "Enchanté", "C", "'Merci beaucoup' translates to 'Thank you very much'."),
            ("What does 'Comment vous appelez-vous ?' ask in English?", "Where do you live?", "What is your name?", "How old are you?", "How are you?", "B", "It is the formal phrase for 'What is your name?'."),
            ("Which verb means 'to be' in French?", "Avoir", "Faire", "Être", "Aller", "C", "'Être' is the fundamental French verb for 'to be'."),
            ("What is the feminine definite article in French?", "Le", "Les", "La", "Un", "C", "'La' is the singular feminine definite article in French."),
            ("How do you say 'Goodbye' in French?", "S'il vous plaît", "Au revoir", "Bonsoir", "Oui", "B", "'Au revoir' means 'Goodbye'."),
            ("What does 'Je voudrais' express?", "I was", "I would like", "I am going", "I have", "B", "'Je voudrais' is the polite conditional for 'I would like'.")
        ]
        
    selected = base_pool[:min(num_questions, len(base_pool))]
    # If more requested than in pool, duplicate with variant suffixes
    while len(selected) < num_questions:
        orig = base_pool[len(selected) % len(base_pool)]
        selected.append((f"{orig[0]} (Review)", orig[1], orig[2], orig[3], orig[4], orig[5], orig[6]))

    questions = []
    for q in selected:
        questions.append({
            "question_text": q[0],
            "option_a": q[1],
            "option_b": q[2],
            "option_c": q[3],
            "option_d": q[4],
            "correct_option": q[5],
            "explanation": q[6]
        })

    title = f"{topic.strip().title()} Assessment"
    return {
        "title": title,
        "description": f"Curriculum quiz covering {topic.strip()} ({difficulty} level).",
        "questions": questions
    }
