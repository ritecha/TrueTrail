import os
import shutil
import sys

# ==========================================
# ✅ JAYA KE IMPORT FIX (Sabse pehle aayega)
# ==========================================
current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, current_dir)
sys.path.insert(0, os.path.join(current_dir, "app"))

from fastapi import FastAPI, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from agent import router as agent_router
from integrity import sha256_file, log_event, _conn, verify_chain
from report import generate_report
from dotenv import load_dotenv

# ✅ Manya ka code
from truetrail.timeline import build_timeline

# ✅ Jaya ka code (Ab yeh path milne ke baad chalega)
from app.main import app as jaya_app

app = FastAPI()
app.include_router(agent_router)

load_dotenv()

# CORS 
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:5174"],
    allow_origin_regex=r"https://.*\.vercel\.app", 
    allow_methods=["*"],
    allow_headers=["*"],
)

os.makedirs("evidence", exist_ok=True)
os.makedirs("data", exist_ok=True) 

@app.post("/evidence/upload")
async def upload(file: UploadFile = File(...), actor: str = "investigator"):
    path = f"evidence/{file.filename}"
    with open(path, "wb") as f:
        shutil.copyfileobj(file.file, f)
    h = sha256_file(path)
    log_event(actor, "INGEST", file.filename, h)
    return {"file": file.filename, "sha256": h}

@app.get("/evidence/{name}/verify")
def verify(name: str):
    h = sha256_file(f"evidence/{name}")
    row = _conn().execute("SELECT file_hash FROM audit WHERE file_name=? AND action='INGEST' "
                          "ORDER BY id LIMIT 1", (name,)).fetchone()
    log_event("investigator", "VERIFY", name, h)
    return {"file": name, "current": h, "original": row[0] if row else None, "match": h == row[0] if row else False}

@app.get("/audit")
def audit():
    rows = _conn().execute("SELECT * FROM audit ORDER BY id").fetchall()
    return [dict(zip(["id","ts","actor","action","file","file_hash","prev_hash","entry_hash"], r)) for r in rows]

@app.get("/audit/verify")
def audit_verify():
    return verify_chain()

@app.post("/report")
def create_report(file_name: str, file_hash: str, case_id: str):
    path = generate_report(file_name, file_hash, case_id, "Investigating Officer")
    return FileResponse(path, media_type="application/pdf", filename=f"BSA_{case_id}.pdf")

@app.get("/api/timeline")
def get_manya_timeline():
    try:
        timeline_data = build_timeline()
        return {"status": "success", "data": timeline_data}
    except Exception as e:
        return {"status": "error", "message": str(e)}

# ==========================================
# ✅ JAYA KA CODE MOUNT KAR DIYA
# ==========================================
app.mount("/jaya", jaya_app)