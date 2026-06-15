from fastapi import FastAPI, HTTPException, UploadFile, File, Form, Depends
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, RedirectResponse
from pydantic import BaseModel
from typing import Optional, List
import os
import shutil
from datetime import datetime
import socket
import random
import time
import re
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

import database as db

# Initialize database
db.init_db()

app = FastAPI(title="Family Tree Builder API")

# Directories
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MEDIA_DIR = os.path.join(BASE_DIR, "media")
STATIC_DIR = os.path.join(BASE_DIR, "static")

# Create folders if not present
os.makedirs(MEDIA_DIR, exist_ok=True)
os.makedirs(STATIC_DIR, exist_ok=True)

# Mount media static files (served at /media/filename)
app.mount("/media", StaticFiles(directory=MEDIA_DIR), name="media")

# Load .env file manually to support zero-dependency environments
def load_env():
    env_path = os.path.join(BASE_DIR, ".env")
    if os.path.exists(env_path):
        with open(env_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" in line:
                    key, val = line.split("=", 1)
                    os.environ[key.strip()] = val.strip().strip('"').strip("'")

load_env()

def is_online() -> bool:
    try:
        socket.gethostbyname("google.com")
        return True
    except socket.gaierror:
        return False

def verify_email_dns(email: str) -> bool:
    email = email.strip()
    if "@" not in email:
        return False
    domain = email.split("@")[-1].strip()
    if not is_online():
        print(f"⚠️ Offline: Skipping DNS check for domain {domain}")
        return True
    try:
        socket.gethostbyname(domain)
        return True
    except socket.gaierror:
        return False

# Pydantic request models
class TreeCreateRequest(BaseModel):
    tree_name: str
    password: str
    creator_name: str
    creator_email: str

class TreeEnterRequest(BaseModel):
    tree_name: str
    password: str
    contributor_name: str
    contributor_email: str

class TreeSettingsRequest(BaseModel):
    new_name: str
    new_password: Optional[str] = None
    contributor_id: int
    tree_type: str = 'family' # Added

class ImportTreeRequest(BaseModel):
    tree_name: str
    password: str
    creator_name: str
    creator_email: str
    data: dict
    tree_type: str = 'family' # Added

class PersonCreateRequest(BaseModel):
    tree_id: int
    contributor_id: int
    first_name: str
    surname_now: Optional[str] = ""
    surname_at_birth: Optional[str] = ""
    gender: Optional[str] = ""
    birth_date: Optional[str] = ""

class PersonUpdateRequest(BaseModel):
    tree_id: int
    contributor_id: int
    first_name: str
    surname_now: Optional[str] = ""
    surname_at_birth: Optional[str] = ""
    gender: Optional[str] = ""
    birth_date: Optional[str] = ""
    deceased: int = 0
    death_date: Optional[str] = ""
    country_of_birth: Optional[str] = ""
    profession: Optional[str] = ""
    phone: Optional[str] = ""
    email: Optional[str] = ""
    address: Optional[str] = ""
    biography: Optional[str] = ""
    interesting_facts: Optional[str] = ""
    updated_at_client: Optional[str] = None # Added for conflict validation

class LinkRelationshipRequest(BaseModel):
    tree_id: int
    contributor_id: int
    person1_id: int
    person2_id: int
    relationship_type: str
    relationship_status: Optional[str] = 'active'
    relationship_subtype: Optional[str] = 'biological'

class UpdateRelationshipStatusRequest(BaseModel):
    tree_id: int
    contributor_id: int
    person1_id: int
    person2_id: int
    relationship_status: str

class MergePersonsRequest(BaseModel):
    tree_id: int
    contributor_id: int
    target_id: int
    duplicate_id: int

class AddParentsRequest(BaseModel):
    tree_id: int
    contributor_id: int
    child_id: int
    father_name: str
    mother_name: str

class AddSiblingRequest(BaseModel):
    tree_id: int
    contributor_id: int
    person_id: int
    sibling_name: str
    sibling_gender: str

class AddPartnerRequest(BaseModel):
    tree_id: int
    contributor_id: int
    person_id: int
    partner_name: str
    partner_gender: str

class AddChildRequest(BaseModel):
    tree_id: int
    contributor_id: int
    parent1_id: int
    child_name: str
    child_gender: str
    parent2_id: Optional[int] = None

class TreeSettingsRequest(BaseModel):
    new_name: str
    new_password: Optional[str] = None
    contributor_id: int
    tree_type: str = 'family'
    description: Optional[str] = None

class DangerZoneRequest(BaseModel):
    contributor_id: int

class TransferOwnershipRequest(BaseModel):
    contributor_id: int
    new_owner_email: str

class ImportTreeRequest(BaseModel):
    tree_name: str
    password: str
    creator_name: str
    creator_email: str
    data: dict
    tree_type: str = 'family'

class DeletePhotoRequest(BaseModel):
    tree_id: int
    contributor_id: int

class CheckEmailResponse(BaseModel):
    exists: bool
    name: Optional[str] = None

class OTPRequest(BaseModel):
    email: str
    password: str
    name: Optional[str] = None

class OTPVerifyRequest(BaseModel):
    email: str
    password: str
    otp_code: str
    name: Optional[str] = None

# API Endpoint routes

@app.get("/api/auth/check-email", response_model=CheckEmailResponse)
def api_check_email(email: str):
    conn = db.get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM Contributors WHERE email = ?", (email.strip().lower(),))
    row = cursor.fetchone()
    conn.close()
    if row:
        return CheckEmailResponse(exists=True, name=row["name"])
    return CheckEmailResponse(exists=False, name=None)

@app.post("/api/auth/request-otp")
def api_request_otp(req: OTPRequest):
    load_env()
    email = req.email.strip().lower()
    if not email:
        raise HTTPException(status_code=400, detail="Email is required.")
    
    # Format check
    email_regex = r"^[^\s@]+@[^\s@]+\.[^\s@]+$"
    if not re.match(email_regex, email):
        raise HTTPException(status_code=400, detail="Invalid email address format.")
    
    # DNS lookup
    if not verify_email_dns(email):
        raise HTTPException(status_code=400, detail="The email domain is invalid or cannot be resolved.")
        
    # Check account existence
    user = db.get_contributor_by_email(email)
    
    # Signup attempt (name is provided)
    if req.name:
        name_val = req.name.strip()
        if not name_val:
            raise HTTPException(status_code=400, detail="Name is required for signup.")
        if user and user["password_hash"]:
            raise HTTPException(status_code=400, detail="Account already exists. Please sign in instead.")
    else:
        # Login attempt
        if not user or not user["password_hash"]:
            raise HTTPException(status_code=400, detail="Account does not exist. Please sign up instead.")
        # Verify password
        if db.hash_password(req.password) != user["password_hash"]:
            raise HTTPException(status_code=400, detail="Invalid password.")
            
    # Generate 6-digit OTP
    otp = str(random.randint(100000, 999999))
    
    # Expiry 5 minutes from now
    expires_at = (time.time() + 300)
    expires_at_iso = datetime.fromtimestamp(expires_at).isoformat()
    db.save_otp(email, otp, expires_at_iso)
    
    # Print OTP code inside a prominent console box
    border = "*" * 50
    print(f"\n{border}")
    print(f"* LOGIN / SIGNUP OTP CODE FOR: {email}")
    print(f"* CODE: {otp}")
    print(f"{border}\n")
    
    # Send email (hybrid)
    email_sent = False
    
    # 1. Resend API
    resend_api_key = os.environ.get("RESEND_API_KEY")
    email_from = os.environ.get("EMAIL_FROM", "Family Tree <noreply@yourdomain.com>")
    if resend_api_key:
        try:
            import requests
            res = requests.post(
                "https://api.resend.com/emails",
                headers={
                    "Authorization": f"Bearer {resend_api_key}",
                    "Content-Type": "application/json"
                },
                json={
                    "from": email_from,
                    "to": [email],
                    "subject": "Your Family Tree Verification Code",
                    "html": f"<h2>Your OTP is {otp}</h2><p>This code will expire in 5 minutes.</p>"
                },
                timeout=10
            )
            if res.status_code == 200 or res.status_code == 201:
                email_sent = True
            else:
                print(f"Resend API returned non-success status code {res.status_code}: {res.text}")
        except Exception as e:
            print(f"Failed to send email via Resend API: {e}")
            
    # 2. Gmail SMTP / Generic SMTP
    smtp_server = os.environ.get("SMTP_SERVER")
    smtp_password = os.environ.get("SMTP_PASSWORD")
    if not email_sent and smtp_server and smtp_password:
        smtp_port = int(os.environ.get("SMTP_PORT", "465"))
        smtp_user = os.environ.get("SMTP_USER", email_from)
        try:
            msg = MIMEText(f"Your OTP code is: {otp}\nThis code will expire in 5 minutes.")
            msg["Subject"] = "Family Tree Verification Code"
            msg["From"] = email_from
            msg["To"] = email
            
            if smtp_port == 465:
                server = smtplib.SMTP_SSL(smtp_server, smtp_port)
            else:
                server = smtplib.SMTP(smtp_server, smtp_port)
                server.starttls()
                
            server.login(smtp_user, smtp_password)
            server.send_message(msg)
            server.quit()
            email_sent = True
        except Exception as e:
            print(f"Failed to send email via SMTP: {e}")
    return {
        "message": "OTP verification code sent directly to your email." if email_sent else "OTP code printed to server logs.",
        "dev_otp": None if email_sent else otp
    }

@app.post("/api/auth/verify-otp")
def api_verify_otp(req: OTPVerifyRequest):
    email = req.email.strip().lower()
    otp_code = req.otp_code.strip()
    
    if not email or not otp_code:
        raise HTTPException(status_code=400, detail="Email and OTP code are required.")
        
    # Verify OTP
    if not db.verify_otp(email, otp_code):
        raise HTTPException(status_code=400, detail="Invalid or expired verification code.")
        
    # Hash password
    pw_hash = db.hash_password(req.password)
    
    # Determine signup vs login
    # If name is provided, register/update contributor details
    if req.name:
        name_val = req.name.strip()
        contributor_id = db.register_contributor_with_password(name_val, email, pw_hash)
        contributor_name = name_val
    else:
        # Login
        user = db.get_contributor_by_email(email)
        if not user:
            raise HTTPException(status_code=400, detail="Account does not exist.")
        # Ensure password hash is set
        if not user["password_hash"]:
            db.register_contributor_with_password(user["name"], email, pw_hash)
        contributor_id = user["id"]
        contributor_name = user["name"]
        
    return {
        "contributor_id": contributor_id,
        "contributor_name": contributor_name,
        "contributor_email": email
    }

@app.post("/api/trees/create")
def api_create_tree(req: TreeCreateRequest):
    email = req.creator_email.strip()
    if not email:
        raise HTTPException(status_code=400, detail="Email is required.")
        
    # Email regex validation (Level 1 format check)
    email_regex = r"^[^\s@]+@[^\s@]+\.[^\s@]+$"
    if not re.match(email_regex, email):
        raise HTTPException(status_code=400, detail="Invalid email address format.")
    
    # DNS Domain existence check (Level 2)
    if not verify_email_dns(email):
        raise HTTPException(status_code=400, detail="The email domain is invalid or cannot be resolved.")

    try:
        res = db.create_tree(req.tree_name, req.password, req.creator_name, req.creator_email)
        # Create first default person node for the creator
        pid = db.add_person(
            res["tree_id"], res["contributor_id"],
            first_name=req.creator_name,
            email=req.creator_email
        )
        db.save_snapshot(res["tree_id"], res["contributor_id"], "Create Tree")
        return {
            "tree_id": res["tree_id"],
            "tree_name": req.tree_name,
            "contributor_id": res["contributor_id"],
            "contributor_name": req.creator_name,
            "contributor_email": req.creator_email,
            "selected_person_id": pid
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail="A family tree with this name already exists.")

@app.post("/api/trees/enter")
def api_enter_tree(req: TreeEnterRequest):
    email = req.contributor_email.strip()
    if not email:
        raise HTTPException(status_code=400, detail="Email is required.")
        
    # Email regex validation (Level 1 format check)
    email_regex = r"^[^\s@]+@[^\s@]+\.[^\s@]+$"
    if not re.match(email_regex, email):
        raise HTTPException(status_code=400, detail="Invalid email address format.")
    
    # DNS Domain existence check (Level 2)
    if not verify_email_dns(email):
        raise HTTPException(status_code=400, detail="The email domain is invalid or cannot be resolved.")

    # Check if contributor email already exists for Welcome Back rule
    conn = db.get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM Contributors WHERE email = ?", (req.contributor_email.strip(),))
    existing = cursor.fetchone()
    conn.close()
    
    res = db.enter_tree(req.tree_name, req.password, req.contributor_name, req.contributor_email)
    if not res:
        raise HTTPException(status_code=401, detail="Invalid Tree Name or Password.")
    
    welcome_msg = f"Welcome back contributor {existing['name']}!" if existing else f"Welcome to the '{req.tree_name}' tree, {req.contributor_name}!"
    
    return {
        "tree_id": res["tree_id"],
        "tree_name": req.tree_name,
        "contributor_id": res["contributor_id"],
        "contributor_name": req.contributor_name,
        "contributor_email": req.contributor_email,
        "message": welcome_msg
    }

@app.get("/api/trees/my-trees")
def api_get_my_trees(email: str):
    return db.get_contributor_trees(email)

@app.get("/api/trees/{tree_id}/stats")
def api_get_tree_stats(tree_id: int):
    return db.get_tree_stats(tree_id)

@app.put("/api/trees/{tree_id}/settings")
def api_update_settings(tree_id: int, req: TreeSettingsRequest):
    try:
        db.update_tree_settings(tree_id, req.new_name, req.new_password, req.tree_type, req.description)
        db.log_change(tree_id, req.contributor_id, None, "Settings Change", f"Modified tree details. Name: {req.new_name}, Type: {req.tree_type}")
        db.save_snapshot(tree_id, req.contributor_id, "Update Settings")
        return {"message": "Settings updated"}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.delete("/api/trees/{tree_id}")
def api_delete_tree(tree_id: int, contributor_id: int):
    conn = db.get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT created_by, tree_name FROM FamilyTrees WHERE id = ?", (tree_id,))
    row = cursor.fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="Family tree not found.")
    if row["created_by"] != contributor_id:
        conn.close()
        raise HTTPException(status_code=403, detail="Only the owner of the tree can delete it.")
    conn.close()
    
    db.delete_family_tree(tree_id)
    return {"message": f"Family tree '{row['tree_name']}' has been deleted successfully."}

@app.post("/api/trees/{tree_id}/clear-data")
def api_clear_tree_data(tree_id: int, req: DangerZoneRequest):
    conn = db.get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT created_by FROM FamilyTrees WHERE id = ?", (tree_id,))
    row = cursor.fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="Family tree not found.")
    if row["created_by"] != req.contributor_id:
        conn.close()
        raise HTTPException(status_code=403, detail="Only the owner of the tree can clear all data.")
    conn.close()
    
    db.clear_family_tree_data(tree_id)
    db.log_change(tree_id, req.contributor_id, None, "Clear Data", "Cleared all person and relationship records in the tree.")
    db.save_snapshot(tree_id, req.contributor_id, "Clear Tree Data")
    return {"message": "All family tree person and relationship records have been cleared successfully."}

@app.post("/api/trees/{tree_id}/transfer-ownership")
def api_transfer_ownership(tree_id: int, req: TransferOwnershipRequest):
    conn = db.get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT created_by FROM FamilyTrees WHERE id = ?", (tree_id,))
    row = cursor.fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="Family tree not found.")
    if row["created_by"] != req.contributor_id:
        conn.close()
        raise HTTPException(status_code=403, detail="Only the owner of the tree can transfer ownership.")
    conn.close()
    
    try:
        db.transfer_tree_ownership(tree_id, req.new_owner_email)
        db.log_change(tree_id, req.contributor_id, None, "Transfer Ownership", f"Transferred tree ownership to {req.new_owner_email}")
        return {"message": f"Tree ownership has been transferred to '{req.new_owner_email}' successfully."}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.get("/api/trees/{tree_id}/export")
def api_export_tree(tree_id: int):
    return db.export_tree_to_dict(tree_id)

@app.post("/api/trees/import")
def api_import_tree(req: ImportTreeRequest):
    try:
        new_id = db.import_tree_from_dict(
            req.tree_name, req.password, req.data,
            req.creator_email, req.creator_name,
            req.tree_type
        )
        # Fetch the contributor_id for snapshot logging
        conn = db.get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT contributor_id FROM TreeContributors WHERE tree_id = ? LIMIT 1", (new_id,))
        contrib_row = cursor.fetchone()
        contrib_id = contrib_row["contributor_id"] if contrib_row else 1
        conn.close()
        
        # Save initial snapshot
        db.save_snapshot(new_id, contrib_id, "Import Tree")
        
        # Get one imported member to select by default
        active_p = db.get_all_active_persons(new_id)
        pid = active_p[0]["id"] if active_p else None
        return {
            "tree_id": new_id,
            "tree_name": req.tree_name,
            "selected_person_id": pid,
            "message": "Tree imported successfully!"
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

# Person operations

@app.get("/api/trees/{tree_id}/persons")
def api_get_persons(tree_id: int, search: Optional[str] = None):
    # Support legacy trees or new entries with an initial snapshot
    db.ensure_initial_snapshot(tree_id)
    if search and search.strip():
        return db.search_persons(tree_id, search.strip())
    return db.get_all_active_persons(tree_id)

@app.get("/api/persons/{person_id}")
def api_get_person_details(person_id: int):
    p = db.get_person(person_id)
    if not p:
        raise HTTPException(status_code=404, detail="Person not found")
    # Resolve local media system paths to absolute web URLs
    res = dict(p)
    if res.get("photo_path"):
        res["photo_url"] = "/media/" + os.path.basename(res["photo_path"])
    else:
        res["photo_url"] = None
    return res

@app.post("/api/persons")
def api_create_person(req: PersonCreateRequest):
    pid = db.add_person(
        req.tree_id, req.contributor_id,
        first_name=req.first_name,
        surname_now=req.surname_now,
        surname_at_birth=req.surname_at_birth,
        gender=req.gender,
        birth_date=req.birth_date
    )
    db.save_snapshot(req.tree_id, req.contributor_id, f"Add Person: {req.first_name}")
    return {"person_id": pid}

@app.put("/api/persons/{person_id}")
def api_update_person(person_id: int, req: PersonUpdateRequest):
    updates = req.dict(exclude={"tree_id", "contributor_id", "updated_at_client"})
    try:
        db.update_person(req.tree_id, req.contributor_id, person_id, updates, req.updated_at_client)
        db.save_snapshot(req.tree_id, req.contributor_id, f"Update Person: {req.first_name}")
        return {"message": "Person updated successfully"}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.delete("/api/trees/{tree_id}/persons/{person_id}")
def api_delete_person(tree_id: int, person_id: int, contributor_id: int):
    p = db.get_person(person_id)
    p_name = f"{p['first_name']} {p['surname_now'] or ''}".strip() if p else "Person"
    success = db.delete_person(tree_id, contributor_id, person_id)
    if not success:
        raise HTTPException(status_code=409, detail="Deleting this person is not possible as it would result in a split in the tree.")
    db.save_snapshot(tree_id, contributor_id, f"Delete Person: {p_name}")
    return {"message": "Person soft-deleted successfully"}

# Photo upload

@app.post("/api/persons/{person_id}/photo")
def api_upload_photo(
    person_id: int,
    tree_id: int = Form(...),
    contributor_id: int = Form(...),
    file: UploadFile = File(...)
):
    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in [".png", ".jpg", ".jpeg"]:
        raise HTTPException(status_code=400, detail="Only JPG, JPEG, and PNG images are supported.")
        
    save_name = f"person_{person_id}_{int(datetime.now().timestamp())}{ext}"
    save_path = os.path.join(MEDIA_DIR, save_name)
    
    with open(save_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
        
    db.update_person(tree_id, contributor_id, person_id, {"photo_path": save_path})
    p = db.get_person(person_id)
    p_name = f"{p['first_name']} {p['surname_now'] or ''}".strip() if p else "Person"
    db.save_snapshot(tree_id, contributor_id, f"Upload Photo for {p_name}")
    
    return {"photo_url": f"/media/{save_name}"}

@app.delete("/api/persons/{person_id}/photo")
def api_delete_photo(person_id: int, req: DeletePhotoRequest):
    # Retrieve the person to check if they exist and get current photo path
    p = db.get_person(person_id)
    if not p:
        raise HTTPException(status_code=404, detail="Person not found")
    
    photo_path = p.get("photo_path")
    if photo_path and os.path.exists(photo_path):
        try:
            os.remove(photo_path)
        except Exception:
            pass # Ignore file system errors if the file is already gone or locked
            
    # Update person's photo_path to NULL in the database
    db.update_person(req.tree_id, req.contributor_id, person_id, {"photo_path": None})
    p_name = f"{p['first_name']} {p['surname_now'] or ''}".strip() if p else "Person"
    db.save_snapshot(req.tree_id, req.contributor_id, f"Delete Photo for {p_name}")
    return {"message": "Profile photo deleted successfully"}

# Relationships

@app.get("/api/trees/{tree_id}/relationships")
def api_get_relationships(tree_id: int):
    return db.get_relationships(tree_id)

@app.post("/api/relationships/parents")
def api_add_parents(req: AddParentsRequest):
    f_id, m_id = db.add_parents(req.tree_id, req.contributor_id, req.child_id, req.father_name, req.mother_name)
    child = db.get_person(req.child_id)
    c_name = child["first_name"] if child else "Child"
    db.save_snapshot(req.tree_id, req.contributor_id, f"Add Parents for {c_name}")
    return {"father_id": f_id, "mother_id": m_id}

@app.post("/api/relationships/sibling")
def api_add_sibling(req: AddSiblingRequest):
    sid = db.add_sibling(req.tree_id, req.contributor_id, req.person_id, req.sibling_name, req.sibling_gender)
    person = db.get_person(req.person_id)
    p_name = person["first_name"] if person else "Person"
    db.save_snapshot(req.tree_id, req.contributor_id, f"Add Sibling for {p_name}")
    return {"sibling_id": sid}

@app.post("/api/relationships/partner")
def api_add_partner(req: AddPartnerRequest):
    pid = db.add_partner(req.tree_id, req.contributor_id, req.person_id, req.partner_name, req.partner_gender)
    person = db.get_person(req.person_id)
    p_name = person["first_name"] if person else "Person"
    db.save_snapshot(req.tree_id, req.contributor_id, f"Add Partner for {p_name}")
    return {"partner_id": pid}

@app.post("/api/relationships/child")
def api_add_child(req: AddChildRequest):
    cid = db.add_child(
        req.tree_id, req.contributor_id,
        parent1_id=req.parent1_id,
        child_name=req.child_name,
        child_gender=req.child_gender,
        parent2_id=req.parent2_id
    )
    parent1 = db.get_person(req.parent1_id)
    p1_name = parent1["first_name"] if parent1 else "Parent"
    db.save_snapshot(req.tree_id, req.contributor_id, f"Add Child for {p1_name}")
    return {"child_id": cid}

@app.post("/api/relationships/link")
def api_link_relationship(req: LinkRelationshipRequest):
    try:
        db.create_relationship(
            req.tree_id, req.contributor_id,
            req.person1_id, req.person2_id,
            req.relationship_type,
            req.relationship_status,
            req.relationship_subtype
        )
        p1 = db.get_person(req.person1_id)
        p2 = db.get_person(req.person2_id)
        p1_name = p1["first_name"] if p1 else "Person 1"
        p2_name = p2["first_name"] if p2 else "Person 2"
        db.save_snapshot(req.tree_id, req.contributor_id, f"Link {req.relationship_type}: {p1_name} & {p2_name}")
        return {"message": "Relationship linked successfully"}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.put("/api/relationships/status")
def api_update_relationship_status(req: UpdateRelationshipStatusRequest):
    try:
        db.update_relationship_status(
            req.tree_id, req.contributor_id,
            req.person1_id, req.person2_id,
            req.relationship_status
        )
        p1 = db.get_person(req.person1_id)
        p2 = db.get_person(req.person2_id)
        p1_name = p1["first_name"] if p1 else "Person 1"
        p2_name = p2["first_name"] if p2 else "Person 2"
        db.save_snapshot(req.tree_id, req.contributor_id, f"Change status to {req.relationship_status} for {p1_name} & {p2_name}")
        return {"message": "Relationship status updated successfully"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/api/persons/merge")
def api_merge_persons(req: MergePersonsRequest):
    try:
        db.merge_persons(req.tree_id, req.contributor_id, req.target_id, req.duplicate_id)
        db.save_snapshot(req.tree_id, req.contributor_id, "Merge Persons")
        return {"message": "Persons merged successfully"}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

# History

@app.get("/api/trees/{tree_id}/history")
def api_get_history(tree_id: int, limit: int = 50):
    return db.get_change_history(tree_id, limit)

# Undo / Redo

class UndoRedoRequest(BaseModel):
    contributor_id: int

@app.get("/api/trees/{tree_id}/undo-redo-status")
def api_undo_redo_status(tree_id: int):
    return db.get_undo_redo_status(tree_id)

@app.post("/api/trees/{tree_id}/undo")
def api_undo_tree(tree_id: int, req: UndoRedoRequest):
    try:
        res = db.undo_action(tree_id, req.contributor_id)
        return res
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/api/trees/{tree_id}/redo")
def api_redo_tree(tree_id: int, req: UndoRedoRequest):
    try:
        res = db.redo_action(tree_id, req.contributor_id)
        return res
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

# Serve SPA
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

@app.get("/")
def read_root():
    return RedirectResponse(url="/static/index.html")