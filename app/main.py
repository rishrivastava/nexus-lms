import os
from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from app.database import init_db, UPLOAD_DIR
from app.seed import seed_data
from app.auth import get_current_user

from app.routes.auth_routes import router as auth_router
from app.routes.student_routes import router as student_router
from app.routes.teacher_routes import router as teacher_router
from app.routes.dept_routes import router as dept_router
from app.routes.api_routes import router as api_router

app = FastAPI(title="Nexus LMS", description="Departmental Learning Management System")

# Ensure static directories exist
STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")
os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(STATIC_DIR, exist_ok=True)

# Mount static files
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

# Include Routers
app.include_router(auth_router)
app.include_router(student_router)
app.include_router(teacher_router)
app.include_router(dept_router)
app.include_router(api_router)

@app.on_event("startup")
async def on_startup():
    init_db()
    seed_data()

@app.get("/")
async def root(request: Request):
    user = get_current_user(request)
    if not user:
        return RedirectResponse(url="/login", status_code=303)
        
    if user["must_change_password"]:
        return RedirectResponse(url="/setup-account", status_code=303)
        
    if user["role"] == "teacher":
        return RedirectResponse(url="/teacher", status_code=303)
    elif user["role"] == "department_admin":
        return RedirectResponse(url="/department", status_code=303)
    else:
        return RedirectResponse(url="/student", status_code=303)
