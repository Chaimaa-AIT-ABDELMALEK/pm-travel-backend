from fastapi import FastAPI, HTTPException, Depends, Header
from sqlalchemy import create_engine, text
from dotenv import load_dotenv
from pydantic import BaseModel
from typing import Optional
import os
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

@app.get("/prospects")
def get_prospects(current_user = Depends(get_current_user)):
    """Récupère tous les prospects"""
    with engine.connect() as conn:
        result = conn.execute(text("SELECT * FROM prospects ORDER BY score DESC"))
        rows = result.fetchall()
        return [dict(row._mapping) for row in rows]

@app.get("/prospects/{id}")
def get_prospect(id: int, current_user = Depends(get_current_user)):
    """Récupère un prospect par ID"""
    with engine.connect() as conn:
        result = conn.execute(text("SELECT * FROM prospects WHERE id = :id"), {"id": id})
        row = result.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Prospect non trouvé")
        return dict(row._mapping)

@app.post("/prospects")
def create_prospect(prospect: Prospect, current_user = Depends(get_current_user)):
    """Crée un nouveau prospect"""
    with engine.connect() as conn:
        conn.execute(text("""
            INSERT IGNORE INTO prospects 
            (user_id, nom, email, telephone, secteur, ville, source, score, email_valide)
            VALUES (:user_id, :nom, :email, :telephone, :secteur, :ville, :source, :score, :email_valide)
        """), {
            "user_id": current_user['user_id'],
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

@app.post("/scraper/lancer")
def lancer_scraper(current_user = Depends(require_role('manager'))):
    """Lance le scraper Google Maps"""
    try:
        subprocess.Popen(["python", "scrapers/scraper_places.py"])
        return {"message": "Scraper Google Maps lancé ✅"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ═══════════════════════════════════════════
# ROUTES CAMPAGNES
# ═══════════════════════════════════════════

@app.post("/campagnes")
def creer_campagne(nom: str, sujet: str, current_user = Depends(get_current_user)):
    """Crée une nouvelle campagne"""
    with engine.connect() as conn:
        conn.execute(text("""
            INSERT INTO campagnes (user_id, nom, sujet, statut)
            VALUES (:user_id, :nom, :sujet, 'brouillon')
        """), {
            "user_id": current_user['user_id'],
            "nom": nom,
            "sujet": sujet
        })
        conn.commit()
        result = conn.execute(text("SELECT LAST_INSERT_ID()"))
        campagne_id = result.scalar()
        return {"message": "Campagne créée ✅", "id": campagne_id}

@app.get("/campagnes")
def get_campagnes(current_user = Depends(get_current_user)):
    """Récupère toutes les campagnes"""
    with engine.connect() as conn:
        result = conn.execute(text("""
            SELECT * FROM campagnes WHERE user_id = :user_id ORDER BY date_creation DESC
        """), {"user_id": current_user['user_id']})
        return [dict(row._mapping) for row in result.fetchall()]

@app.get("/campagnes/{campagne_id}")
def get_campagne(campagne_id: int, current_user = Depends(get_current_user)):
    """Récupère une campagne par ID"""
    with engine.connect() as conn:
        result = conn.execute(text("""
            SELECT * FROM campagnes WHERE id = :id AND user_id = :user_id
        """), {"id": campagne_id, "user_id": current_user['user_id']})
        row = result.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Campagne non trouvée")
        return dict(row._mapping)

@app.post("/campagnes/{campagne_id}/lancer")
def lancer_campagne(campagne_id: int, current_user = Depends(get_current_user)):
    """Lance une campagne email"""
    with engine.connect() as conn:
        prospects = conn.execute(text("""
            SELECT * FROM prospects
            WHERE user_id = :user_id
            AND statut = 'nouveau'
            AND email_valide = 1
            ORDER BY score DESC
            LIMIT 50
        """), {"user_id": current_user['user_id']}).fetchall()

        if not prospects:
            return {"message": "Aucun prospect disponible", "envoyes": 0}

        envoyes = 0
        echecs = 0

        for row in prospects:
            prospect = dict(row._mapping)
            print(f"\n📧 Traitement : {prospect['nom']}")

            try:
                contenu = generer_contenu_email(prospect)
                sujet = generer_sujet_email(prospect)

                succes = envoyer_email(
                    prospect['email'],
                    sujet,
                    contenu,
                    prospect['nom']
                )

                if succes:
                    sauvegarder_email(
                        campagne_id,
                        prospect['id'],
                        prospect['email'],
                        sujet,
                        contenu,
                        'envoyé'
                    )
                    creer_sequence(campagne_id, prospect['id'])
                    conn.execute(text("""
                        UPDATE prospects SET statut = 'contacté'
                        WHERE id = :id
                    """), {"id": prospect['id']})
                    envoyes += 1
                else:
                    echecs += 1
                    sauvegarder_email(
                        campagne_id,
                        prospect['id'],
                        prospect['email'],
                        sujet,
                        contenu,
                        'échec'
                    )

            except Exception as e:
                print(f"❌ Erreur pour {prospect['nom']} : {e}")
                echecs += 1
                continue

        conn.execute(text("""
            UPDATE campagnes SET
            statut = 'en_cours',
            date_envoi = :date,
            total_envoyes = :total
            WHERE id = :id
        """), {
            "date": datetime.now(),
            "total": envoyes,
            "id": campagne_id
        })
        conn.commit()

        return {
            "message": "Campagne lancée ✅",
            "envoyes": envoyes,
            "echecs": echecs
        }
@app.get("/campagnes/stats/kpis")
def get_kpis_campagnes(current_user = Depends(get_current_user)):
    """Récupère les KPIs des campagnes"""
    with engine.connect() as conn:
        total_campagnes = conn.execute(text(
            "SELECT COUNT(*) FROM campagnes WHERE user_id = :user_id"
        ), {"user_id": current_user['user_id']}).scalar() or 0
        
        total_envoyes = conn.execute(text(
            "SELECT COALESCE(SUM(total_envoyes), 0) FROM campagnes WHERE user_id = :user_id"
        ), {"user_id": current_user['user_id']}).scalar() or 0
        
        total_ouverts = conn.execute(text(
            "SELECT COALESCE(SUM(total_ouverts), 0) FROM campagnes WHERE user_id = :user_id"
        ), {"user_id": current_user['user_id']}).scalar() or 0
        
        taux_ouverture = round((total_ouverts / total_envoyes * 100), 1) if total_envoyes > 0 else 0
        
        return {
            "total_campagnes": total_campagnes,
            "total_envoyes": total_envoyes,
            "total_ouverts": total_ouverts,
            "taux_ouverture": taux_ouverture
        }

# ═══════════════════════════════════════════
# ROUTES RÉSEAUX SOCIAUX
# ═══════════════════════════════════════════

@app.post("/social/post/generer")
def generer_post(plateforme: str, theme: str, langue: str = 'français', current_user = Depends(get_current_user)):
    """Génère un post"""
    try:
        post = generer_post_complet(plateforme, theme, langue)
        delete_cache_pattern("social*")
        return {"message": "Post généré ✅", "post": post}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/social/calendrier/generer")
def generer_calendrier(current_user = Depends(get_current_user)):
    """Génère le calendrier de la semaine"""
    try:
        posts = generer_calendrier_semaine()
        delete_cache_pattern("social*")
        return {
            "message": f"Calendrier généré ✅ — {len(posts)} posts créés",
            "total_posts": len(posts),
            "posts": posts
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/social/posts")
def get_posts(current_user = Depends(get_current_user)):
    """Récupère tous les posts"""
    cache_key = "social:posts"
    cached = get_cache(cache_key)
    if cached:
        return cached

    with engine.connect() as conn:
        result = conn.execute(text("""
            SELECT * FROM posts_sociaux WHERE user_id = :user_id
            ORDER BY date_creation DESC
        """), {"user_id": current_user['user_id']})
        data = [dict(row._mapping) for row in result.fetchall()]

    set_cache(cache_key, data, expiration=60)
    return data

@app.get("/social/posts/planifies")
def get_posts_planifies(current_user = Depends(get_current_user)):
    """Récupère les posts planifiés"""
    try:
        with engine.connect() as conn:
            result = conn.execute(text("""
                SELECT * FROM posts_sociaux
                WHERE user_id = :user_id
                AND statut = 'planifié'
                AND date_publication <= NOW()
                ORDER BY date_publication ASC
            """), {"user_id": current_user['user_id']})
            rows = result.fetchall()
            return [dict(row._mapping) for row in rows]
    except Exception as e:
        print(f"Erreur: {e}")
        return []

@app.get("/social/themes")
def get_themes(current_user = Depends(get_current_user)):
    """Récupère les thèmes disponibles"""
    return {
        "themes": list(THEMES_TOURISTIQUES.keys()),
        "details": THEMES_TOURISTIQUES
    }

@app.put("/social/posts/{post_id}/statut")
def update_statut_post(post_id: int, statut: str, current_user = Depends(get_current_user)):
    """Met à jour le statut d'un post"""
    mettre_a_jour_statut_post(post_id, statut)
    delete_cache_pattern("social*")
    return {"message": "Statut mis à jour ✅"}

# ═══════════════════════════════════════════
# ROUTES SETTINGS
# ═══════════════════════════════════════════

@app.post("/settings/api")
def save_api_config(api_name: str, config: dict, current_user = Depends(get_current_user)):
    """Sauvegarde la configuration d'une API"""
    try:
        encrypted_key = CIPHER_SUITE.encrypt(
            config.get('api_key', '').encode()
        ).decode()
        
        with engine.connect() as conn:
            conn.execute(text("""
                INSERT INTO api_integrations 
                (user_id, api_name, api_key, config, enabled)
                VALUES (:user_id, :api_name, :api_key, :config, :enabled)
                ON DUPLICATE KEY UPDATE
                api_key = :api_key, config = :config, enabled = :enabled
            """), {
                "user_id": current_user['user_id'],
                "api_name": api_name,
                "api_key": encrypted_key,
                "config": json.dumps(config),
                "enabled": config.get('enabled', False)
            })
            conn.commit()
        return {"message": f"✅ {api_name} sauvegardé!"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/settings/smtp")
def save_smtp_config(config: SMTPConfig, current_user = Depends(get_current_user)):
    try:
        encrypted_password = CIPHER_SUITE.encrypt(config.password.encode()).decode()
        
        with engine.connect() as conn:
            conn.execute(text("""
                INSERT INTO email_settings
                (user_id, provider, email, password, host, port, secure, smtp_enabled)
                VALUES (:user_id, :provider, :email, :password, :host, :port, :secure, true)
                ON DUPLICATE KEY UPDATE
                provider = :provider, email = :email, password = :password,
                host = :host, port = :port, secure = :secure, smtp_enabled = true
            """), {
                "user_id": current_user['user_id'],
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
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/settings/smtp/test")
async def test_smtp(config: SMTPConfig, current_user = Depends(get_current_user)):
    """Tester l'envoi d'email avec SendGrid"""
    try:
        import sendgrid
        from sendgrid.helpers.mail import Mail
        
        api_key = os.getenv('SENDGRID_API_KEY')
        from_email = os.getenv('SENDGRID_FROM_EMAIL')
        test_email = os.getenv('TEST_EMAIL')
        
        if not api_key or not from_email or not test_email:
            raise HTTPException(status_code=400, detail="SendGrid non configuré dans .env")
        
        sg = sendgrid.SendGridAPIClient(api_key)
        
        mail = Mail(
            from_email=from_email,
            to_emails=test_email,
            subject="🧪 Test Email - PM Travel",
            plain_text_content="Ceci est un email de test de PM Travel Agency!"
        )
        
        response = sg.send(mail)
        
        return {
            "success": True,
            "message": f"Email test envoyé à {test_email}",
            "status_code": response.status_code
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/settings/imap")
def save_imap_config(provider: str, email: str, password: str, host: str = None, port: int = None, secure: bool = True, sync_interval: int = 5, current_user = Depends(get_current_user)):
    """Sauvegarde la configuration IMAP"""
    try:
        encrypted_password = CIPHER_SUITE.encrypt(password.encode()).decode()
        
        with engine.connect() as conn:
            conn.execute(text("""
                INSERT INTO email_settings
                (user_id, provider, email, password, host, port, secure, imap_enabled, sync_interval)
                VALUES (:user_id, :provider, :email, :password, :host, :port, :secure, true, :sync_interval)
                ON DUPLICATE KEY UPDATE
                imap_enabled = true, sync_interval = :sync_interval
            """), {
                "user_id": current_user['user_id'],
                "provider": provider,
                "email": email,
                "password": encrypted_password,
                "host": host,
                "port": port,
                "secure": secure,
                "sync_interval": sync_interval
            })
            conn.commit()
        return {"message": f"✅ IMAP configuré! Synchronisation chaque {sync_interval} minutes"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/settings/imap/sync")
def sync_emails(current_user = Depends(get_current_user)):
    """Synchronise les emails depuis IMAP"""
    try:
        import imaplib
        from email.parser import EmailParser
        
        with engine.connect() as conn:
            result = conn.execute(text("""
                SELECT provider, email, password, host, port, secure
                FROM email_settings
                WHERE user_id = :user_id AND imap_enabled = true
            """), {"user_id": current_user['user_id']})
            
            config_row = result.fetchone()
            if not config_row:
                return {"error": "IMAP non configuré"}, 400
            
            config = dict(config_row._mapping)
            password = CIPHER_SUITE.decrypt(config['password'].encode()).decode()
            
            if config['secure']:
                imap = imaplib.IMAP4_SSL(config['host'], config['port'])
            else:
                imap = imaplib.IMAP4(config['host'], config['port'])
            
            imap.login(config['email'], password)
            imap.select('INBOX')
            
            status, messages = imap.search(None, 'UNSEEN')
            
            email_count = 0
            
            for msg_id in messages[0].split():
                status, msg_data = imap.fetch(msg_id, '(RFC822)')
                
                for response_part in msg_data:
                    if isinstance(response_part, tuple):
                        email_message = EmailParser().parsestr(response_part[1].decode())
                        
                        with engine.connect() as conn2:
                            conn2.execute(text("""
                                INSERT IGNORE INTO email_messages
                                (user_id, from_email, to_email, subject, body, message_id, received_at)
                                VALUES (:user_id, :from_email, :to_email, :subject, :body, :message_id, :received_at)
                            """), {
                                "user_id": current_user['user_id'],
                                "from_email": email_message['From'],
                                "to_email": email_message['To'],
                                "subject": email_message['Subject'],
                                "body": email_message.get_payload(),
                                "message_id": email_message['Message-ID'],
                                "received_at": datetime.now()
                            })
                            conn2.commit()
                        
                        email_count += 1
            
            imap.close()
            
            return {"message": "✅ Emails synchronisés", "count": email_count}
    except Exception as e:
        return {"error": f"❌ Erreur IMAP: {str(e)}"}, 500

# ═══════════════════════════════════════════
# ROUTES SÉQUENCES
# ═══════════════════════════════════════════

@app.post("/sequences/relances")
def traiter_relances(current_user = Depends(get_current_user)):
    """Traite les relances email"""
    with engine.connect() as conn:
        sequences = conn.execute(text("""
            SELECT s.*, p.email, p.nom, p.secteur, p.ville, p.score
            FROM sequences_email s
            JOIN prospects p ON s.prospect_id = p.id
            WHERE s.statut = 'actif'
            AND s.prochaine_relance <= NOW()
            AND s.etape < 3
        """)).fetchall()

        if not sequences:
            return {"message": "Aucune relance à traiter", "relances": 0}

        relances = 0

        for row in sequences:
            seq = dict(row._mapping)
            prospect = {
                'nom': seq['nom'],
                'email': seq['email'],
                'secteur': seq['secteur'],
                'ville': seq['ville'],
                'score': seq['score']
            }

            try:
                contenu = generer_contenu_email(prospect)
                etape = seq['etape'] + 1
                sujet = f"[Relance {etape}] {generer_sujet_email(prospect)}"

                succes = envoyer_email(seq['email'], sujet, contenu, seq['nom'])

                if succes:
                    nouvelle_etape = seq['etape'] + 1
                    nouveau_statut = 'actif' if nouvelle_etape < 3 else 'terminé'
                    conn.execute(text("""
                        UPDATE sequences_email SET
                        etape = :etape,
                        prochaine_relance = :relance,
                        statut = :statut
                        WHERE id = :id
                    """), {
                        "etape": nouvelle_etape,
                        "relance": datetime.now() + timedelta(days=7),
                        "statut": nouveau_statut,
                        "id": seq['id']
                    })
                    relances += 1

            except Exception as e:
                print(f"❌ Erreur relance {seq['nom']} : {e}")
                continue

        conn.commit()
        return {"message": f"{relances} relances envoyées ✅", "relances": relances}
@app.get("/sequences")
def get_sequences(current_user = Depends(get_current_user)):
    """Récupère les séquences"""
    with engine.connect() as conn:
        result = conn.execute(text("""
            SELECT s.*, p.nom, p.email, p.secteur, p.ville
            FROM sequences_email s
            JOIN prospects p ON s.prospect_id = p.id
            ORDER BY s.prochaine_relance ASC
        """))
        return [dict(row._mapping) for row in result.fetchall()]

# ═══════════════════════════════════════════

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)