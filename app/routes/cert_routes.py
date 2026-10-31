from fastapi import APIRouter, Request, HTTPException, Form, Depends
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from app.templates_config import templates
from app.database import (
    get_db,
    verify_certificate,
    get_certificate_by_id,
    issue_certificate,
    revoke_certificate,
    reissue_certificate,
    list_certificates,
    get_student_certificates
)
from app.auth import get_current_user
from typing import Optional

router = APIRouter()

# ===================================================================
# 1. PUBLIC CERTIFICATE VERIFICATION (NO LOGIN REQUIRED)
# ===================================================================

@router.get("/verify/{certificate_id}", response_class=HTMLResponse)
async def public_certificate_verification(request: Request, certificate_id: str):
    """
    Publicly verifies certificate authenticity by scanning QR code or direct link.
    No login required. Increments scan/access tracking counter.
    """
    cert = verify_certificate(certificate_id, increment_count=True)
    user = get_current_user(request)

    if not cert:
        return templates.TemplateResponse("certificate_verification.html", {
            "request": request,
            "user": user,
            "status": "invalid",
            "cert_id": certificate_id,
            "cert": None
        })

    status_val = cert.get("status", "verified")
    return templates.TemplateResponse("certificate_verification.html", {
        "request": request,
        "user": user,
        "status": status_val,
        "cert_id": certificate_id,
        "cert": cert
    })

# ===================================================================
# 2. PRINTABLE DIGITAL CERTIFICATE VIEW
# ===================================================================

@router.get("/certificate/{certificate_id}", response_class=HTMLResponse)
async def view_certificate(request: Request, certificate_id: str):
    """
    Renders high-resolution printable academic certificate of completion with embedded QR code.
    """
    cert = get_certificate_by_id(certificate_id)
    if not cert:
        return RedirectResponse(url=f"/verify/{certificate_id}", status_code=303)

    return templates.TemplateResponse("certificate_view.html", {
        "request": request,
        "cert": cert
    })

# ===================================================================
# 3. STUDENT COURSE CERTIFICATE RETRIEVAL
# ===================================================================

@router.get("/course/{course_id}/certificate")
async def student_course_certificate(request: Request, course_id: int):
    """
    Retrieves or generates the authentic certificate for an enrolled student.
    """
    user = get_current_user(request)
    if not user:
        return RedirectResponse(url="/login", status_code=303)

    # Issue or retrieve existing certificate
    try:
        cert = issue_certificate(student_id=user["id"], course_id=course_id)
        return RedirectResponse(url=f"/certificate/{cert['certificate_id']}", status_code=303)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

# ===================================================================
# 4. ADMIN CERTIFICATE MANAGEMENT API ENDPOINTS
# ===================================================================

def require_admin(request: Request):
    user = get_current_user(request)
    if not user or user.get("role") != "department_admin":
        raise HTTPException(status_code=403, detail="Administrative access required")
    return user

@router.get("/api/certificates")
async def get_certificates_api(
    request: Request,
    status: Optional[str] = None,
    search: Optional[str] = None
):
    """Lists all registered certificates with search and status filtering."""
    require_admin(request)
    certs = list_certificates(status=status, search=search)
    return JSONResponse({"status": "success", "count": len(certs), "data": certs})

@router.post("/api/certificates/issue")
async def issue_certificate_api(
    request: Request,
    student_id: int = Form(...),
    course_id: int = Form(...),
    completion_date: Optional[str] = Form(None),
    grade_score: Optional[float] = Form(100.0)
):
    """Admins can manually issue an authentic certificate to any student for a course."""
    admin = require_admin(request)
    try:
        cert = issue_certificate(
            student_id=student_id,
            course_id=course_id,
            admin_user_id=admin["id"],
            completion_date=completion_date,
            grade_score=grade_score
        )
        return JSONResponse({"status": "success", "message": "Certificate issued successfully", "data": cert})
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/api/certificates/revoke")
async def revoke_certificate_api(
    request: Request,
    certificate_id: str = Form(...),
    reason: Optional[str] = Form("Revoked by Administrator")
):
    """Admins can immediately revoke a certificate, invalidating future verification."""
    admin = require_admin(request)
    success = revoke_certificate(certificate_id=certificate_id, reason=reason, admin_user_id=admin["id"])
    if not success:
        raise HTTPException(status_code=404, detail="Certificate not found")
    return JSONResponse({"status": "success", "message": f"Certificate {certificate_id} has been revoked."})

@router.post("/api/certificates/reissue")
async def reissue_certificate_api(
    request: Request,
    certificate_id: str = Form(...)
):
    """Admins can reissue a certificate with a new unique ID while archiving previous record."""
    admin = require_admin(request)
    try:
        new_cert = reissue_certificate(old_certificate_id=certificate_id, admin_user_id=admin["id"])
        return JSONResponse({
            "status": "success",
            "message": f"Certificate reissued with new ID: {new_cert['certificate_id']}",
            "data": new_cert
        })
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
