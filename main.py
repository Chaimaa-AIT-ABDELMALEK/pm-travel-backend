from fastapi import FastAPI, HTTPException
from sqlalchemy import create_engine, text
from dotenv import load_dotenv
from pydantic import BaseModel
from typing import Optional
import os
import subprocess

load_dotenv()

app = FastAPI()

DB_URL = f"mysql+pymysql://{os.getenv('DB_USER')}:{os.getenv('DB_PASSWORD')}@{os.getenv('DB_HOST')}:{os.getenv('DB_PORT')}/{os.getenv('DB_NAME')}"
engine = create_engine(DB_URL)

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
        subprocess.Popen(["python", "scrapers/scraper_google.py"])
        return {"message": "Scraper lancé ✅"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))