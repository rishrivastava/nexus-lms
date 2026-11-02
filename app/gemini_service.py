import os
import json
import ssl
import urllib.request
import urllib.error
from typing import Optional, List, Dict, Any
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
    course_title: Optional[str] = None,
    course_subject: Optional[str] = None,
    module_title: Optional[str] = None,
    module_description: Optional[str] = None,
    department: Optional[str] = None
) -> dict:
    """Generates a module-dependent academic assessment quiz using Gemini AI or domain-specific curriculum engine."""
    conf = get_gemini_config()
    
    if conf["api_key"] and conf["enabled"]:
        system_prompt = (
            "You are an expert academic curriculum designer and assessment specialist for LEAD Group LMS. "
            "Your task is to generate a high-quality educational quiz in valid JSON without markdown code fences. "
            "IMPORTANT: Base the questions strictly on the specified module, course, subject, and topic! "
            "Do NOT generate foreign language or French questions unless the module or subject explicitly specifies a foreign language. "
            "If the subject is Test Prep, Science, Coding, Mathematics, History, or Business, all questions MUST test that specific subject and module. "
            "Format: {\"title\": \"...\", \"description\": \"...\", \"questions\": [{\"question_text\": \"...\", \"option_a\": \"...\", \"option_b\": \"...\", \"option_c\": \"...\", \"option_d\": \"...\", \"correct_option\": \"A\", \"explanation\": \"...\"}]}"
        )
        user_prompt = (
            f"Course: {course_title or 'Academic Course'}\n"
            f"Subject / Department: {course_subject or department or 'General Academic'}\n"
            f"Module Title: {module_title or 'Curriculum Module'}\n"
            f"Module Overview / Objectives: {module_description or topic}\n"
            f"Target Quiz Topic / Concept: {topic}\n"
            f"Difficulty Level: {difficulty}\n"
            f"Number of Questions: {num_questions}\n\n"
            "Generate questions testing concepts from this specific module and topic. "
            "Ensure each question has 4 distinct options (A, B, C, D), 1 valid correct_option (A, B, C, or D), and an instructive pedagogical explanation."
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

    # Module-dependent fallback generator tailored to requested subject, module, and topic
    return generate_fallback_quiz(
        topic=topic,
        num_questions=num_questions,
        difficulty=difficulty,
        course_title=course_title,
        course_subject=course_subject,
        module_title=module_title,
        module_description=module_description,
        department=department
    )

def generate_fallback_quiz(
    topic: str,
    num_questions: int = 5,
    difficulty: str = "Beginner",
    course_title: Optional[str] = None,
    course_subject: Optional[str] = None,
    module_title: Optional[str] = None,
    module_description: Optional[str] = None,
    department: Optional[str] = None
) -> dict:
    """Contextual, domain-specific question generator dynamically tailored to the module, course, and topic."""
    context_text = f"{topic} {module_title or ''} {module_description or ''} {course_subject or ''} {course_title or ''} {department or ''}".lower()
    
    # 1. French Language (strictly when specified)
    if "french" in context_text or "français" in context_text:
        base_pool = [
            ("Which French greeting means 'Good morning' or 'Hello'?", "Au revoir", "Bonjour", "Merci", "Bonne nuit", "B", "'Bonjour' is the daytime greeting in French."),
            ("How do you say 'Thank you very much' in French?", "De rien", "S'il vous plaît", "Merci beaucoup", "Enchanté", "C", "'Merci beaucoup' translates to 'Thank you very much'."),
            ("What does 'Comment vous appelez-vous ?' ask in English?", "Where do you live?", "What is your name?", "How old are you?", "How are you?", "B", "It is the formal phrase for 'What is your name?'."),
            ("Which verb means 'to be' in French?", "Avoir", "Faire", "Être", "Aller", "C", "'Être' is the fundamental French verb for 'to be'."),
            ("What is the feminine definite article in French?", "Le", "Les", "La", "Un", "C", "'La' is the singular feminine definite article in French."),
            ("How do you say 'Goodbye' in French?", "S'il vous plaît", "Au revoir", "Bonsoir", "Oui", "B", "'Au revoir' means 'Goodbye'.")
        ]

    # 2. Spanish Language (strictly when specified)
    elif "spanish" in context_text or "español" in context_text:
        base_pool = [
            ("What is the Spanish translation for 'Good morning'?", "Buenas noches", "Buenos días", "Buenas tardes", "Hola", "B", "'Buenos días' is used in the morning until noon."),
            ("How do you say 'Please' in Spanish?", "Gracias", "De nada", "Por favor", "Perdón", "C", "'Por favor' translates to 'Please'."),
            ("Which pronoun corresponds to 'We' in Spanish?", "Ellos", "Tú", "Nosotros", "Ustedes", "C", "'Nosotros' is the first person plural pronoun (we)."),
            ("What does the verb 'Comer' mean?", "To drink", "To eat", "To sleep", "To speak", "B", "'Comer' means 'to eat' in Spanish."),
            ("Which word means 'Water' in Spanish?", "Agua", "Fuego", "Tierra", "Aire", "A", "'Agua' translates to 'water' in Spanish.")
        ]

    # 3. German Language (strictly when specified)
    elif "german" in context_text or "deutsch" in context_text:
        base_pool = [
            ("What is the German word for 'Thank you'?", "Bitte", "Danke", "Guten Tag", "Hallo", "B", "'Danke' means 'Thank you' in German."),
            ("How do you say 'Good evening' in German?", "Guten Morgen", "Gute Nacht", "Guten Abend", "Auf Wiedersehen", "C", "'Guten Abend' is used in the evening."),
            ("What is the definite article for masculine nouns in nominative case?", "Die", "Das", "Der", "Den", "C", "'Der' is the masculine nominative article in German."),
            ("What does the verb 'Sprechen' mean?", "To write", "To speak", "To read", "To listen", "B", "'Sprechen' means 'to speak'.")
        ]

    # 4. Test Prep / Aptitude / Reasoning
    elif any(k in context_text for k in ["test prep", "aptitude", "reasoning", "verbal ability", "quantitative", "gre", "sat prep", "cat prep", "gmat", "logic", "general intelligence"]):
        base_pool = [
            ("If a train travels 360 km in 4 hours, what is its average speed in meters per second?", "25 m/s", "20 m/s", "30 m/s", "15 m/s", "A", "Speed = 360 km / 4 hr = 90 km/h. To convert to m/s, multiply by 5/18: 90 * (5/18) = 25 m/s."),
            ("Complete the logical series: 2, 6, 12, 20, 30, ?", "40", "42", "44", "48", "B", "The differences between successive terms are 4, 6, 8, 10, so next difference is 12: 30 + 12 = 42."),
            ("Identify the synonym of 'CANDID':", "Deceptive", "Frank", "Reserved", "Complex", "B", "'Candid' means truthful, straightforward, and frank."),
            ("A product was sold for $240 at a 20% profit on cost. What was the cost price?", "$180", "$200", "$210", "$220", "B", "Selling Price = Cost * 1.20 => Cost = 240 / 1.20 = $200."),
            ("Which word is an antonym of 'EPHEMERAL'?", "Transient", "Eternal", "Fleeting", "Fragile", "B", "'Ephemeral' means lasting for a short time; its antonym is 'eternal'."),
            ("In a group of 60 students, 35 play football and 30 play cricket. If 15 play both, how many play neither?", "5", "10", "15", "8", "B", "Total playing at least one = 35 + 30 - 15 = 50. Neither = 60 - 50 = 10.")
        ]

    # 5. Computer Science / Programming / Python / Tech
    elif any(k in context_text for k in ["python", "code", "programming", "database", "sql", "software", "algorithm", "data structure", "tech"]):
        base_pool = [
            ("What is the time complexity of searching an element in a balanced Binary Search Tree (BST)?", "O(1)", "O(log n)", "O(n)", "O(n log n)", "B", "A balanced BST has height log n, allowing binary search in O(log n) time."),
            ("In Python, which built-in data type is immutable?", "List", "Dictionary", "Tuple", "Set", "C", "Tuples cannot be altered after creation, making them immutable."),
            ("Which SQL clause is used to filter records based on group aggregate values?", "WHERE", "HAVING", "GROUP BY", "ORDER BY", "B", "'HAVING' filters aggregated result sets, whereas 'WHERE' filters rows before grouping."),
            ("What does the 'self' keyword represent in Python class methods?", "A reference to the class itself", "A reference to the current object instance", "A global execution scope", "A private variable", "B", "'self' points directly to the instance on which the method is called."),
            ("Which HTTP status code signifies that a requested resource was not found?", "400", "401", "403", "404", "D", "HTTP 404 indicates Not Found."),
            ("Which data structure operates on a Last-In, First-Out (LIFO) principle?", "Queue", "Stack", "Linked List", "Tree", "B", "A Stack pushes and pops items according to the LIFO discipline.")
        ]

    # 6. Mathematics / Algebra / Calculus
    elif any(k in context_text for k in ["math", "algebra", "calculus", "geometry", "trigonometry", "statistics"]):
        base_pool = [
            ("What is the derivative of f(x) = 3x^2 + 5x - 7 with respect to x?", "6x", "6x + 5", "3x + 5", "6x^2 + 5", "B", "Using the power rule: d/dx(3x^2) = 6x, d/dx(5x) = 5, and d/dx(-7) = 0, giving 6x + 5."),
            ("What is the solution to the equation 2x + 8 = 20?", "x = 4", "x = 6", "x = 8", "x = 12", "B", "2x = 20 - 8 = 12, so x = 6."),
            ("In a right-angled triangle, if legs are of length 6 and 8, what is the length of the hypotenuse?", "9", "10", "12", "14", "B", "By Pythagorean theorem: sqrt(6^2 + 8^2) = sqrt(36 + 64) = sqrt(100) = 10."),
            ("What is the probability of rolling an even number on a fair standard six-sided die?", "1/3", "1/2", "2/3", "1/6", "B", "The even outcomes are {2, 4, 6}, which is 3 out of 6 outcomes, simplifying to 1/2."),
            ("What is the value of log10(1000)?", "1", "2", "3", "10", "C", "10^3 = 1000, so log10(1000) = 3.")
        ]

    # 7. Science / Physics / Chemistry / Biology
    elif any(k in context_text for k in ["science", "physic", "chem", "biology", "force", "cell", "energy", "matter"]):
        base_pool = [
            ("According to Newton's Second Law of Motion, Force equals:", "Mass * Acceleration", "Mass / Velocity", "Work * Distance", "Power / Time", "A", "Newton's second law states that Force = mass * acceleration (F = ma)."),
            ("Which cellular organelle is recognized as the 'powerhouse of the cell'?", "Nucleus", "Ribosome", "Mitochondria", "Endoplasmic Reticulum", "C", "Mitochondria produce ATP, generating chemical energy for cellular functions."),
            ("What is the chemical formula for water?", "CO2", "H2O", "NaCl", "O2", "B", "Water is composed of two hydrogen atoms bonded to one oxygen atom (H2O)."),
            ("What is the pH level of pure neutral water at 25°C?", "5", "7", "9", "14", "B", "A pH of 7 represents a completely neutral solution."),
            ("What process do plants use to convert sunlight into chemical energy?", "Respiration", "Photosynthesis", "Fermentation", "Transpiration", "B", "Photosynthesis uses sunlight, water, and CO2 to create glucose and oxygen.")
        ]

    # 8. History / Social Studies / Civics
    elif any(k in context_text for k in ["history", "social", "civic", "geograph", "polity", "economics"]):
        base_pool = [
            ("In which year did the United Nations officially form?", "1919", "1945", "1950", "1939", "B", "The United Nations was chartered on October 24, 1945 following World War II."),
            ("Which document serves as the supreme law of a constitutional democracy?", "The Civil Code", "The Constitution", "Executive Orders", "Treaty of Versailles", "B", "The Constitution establishes the legal framework and supreme law of the state."),
            ("What is the primary economic indicator used to measure total economic output?", "Inflation Rate", "Gross Domestic Product (GDP)", "Consumer Price Index", "Interest Rate", "B", "GDP measures the monetary value of all finished goods and services produced within a country."),
            ("Which imaginary line divides the Earth into the Northern and Southern Hemispheres?", "Prime Meridian", "Equator", "Tropic of Cancer", "International Date Line", "B", "The Equator is at 0 degrees latitude and divides the Earth into North and South hemispheres.")
        ]

    # 9. General Academic Module / Subject (Default)
    else:
        m_name = module_title.strip() if module_title else topic.strip()
        base_pool = [
            (f"Which foundational concept is central to mastering '{m_name}'?", f"Core principles and analytical frameworks of {topic}", "Random memorization without context", "Unverified empirical assumptions", "Superficial skimming of terms", "A", f"Deep mastery of {m_name} requires understanding foundational principles and their structured application."),
            (f"In the context of '{topic}', what is the primary role of systematic evaluation?", "To identify knowledge gaps and reinforce understanding", "To assign arbitrary numerical grades", "To bypass prerequisite chapters", "To avoid critical problem solving", "A", "Systematic evaluation pinpoints comprehension gaps and consolidates core learning objectives."),
            (f"When applying principles from '{m_name}', what is the recommended methodology?", "Structured problem decomposition and practical synthesis", "Skipping fundamental definitions", "Ignoring error analysis", "Sole reliance on passive reading", "A", "Structured decomposition allows complex problems within the curriculum to be solved methodically."),
            (f"Which outcome represents the highest level of proficiency in '{topic}'?", "Synthesis and practical application in new scenarios", "Recall of isolated definitions only", "Passive lecture attendance", "Copying solved examples", "A", "Applying concepts effectively in real-world or novel contexts demonstrates true subject mastery."),
            (f"What is an essential prerequisite for advancing beyond '{m_name}'?", f"Consistent verification of fundamental {topic} concepts", "Rushing through advanced modules", "Eliminating revision cycles", "Avoiding practice questions", "A", f"Solidifying prerequisites in {m_name} ensures continuous academic progression.")
        ]

    selected = base_pool[:min(num_questions, len(base_pool))]
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
    if module_title:
        title = f"{module_title}: {topic.strip().title()}"

    return {
        "title": title,
        "description": f"Curriculum quiz covering {topic.strip()} under {module_title or 'Curriculum Module'} ({difficulty} level).",
        "questions": questions
    }
