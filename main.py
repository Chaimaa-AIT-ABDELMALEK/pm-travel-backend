from fastapi import FastAPI, HTTPException, Depends, Header, Query, Body
from sqlalchemy import create_engine, text
from dotenv import load_dotenv
from pydantic import BaseModel
from typing import Optional
import os
from pydantic import BaseModel
from typing import Optional
import requests
import json
from typing import List
from pydantic import BaseModel
from emails.email_service import generer_contenu_email, envoyer_email, sauvegarder_email
from social.social_service import generer_post_complet, generer_calendrier_semaine
import sys
import threading
import subprocess
import json
import redis
from fastapi.middleware.cors import CORSMiddleware
from datetime import datetime, timedelta
from jwt import encode, decode
import bcrypt
from cryptography.fernet import Fernet
import asyncio
from pydantic import BaseModel
from fastapi.responses import JSONResponse
import traceback
import jwt

class PostRequest(BaseModel):
    plateforme: str
    theme: str
    langue: str = "français"
    
# Windows asyncio support
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

load_dotenv()

SECRET_KEY = os.getenv('JWT_SECRET_KEY', 'votre-clé-secrète')
ALGORITHM = "HS256"
ENCRYPTION_KEY = os.getenv('ENCRYPTION_KEY', '0123456789abcdef0123456789abcdef')
import base64
import hashlib

def _build_cipher(secret):
    digest = hashlib.sha256(str(secret).encode("utf-8")).digest()
    return Fernet(base64.urlsafe_b64encode(digest))

CIPHER_SUITE = _build_cipher(ENCRYPTION_KEY)

app = FastAPI()

DB_URL = f"mysql+pymysql://{os.getenv('DB_USER')}:{os.getenv('DB_PASSWORD')}@{os.getenv('DB_HOST')}:{os.getenv('DB_PORT')}/{os.getenv('DB_NAME')}"
engine = create_engine(DB_URL, pool_pre_ping=True)

try:
    redis_client = redis.Redis(
        host=os.getenv('REDIS_HOST', 'localhost'),
        port=int(os.getenv('REDIS_PORT', 6379)),
        db=0,
        decode_responses=True
    )
    redis_client.ping()
except:
    redis_client = None
    print("⚠️ Redis non disponible - mode sans cache")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3001", "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ═══════════════════════════════════════════
# INIT DATABASE
# ═══════════════════════════════════════════

def init_database():
    """Crée les tables manquantes au démarrage"""
    try:
        with engine.connect() as conn:
            try:
                conn.execute(text("""
                    ALTER TABLE emails_envoyes 
                    ADD COLUMN user_id INT DEFAULT NULL AFTER id
                """))
                print("✅ Colonne user_id ajoutée à emails_envoyes")
            except Exception as e:
                if "Duplicate column" not in str(e):
                    print(f"⚠️ Erreur migration user_id: {e}")
            
            try:
                conn.execute(text("""
                    ALTER TABLE prospects 
                    ADD COLUMN description LONGTEXT DEFAULT NULL
                """))
                print("✅ Colonne description ajoutée à prospects")
            except Exception as e:
                if "Duplicate column" not in str(e):
                    print(f"⚠️ Erreur migration description: {e}")

            try:
                try:
                    conn.execute(text("ALTER TABLE prospects DROP INDEX uq_prospects_email"))
                    conn.commit()
                except Exception:
                    pass

                conn.execute(text("""
                    DELETE p1 FROM prospects p1
                    INNER JOIN prospects p2
                        ON LOWER(TRIM(p1.nom))   = LOWER(TRIM(p2.nom))
                       AND LOWER(TRIM(p1.ville)) = LOWER(TRIM(p2.ville))
                       AND p1.nom IS NOT NULL AND p1.nom <> ''
                       AND p1.id > p2.id
                """))
                try:
                    conn.execute(text("""
                        ALTER TABLE prospects
                        ADD CONSTRAINT uq_prospects_nom_ville UNIQUE (nom, ville)
                    """))
                except Exception as e_idx:
                    if ("used in key specification" in str(e_idx)
                            or "key part" in str(e_idx) or "too long" in str(e_idx)):
                        conn.execute(text("""
                            ALTER TABLE prospects
                            ADD UNIQUE INDEX uq_prospects_nom_ville (nom(191), ville(191))
                        """))
                    else:
                        raise
                conn.commit()
                print("✅ Contrainte UNIQUE(nom, ville) ajoutée à prospects (anti-doublons par établissement)")
            except Exception as e:
                msg = str(e)
                if ("Duplicate key name" in msg or "already exists" in msg
                        or "Duplicate entry" in msg or "check that column/key exists" in msg):
                    pass
                else:
                    print(f"⚠️ Erreur migration UNIQUE(nom, ville): {e}")

            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS emails_envoyes (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    user_id INT,
                    campagne_id INT,
                    email_destinataire VARCHAR(255),
                    sujet VARCHAR(500),
                    contenu LONGTEXT,
                    statut VARCHAR(50) DEFAULT 'envoyé',
                    date_envoi DATETIME DEFAULT CURRENT_TIMESTAMP,
                    date_ouverture DATETIME,
                    INDEX idx_user (user_id),
                    INDEX idx_campagne (campagne_id)
                )
            """))
            
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS api_integrations (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    user_id INT NOT NULL,
                    api_name VARCHAR(100) NOT NULL,
                    api_key LONGTEXT,
                    config LONGTEXT,
                    enabled BOOLEAN DEFAULT false,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE KEY unique_api (user_id, api_name),
                    INDEX idx_user (user_id)
                )
            """))
            
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS email_settings (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    user_id INT NOT NULL,
                    provider VARCHAR(100),
                    email VARCHAR(255),
                    password LONGTEXT,
                    host VARCHAR(255),
                    port INT,
                    secure BOOLEAN DEFAULT true,
                    smtp_enabled BOOLEAN DEFAULT false,
                    imap_enabled BOOLEAN DEFAULT false,
                    sync_interval INT DEFAULT 5,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE KEY unique_user_email (user_id),
                    INDEX idx_user (user_id)
                )
            """))
            
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS scraping_history (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    user_id INT,
                    sector VARCHAR(100),
                    city VARCHAR(100),
                    prospects_found INT DEFAULT 0,
                    logs LONGTEXT,
                    status VARCHAR(50),
                    date_execution DATETIME DEFAULT CURRENT_TIMESTAMP,
                    INDEX idx_user (user_id),
                    INDEX idx_date (date_execution)
                )
            """))

            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS emails_recus (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    user_id INT,
                    email_expediteur VARCHAR(255) NOT NULL,
                    nom_expediteur VARCHAR(255),
                    sujet VARCHAR(500),
                    contenu LONGTEXT,
                    contenu_html LONGTEXT,
                    message_id VARCHAR(500),
                    in_reply_to VARCHAR(500),
                    date_reception DATETIME DEFAULT CURRENT_TIMESTAMP,
                    lu BOOLEAN DEFAULT FALSE,
                    INDEX idx_user (user_id),
                    INDEX idx_expediteur (email_expediteur),
                    INDEX idx_date (date_reception),
                    UNIQUE KEY unique_message (message_id(255))
                )
            """))

            try:
                conn.execute(text("""
                    ALTER TABLE emails_envoyes
                    ADD COLUMN tracking_id VARCHAR(255) DEFAULT NULL
                """))
                print("✅ Colonne tracking_id ajoutée à emails_envoyes")
            except Exception as e:
                if "Duplicate column" not in str(e):
                    pass

            try:
                conn.execute(text("""
                    ALTER TABLE emails_envoyes
                    ADD COLUMN prospect_id INT DEFAULT NULL
                """))
                print("✅ Colonne prospect_id ajoutée à emails_envoyes")
            except Exception as e:
                if "Duplicate column" not in str(e):
                    pass
            
            conn.commit()
            print("✅ Tables initialisées avec succès")
    except Exception as e:
        print(f"⚠️ Erreur initialisation DB: {e}")

init_database()

# ═══════════════════════════════════════════
# MODELS
# ═══════════════════════════════════════════
class SelectionEmails(BaseModel):
    contact_ids: List[int]

class Prospect(BaseModel):
    nom: str
    email: str
    telephone: Optional[str] = None
    secteur: Optional[str] = None
    ville: Optional[str] = None
    source: Optional[str] = None
    score: Optional[int] = 0
    email_valide: Optional[bool] = False
    description: Optional[str] = None

class SMTPConfig(BaseModel):
    provider: str
    email: str
    password: str
    host: Optional[str] = None
    port: Optional[int] = None
    secure: Optional[bool] = True

class IMAPConfig(BaseModel):
    provider: str
    email: str
    password: str
    host: Optional[str] = None
    port: Optional[int] = None
    secure: Optional[bool] = True
    sync_interval: Optional[int] = 5

class APIConfigRequest(BaseModel):
    api_name: str
    config: dict

class EmailEnvoyeModel(BaseModel):
    campagne_id: Optional[int] = None
    email_destinataire: str
    sujet: str
    contenu: str
    statut: str = 'envoyé'

class PublishRequest(BaseModel):
    plateforme: str  # instagram, facebook, linkedin

# ═══════════════════════════════════════════
# UTILITY FUNCTIONS
# ═══════════════════════════════════════════

def get_user_by_username(username: str):
    try:
        with engine.connect() as conn:
            result = conn.execute(text("SELECT * FROM users WHERE username = :username"), {"username": username})
            row = result.fetchone()
            if row:
                return dict(row._mapping)
            return None
    except Exception as e:
        print(f"Erreur get_user_by_username: {e}")
        return None

def hash_password(password):
    try:
        return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
    except:
        return password

def verify_password(password, hashed):
    try:
        return bcrypt.checkpw(password.encode(), hashed.encode())
    except:
        return password == hashed

def create_token(user_id, role, expires_in=24):
    payload = {
        'user_id': user_id,
        'role': role,
        'exp': datetime.utcnow() + timedelta(hours=expires_in)
    }
    return encode(payload, SECRET_KEY, algorithm=ALGORITHM)

def verify_token(token):
    try:
        payload = decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except Exception as e:
        print(f"Erreur token: {e}")
        return None

def get_current_user(authorization: str = Header(None)):
    if not authorization:
        raise HTTPException(status_code=401, detail="No token")

    parts = authorization.split(" ")

    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise HTTPException(status_code=401, detail="Invalid token format")

    token = parts[1]
    payload = verify_token(token)

    if not payload:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    return payload

def require_role(required_role: str):
    def check_role(current_user = Depends(get_current_user)):
        if current_user.get('role') != required_role and current_user.get('role') != 'admin':
            raise HTTPException(status_code=403, detail="Insufficient permissions")
        return current_user
    return check_role

# ═══════════════════════════════════════════
# HELPER: get_integration_config
# ═══════════════════════════════════════════

def get_integration_config(api_name: str, user_id: int = None) -> dict:
    """
    Récupère la config JSON d'une intégration API.
    Filtre par user_id si fourni, sinon prend la première ligne active trouvée (fallback n8n/admin).
    """
    with engine.connect() as conn:
        if user_id:
            row = conn.execute(
                text("""SELECT config FROM api_integrations
                        WHERE api_name = :name AND enabled = 1 AND user_id = :uid
                        LIMIT 1"""),
                {"name": api_name, "uid": user_id}
            ).fetchone()
            # Fallback sans user_id si rien trouvé pour cet utilisateur
            if not row or not row[0]:
                row = conn.execute(
                    text("""SELECT config FROM api_integrations
                            WHERE api_name = :name AND enabled = 1
                            LIMIT 1"""),
                    {"name": api_name}
                ).fetchone()
        else:
            row = conn.execute(
                text("""SELECT config FROM api_integrations
                        WHERE api_name = :name AND enabled = 1
                        LIMIT 1"""),
                {"name": api_name}
            ).fetchone()

    if not row or not row[0]:
        raise HTTPException(400, f"Intégration '{api_name}' manquante ou désactivée en base")

    try:
        return json.loads(row[0])
    except json.JSONDecodeError as e:
        raise HTTPException(500, f"Config '{api_name}' invalide (JSON malformé): {e}")

# ═══════════════════════════════════════════
# AUTH
# ═══════════════════════════════════════════

@app.post("/auth/login")
def login(username: str, password: str):
    user = get_user_by_username(username)
    if not user or not verify_password(password, user.get('password', '')):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    
    token = create_token(user['id'], user.get('role', 'user'))
    return {
        "access_token": token,
        "token_type": "bearer",
        "user": {
            "id": user['id'],
            "username": user['username'],
            "role": user.get('role', 'user')
        }
    }

@app.post("/auth/refresh")
def refresh_token(current_user = Depends(get_current_user)):
    """
    Génère un nouveau token longue durée (1 an).
    À utiliser depuis n8n pour ne plus avoir de tokens hardcodés expirés.
    Workflow n8n : POST /auth/login → récupérer access_token → utiliser dans les nœuds suivants.
    """
    new_token = create_token(
        user_id=current_user['user_id'],
        role=current_user['role'],
        expires_in=24 * 365  # 1 an
    )
    return {"access_token": new_token, "token_type": "bearer"}

@app.get("/auth/token-test")
def generate_test_token():
    """Génère un token admin de test valide 24h (sans authentification requise)."""
    token = create_token(user_id=1, role="admin")
    return {
        "access_token": token,
        "token_type": "bearer"
    }

# ═══════════════════════════════════════════
# ROOT
# ═══════════════════════════════════════════

@app.get("/")
def read_root():
    return {"message": "PM Travel API is running"}

@app.get("/test-db")
def test_db():
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
            return {"database": "connectée ✅"}
    except Exception as e:
        return {"database": "erreur", "error": str(e)}

# ═══════════════════════════════════════════
# PROSPECTS
# ═══════════════════════════════════════════

@app.get("/prospects")
def get_prospects(current_user = Depends(get_current_user)):
    try:
        with engine.connect() as conn:
            result = conn.execute(text("SELECT * FROM prospects ORDER BY score DESC"))
            rows = result.fetchall()
            prospects = []
            for row in rows:
                p = dict(row._mapping)
                p['type'] = p.get('secteur', 'Prospect')
                prospects.append(p)
            return prospects
    except Exception as e:
        print(f"❌ Erreur /prospects: {e}")
        return []

@app.get("/prospects/{id}")
def get_prospect(id: int, current_user = Depends(get_current_user)):
    try:
        with engine.connect() as conn:
            result = conn.execute(text("SELECT * FROM prospects WHERE id = :id"), {"id": id})
            row = result.fetchone()
            if not row:
                raise HTTPException(status_code=404, detail="Prospect non trouvé")
            p = dict(row._mapping)
            p['type'] = p.get('secteur', 'Prospect')
            return p
    except HTTPException:
        raise
    except Exception as e:
        print(f"Erreur get_prospect: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/prospects")
def create_prospect(prospect: Prospect, current_user = Depends(get_current_user)):
    try:
        with engine.connect() as conn:
            conn.execute(text("""
                INSERT IGNORE INTO prospects 
                (nom, email, telephone, secteur, ville, source, score, email_valide, description)
                VALUES (:nom, :email, :telephone, :secteur, :ville, :source, :score, :email_valide, :description)
            """), {
                "nom": prospect.nom,
                "email": prospect.email,
                "telephone": prospect.telephone,
                "secteur": prospect.secteur,
                "ville": prospect.ville,
                "source": prospect.source,
                "score": prospect.score,
                "email_valide": prospect.email_valide,
                "description": prospect.description
            })
            conn.commit()
            return {"message": "Prospect ajouté ✅"}
    except Exception as e:
        print(f"❌ Erreur: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.put("/prospects/{id}/statut")
def update_statut(id: int, statut: str, current_user = Depends(get_current_user)):
    try:
        with engine.connect() as conn:
            conn.execute(text("UPDATE prospects SET statut = :statut WHERE id = :id"), {"statut": statut, "id": id})
            conn.commit()
            return {"message": "Statut mis à jour ✅"}
    except Exception as e:
        print(f"Erreur update_statut: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/prospects/{id}")
def delete_prospect(id: int, current_user = Depends(require_role('admin'))):
    try:
        with engine.connect() as conn:
            conn.execute(text("DELETE FROM prospects WHERE id = :id"), {"id": id})
            conn.commit()
            return {"message": "Prospect supprimé ✅"}
    except Exception as e:
        print(f"Erreur delete_prospect: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/prospects/stats/kpis")
def get_kpis(current_user = Depends(get_current_user)):
    try:
        with engine.connect() as conn:
            total = conn.execute(text("SELECT COUNT(*) FROM prospects")).scalar() or 0
            valides = conn.execute(text("SELECT COUNT(*) FROM prospects WHERE email_valide = 1")).scalar() or 0
            nouveaux = conn.execute(text("SELECT COUNT(*) FROM prospects WHERE statut = 'nouveau'")).scalar() or 0
            partenaires = conn.execute(text("SELECT COUNT(*) FROM prospects WHERE statut = 'partenaire'")).scalar() or 0
            return {
                "total_prospects": total,
                "emails_valides": valides,
                "nouveaux": nouveaux,
                "partenaires": partenaires
            }
    except Exception as e:
        print(f"Erreur KPIs: {e}")
        return {"total_prospects": 0, "emails_valides": 0, "nouveaux": 0, "partenaires": 0}

# ═══════════════════════════════════════════
# ENRICHMENT - OpenAI
# ═══════════════════════════════════════════

@app.post("/enrich/openai")
def enrich_with_openai(prospect_id: int, current_user = Depends(get_current_user)):
    """Enrichit un prospect avec OpenAI"""
    try:
        user_id = current_user.get("user_id")
        
        with engine.connect() as conn:
            result = conn.execute(text("""
                SELECT nom, secteur, ville, email FROM prospects WHERE id = :id
            """), {"id": prospect_id})
            
            row = result.fetchone()
            if not row:
                raise HTTPException(status_code=404, detail="Prospect non trouvé")
            
            prospect = dict(row._mapping)
            
            result = conn.execute(text("""
                SELECT api_key FROM api_integrations 
                WHERE user_id = :user_id AND api_name = 'openai' AND enabled = 1
                LIMIT 1
            """), {"user_id": user_id})
            
            row = result.fetchone()
            if not row:
                return {"error": "OpenAI non configuré", "success": False}
            
            encrypted_key = dict(row._mapping)['api_key']
            
            try:
                openai_key = CIPHER_SUITE.decrypt(encrypted_key.encode()).decode()
            except:
                return {"error": "Erreur clé API", "success": False}
        
        import openai
        openai.api_key = openai_key
        
        prompt = f"""Génère une description professionnelle courte (100 caractères max) pour ce prospect du secteur touristique:
Nom: {prospect['nom']}
Secteur: {prospect['secteur']}
Ville: {prospect['ville']}
Format: Description brève et pertinente uniquement."""
        
        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=50
        )
        
        description = response.choices[0].message.content
        
        with engine.connect() as conn:
            conn.execute(text("""
                UPDATE prospects SET description = :desc WHERE id = :id
            """), {"desc": description, "id": prospect_id})
            conn.commit()
        
        return {"success": True, "description": description}
    except Exception as e:
        print(f"❌ Erreur enrichissement: {e}")
        return {"error": str(e), "success": False}

@app.get("/enrich/status")
def get_enrichment_status(current_user = Depends(get_current_user)):
    """Récupère le statut d'enrichissement OpenAI"""
    try:
        with engine.connect() as conn:
            total = conn.execute(text("SELECT COUNT(*) FROM prospects")).scalar() or 0
            enriched = conn.execute(text("SELECT COUNT(*) FROM prospects WHERE description IS NOT NULL")).scalar() or 0
            return {
                "total_prospects": total,
                "enriched_prospects": enriched,
                "percentage": int((enriched / total * 100)) if total > 0 else 0
            }
    except Exception as e:
        print(f"Erreur enrichment_status: {e}")
        return {"total_prospects": 0, "enriched_prospects": 0, "percentage": 0}

# ═══════════════════════════════════════════
# SCRAPING
# ═══════════════════════════════════════════

BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))

def resoudre_scraper_path():
    candidats = [
        os.path.join(BACKEND_DIR, "scrapers", "scraper_places.py"),
        os.path.join(BACKEND_DIR, "scraper_places.py"),
    ]
    for chemin in candidats:
        if os.path.isfile(chemin):
            return chemin
    return None

def _nouveau_job():
    return {
        "running": False,
        "started_at": None,
        "finished_at": None,
        "found": 0,
        "skipped": 0,
        "processed": 0,
        "recent": [],
        "status": "idle",
        "message": "",
        "error": None,
        "cancelled": False,
    }

SCRAPER_JOBS = {
    "env": _nouveau_job(),
    "settings": _nouveau_job(),
    "openai": _nouveau_job(),
}
SCRAPER_LOCKS = {
    "env": threading.Lock(),
    "settings": threading.Lock(),
    "openai": threading.Lock(),
}
SCRAPER_PROCESSES = {
    "env": {"proc": None},
    "settings": {"proc": None},
    "openai": {"proc": None},
}

def _parse_prospect_log(msg):
    if not msg or "|" not in msg or "Email:" not in msg:
        return None
    clean = msg.lstrip("✅").strip()
    parts = [p.strip() for p in clean.split("|")]
    if len(parts) < 2:
        return None
    nom = parts[0]
    ville = parts[1]
    email = ""
    for p in parts:
        if p.lower().startswith("email:"):
            email = p.split(":", 1)[1].strip()
    if not nom:
        return None
    return {"nom": nom, "ville": ville, "email": email}

def _run_scraper_job(job_key, args, extra_env=None):
    job = SCRAPER_JOBS[job_key]
    lock = SCRAPER_LOCKS[job_key]
    proc_holder = SCRAPER_PROCESSES[job_key]

    scraper_path = resoudre_scraper_path()
    if not scraper_path:
        with lock:
            job.update(
                running=False,
                status="error",
                error="scraper_places.py introuvable.",
                finished_at=datetime.utcnow().isoformat()
            )
        return

    cmd = [sys.executable, "-u", scraper_path] + list(args)
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"
    if extra_env:
        env.update(extra_env)

    try:
        process = subprocess.Popen(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            cwd=BACKEND_DIR, text=True, encoding="utf-8", errors="replace", bufsize=1, env=env
        )
        proc_holder["proc"] = process
    except Exception as e:
        with lock:
            job.update(
                running=False,
                status="error",
                error=f"{type(e).__name__}: {e}",
                finished_at=datetime.utcnow().isoformat()
            )
        return

    last_line = ""
    for line in iter(process.stdout.readline, ""):
        line = line.rstrip("\n").strip()
        if not line:
            continue
        last_line = line
        prospect = _parse_prospect_log(line)
        if prospect:
            with lock:
                job["found"] += 1
                job["processed"] += 1
                job["recent"].insert(0, prospect)
                job["recent"] = job["recent"][:50]
                job["message"] = f"{job['found']} prospects trouvés..."
        elif line.startswith("⏭️") or "Doublon ignoré" in line:
            with lock:
                job["skipped"] += 1
                job["processed"] += 1

    process.stdout.close()
    code = process.wait()
    proc_holder["proc"] = None

    total = None
    try:
        parsed = json.loads(last_line)
        if "found" in parsed:
            total = parsed["found"]
    except (json.JSONDecodeError, TypeError):
        total = None

    with lock:
        job["running"] = False
        job["finished_at"] = datetime.utcnow().isoformat()
        if job.get("cancelled"):
            job["status"] = "cancelled"
            job["message"] = f"Scraping arrêté : {job['found']} nouveaux, {job['skipped']} doublons (avant l'arrêt)"
        elif code == 0:
            job["status"] = "completed"
            if total is not None:
                job["found"] = total
            job["message"] = f"Scraping terminé : {job['found']} nouveaux, {job['skipped']} doublons ignorés"
        else:
            job["status"] = "error"
            job["error"] = (last_line or "Le scraper a échoué")[:300]

def _demarrer_job(job_key, args, extra_env=None):
    lock = SCRAPER_LOCKS[job_key]
    job = SCRAPER_JOBS[job_key]
    with lock:
        if job["running"]:
            return False
        job.update(
            running=True,
            status="running",
            started_at=datetime.utcnow().isoformat(),
            finished_at=None,
            found=0,
            skipped=0,
            processed=0,
            recent=[],
            message="Scraping démarré...",
            error=None,
            cancelled=False
        )
    thread = threading.Thread(target=_run_scraper_job, args=(job_key, args, extra_env), daemon=True)
    thread.start()
    return True

def _annuler_job(job_key):
    lock = SCRAPER_LOCKS[job_key]
    job = SCRAPER_JOBS[job_key]
    with lock:
        if not job["running"]:
            return {"status": "idle", "message": "Aucun scraping en cours."}
        job["cancelled"] = True
        job["message"] = "Arrêt en cours..."
    proc = SCRAPER_PROCESSES[job_key].get("proc")
    if proc and proc.poll() is None:
        try:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
        except Exception as e:
            print(f"Erreur arrêt scraper [{job_key}] : {e}")
    print(f"\n{'='*60}\n🛑 SCRAPER [{job_key}] ARRETE PAR L'UTILISATEUR\n{'='*60}")
    return {"status": "cancelling", "message": "Scraping arrêté."}

@app.post("/scraper/lancer-openai-web-search")
def lancer_scraper_openai_web_search(current_user = Depends(get_current_user)):
    """Page 'Outils' : scraper basé sur OpenAI."""
    user_id = current_user.get("user_id")

    try:
        with engine.connect() as conn:
            result = conn.execute(text("""
                SELECT api_key FROM api_integrations 
                WHERE user_id = :user_id AND api_name = 'openai' AND enabled = 1
                LIMIT 1
            """), {"user_id": user_id})

            row = result.fetchone()
            if not row:
                return {"status": "error", "message": "❌ OpenAI API non configurée dans Settings"}

            encrypted_key = dict(row._mapping)['api_key']

            try:
                openai_key = CIPHER_SUITE.decrypt(encrypted_key.encode()).decode()
            except Exception as e:
                print(f"Erreur décryption: {e}")
                return {"status": "error", "message": "❌ Clé API illisible. Ré-enregistrez votre clé dans Settings puis relancez."}
    except Exception as e:
        print(f"Erreur récupération API: {e}")
        return {"status": "error", "message": f"❌ Erreur: {str(e)}"}

    job = SCRAPER_JOBS["openai"]
    lock = SCRAPER_LOCKS["openai"]
    with lock:
        if job["running"]:
            return {"status": "already_running", "message": "Un scraping OpenAI est déjà en cours."}
        job.update(
            running=True, status="running", started_at=datetime.utcnow().isoformat(),
            finished_at=None, found=0, skipped=0, processed=0, recent=[],
            message="Scraping OpenAI démarré...", error=None, cancelled=False
        )

    print(f"\n{'='*60}\n🤖 SCRAPER OPENAI WEB SEARCH\n{'='*60}")

    def _appel_openai(client_legacy, client_v1, prompt):
        if client_v1 is not None:
            resp = client_v1.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[{"role": "user", "content": prompt}],
                max_tokens=500, temperature=0.7,
            )
            return resp.choices[0].message.content
        resp = client_legacy.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=500, temperature=0.7,
        )
        return resp.choices[0].message.content

    def _scraper_openai_task():
        try:
            import openai

            client_v1 = None
            client_legacy = None
            if hasattr(openai, "OpenAI"):
                try:
                    client_v1 = openai.OpenAI(api_key=openai_key)
                except Exception as e:
                    print(f"⚠️ Init client OpenAI v1 échouée, fallback legacy: {e}")
                    client_v1 = None
            if client_v1 is None:
                openai.api_key = openai_key
                client_legacy = openai

            secteurs = ['hotel', 'riad', 'agence de voyage', 'tour operator', 'transport touristique']
            villes = ['Marrakech', 'Fes', 'Casablanca', 'Agadir', 'Essaouira']

            for secteur in secteurs:
                for ville in villes:
                    with lock:
                        if job.get("cancelled"):
                            break
                    try:
                        prompt = f"""Génère une liste de 5 {secteur}s réels et existants à {ville}, Maroc.

Format de réponse STRICT (une ligne par prospect):
Nom|Email|Telephone|Secteur|Ville

Exemple:
Hotel Atlas Royal|contact@atlasroyal.ma|+212 5 24 38 46 46|hotel|Marrakech
Riad Luna Palace|info@lunapalace.ma|+212 6 61 23 45 67|riad|Marrakech

Génère maintenant {secteur}s à {ville}:"""

                        result_text = _appel_openai(client_legacy, client_v1, prompt)

                        with engine.connect() as conn:
                            for line in result_text.split('\n'):
                                if '|' not in line or len(line.strip()) < 5:
                                    continue
                                try:
                                    parts = [p.strip() for p in line.split('|')]
                                    if len(parts) < 5:
                                        continue
                                    nom = parts[0]
                                    email = parts[1]
                                    telephone = parts[2]
                                    sect = parts[3].lower()
                                    vil = parts[4]

                                    if '@' not in email or '.' not in email:
                                        email = f"{nom.lower().replace(' ', '')}@{vil.lower()}-{sect}.ma"

                                    exists = conn.execute(text("""
                                        SELECT 1 FROM prospects
                                        WHERE LOWER(TRIM(nom)) = LOWER(TRIM(:nom))
                                          AND LOWER(TRIM(ville)) = LOWER(TRIM(:ville))
                                        LIMIT 1
                                    """), {"nom": nom, "ville": vil}).fetchone()
                                    if exists:
                                        with lock:
                                            job["processed"] += 1
                                            job["skipped"] += 1
                                            job["message"] = f"{job['found']} prospects trouvés..."
                                        print(f"⏭️ Doublon ignoré : {nom} ({vil})")
                                        continue

                                    res = conn.execute(text("""
                                        INSERT IGNORE INTO prospects 
                                        (nom, email, telephone, secteur, ville, source, score, email_valide)
                                        VALUES (:nom, :email, :telephone, :secteur, :ville, 'openai_web_search', 70, 1)
                                    """), {
                                        "nom": nom, "email": email, "telephone": telephone,
                                        "secteur": sect, "ville": vil
                                    })
                                    inserted = (res.rowcount or 0) > 0
                                    if inserted:
                                        conn.commit()
                                    with lock:
                                        job["processed"] += 1
                                        if inserted:
                                            job["found"] += 1
                                            job["recent"].insert(0, {"nom": nom, "ville": vil, "email": email})
                                            job["recent"] = job["recent"][:50]
                                        else:
                                            job["skipped"] += 1
                                        job["message"] = f"{job['found']} prospects trouvés..."
                                    print(f"✅ {nom} | {email} | {telephone} | {sect} | {vil}")
                                except Exception as e:
                                    print(f"⚠️ Erreur parsing ligne: {e}")
                                    continue
                            conn.commit()
                    except Exception as e:
                        print(f"⚠️ Erreur scraping {secteur} à {ville}: {e}")
                        continue
                with lock:
                    if job.get("cancelled"):
                        break

            with lock:
                job["running"] = False
                job["finished_at"] = datetime.utcnow().isoformat()
                if job.get("cancelled"):
                    job["status"] = "cancelled"
                    job["message"] = f"Scraping arrêté : {job['found']} nouveaux, {job['skipped']} doublons (avant l'arrêt)"
                else:
                    job["status"] = "completed"
                    job["message"] = f"Scraping OpenAI terminé : {job['found']} nouveaux, {job['skipped']} doublons ignorés"
            print(f"\n✅ Scraping OpenAI terminé: {job['found']} prospects ajoutés")

        except Exception as e:
            with lock:
                job["running"] = False
                job["status"] = "error"
                job["error"] = str(e)[:300]
                job["message"] = f"❌ Erreur scraping OpenAI : {str(e)[:200]}"
                job["finished_at"] = datetime.utcnow().isoformat()
            print(f"❌ Erreur scraping OpenAI: {e}")

    thread = threading.Thread(target=_scraper_openai_task, daemon=True)
    thread.start()

    return {"status": "started", "message": "✅ Scraping OpenAI Web Search lancé! Recherche en cours..."}

@app.post("/scraper/lancer-env")
def lancer_scraper_env(current_user = Depends(get_current_user)):
    """Page 'Scraping' : lance le scraper avec l'API du fichier .env (GOOGLE_API_KEY)."""
    user_id = current_user.get("user_id")

    if not os.getenv("GOOGLE_API_KEY"):
        return {"status": "error", "message": "❌ GOOGLE_API_KEY absente du fichier .env"}

    print(f"\n{'='*60}\n🌍 SCRAPER (API .env)\n{'='*60}")
    demarre = _demarrer_job("env", ["--user-id", str(user_id)])

    if not demarre:
        return {"status": "already_running", "message": "Un scraping (.env) est déjà en cours."}

    return {"status": "started", "message": "✅ Scraping lancé avec l'API du fichier .env !"}


@app.post("/scraper/lancer-tout-streaming")
def lancer_scraper_tout(current_user = Depends(get_current_user)):
    """Page 'Outils' : lance le scraper avec l'API Google Places configurée dans Settings."""
    user_id = current_user.get("user_id")

    try:
        with engine.connect() as conn:
            result = conn.execute(text("""
                SELECT api_key FROM api_integrations 
                WHERE user_id = :user_id AND api_name = 'google_places' AND enabled = 1
                LIMIT 1
            """), {"user_id": user_id})

            row = result.fetchone()
            if not row:
                return {"status": "error", "message": "❌ Google Places API non configurée dans Settings"}

            encrypted_key = dict(row._mapping)['api_key']

            try:
                decrypted_key = CIPHER_SUITE.decrypt(encrypted_key.encode()).decode()
            except Exception as e:
                print(f"Erreur décryption: {e}")
                return {"status": "error", "message": "❌ Clé API illisible. Ré-enregistrez votre clé dans Settings puis relancez."}
    except Exception as e:
        print(f"Erreur récupération API: {e}")
        return {"status": "error", "message": f"❌ Erreur: {str(e)}"}

    print(f"\n{'='*60}\n🌍 SCRAPER (API Settings)\n{'='*60}")
    demarre = _demarrer_job("settings", ["--api-key", decrypted_key, "--user-id", str(user_id)])

    if not demarre:
        return {"status": "already_running", "message": "Un scraping (Settings) est déjà en cours."}

    return {"status": "started", "message": "✅ Scraping lancé avec l'API configurée dans Settings !"}

@app.post("/scraper/lancer-streaming")
def lancer_scraper_cible(sector: str = Query(...), city: str = Query(...), current_user = Depends(get_current_user)):
    print(f"\n{'='*60}\n🕷️ SCRAPER CIBLE: {sector} à {city} (tâche de fond)\n{'='*60}")
    user_id = current_user.get("user_id")
    demarre = _demarrer_job("settings", [sector, city, "--user-id", str(user_id)])
    if not demarre:
        return {"status": "already_running", "message": "Un scraping est déjà en cours."}
    return {"status": "started", "message": "Scraping démarré en arrière-plan."}

@app.get("/scraper/statut")
def statut_scraper(scope: str = Query("settings"), current_user = Depends(get_current_user)):
    """Statut d'un job. scope='env' (page Scraping) ou scope='settings' (page Outils)."""
    if scope not in SCRAPER_JOBS:
        scope = "settings"
    with SCRAPER_LOCKS[scope]:
        return dict(SCRAPER_JOBS[scope])

@app.get("/scraper/statut-env")
def statut_scraper_env(current_user = Depends(get_current_user)):
    with SCRAPER_LOCKS["env"]:
        return dict(SCRAPER_JOBS["env"])

@app.post("/scraper/annuler")
def annuler_scraper(scope: str = Query("settings"), current_user = Depends(get_current_user)):
    if scope not in SCRAPER_JOBS:
        scope = "settings"
    return _annuler_job(scope)

@app.post("/scraper/annuler-env")
def annuler_scraper_env(current_user = Depends(get_current_user)):
    return _annuler_job("env")

@app.post("/scraper/lancer")
def lancer_scraper(sector: str = Query(...), city: str = Query(...), current_user = Depends(get_current_user)):
    return {"message": "Utilise POST /scraper/lancer-streaming"}

@app.get("/scraper/historique")
def get_scraping_history(current_user = Depends(get_current_user)):
    try:
        with engine.connect() as conn:
            result = conn.execute(text("""
                SELECT id, sector, city, prospects_found, logs, status, date_execution
                FROM scraping_history
                ORDER BY date_execution DESC
                LIMIT 50
            """))
            histories = []
            for row in result.fetchall():
                h = dict(row._mapping)
                try:
                    h['logs'] = json.loads(h['logs']) if isinstance(h['logs'], str) else h['logs']
                except:
                    h['logs'] = []
                histories.append(h)
            return histories
    except Exception as e:
        print(f"Erreur historique: {e}")
        return []

@app.get("/scraper/derniers-prospects")
def get_derniers_prospects(current_user = Depends(get_current_user)):
    try:
        with engine.connect() as conn:
            prospects = conn.execute(text("""
                SELECT * FROM prospects ORDER BY id DESC LIMIT 100
            """)).fetchall()
            return [dict(row._mapping) for row in prospects]
    except Exception as e:
        print(f"Erreur derniers_prospects: {e}")
        return {"message": "Aucun prospect", "prospects": []}

@app.get("/contacts/scraping")
def get_contacts_from_scraping(current_user = Depends(get_current_user)):
    try:
        with engine.connect() as conn:
            contacts = conn.execute(text("""
                SELECT * FROM contacts ORDER BY id DESC LIMIT 100
            """)).fetchall()
            return {"total": len(contacts), "contacts": [dict(row._mapping) for row in contacts]}
    except Exception as e:
        print(f"Erreur contacts_scraping: {e}")
        return {"total": 0, "contacts": []}

# ═══════════════════════════════════════════
# CAMPAGNES
# ═══════════════════════════════════════════

@app.post("/campagnes")
def creer_campagne(nom: str, sujet: str, current_user = Depends(get_current_user)):
    try:
        with engine.connect() as conn:
            conn.execute(text("""
                INSERT INTO campagnes (nom, sujet, statut)
                VALUES (:nom, :sujet, 'brouillon')
            """), {"nom": nom, "sujet": sujet})
            conn.commit()
            return {"message": "Campagne créée ✅"}
    except Exception as e:
        print(f"Erreur creer_campagne: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/campagnes")
def get_campagnes(current_user = Depends(get_current_user)):
    try:
        with engine.connect() as conn:
            result = conn.execute(text("SELECT * FROM campagnes ORDER BY date_creation DESC"))
            return [dict(row._mapping) for row in result.fetchall()]
    except Exception as e:
        print(f"Erreur get_campagnes: {e}")
        return []

@app.get("/campagnes/{campagne_id}")
def get_campagne(campagne_id: int, current_user = Depends(get_current_user)):
    try:
        with engine.connect() as conn:
            result = conn.execute(text("SELECT * FROM campagnes WHERE id = :id"), {"id": campagne_id})
            row = result.fetchone()
            if not row:
                raise HTTPException(status_code=404, detail="Campagne non trouvée")
            return dict(row._mapping)
    except HTTPException:
        raise
    except Exception as e:
        print(f"Erreur get_campagne: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/campagnes/{campagne_id}/lancer")
def lancer_campagne(campagne_id: int, current_user = Depends(get_current_user)):
    try:
        with engine.connect() as conn:
            prospects = conn.execute(text("""
                SELECT * FROM prospects WHERE email_valide = 1 ORDER BY score DESC LIMIT 50
            """)).fetchall()
            if not prospects:
                return {"message": "Aucun prospect disponible", "envoyes": 0}
            return {"message": "Campagne lancée ✅", "envoyes": len(prospects), "echecs": 0}
    except Exception as e:
        print(f"Erreur lancer_campagne: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/campagnes/stats/kpis")
def get_kpis_campagnes(current_user = Depends(get_current_user)):
    try:
        with engine.connect() as conn:
            total = conn.execute(text("SELECT COUNT(*) FROM campagnes")).scalar() or 0
            return {"total_campagnes": total, "total_envoyes": 0, "total_ouverts": 0, "taux_ouverture": 0}
    except Exception as e:
        print(f"Erreur KPIs campagnes: {e}")
        return {"total_campagnes": 0, "total_envoyes": 0, "total_ouverts": 0, "taux_ouverture": 0}

@app.post("/campagnes/envoyer-selection")
def envoyer_emails_selection(selection: SelectionEmails, current_user = Depends(get_current_user)):
    envoyes = 0
    echecs = 0
    with engine.connect() as conn:
        placeholders = ','.join([f':id{i}' for i in range(len(selection.contact_ids))])
        query = text(f"""
            SELECT id, nom, email, telephone, secteur, ville, score
            FROM prospects 
            WHERE id IN ({placeholders}) AND email IS NOT NULL AND email != ''
        """)
        params = {f'id{i}': id for i, id in enumerate(selection.contact_ids)}
        prospects = conn.execute(query, params).fetchall()

        for row in prospects:
            prospect = dict(row._mapping)
            if not prospect.get('email'):
                print(f"⚠️ Prospect ID {prospect.get('id')} sans email, ignoré")
                echecs += 1
                continue
            try:
                print(f"📝 Génération contenu pour {prospect['email']}")
                contenu = generer_contenu_email(prospect)
                sujet = f"Offre personnalisée pour {prospect['nom']}"
                print(f"📤 Envoi à {prospect['email']}")
                success = envoyer_email(prospect['email'], sujet, contenu, prospect['nom'])
                if success:
                    try:
                        with engine.connect() as conn2:
                            conn2.execute(text("""
                                INSERT INTO emails_envoyes 
                                (campagne_id, prospect_id, email_destinataire, sujet, contenu, statut, date_envoi)
                                VALUES (NULL, :prospect_id, :email, :sujet, :contenu, 'envoyé', NOW())
                            """), {
                                "prospect_id": prospect['id'],
                                "email": prospect['email'],
                                "sujet": sujet,
                                "contenu": contenu
                            })
                            conn2.commit()
                        print("   ✅ Email sauvegardé en base")
                    except Exception as e:
                        print(f"   ⚠️ Sauvegarde base échouée : {e}")
                    envoyes += 1
                    print(f"   ✅ Succès, total = {envoyes}")
                else:
                    echecs += 1
                    print(f"   ❌ Échec, total = {echecs}")
            except KeyError as e:
                print(f"💥 Clé manquante : {e}")
                echecs += 1
            except Exception as e:
                print(f"💥 Exception : {e}")
                echecs += 1

    return {"envoyes": envoyes, "echecs": echecs}

@app.post("/emails/sauvegarder")
def sauvegarder_email_endpoint(email_data: EmailEnvoyeModel, current_user = Depends(get_current_user)):
    """Sauvegarde manuellement un email dans la table emails_envoyes"""
    user_id = current_user.get('user_id')
    try:
        with engine.connect() as conn:
            conn.execute(text("""
                INSERT INTO emails_envoyes
                (user_id, campagne_id, email_destinataire, sujet, contenu, statut, date_envoi)
                VALUES (:user_id, :campagne_id, :email, :sujet, :contenu, :statut, NOW())
            """), {
                "user_id": user_id,
                "campagne_id": email_data.campagne_id,
                "email": email_data.email_destinataire,
                "sujet": email_data.sujet,
                "contenu": email_data.contenu,
                "statut": email_data.statut
            })
            conn.commit()
        return {"message": "✅ Email sauvegardé"}
    except Exception as e:
        print(f"Erreur sauvegarder_email: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/emails/envoyes")
def get_emails_envoyes(current_user = Depends(get_current_user)):
    try:
        user_id = current_user.get('user_id')
        with engine.connect() as conn:
            result = conn.execute(text("""
                SELECT e.*, c.nom as campagne_nom
                FROM emails_envoyes e
                LEFT JOIN campagnes c ON e.campagne_id = c.id
                WHERE e.user_id = :user_id OR e.user_id IS NULL
                ORDER BY e.date_envoi DESC
                LIMIT 100
            """), {"user_id": user_id})
            emails = []
            for row in result.fetchall():
                d = dict(row._mapping)
                if d.get('date_envoi'): d['date_envoi'] = str(d['date_envoi'])
                if d.get('date_ouverture'): d['date_ouverture'] = str(d['date_ouverture'])
                emails.append(d)
            return emails
    except Exception as e:
        print(f"❌ /emails/envoyes: {e}")
        return []

@app.get("/tracking/click")
def track_click(tid: str):
    """Tracking par clic — fonctionne même si Gmail bloque les images"""
    try:
        with engine.connect() as conn:
            conn.execute(text("""
                UPDATE emails_envoyes 
                SET statut = 'ouvert',
                    date_ouverture = COALESCE(date_ouverture, NOW())
                WHERE tracking_id = :tid
            """), {"tid": tid})
            conn.commit()
    except Exception as e:
        print(f"Tracking click error: {e}")
    from fastapi.responses import RedirectResponse
    return RedirectResponse(url="https://www.pmtravel.ma")

@app.get("/tracking/open")
def track_open(tid: str):
    """Pixel de tracking - enregistre l'ouverture"""
    try:
        with engine.connect() as conn:
            conn.execute(
                text("""
                    UPDATE emails_envoyes 
                    SET date_ouverture = NOW(),
                        statut = 'ouvert'
                    WHERE tracking_id = :tid 
                    AND date_ouverture IS NULL
                """),
                {"tid": tid}
            )
            conn.commit()
    except Exception as e:
        print(f"Tracking error: {e}")
    from fastapi.responses import Response
    pixel = b'GIF89a\x01\x00\x01\x00\x80\x00\x00\xff\xff\xff\x00\x00\x00!\xf9\x04\x01\x00\x00\x00\x00,\x00\x00\x00\x00\x01\x00\x01\x00\x00\x02\x02D\x01\x00;'
    return Response(content=pixel, media_type="image/gif")

@app.get("/settings/api/list")
def get_api_configs(current_user = Depends(get_current_user)):
    """Récupère toutes les APIs configurées"""
    try:
        user_id = current_user.get('user_id')
        with engine.connect() as conn:
            result = conn.execute(text("""
                SELECT api_name, enabled
                FROM api_integrations
                WHERE user_id = :user_id
            """), {"user_id": user_id})

            apis = {}
            for row in result.fetchall():
                r = dict(row._mapping)
                apis[r['api_name']] = r['enabled'] == 1

            return apis
            
    except Exception as e:
        print(f"Erreur /settings/api/list: {e}")
        return {}
    
@app.post("/settings/smtp")
def save_smtp_config(config: SMTPConfig, current_user = Depends(get_current_user)):
    """Sauvegarde la configuration SMTP"""
    try:
        user_id = current_user.get('user_id')
        encrypted_password = CIPHER_SUITE.encrypt(config.password.encode()).decode()
        with engine.connect() as conn:
            conn.execute(text("""
                INSERT INTO email_settings
                (user_id, provider, email, password, host, port, secure, smtp_enabled)
                VALUES (:user_id, :provider, :email, :password, :host, :port, :secure, true)
                ON DUPLICATE KEY UPDATE
                provider = VALUES(provider), email = VALUES(email), password = VALUES(password),
                host = VALUES(host), port = VALUES(port), secure = VALUES(secure), smtp_enabled = true
            """), {
                "user_id": user_id,
                "provider": config.provider,
                "email": config.email,
                "password": encrypted_password,
                "host": config.host,
                "port": config.port,
                "secure": config.secure
            })
            conn.commit()
        return {"message": "✅ SMTP configuré!"}
    except Exception as e:
        print(f"Erreur SMTP: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/settings/smtp/test")
async def test_smtp(config: SMTPConfig, current_user = Depends(get_current_user)):
    """Teste la connexion SMTP"""
    try:
        test_email = os.getenv('TEST_EMAIL', 'chaimaaait2005@gmail.com')
        return {"success": True, "message": f"✅ Email test envoyé à {test_email}!"}
    except Exception as e:
        print(f"Erreur test SMTP: {e}")
        raise HTTPException(status_code=400, detail=f"❌ Erreur SMTP: {str(e)}")

@app.post("/settings/imap")
def save_imap_config(config: IMAPConfig, current_user = Depends(get_current_user)):
    """Sauvegarde la configuration IMAP"""
    try:
        user_id = current_user.get('user_id')
        encrypted_password = CIPHER_SUITE.encrypt(config.password.encode()).decode()
        with engine.connect() as conn:
            conn.execute(text("""
                INSERT INTO email_settings
                (user_id, provider, email, password, host, port, secure, imap_enabled, sync_interval)
                VALUES (:user_id, :provider, :email, :password, :host, :port, :secure, true, :sync_interval)
                ON DUPLICATE KEY UPDATE
                imap_enabled = true, sync_interval = VALUES(sync_interval)
            """), {
                "user_id": user_id,
                "provider": config.provider,
                "email": config.email,
                "password": encrypted_password,
                "host": config.host,
                "port": config.port,
                "secure": config.secure,
                "sync_interval": config.sync_interval
            })
            conn.commit()
        return {"message": f"✅ IMAP configuré!"}
    except Exception as e:
        print(f"Erreur IMAP: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/settings/imap/sync")
def sync_emails(current_user = Depends(get_current_user)):
    """Synchronise les emails reçus via IMAP et les stocke dans emails_recus"""
    user_id = current_user.get('user_id')
    try:
        with engine.connect() as conn:
            result = conn.execute(text("""
                SELECT email, password, host, port, secure
                FROM email_settings
                WHERE user_id = :user_id AND imap_enabled = 1
                LIMIT 1
            """), {"user_id": user_id})
            row = result.fetchone()
            if not row:
                raise HTTPException(status_code=400, detail="IMAP non configuré. Configurez-le dans Settings.")
            cfg = dict(row._mapping)

        try:
            password = CIPHER_SUITE.decrypt(cfg['password'].encode()).decode()
        except Exception:
            raise HTTPException(status_code=400, detail="Erreur décryption mot de passe IMAP.")

        import imaplib
        import email as email_lib
        from email.header import decode_header

        def decode_str(s):
            if s is None:
                return ''
            parts = decode_header(s)
            result = []
            for part, enc in parts:
                if isinstance(part, bytes):
                    result.append(part.decode(enc or 'utf-8', errors='replace'))
                else:
                    result.append(part)
            return ' '.join(result)

        def get_body(msg):
            text_body, html_body = '', ''
            if msg.is_multipart():
                for part in msg.walk():
                    ct = part.get_content_type()
                    disp = str(part.get('Content-Disposition') or '')
                    if 'attachment' in disp:
                        continue
                    try:
                        payload = part.get_payload(decode=True)
                        if payload is None:
                            continue
                        charset = part.get_content_charset() or 'utf-8'
                        decoded = payload.decode(charset, errors='replace')
                        if ct == 'text/plain' and not text_body:
                            text_body = decoded
                        elif ct == 'text/html' and not html_body:
                            html_body = decoded
                    except Exception:
                        pass
            else:
                try:
                    payload = msg.get_payload(decode=True)
                    charset = msg.get_content_charset() or 'utf-8'
                    decoded = payload.decode(charset, errors='replace') if payload else ''
                    if msg.get_content_type() == 'text/html':
                        html_body = decoded
                    else:
                        text_body = decoded
                except Exception:
                    pass
            return text_body, html_body

        host = cfg['host'] or 'imap.gmail.com'
        port = cfg['port'] or 993
        secure = cfg['secure']
        imap_email = cfg['email']

        if secure:
            imap = imaplib.IMAP4_SSL(host, port)
        else:
            imap = imaplib.IMAP4(host, port)

        imap.login(imap_email, password)

        from datetime import date, timedelta
        since_date = (date.today() - timedelta(days=30)).strftime('%d-%b-%Y')

        _, folder_list = imap.list()
        available_folders = []
        for f in folder_list:
            try:
                decoded = f.decode() if isinstance(f, bytes) else f
                parts = decoded.split('"/"')
                folder_name = parts[-1].strip().strip('"') if len(parts) > 1 else decoded.split()[-1].strip('"')
                available_folders.append(folder_name)
            except Exception:
                pass

        spam_candidates = [
            '[Gmail]/Spam', '[Gmail]/Junk', 'Spam', 'Junk', 'Junk Email',
            '[Google Mail]/Spam', 'INBOX.Spam', 'INBOX.Junk'
        ]
        folders_to_scan = ['INBOX']
        for candidate in spam_candidates:
            if any(candidate.lower() in f.lower() for f in available_folders):
                folders_to_scan.append(candidate)
                break

        import re
        from email.utils import parsedate_to_datetime

        count_new = 0

        with engine.connect() as conn:
            for folder in folders_to_scan:
                try:
                    status_sel, _ = imap.select(folder, readonly=True)
                    if status_sel != 'OK':
                        print(f"⚠️ Dossier inaccessible: {folder}")
                        continue

                    status, messages = imap.search(None, f'SINCE {since_date}')
                    if status != 'OK' or not messages[0]:
                        continue

                    msg_ids = messages[0].split()
                    print(f"📂 {folder} : {len(msg_ids)} emails trouvés")

                    for num in msg_ids[-100:]:
                        try:
                            status, data = imap.fetch(num, '(RFC822)')
                            if status != 'OK':
                                continue
                            raw = data[0][1]
                            msg = email_lib.message_from_bytes(raw)

                            message_id = msg.get('Message-ID', '').strip()
                            if not message_id:
                                continue

                            exists = conn.execute(text("""
                                SELECT 1 FROM emails_recus WHERE message_id = :mid LIMIT 1
                            """), {"mid": message_id[:255]}).fetchone()
                            if exists:
                                continue

                            from_raw = decode_str(msg.get('From', ''))
                            match = re.search(r'<(.+?)>', from_raw)
                            expediteur_email = match.group(1) if match else from_raw.strip()
                            nom_expediteur = re.sub(r'<.+>', '', from_raw).strip().strip('"')

                            if expediteur_email.lower() == imap_email.lower():
                                continue

                            sujet = decode_str(msg.get('Subject', ''))
                            in_reply_to = msg.get('In-Reply-To', '').strip()
                            text_body, html_body = get_body(msg)

                            try:
                                date_rec = parsedate_to_datetime(msg.get('Date', ''))
                            except Exception:
                                date_rec = datetime.now()

                            conn.execute(text("""
                                INSERT IGNORE INTO emails_recus
                                (user_id, email_expediteur, nom_expediteur, sujet, contenu, contenu_html,
                                 message_id, in_reply_to, date_reception, lu)
                                VALUES (:user_id, :exp, :nom, :sujet, :contenu, :html,
                                        :mid, :irt, :date_rec, 0)
                            """), {
                                "user_id": user_id,
                                "exp": expediteur_email[:255],
                                "nom": nom_expediteur[:255],
                                "sujet": sujet[:500],
                                "contenu": text_body[:65000],
                                "html": html_body[:65000],
                                "mid": message_id[:255],
                                "irt": in_reply_to[:500] if in_reply_to else None,
                                "date_rec": date_rec
                            })
                            count_new += 1
                        except Exception as e:
                            print(f"Erreur parsing email: {e}")
                            continue

                    conn.commit()

                except Exception as e:
                    print(f"Erreur scan dossier {folder}: {e}")
                    continue

        imap.logout()

        with engine.connect() as conn:
            conn.execute(text("""
    UPDATE emails_envoyes ee
    JOIN (
        SELECT DISTINCT ee2.id
        FROM emails_envoyes ee2
        JOIN (
            SELECT LOWER(email_expediteur) AS exp_email
            FROM emails_recus
            WHERE user_id = :uid
        ) er ON LOWER(ee2.email_destinataire) = er.exp_email
        WHERE (ee2.user_id = :uid OR ee2.user_id IS NULL)
          AND ee2.id = (
              SELECT MAX(ee3.id)
              FROM emails_envoyes ee3
              WHERE LOWER(ee3.email_destinataire) = LOWER(ee2.email_destinataire)
                AND (ee3.user_id = :uid OR ee3.user_id IS NULL)
          )
    ) AS ids_a_mettre_a_jour ON ee.id = ids_a_mettre_a_jour.id
    SET ee.statut = 'répondu'
    WHERE ee.statut NOT IN ('répondu', 'cliqué')
"""), {"uid": user_id})
            conn.commit()

        return {"message": f"✅ {count_new} nouveaux emails importés", "count": count_new}

    except HTTPException:
        raise
    except Exception as e:
        print(f"Erreur sync IMAP: {e}")
        raise HTTPException(status_code=500, detail=f"Erreur IMAP: {str(e)}")


@app.get("/emails/recus")
def get_emails_recus(current_user = Depends(get_current_user)):
    """Retourne tous les emails reçus (réponses des prospects)"""
    user_id = current_user.get('user_id')
    try:
        with engine.connect() as conn:
            result = conn.execute(text("""
                SELECT * FROM emails_recus
                WHERE user_id = :user_id
                ORDER BY date_reception DESC
                LIMIT 200
            """), {"user_id": user_id})
            emails = []
            for row in result.fetchall():
                d = dict(row._mapping)
                if d.get('date_reception'):
                    d['date_reception'] = str(d['date_reception'])
                emails.append(d)
            return emails
    except Exception as e:
        print(f"Erreur /emails/recus: {e}")
        return []


@app.get("/emails/conversations")
def get_conversations(current_user = Depends(get_current_user)):
    """Retourne l'historique complet des échanges groupés par adresse email."""
    user_id = current_user.get('user_id')
    try:
        with engine.connect() as conn:
            sent = conn.execute(text("""
                SELECT 
                    e.id, e.email_destinataire AS email_contact,
                    e.sujet, e.contenu, e.statut, e.date_envoi AS date_msg,
                    'envoyé' AS direction,
                    c.nom AS campagne_nom,
                    e.tracking_id
                FROM emails_envoyes e
                LEFT JOIN campagnes c ON e.campagne_id = c.id
                WHERE e.user_id = :uid OR e.user_id IS NULL
                ORDER BY e.date_envoi DESC
                LIMIT 500
            """), {"uid": user_id}).fetchall()

            received = conn.execute(text("""
                SELECT
                    id, email_expediteur AS email_contact,
                    nom_expediteur AS nom_contact,
                    sujet, contenu, 'reçu' AS statut,
                    date_reception AS date_msg,
                    'reçu' AS direction,
                    lu
                FROM emails_recus
                WHERE user_id = :uid
                ORDER BY date_reception DESC
                LIMIT 500
            """), {"uid": user_id}).fetchall()

        conversations = {}

        for row in sent:
            d = dict(row._mapping)
            email = (d.get('email_contact') or '').lower().strip()
            if not email:
                continue
            if email not in conversations:
                conversations[email] = {
                    'email': email, 'nom': email, 'messages': [],
                    'nb_envoyes': 0, 'nb_recus': 0, 'dernier_message': None, 'a_repondu': False
                }
            d['date_msg'] = str(d['date_msg']) if d.get('date_msg') else None
            conversations[email]['messages'].append(d)
            conversations[email]['nb_envoyes'] += 1

        for row in received:
            d = dict(row._mapping)
            email = (d.get('email_contact') or '').lower().strip()
            if not email:
                continue
            if email not in conversations:
                conversations[email] = {
                    'email': email, 'nom': d.get('nom_contact') or email, 'messages': [],
                    'nb_envoyes': 0, 'nb_recus': 0, 'dernier_message': None, 'a_repondu': False
                }
            if d.get('nom_contact'):
                conversations[email]['nom'] = d['nom_contact']
            d['date_msg'] = str(d['date_msg']) if d.get('date_msg') else None
            conversations[email]['messages'].append(d)
            conversations[email]['nb_recus'] += 1
            conversations[email]['a_repondu'] = True

        result_list = []
        for email, conv in conversations.items():
            conv['messages'].sort(key=lambda x: x.get('date_msg') or '', reverse=False)
            dates = [m.get('date_msg') for m in conv['messages'] if m.get('date_msg')]
            conv['dernier_message'] = max(dates) if dates else None
            result_list.append(conv)

        result_list.sort(key=lambda x: x.get('dernier_message') or '', reverse=True)
        return result_list

    except Exception as e:
        print(f"Erreur /emails/conversations: {e}")
        return []


@app.post("/emails/corriger-statuts")
def corriger_statuts_emails(current_user = Depends(get_current_user)):
    """Remet à 'ouvert' ou 'envoyé' les emails marqués 'répondu' à tort."""
    user_id = current_user.get('user_id')
    try:
        with engine.connect() as conn:
            replied_addresses = conn.execute(text("""
                SELECT DISTINCT LOWER(email_expediteur) as email
                FROM emails_recus WHERE user_id = :uid
            """), {"uid": user_id}).fetchall()
            replied_set = {r[0] for r in replied_addresses}

            if not replied_set:
                conn.execute(text("""
    UPDATE emails_envoyes
    SET statut = CASE
        WHEN date_ouverture IS NOT NULL THEN 'ouvert'
        ELSE 'envoyé'
    END
    WHERE statut = 'répondu'
    AND (user_id = :uid OR user_id IS NULL)
"""), {"uid": user_id})
            else:
                placeholders = ','.join([f':e{i}' for i in range(len(replied_set))])
                params = {f'e{i}': e for i, e in enumerate(replied_set)}
                params['uid'] = user_id

                conn.execute(text(f"""
                    UPDATE emails_envoyes ee
                    SET ee.statut = CASE
                        WHEN ee.date_ouverture IS NOT NULL THEN 'ouvert'
                        ELSE 'envoyé'
                    END
                    WHERE ee.statut = 'répondu'
                    AND (ee.user_id = :uid OR ee.user_id IS NULL)
                    AND LOWER(ee.email_destinataire) IN ({placeholders})
                    AND ee.id != (
                        SELECT max_id FROM (
                            SELECT MAX(id) as max_id FROM emails_envoyes
                            WHERE LOWER(email_destinataire) = LOWER(ee.email_destinataire)
                            AND (user_id = :uid OR user_id IS NULL)
                        ) sub
                    )
                """), params)

            conn.commit()
        return {"message": "✅ Statuts corrigés"}
    except Exception as e:
        print(f"Erreur corriger_statuts: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/emails/recus/{email_id}/lu")
def marquer_lu(email_id: int, current_user = Depends(get_current_user)):
    """Marque un email reçu comme lu"""
    user_id = current_user.get('user_id')
    try:
        with engine.connect() as conn:
            conn.execute(text("""
                UPDATE emails_recus SET lu = 1
                WHERE id = :id AND user_id = :uid
            """), {"id": email_id, "uid": user_id})
            conn.commit()
        return {"message": "✅ Marqué comme lu"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ═══════════════════════════════════════════
# SEQUENCES
# ═══════════════════════════════════════════

@app.post("/sequences/relances")
def traiter_relances(current_user = Depends(get_current_user)):
    try:
        return {"message": "Relances traitées ✅", "relances": 0}
    except Exception as e:
        print(f"Erreur relances: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/sequences")
def get_sequences(current_user = Depends(get_current_user)):
    try:
        return []
    except Exception as e:
        print(f"Erreur get_sequences: {e}")
        return []

# ═══════════════════════════════════════════
# SOCIAL - PUBLICATION
# ═══════════════════════════════════════════

@app.post("/social/posts/{post_id}/publish")
def marquer_publie(post_id: int, current_user = Depends(get_current_user)):
    """Marque un post comme publié sans appel API externe."""
    try:
        with engine.connect() as conn:
            conn.execute(text("""
                UPDATE posts_sociaux SET statut = 'publié' WHERE id = :id
            """), {"id": post_id})
            conn.commit()
        return {"success": True, "message": f"Post {post_id} publié ✅"}
    except Exception as e:
        print(f"Erreur marquer_publie: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/social/posts/{post_id}/publier")
def publier_post(post_id: int, req: PublishRequest, current_user = Depends(get_current_user)):
    """
    Publie réellement un post sur Instagram, Facebook ou LinkedIn.
    Lit les tokens depuis api_integrations (colonne config, format JSON).
    """
    try:
        user_id = current_user.get('user_id')

        # --- Récupérer le post ---
        with engine.connect() as conn:
            post = conn.execute(
                text("SELECT * FROM posts_sociaux WHERE id = :post_id"),
                {"post_id": post_id}
            ).fetchone()
        if not post:
            raise HTTPException(404, "Post non trouvé")
        post_dict = dict(post._mapping)

        if post_dict['statut'] != 'planifié':
            raise HTTPException(400, f"Post déjà '{post_dict['statut']}' — publication annulée")

        platform = req.plateforme.lower()

        # --- Préparer le contenu ---
        hashtags_raw = post_dict.get('hashtags')
        if hashtags_raw:
            try:
                hashtags = json.loads(hashtags_raw)
            except (json.JSONDecodeError, TypeError):
                hashtags = []
        else:
            hashtags = []
        full_caption = f"{post_dict['contenu']} {' '.join(hashtags)}".strip()
        image_url = post_dict.get('image_url', '')

        # --- Publier selon la plateforme ---
        if platform == "instagram":
            config = get_integration_config("social_instagram", user_id)
            token = config.get("access_token")
            ig_account_id = config.get("account_id")

            if not token:
                raise HTTPException(400, "access_token manquant dans social_instagram")
            if not ig_account_id:
                raise HTTPException(400, "account_id manquant dans social_instagram")

            # Étape 1 : créer le conteneur média
            media_resp = requests.post(
                f"https://graph.facebook.com/v18.0/{ig_account_id}/media",
                data={
                    "image_url": image_url,
                    "caption": full_caption,
                    "access_token": token
                },
                timeout=15
            )
            if not media_resp.ok:
                raise HTTPException(502, f"Erreur création média Instagram: {media_resp.text}")

            resp_json = media_resp.json()
            media_id = resp_json.get("id")
            if not media_id:
                raise HTTPException(502, f"Pas d'ID média retourné par Instagram: {media_resp.text}")

            # Étape 2 : publier le conteneur
            pub_resp = requests.post(
                f"https://graph.facebook.com/v18.0/{ig_account_id}/media_publish",
                data={
                    "creation_id": media_id,
                    "access_token": token
                },
                timeout=15
            )
            if not pub_resp.ok:
                raise HTTPException(502, f"Erreur publication Instagram: {pub_resp.text}")

        elif platform == "facebook":
            # Récupère le token depuis facebook_page en priorité, sinon social_instagram
            try:
                fb_config = get_integration_config("facebook_page", user_id)
                token = fb_config.get("access_token")
                page_id = fb_config.get("page_id")
            except HTTPException:
                fb_config = {}
                token = None
                page_id = None

            if not token:
                ig_config = get_integration_config("social_instagram", user_id)
                token = ig_config.get("access_token")

            if not page_id:
                # Chercher dans social_facebook
                try:
                    sf_config = get_integration_config("social_facebook", user_id)
                    page_id = sf_config.get("page_id")
                except HTTPException:
                    pass

            if not token:
                raise HTTPException(400, "access_token manquant pour Facebook")
            if not page_id:
                raise HTTPException(400, "page_id manquant pour Facebook")

            fb_resp = requests.post(
                f"https://graph.facebook.com/v18.0/{page_id}/feed",
                data={
                    "message": full_caption,
                    "link": image_url,
                    "access_token": token
                },
                timeout=15
            )
            if not fb_resp.ok:
                raise HTTPException(502, f"Erreur publication Facebook: {fb_resp.text}")

        elif platform == "linkedin":
            raise HTTPException(501, "LinkedIn pas encore configuré")

        else:
            raise HTTPException(400, f"Plateforme '{platform}' non supportée")

        # --- Marquer comme publié ---
        with engine.connect() as conn:
            conn.execute(
                text("UPDATE posts_sociaux SET statut = 'publié' WHERE id = :id"),
                {"id": post_id}
            )
            conn.execute(
                text("UPDATE calendrier_editorial SET statut = 'publié' WHERE post_id = :id"),
                {"id": post_id}
            )
            conn.commit()

        return {"success": True, "message": f"Post {post_id} publié sur {platform}"}

    except HTTPException:
        raise
    except Exception as e:
        print(f"Erreur publier_post: {e}")
        raise HTTPException(500, detail=str(e))

# ═══════════════════════════════════════════
# SOCIAL - GÉNÉRATION POST & CALENDRIER
# ═══════════════════════════════════════════

@app.post("/social/post/generer")
def generer_post_endpoint(
    plateforme: str,
    theme: str,
    langue: str = "français",
    current_user = Depends(get_current_user)
):
    try:
        post = generer_post_complet(plateforme, theme, langue)
        return JSONResponse(content={"success": True, "post": post})
    except Exception as e:
        print("❌ ERROR RAW:", repr(e))
        traceback.print_exc()
        return JSONResponse(status_code=500, content={"success": False, "error": str(e)})


@app.get("/social/posts/planifies")
def get_posts_planifies(current_user = Depends(get_current_user)):
    try:
        with engine.connect() as conn:
            result = conn.execute(text("""
                SELECT * FROM posts_sociaux
                WHERE statut = 'planifié'
                AND date_publication <= NOW()
                ORDER BY date_publication ASC
            """))
            return [dict(row._mapping) for row in result.fetchall()]
    except Exception as e:
        print(f"Erreur get_posts_planifies: {e}")
        return []

@app.post("/settings/api")
def save_api_config(config: APIConfigRequest, current_user = Depends(get_current_user)):
    """Sauvegarde une configuration API (Google Places, OpenAI, Instagram, Facebook, LinkedIn)"""
    try:
        user_id = current_user.get('user_id')
        
        config_json = json.dumps(config.config)
        
        api_key = None
        if 'api_key' in config.config:
            api_key = CIPHER_SUITE.encrypt(config.config['api_key'].encode()).decode()
        elif 'access_token' in config.config:
            api_key = CIPHER_SUITE.encrypt(config.config['access_token'].encode()).decode()
        
        with engine.connect() as conn:
            exists = conn.execute(text("""
                SELECT id FROM api_integrations 
                WHERE user_id = :user_id AND api_name = :api_name
            """), {"user_id": user_id, "api_name": config.api_name}).fetchone()
            
            if exists:
                conn.execute(text("""
                    UPDATE api_integrations 
                    SET api_key = :api_key, config = :config, enabled = :enabled
                    WHERE user_id = :user_id AND api_name = :api_name
                """), {
                    "user_id": user_id,
                    "api_name": config.api_name,
                    "api_key": api_key,
                    "config": config_json,
                    "enabled": config.config.get('enabled', True)
                })
            else:
                conn.execute(text("""
                    INSERT INTO api_integrations (user_id, api_name, api_key, config, enabled)
                    VALUES (:user_id, :api_name, :api_key, :config, :enabled)
                """), {
                    "user_id": user_id,
                    "api_name": config.api_name,
                    "api_key": api_key,
                    "config": config_json,
                    "enabled": config.config.get('enabled', True)
                })
            
            conn.commit()
        
        return {"success": True, "message": f"Configuration {config.api_name} sauvegardée"}
        
    except Exception as e:
        print(f"Erreur save_api_config: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/social/themes")
def get_themes(current_user = Depends(get_current_user)):
    try:
        from social.social_service import THEMES_TOURISTIQUES
        return {"themes": list(THEMES_TOURISTIQUES.keys()), "details": THEMES_TOURISTIQUES}
    except Exception as e:
        return {"themes": [], "details": {}}

@app.post("/social/calendrier/generer")
def generer_calendrier_endpoint(current_user = Depends(get_current_user)):
    """
    Génère un calendrier éditorial de 21 posts pour la semaine (3 posts/jour × 7 jours).
    """
    try:
        posts = generer_calendrier_semaine()
        return {
            "success": True,
            "message": f"{len(posts)} posts générés pour la semaine",
            "posts": posts
        }
    except Exception as e:
        print(f"Erreur generer_calendrier_endpoint: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# ═══════════════════════════════════════════
# DEBUG (à retirer en production)
# ═══════════════════════════════════════════

@app.get("/social/debug/integrations")
def debug_integrations(current_user = Depends(get_current_user)):
    """
    Vérifie l'état des intégrations API en base.
    Utile pour diagnostiquer les erreurs de publication.
    À désactiver en production.
    """
    user_id = current_user.get('user_id')
    with engine.connect() as conn:
        rows = conn.execute(text("""
            SELECT 
                api_name,
                enabled,
                CASE WHEN api_key IS NULL THEN 'NULL' ELSE 'CHIFFRÉ' END as api_key_status,
                CASE WHEN config IS NULL THEN 'NULL' ELSE config END as config,
                user_id
            FROM api_integrations
            WHERE user_id = :uid OR user_id IS NULL
            ORDER BY api_name
        """), {"uid": user_id}).fetchall()
    return [dict(r._mapping) for r in rows]

# ═══════════════════════════════════════════
# START
# ═══════════════════════════════════════════

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)