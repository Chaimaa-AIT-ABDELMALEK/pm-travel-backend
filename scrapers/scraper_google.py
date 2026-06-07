import requests
from bs4 import BeautifulSoup
import pymysql
import re
import time
from dotenv import load_dotenv
import os
import sys

# Force la sortie en UTF-8 (évite UnicodeEncodeError avec les emojis sous Windows)
try:
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')
except Exception:
    pass

load_dotenv()

def connect_db():
    return pymysql.connect(
        host=os.getenv('DB_HOST'),
        port=int(os.getenv('DB_PORT')),
        user=os.getenv('DB_USER'),
        password=os.getenv('DB_PASSWORD'),
        database=os.getenv('DB_NAME'),
        charset='utf8mb4'
    )

def valider_email(email):
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return bool(re.match(pattern, email))

def calculer_score(secteur, ville):
    score = 0
    secteurs_prioritaires = ['hotel', 'riad', 'tour operator', 'transport']
    villes_prioritaires = ['marrakech', 'casablanca', 'agadir', 'fes']
    if any(s in secteur.lower() for s in secteurs_prioritaires):
        score += 50
    if any(v in ville.lower() for v in villes_prioritaires):
        score += 30
    return score

def sauvegarder_prospect(prospect):
    conn = connect_db()
    try:
        with conn.cursor() as cursor:
            sql = """
                INSERT IGNORE INTO prospects 
                (nom, email, telephone, secteur, ville, source, score, email_valide)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """
            cursor.execute(sql, (
                prospect['nom'],
                prospect['email'],
                prospect['telephone'],
                prospect['secteur'],
                prospect['ville'],
                prospect['source'],
                prospect['score'],
                prospect['email_valide']
            ))
        conn.commit()
        return True
    except Exception as e:
        print(f"Erreur sauvegarde : {e}")
        return False
    finally:
        conn.close()

def scraper_hotels_marrakech():
    prospects = []
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
    }
    
    # Simulation de données scrappées (à remplacer par vrai scraping)
    donnees_simulees = [
        {
            'nom': 'Hotel Atlas Marrakech',
            'email': 'contact@atlas-marrakech.com',
            'telephone': '+212524000001',
            'secteur': 'hotel',
            'ville': 'Marrakech',
            'source': 'Google Maps'
        },
        {
            'nom': 'Riad Zitoun',
            'email': 'info@riadzitoun.com',
            'telephone': '+212524000002',
            'secteur': 'riad',
            'ville': 'Marrakech',
            'source': 'Google Maps'
        },
        {
            'nom': 'Marrakech Tours',
            'email': 'booking@marrakech-tours.com',
            'telephone': '+212524000003',
            'secteur': 'tour operator',
            'ville': 'Marrakech',
            'source': 'Google Maps'
        }
    ]
    
    for donnee in donnees_simulees:
        email_valide = valider_email(donnee['email'])
        score = calculer_score(donnee['secteur'], donnee['ville'])
        
        prospect = {
            **donnee,
            'email_valide': email_valide,
            'score': score
        }
        
        if sauvegarder_prospect(prospect):
            prospects.append(prospect)
            print(f"✅ Prospect sauvegardé : {donnee['nom']}")
        
        time.sleep(1)
    
    return prospects

def logger_scraping(source, nombre_collectes, nombre_valides, statut):
    conn = connect_db()
    try:
        with conn.cursor() as cursor:
            sql = """
                INSERT INTO logs_scraping 
                (source, nombre_collectes, nombre_valides, statut)
                VALUES (%s, %s, %s, %s)
            """
            cursor.execute(sql, (source, nombre_collectes, nombre_valides, statut))
        conn.commit()
    finally:
        conn.close()

if __name__ == "__main__":
    print("🚀 Démarrage du scraping...")
    prospects = scraper_hotels_marrakech()
    valides = [p for p in prospects if p['email_valide']]
    logger_scraping('Google Maps', len(prospects), len(valides), 'succès')
    print(f"✅ Scraping terminé : {len(prospects)} prospects, {len(valides)} emails valides")