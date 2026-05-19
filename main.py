from fastapi import FastAPI, HTTPException
from sqlalchemy import create_engine, text
from dotenv import load_dotenv
from pydantic import BaseModel
from typing import Optional
import os
import subprocess
from fastapi.middleware.cors import CORSMiddleware
from emails.email_service import (
    generer_contenu_email,
    generer_sujet_email,
    envoyer_email,
    sauvegarder_email,
    creer_sequence
)
from datetime import datetime, timedelta

load_dotenv()

app = FastAPI()

DB_URL = f"mysql+pymysql://{os.getenv('DB_USER')}:{os.getenv('DB_PASSWORD')}@{os.getenv('DB_HOST')}:{os.getenv('DB_PORT')}/{os.getenv('DB_NAME')}"
engine = create_engine(DB_URL)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3001", "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
# ─── Models ───────────────────────────────────────────────
class Prospect(BaseModel):
    nom: str
    email: str
    telephone: Optional[str] = None
    secteur: Optional[str] = None
    ville: Optional[str] = None
    source: Optional[str] = None
    score: Optional[int] = 0
    email_valide: Optional[bool] = False
    

# ─── Routes ───────────────────────────────────────────────
@app.get("/")
def read_root():
    return {"message": "PM Travel API is running"}

@app.get("/test-db")
def test_db():
    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))
        return {"database": "connectée ✅"}

@app.get("/prospects")
def get_prospects():
    with engine.connect() as conn:
        result = conn.execute(text("SELECT * FROM prospects ORDER BY score DESC"))
        rows = result.fetchall()
        return [dict(row._mapping) for row in rows]

@app.get("/prospects/{id}")
def get_prospect(id: int):
    with engine.connect() as conn:
        result = conn.execute(text("SELECT * FROM prospects WHERE id = :id"), {"id": id})
        row = result.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Prospect non trouvé")
        return dict(row._mapping)

@app.post("/prospects")
def create_prospect(prospect: Prospect):
    with engine.connect() as conn:
        conn.execute(text("""
            INSERT IGNORE INTO prospects 
            (nom, email, telephone, secteur, ville, source, score, email_valide)
            VALUES (:nom, :email, :telephone, :secteur, :ville, :source, :score, :email_valide)
        """), prospect.dict())
        conn.commit()
        return {"message": "Prospect ajouté ✅"}

@app.put("/prospects/{id}/statut")
def update_statut(id: int, statut: str):
    with engine.connect() as conn:
        conn.execute(text("""
            UPDATE prospects SET statut = :statut WHERE id = :id
        """), {"statut": statut, "id": id})
        conn.commit()
        return {"message": "Statut mis à jour ✅"}

@app.delete("/prospects/{id}")
def delete_prospect(id: int):
    with engine.connect() as conn:
        conn.execute(text("DELETE FROM prospects WHERE id = :id"), {"id": id})
        conn.commit()
        return {"message": "Prospect supprimé ✅"}

@app.get("/prospects/stats/kpis")
def get_kpis():
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
def lancer_scraper():
    try:
        subprocess.Popen(["python", "scrapers/scraper_places.py"])
        return {"message": "Scraper Google Maps lancé ✅"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    
# ─────────────────────────────────────────
# ROUTES CAMPAGNES
# ─────────────────────────────────────────

@app.post("/campagnes")
def creer_campagne(nom: str, sujet: str):
    with engine.connect() as conn:
        conn.execute(text("""
            INSERT INTO campagnes (nom, sujet, statut)
            VALUES (:nom, :sujet, 'brouillon')
        """), {"nom": nom, "sujet": sujet})
        conn.commit()
        result = conn.execute(text("SELECT LAST_INSERT_ID()"))
        campagne_id = result.scalar()
        return {"message": "Campagne créée ✅", "id": campagne_id}

@app.get("/campagnes")
def get_campagnes():
    with engine.connect() as conn:
        result = conn.execute(text("""
            SELECT * FROM campagnes ORDER BY date_creation DESC
        """))
        return [dict(row._mapping) for row in result.fetchall()]

@app.get("/campagnes/{campagne_id}")
def get_campagne(campagne_id: int):
    with engine.connect() as conn:
        result = conn.execute(text("""
            SELECT * FROM campagnes WHERE id = :id
        """), {"id": campagne_id})
        row = result.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Campagne non trouvée")
        return dict(row._mapping)

@app.post("/campagnes/{campagne_id}/lancer")
def lancer_campagne(campagne_id: int):
    with engine.connect() as conn:
        prospects = conn.execute(text("""
            SELECT * FROM prospects
            WHERE statut = 'nouveau'
            AND email_valide = 1
            ORDER BY score DESC
            LIMIT 50
        """)).fetchall()

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
def get_kpis_campagnes():
    with engine.connect() as conn:
        total_campagnes = conn.execute(text(
            "SELECT COUNT(*) FROM campagnes"
        )).scalar() or 0
        total_envoyes = conn.execute(text(
            "SELECT COALESCE(SUM(total_envoyes), 0) FROM campagnes"
        )).scalar() or 0
        total_ouverts = conn.execute(text(
            "SELECT COALESCE(SUM(total_ouverts), 0) FROM campagnes"
        )).scalar() or 0
        total_cliques = conn.execute(text(
            "SELECT COALESCE(SUM(total_cliques), 0) FROM campagnes"
        )).scalar() or 0
        taux_ouverture = round(
            (total_ouverts / total_envoyes * 100), 1
        ) if total_envoyes > 0 else 0
        taux_clic = round(
            (total_cliques / total_envoyes * 100), 1
        ) if total_envoyes > 0 else 0
        return {
            "total_campagnes": total_campagnes,
            "total_envoyes": total_envoyes,
            "total_ouverts": total_ouverts,
            "total_cliques": total_cliques,
            "taux_ouverture": taux_ouverture,
            "taux_clic": taux_clic
        }

# ─────────────────────────────────────────
# ROUTES SÉQUENCES & RELANCES
# ─────────────────────────────────────────

@app.post("/sequences/relances")
def traiter_relances():
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

                succes = envoyer_email(
                    seq['email'],
                    sujet,
                    contenu,
                    seq['nom']
                )

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
                    sauvegarder_email(
                        seq['campagne_id'],
                        seq['prospect_id'],
                        seq['email'],
                        sujet,
                        contenu,
                        'envoyé'
                    )
                    relances += 1

            except Exception as e:
                print(f"❌ Erreur relance {seq['nom']} : {e}")
                continue

        conn.commit()
        return {"message": f"{relances} relances envoyées ✅", "relances": relances}

@app.get("/sequences")
def get_sequences():
    with engine.connect() as conn:
        result = conn.execute(text("""
            SELECT s.*, p.nom, p.email, p.secteur, p.ville
            FROM sequences_email s
            JOIN prospects p ON s.prospect_id = p.id
            ORDER BY s.prochaine_relance ASC
        """))
        return [dict(row._mapping) for row in result.fetchall()]    