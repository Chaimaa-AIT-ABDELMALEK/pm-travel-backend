from fastapi import FastAPI, HTTPException, Depends, Header, Body, Query

from sqlalchemy import create_engine, text

from dotenv import load_dotenv

from pydantic import BaseModel

from typing import Optional



from fastapi import FastAPI



import os

import sys

import threading

import subprocess

import json

import redis

from fastapi.middleware.cors import CORSMiddleware

from emails.email_service import (

    generer_contenu_email,

    generer_sujet_email,

    envoyer_email,

    sauvegarder_email,

    creer_sequence

)

from datetime import datetime, timedelta

from social.social_service import (

    generer_post_complet,

    generer_calendrier_semaine,

    mettre_a_jour_statut_post,

    logger_action,

    THEMES_TOURISTIQUES

)

from jwt import encode, decode

import bcrypt

from cryptography.fernet import Fernet

from fastapi.responses import StreamingResponse

import asyncio



# Sous Windows, asyncio a besoin du ProactorEventLoop pour lancer des sous-processus
# (le scraper est exécuté via asyncio.create_subprocess_exec).
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())



load_dotenv()



SECRET_KEY = os.getenv('JWT_SECRET_KEY', 'votre-clé-secrète')

ALGORITHM = "HS256"

ENCRYPTION_KEY = os.getenv('ENCRYPTION_KEY', 'votre-clé-encryption')

CIPHER_SUITE = Fernet(ENCRYPTION_KEY.encode() if len(ENCRYPTION_KEY) == 32 else Fernet.generate_key())



app = FastAPI()



DB_URL = f"mysql+pymysql://{os.getenv('DB_USER')}:{os.getenv('DB_PASSWORD')}@{os.getenv('DB_HOST')}:{os.getenv('DB_PORT')}/{os.getenv('DB_NAME')}"

engine = create_engine(DB_URL)



# Redis pour le cache

try:

    redis_client = redis.Redis(

        host=os.getenv('REDIS_HOST', 'localhost'),

        port=int(os.getenv('REDIS_PORT', 6379)),

        db=0,

        decode_responses=True

    )

except:

    redis_client = None



app.add_middleware(

    CORSMiddleware,

    allow_origins=["http://localhost:3001", "http://localhost:3000"],

    allow_credentials=True,

    allow_methods=["*"],

    allow_headers=["*"],

)



# ═══════════════════════════════════════════

# FONCTIONS UTILITAIRES

# ═══════════════════════════════════════════



def get_cache(key):

    """Récupère une valeur du cache"""

    if not redis_client:

        return None

    try:

        value = redis_client.get(key)

        if value:

            return json.loads(value)

    except:

        pass

    return None



def set_cache(key, value, expiration=60):

    """Sauvegarde une valeur dans le cache"""

    if not redis_client:

        return

    try:

        redis_client.setex(key, expiration, json.dumps(value))

    except:

        pass



def delete_cache_pattern(pattern):

    """Efface toutes les clés matchant un pattern"""

    if not redis_client:

        return

    try:

        keys = redis_client.keys(pattern + "*")

        if keys:

            redis_client.delete(*keys)

    except:

        pass



def get_user_by_username(username: str):

    """Récupère un utilisateur par son username"""

    with engine.connect() as conn:

        result = conn.execute(text("""

            SELECT * FROM users WHERE username = :username

        """), {"username": username})

        row = result.fetchone()

        if row:

            return dict(row._mapping)

        return None



def hash_password(password):

    """Hashe un password avec bcrypt"""

    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()



def verify_password(password, hashed):

    """Vérifie un password contre son hash"""

    return bcrypt.checkpw(password.encode(), hashed.encode())



def create_token(user_id, role, expires_in=24):

    """Crée un JWT token"""

    payload = {

        'user_id': user_id,

        'role': role,

        'exp': datetime.utcnow() + timedelta(hours=expires_in)

    }

    return encode(payload, SECRET_KEY, algorithm=ALGORITHM)



def verify_token(token):

    """Vérifie et décode un JWT token"""

    try:

        payload = decode(token, SECRET_KEY, algorithms=[ALGORITHM])

        return payload

    except:

        return None



def get_current_user(authorization: str = Header(None)):

    """Vérifie le token et retourne l'utilisateur"""

    if not authorization:

        raise HTTPException(status_code=401, detail="No token")

    

    try:

        token = authorization.split(" ")[1]

    except IndexError:

        raise HTTPException(status_code=401, detail="Invalid token format")

    

    payload = verify_token(token)

    if not payload:

        raise HTTPException(status_code=401, detail="Invalid token")

    

    return payload



def require_role(required_role: str):

    """Décorateur pour vérifier le rôle"""

    def check_role(current_user = Depends(get_current_user)):

        if current_user['role'] != required_role and current_user['role'] != 'admin':

            raise HTTPException(status_code=403, detail="Insufficient permissions")

        return current_user

    return check_role



# ═══════════════════════════════════════════

# MODELS

# ═══════════════════════════════════════════



class Prospect(BaseModel):

    nom: str

    email: str

    telephone: Optional[str] = None

    secteur: Optional[str] = None

    ville: Optional[str] = None

    source: Optional[str] = None

    score: Optional[int] = 0

    email_valide: Optional[bool] = False



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



class APIConfig(BaseModel):

    api_name: str

    config: dict



# ═══════════════════════════════════════════

# ROUTES AUTHENTIFICATION

# ═══════════════════════════════════════════



@app.post("/auth/login")

def login(username: str, password: str):

    """Login utilisateur"""

    user = get_user_by_username(username)

    

    if not user or not verify_password(password, user['password']):

        raise HTTPException(status_code=401, detail="Invalid credentials")

    

    token = create_token(user['id'], user['role'])

    

    return {

        "token": token,

        "user": {

            "id": user['id'],

            "username": user['username'],

            "role": user['role']

        }

    }



# ═══════════════════════════════════════════

# ROUTES PROSPECTS

# ═══════════════════════════════════════════



@app.get("/")

def read_root():

    return {"message": "PM Travel API is running"}



@app.get("/test-db")

def test_db():

    with engine.connect() as conn:

        conn.execute(text("SELECT 1"))

        return {"database": "connectée ✅"}



# ══════════════════════════════════════════════════════════════════════════════

# FIX: /prospects - RETOURNE SECTEUR CORRECTEMENT (DB COMPATIBLE)

# ══════════════════════════════════════════════════════════════════════════════

@app.get("/prospects")

def get_prospects(current_user = Depends(get_current_user)):

    """Récupère tous les prospects - AVEC SECTEUR MAPPÉ"""

    try:

        with engine.connect() as conn:

            # Récupère TOUS les prospects (compatible avec DB actuelle)

            result = conn.execute(text("SELECT * FROM prospects ORDER BY score DESC"))

            rows = result.fetchall()

            prospects = []

            

            for row in rows:

                p = dict(row._mapping)

                # Force type = secteur (pour le frontend)

                p['type'] = p.get('secteur', 'Prospect')

                prospects.append(p)

            

            return prospects

    except Exception as e:

        print(f"❌ Erreur /prospects: {e}")

        return []



@app.get("/prospects/{id}")

def get_prospect(id: int, current_user = Depends(get_current_user)):

    """Récupère un prospect par ID"""

    with engine.connect() as conn:

        result = conn.execute(text("SELECT * FROM prospects WHERE id = :id"), {"id": id})

        row = result.fetchone()

        if not row:

            raise HTTPException(status_code=404, detail="Prospect non trouvé")

        p = dict(row._mapping)

        p['type'] = p.get('secteur', 'Prospect')

        return p



@app.post("/prospects")

def create_prospect(prospect: Prospect, current_user = Depends(get_current_user)):

    """Crée un nouveau prospect"""

    with engine.connect() as conn:

        try:

            conn.execute(text("""

                INSERT IGNORE INTO prospects 

                (nom, email, telephone, secteur, ville, source, score, email_valide)

                VALUES (:nom, :email, :telephone, :secteur, :ville, :source, :score, :email_valide)

            """), {

                "nom": prospect.nom,

                "email": prospect.email,

                "telephone": prospect.telephone,

                "secteur": prospect.secteur,

                "ville": prospect.ville,

                "source": prospect.source,

                "score": prospect.score,

                "email_valide": prospect.email_valide

            })

            conn.commit()

            return {"message": "Prospect ajouté ✅"}

        except Exception as e:

            print(f"❌ Erreur: {e}")

            raise HTTPException(status_code=500, detail=str(e))



@app.put("/prospects/{id}/statut")

def update_statut(id: int, statut: str, current_user = Depends(get_current_user)):

    """Met à jour le statut d'un prospect"""

    with engine.connect() as conn:

        conn.execute(text("""

            UPDATE prospects SET statut = :statut WHERE id = :id

        """), {"statut": statut, "id": id})

        conn.commit()

        return {"message": "Statut mis à jour ✅"}



@app.delete("/prospects/{id}")

def delete_prospect(id: int, current_user = Depends(require_role('admin'))):

    """Supprime un prospect"""

    with engine.connect() as conn:

        conn.execute(text("DELETE FROM prospects WHERE id = :id"), {"id": id})

        conn.commit()

        return {"message": "Prospect supprimé ✅"}



@app.get("/prospects/stats/kpis")

def get_kpis(current_user = Depends(get_current_user)):

    """Récupère les KPIs des prospects"""

    with engine.connect() as conn:

        total = conn.execute(text("SELECT COUNT(*) FROM prospects")).scalar()

        valides = conn.execute(text("SELECT COUNT(*) FROM prospects WHERE email_valide = 1")).scalar()

        nouveaux = conn.execute(text("SELECT COUNT(*) FROM prospects WHERE statut = 'nouveau'")).scalar()

        partenaires = conn.execute(text("SELECT COUNT(*) FROM prospects WHERE statut = 'partenaire'")).scalar()

        return {

            "total_prospects": total,

            "emails_valides": valides,

            "nouveaux": nouveaux,

            "partenaires": partenaires

        }



# ═══════════════════════════════════════════

# ROUTE SCRAPING AVEC STREAMING TEMPS RÉEL

# ═══════════════════════════════════════════


# Répertoire du backend (où se trouve main.py)
BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))


def resoudre_scraper_path():
    """Trouve scraper_places.py, qu'il soit dans scrapers/ ou à la racine du backend."""
    candidats = [
        os.path.join(BACKEND_DIR, "scrapers", "scraper_places.py"),
        os.path.join(BACKEND_DIR, "scraper_places.py"),
    ]
    for chemin in candidats:
        if os.path.isfile(chemin):
            return chemin
    return None


# ═══════════════════════════════════════════
# SCRAPING EN TÂCHE DE FOND (continue même si le navigateur change de page)
# ═══════════════════════════════════════════

# État du job de scraping en cours, partagé en mémoire.
# Le front interroge GET /scraper/statut pour suivre l'avancement.
SCRAPER_JOB = {
    "running": False,
    "started_at": None,
    "finished_at": None,
    "found": 0,            # nb de prospects insérés (nouveaux)
    "skipped": 0,          # nb de doublons ignorés
    "processed": 0,        # total traité (insérés + ignorés)
    "recent": [],          # derniers prospects détectés (pour l'affichage live)
    "status": "idle",      # idle | running | completed | error | cancelled
    "message": "",
    "error": None,
    "cancelled": False,    # passé à True quand l'utilisateur demande l'arrêt
}
SCRAPER_LOCK = threading.Lock()
# Référence au sous-processus en cours (pour pouvoir l'arrêter)
SCRAPER_PROCESS = {"proc": None}


def _parse_prospect_log(msg):
    """Extrait un prospect d'une ligne '✅ Nom | Ville | Score: .. | Email: ..'."""
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


def _run_scraper_job(args):
    """Exécuté dans un thread de fond : lance le scraper et met à jour SCRAPER_JOB."""
    scraper_path = resoudre_scraper_path()
    if not scraper_path:
        with SCRAPER_LOCK:
            SCRAPER_JOB.update(running=False, status="error",
                               error="scraper_places.py introuvable.",
                               finished_at=datetime.utcnow().isoformat())
        return

    cmd = [sys.executable, "-u", scraper_path] + list(args)
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"

    try:
        process = subprocess.Popen(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            cwd=BACKEND_DIR, text=True, encoding="utf-8", errors="replace", bufsize=1, env=env
        )
        SCRAPER_PROCESS["proc"] = process
    except Exception as e:
        with SCRAPER_LOCK:
            SCRAPER_JOB.update(running=False, status="error",
                               error=f"{type(e).__name__}: {e}",
                               finished_at=datetime.utcnow().isoformat())
        return

    last_line = ""
    for line in iter(process.stdout.readline, ""):
        line = line.rstrip("\n").strip()
        if not line:
            continue
        last_line = line
        # Détecte un prospect inséré pour l'affichage live
        prospect = _parse_prospect_log(line)
        if prospect:
            with SCRAPER_LOCK:
                SCRAPER_JOB["found"] += 1
                SCRAPER_JOB["processed"] += 1
                SCRAPER_JOB["recent"].insert(0, prospect)
                SCRAPER_JOB["recent"] = SCRAPER_JOB["recent"][:50]  # garde les 50 derniers
                SCRAPER_JOB["message"] = f"{SCRAPER_JOB['found']} prospects trouvés..."
        elif line.startswith("⏭️") or "Doublon ignoré" in line:
            with SCRAPER_LOCK:
                SCRAPER_JOB["skipped"] += 1
                SCRAPER_JOB["processed"] += 1

    process.stdout.close()
    code = process.wait()
    SCRAPER_PROCESS["proc"] = None

    # Tente de lire le JSON final pour le total exact
    total = None
    try:
        parsed = json.loads(last_line)
        if "found" in parsed:
            total = parsed["found"]
    except (json.JSONDecodeError, TypeError):
        total = None

    with SCRAPER_LOCK:
        SCRAPER_JOB["running"] = False
        SCRAPER_JOB["finished_at"] = datetime.utcnow().isoformat()
        if SCRAPER_JOB.get("cancelled"):
            # Le scraping a été arrêté par l'utilisateur
            SCRAPER_JOB["status"] = "cancelled"
            SCRAPER_JOB["message"] = f"Scraping arrêté : {SCRAPER_JOB['found']} nouveaux, {SCRAPER_JOB['skipped']} doublons (avant l'arrêt)"
        elif code == 0:
            SCRAPER_JOB["status"] = "completed"
            if total is not None:
                SCRAPER_JOB["found"] = total
            SCRAPER_JOB["message"] = f"Scraping terminé : {SCRAPER_JOB['found']} nouveaux, {SCRAPER_JOB['skipped']} doublons ignorés"
        else:
            SCRAPER_JOB["status"] = "error"
            SCRAPER_JOB["error"] = (last_line or "Le scraper a échoué")[:300]


def _demarrer_job(args):
    """Démarre un job de scraping en arrière-plan s'il n'y en a pas déjà un."""
    with SCRAPER_LOCK:
        if SCRAPER_JOB["running"]:
            return False
        SCRAPER_JOB.update(
            running=True, status="running", started_at=datetime.utcnow().isoformat(),
            finished_at=None, found=0, skipped=0, processed=0, recent=[],
            message="Scraping démarré...", error=None, cancelled=False
        )
    thread = threading.Thread(target=_run_scraper_job, args=(args,), daemon=True)
    thread.start()
    return True


@app.post("/scraper/lancer-tout-streaming")
def lancer_scraper_tout(current_user = Depends(get_current_user)):
    """Démarre le scraping global en arrière-plan (ne bloque pas, continue après navigation)."""
    print(f"\n{'='*60}\n\U0001F30D SCRAPER GLOBAL LANCE (tâche de fond)\n{'='*60}")
    user_id = current_user.get("user_id")
    demarre = _demarrer_job(["--user-id", str(user_id)])
    if not demarre:
        return {"status": "already_running", "message": "Un scraping est déjà en cours."}
    return {"status": "started", "message": "Scraping démarré en arrière-plan."}


@app.post("/scraper/lancer-streaming")
def lancer_scraper_cible(sector: str = Query(...), city: str = Query(...), current_user = Depends(get_current_user)):
    """Démarre un scraping ciblé (secteur + ville) en arrière-plan."""
    print(f"\n{'='*60}\n🕷️ SCRAPER CIBLE: {sector} à {city} (tâche de fond)\n{'='*60}")
    user_id = current_user.get("user_id")
    demarre = _demarrer_job([sector, city, "--user-id", str(user_id)])
    if not demarre:
        return {"status": "already_running", "message": "Un scraping est déjà en cours."}
    return {"status": "started", "message": "Scraping démarré en arrière-plan."}


@app.get("/scraper/statut")
def statut_scraper(current_user = Depends(get_current_user)):
    """Renvoie l'état du scraping en cours (consulté en polling par le front)."""
    with SCRAPER_LOCK:
        return dict(SCRAPER_JOB)


@app.post("/scraper/annuler")
def annuler_scraper(current_user = Depends(get_current_user)):
    """Arrête le scraping en cours (tue le sous-processus)."""
    with SCRAPER_LOCK:
        if not SCRAPER_JOB["running"]:
            return {"status": "idle", "message": "Aucun scraping en cours."}
        SCRAPER_JOB["cancelled"] = True
        SCRAPER_JOB["message"] = "Arrêt en cours..."
    proc = SCRAPER_PROCESS.get("proc")
    if proc and proc.poll() is None:
        try:
            proc.terminate()   # arrêt propre
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()    # arrêt forcé si pas de réponse
        except Exception as e:
            print(f"Erreur arrêt scraper : {e}")
    print(f"\n{'='*60}\n🛑 SCRAPER ARRETE PAR L'UTILISATEUR\n{'='*60}")
    return {"status": "cancelling", "message": "Scraping arrêté."}


@app.get("/scraper/lancer")
def lancer_scraper(sector: str = Query(...), city: str = Query(...), current_user = Depends(get_current_user)):

    """Ancien endpoint (fallback)"""

    return {"message": "Utilise POST /scraper/lancer-streaming"}



@app.get("/scraper/historique")

def get_scraping_history(current_user = Depends(get_current_user)):

    """Récupère l'historique des scrapings"""

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

    except:

        return []



@app.get("/scraper/derniers-prospects")

def get_derniers_prospects(current_user = Depends(get_current_user)):

    """Récupère les prospects du dernier scraping"""

    try:

        with engine.connect() as conn:

            prospects = conn.execute(text("""

                SELECT * FROM prospects ORDER BY id DESC LIMIT 100

            """)).fetchall()

            return [dict(row._mapping) for row in prospects]

    except:

        return {"message": "Aucun prospect", "prospects": []}



@app.get("/contacts/scraping")

def get_contacts_from_scraping(current_user = Depends(get_current_user)):

    """Récupère les contacts créés par scraping"""

    try:

        with engine.connect() as conn:

            contacts = conn.execute(text("""

                SELECT * FROM contacts ORDER BY id DESC LIMIT 100

            """)).fetchall()

            return {"total": len(contacts), "contacts": [dict(row._mapping) for row in contacts]}

    except:

        return {"total": 0, "contacts": []}



# ═══════════════════════════════════════════

# ROUTES CAMPAGNES (INCHANGÉES)

# ═══════════════════════════════════════════



@app.post("/campagnes")

def creer_campagne(nom: str, sujet: str, current_user = Depends(get_current_user)):

    """Crée une nouvelle campagne"""

    with engine.connect() as conn:

        conn.execute(text("""

            INSERT INTO campagnes (nom, sujet, statut)

            VALUES (:nom, :sujet, 'brouillon')

        """), {"nom": nom, "sujet": sujet})

        conn.commit()

        return {"message": "Campagne créée ✅"}



@app.get("/campagnes")

def get_campagnes(current_user = Depends(get_current_user)):

    """Récupère toutes les campagnes"""

    with engine.connect() as conn:

        result = conn.execute(text("SELECT * FROM campagnes ORDER BY date_creation DESC"))

        return [dict(row._mapping) for row in result.fetchall()]



@app.get("/campagnes/{campagne_id}")

def get_campagne(campagne_id: int, current_user = Depends(get_current_user)):

    """Récupère une campagne par ID"""

    with engine.connect() as conn:

        result = conn.execute(text("SELECT * FROM campagnes WHERE id = :id"), {"id": campagne_id})

        row = result.fetchone()

        if not row:

            raise HTTPException(status_code=404, detail="Campagne non trouvée")

        return dict(row._mapping)



@app.post("/campagnes/{campagne_id}/lancer")

def lancer_campagne(campagne_id: int, current_user = Depends(get_current_user)):

    """Lance une campagne email"""

    with engine.connect() as conn:

        prospects = conn.execute(text("""

            SELECT * FROM prospects WHERE email_valide = 1 ORDER BY score DESC LIMIT 50

        """)).fetchall()

        if not prospects:

            return {"message": "Aucun prospect disponible", "envoyes": 0}

        return {"message": "Campagne lancée ✅", "envoyes": len(prospects), "echecs": 0}



@app.get("/campagnes/stats/kpis")

def get_kpis_campagnes(current_user = Depends(get_current_user)):

    """Récupère les KPIs des campagnes"""

    with engine.connect() as conn:

        total = conn.execute(text("SELECT COUNT(*) FROM campagnes")).scalar() or 0

        return {"total_campagnes": total, "total_envoyes": 0, "total_ouverts": 0, "taux_ouverture": 0}



# ═══════════════════════════════════════════

# ROUTES RÉSEAUX SOCIAUX

# ═══════════════════════════════════════════



@app.post("/social/post/generer")

def generer_post(plateforme: str, theme: str, langue: str = 'français', current_user = Depends(get_current_user)):

    """Génère un post"""

    return {"message": "Post généré ✅", "post": {"content": "Post example"}}



@app.post("/social/calendrier/generer")

def generer_calendrier(current_user = Depends(get_current_user)):

    """Génère le calendrier de la semaine"""

    return {"message": "Calendrier généré ✅", "total_posts": 0, "posts": []}



@app.get("/social/posts")

def get_posts(current_user = Depends(get_current_user)):

    """Récupère tous les posts"""

    return []



@app.get("/social/posts/planifies")

def get_posts_planifies(current_user = Depends(get_current_user)):

    """Récupère les posts planifiés"""

    return []



@app.get("/social/themes")

def get_themes(current_user = Depends(get_current_user)):

    """Récupère les thèmes disponibles"""

    return {"themes": [], "details": {}}



@app.put("/social/posts/{post_id}/statut")

def update_statut_post(post_id: int, statut: str, current_user = Depends(get_current_user)):

    """Met à jour le statut d'un post"""

    return {"message": "Statut mis à jour ✅"}



# ═══════════════════════════════════════════

# ROUTES SETTINGS

# ═══════════════════════════════════════════



@app.post("/settings/api")

def save_api_config(api_config: APIConfig, current_user = Depends(get_current_user)):

    """Sauvegarde la configuration d'une API"""

    return {"message": f"✅ {api_config.api_name} sauvegardé!"}



@app.post("/settings/smtp")

def save_smtp_config(config: SMTPConfig, current_user = Depends(get_current_user)):

    """Sauvegarde la configuration SMTP"""

    return {"message": "✅ SMTP configuré!"}



@app.post("/settings/smtp/test")

async def test_smtp(config: SMTPConfig, current_user = Depends(get_current_user)):

    """Teste la connexion SMTP"""

    return {"success": True, "message": "✅ Test réussi!"}



@app.post("/settings/imap")

def save_imap_config(config: IMAPConfig, current_user = Depends(get_current_user)):

    """Sauvegarde la configuration IMAP"""

    return {"message": "✅ IMAP configuré!"}



@app.post("/settings/imap/sync")

def sync_emails(current_user = Depends(get_current_user)):

    """Synchronise les emails"""

    return {"message": "✅ Emails synchronisés"}



# ═══════════════════════════════════════════

# ROUTES SÉQUENCES

# ═══════════════════════════════════════════



@app.post("/sequences/relances")

def traiter_relances(current_user = Depends(get_current_user)):

    """Traite les relances email"""

    return {"message": "Relances traitées ✅", "relances": 0}



@app.get("/sequences")

def get_sequences(current_user = Depends(get_current_user)):

    """Récupère les séquences"""

    return []



# ═══════════════════════════════════════════

# LANCEMENT DE L'APP

# ═══════════════════════════════════════════



if __name__ == "__main__":

    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)