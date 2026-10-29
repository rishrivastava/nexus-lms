import os
from fastapi.templating import Jinja2Templates
from app.database import get_system_settings

TEMPLATES_DIR = os.path.join(os.path.dirname(__file__), "templates")
templates = Jinja2Templates(directory=TEMPLATES_DIR)

# Expose branding dynamically to every Jinja2 template
templates.env.globals["get_branding"] = get_system_settings
