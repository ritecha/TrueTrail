import os
import shutil
import sys

# ==========================================
# ✅ PATH FIX (Sirf zaroori paths)
# ==========================================
current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, current_dir)          
sys.path.insert(0, os.path.join(current_dir, "app")) 
# ❌ truetrail waali line hata di hai taaki Jaya ka config load ho

from fastapi import FastAPI, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from agent import router as agent_router
from integrity import sha256_file, log_event, _conn, verify_chain
from report import generate_report
from dotenv import load_dotenv

# ✅ Manya ka code (Relative import use karta hai, toh bina path ke bhi chalega)
from truetrail.timeline import build_timeline

# ✅ Jaya ka code (Ab isko apni config file milegi)
from app.main import app as jaya_app

app = FastAPI()
app.include_router(agent_router)

load_dotenv()

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://digitalevidencebytruetrail-ver.vercel.app",
        "http://localhost:5173",
        "http://localhost:5174",
        "http://localhost:4173",
    ],
    allow_origin_regex=r"https://.*\.vercel\.app|http://(localhost|127\.0\.0\.1)(:\d+)?",
    allow_methods=["*"],
    allow_headers=["*"],
)

# Purana local evidence hata diya, sirf data rakha
os.makedirs("data", exist_ok=True)

@app.post("/evidence/upload")
async def upload(file: UploadFile = File(...), actor: str = "investigator"):
    path = f"data/{file.filename}"
    with open(path, "wb") as f:
        shutil.copyfileobj(file.file, f)
    h = sha256_file(path)
    log_event(actor, "INGEST", file.filename, h)
    return {"file": file.filename, "sha256": h}

@app.get("/evidence/{name}/verify")
def verify(name: str):
    path = f"data/{name}"
    if not os.path.exists(path):
        return {"error": "File not found"}
    h = sha256_file(path)
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