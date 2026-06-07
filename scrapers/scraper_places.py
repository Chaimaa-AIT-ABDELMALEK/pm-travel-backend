import requests
import pymysql
import re
import time
from dotenv import load_dotenv
import os
import dns.resolver
import smtplib
import socket
import sys
import json

# Sous Windows, la console utilise cp1252 par défaut et ne peut pas afficher
# les emojis (🔍, 📍, ✅...). On force la sortie en UTF-8 pour éviter
# UnicodeEncodeError: 'charmap' codec can't encode character ...
try:
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')
except Exception:
    pass

load_dotenv()

GOOGLE_API_KEY = os.getenv('GOOGLE_API_KEY')

if not GOOGLE_API_KEY:
    print("⚠️ GOOGLE_API_KEY absente du fichier .env — les recherches Google Places échoueront (0 prospect).")

# CONFIGURATION

VILLES_HOTELS = [
    'Marrakech', 'Casablanca', 'Agadir', 'Fes',
    'Rabat', 'Chefchaouen', 'Tanger', 'Ouarzazate', 'Merzouga'
]

VILLES_AGENCES = [
    'New York', 'Los Angeles', 'Miami', 'Chicago',
    'Toronto', 'Montreal',
    'Mexico City',
    'Sao Paulo', 'Rio de Janeiro',
    'Buenos Aires',
    'Bogota',
    'Santiago',
    'Lima'
]

SECTEURS_HOTELS = [
    'hotel',
    'riad',
    'transport touristique'
]

SECTEURS_AGENCES = [
    'agence de voyage',
    'tour operator'
]

# CONNEXION BASE DE DONNÉES

def connect_db():
    return pymysql.connect(
        host=os.getenv('DB_HOST'),
        port=int(os.getenv('DB_PORT')),
        user=os.getenv('DB_USER'),
        password=os.getenv('DB_PASSWORD'),
        database=os.getenv('DB_NAME'),
        charset='utf8mb4'
    )

# VALIDATION EMAIL

def verifier_dns(email):
    domaine = email.split('@')[1]
    try:
        records = dns.resolver.resolve(domaine, 'MX')
        return True, str(records[0].exchange)
    except:
        return False, None

def verifier_smtp(email, mx_serveur):
    try:
        serveur = smtplib.SMTP(timeout=10)
        serveur.connect(mx_serveur)
        serveur.helo('gmail.com')
        serveur.mail('test@gmail.com')
        code, message = serveur.rcpt(email)
        serveur.quit()
        return code == 250
    except:
        return False

def valider_email(email):
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    if not bool(re.match(pattern, email)):
        print(f"   ❌ Format invalide : {email}")
        return False

    dns_valide, mx_serveur = verifier_dns(email)
    if not dns_valide:
        print(f"   ❌ Domaine inexistant : {email}")
        return False

    smtp_valide = verifier_smtp(email, mx_serveur)
    if not smtp_valide:
        print(f"   ❌ Boîte inexistante : {email}")
        return False

    print(f"   ✅ Email vérifié : {email}")
    return True

# CALCUL DU SCORE

def calculer_score(secteur, ville, telephone, website, nom):
    score = 0

    secteurs_scores = {
        'hotel': 50,
        'riad': 50,
        'tour operator': 45,
        'agence de voyage': 45,
        'transport touristique': 35
    }
    for s, points in secteurs_scores.items():
        if s in secteur.lower():
            score += points
            break

    villes_maroc_scores = {
        'marrakech': 30, 'casablanca': 25, 'agadir': 20,
        'fes': 20, 'rabat': 20, 'chefchaouen': 15,
        'tanger': 20, 'ouarzazate': 15, 'merzouga': 15
    }
    villes_etranger_scores = {
        'new york': 30, 'los angeles': 25, 'miami': 25,
        'chicago': 20, 'toronto': 25, 'montreal': 20,
        'mexico city': 20, 'sao paulo': 20, 'rio de janeiro': 20,
        'buenos aires': 20, 'bogota': 15, 'santiago': 15, 'lima': 15
    }

    for v, points in {**villes_maroc_scores, **villes_etranger_scores}.items():
        if v in ville.lower():
            score += points
            break

    if website:
        score += 10
    if telephone:
        score += 5

    mots_pro = ['hotel', 'riad', 'resort', 'lodge', 'tours', 'travel', 'voyages', 'turismo', 'viajes']
    if any(mot in nom.lower() for mot in mots_pro):
        score += 5

    return score

# COORDONNÉES DES VILLES - Liste en dur (plus rapide et fiable)

VILLES_COORDONNEES = {
    # MAROC
    'marrakech': (31.6295, -8.0089),
    'casablanca': (33.5731, -7.5898),
    'agadir': (30.4203, -9.5981),
    'fes': (34.0334, -5.0024),
    'rabat': (34.0209, -6.8416),
    'chefchaouen': (35.1684, -5.2698),
    'tanger': (35.7596, -5.8018),
    'ouarzazate': (30.9315, -6.5092),
    'merzouga': (31.1521, -4.0097),
    # AMÉRIQUE DU NORD
    'new york': (40.7128, -74.0060),
    'los angeles': (34.0522, -118.2437),
    'miami': (25.7617, -80.1918),
    'chicago': (41.8781, -87.6298),
    'toronto': (43.6532, -79.3832),
    'montreal': (45.5017, -73.5673),
    'mexico city': (19.4326, -99.1332),
    # AMÉRIQUE DU SUD
    'sao paulo': (-23.5505, -46.6333),
    'rio de janeiro': (-22.9068, -43.1729),
    'buenos aires': (-34.6037, -58.3816),
    'bogota': (4.7110, -74.0721),
    'santiago': (-33.4489, -70.6693),
    'lima': (-12.0464, -77.0428),
}

def geocoder_ville(ville):
    """Retourne les coordonnées d'une ville depuis la liste en dur"""
    ville_lower = ville.lower()
    
    if ville_lower in VILLES_COORDONNEES:
        lat, lng = VILLES_COORDONNEES[ville_lower]
        print(f"   📍 Coordonnées trouvées pour {ville}")
        return lat, lng
    else:
        print(f"❌ Ville non trouvée: {ville}")
        return None, None

# APPEL GOOGLE PLACES API - AVEC RESTRICTION GÉOGRAPHIQUE

def chercher_places(query, ville):
    """Recherche avec restriction géographique à la ville"""
    
    lat, lng = geocoder_ville(ville)
    
    if not lat or not lng:
        print(f"❌ Impossible de géocoder: {ville}")
        return []
    
    print(f"   📍 Coordonnées de {ville}: ({lat}, {lng})")
    
    # On utilise searchText (recherche par texte) car on a une requête type "hotel", "riad"...
    # searchText accepte le champ textQuery, contrairement à searchNearby.
    url = "https://places.googleapis.com/v1/places:searchText"
    headers = {
        'Content-Type': 'application/json',
        'X-Goog-Api-Key': GOOGLE_API_KEY,
        'X-Goog-FieldMask': 'places.displayName,places.formattedAddress,places.nationalPhoneNumber,places.websiteUri,places.id'
    }

    body = {
        "textQuery": f"{query} {ville}",
        "languageCode": "fr",
        "locationBias": {
            "circle": {
                "center": {
                    "latitude": lat,
                    "longitude": lng
                },
                "radius": 15000
            }
        }
    }
    
    try:
        res = requests.post(url, headers=headers, json=body, timeout=30)

        # Diagnostic : si la réponse n'est pas du JSON exploitable, afficher la cause réelle
        try:
            data = res.json()
        except ValueError:
            print(f"❌ Réponse non-JSON de Google (HTTP {res.status_code}) : {res.text[:300]}")
            if res.status_code in (401, 403):
                print("   → Clé API invalide, restreinte, ou 'Places API (New)' non activée / facturation absente.")
            return []

        if res.status_code != 200 or data.get('error'):
            err = data.get('error', {})
            print(f"❌ Erreur API Google (HTTP {res.status_code}) : {err.get('message', res.text[:200])}")
            return []

        places = data.get('places', [])
        return places
    except Exception as e:
        print(f"❌ Erreur recherche Google Places: {e}")
        return []

def get_details_place(place):
    return {
        'name': place.get('displayName', {}).get('text', ''),
        'formatted_phone_number': place.get('nationalPhoneNumber', ''),
        'website': place.get('websiteUri', ''),
        'formatted_address': place.get('formattedAddress', '')
    }

# EXTRACTION EMAIL DEPUIS SITE WEB

def extraire_email_depuis_site(website):
    try:
        res = requests.get(website, timeout=5)
        emails = re.findall(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', res.text)
        emails_filtres = [e for e in emails if not any(x in e.lower() for x in ['example', 'test', 'noreply', 'no-reply'])]
        if emails_filtres:
            return emails_filtres[0]
    except:
        pass
    return None

# SAUVEGARDE PROSPECT

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
            # rowcount == 1 => ligne insérée ; == 0 => doublon ignoré (INSERT IGNORE)
            inserted = cursor.rowcount == 1
        conn.commit()
        return 'inserted' if inserted else 'skipped'
    except Exception as e:
        print(f"Erreur sauvegarde : {e}")
        return 'error'
    finally:
        conn.close()

# LOG SCRAPING

def logger_scraping(source, nombre_collectes, nombre_valides, statut):
    """Ancien log (table logs_scraping) — conservé pour debug."""
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
    except Exception as e:
        print(f"Erreur logs_scraping : {e}")
    finally:
        conn.close()


def enregistrer_historique(user_id, sector, city, inserted, skipped, statut='completed'):
    """Trace une exécution dans scraping_history.
    prospects_found = total traité ; logs (JSON) = {inserted, skipped}."""
    conn = connect_db()
    try:
        total = inserted + skipped
        details = json.dumps({'inserted': inserted, 'skipped': skipped})
        with conn.cursor() as cursor:
            sql = """
                INSERT INTO scraping_history 
                (user_id, sector, city, prospects_found, logs, status)
                VALUES (%s, %s, %s, %s, %s, %s)
            """
            cursor.execute(sql, (user_id, sector, city, total, details, statut))
        conn.commit()
    except Exception as e:
        print(f"Erreur scraping_history : {e}")
    finally:
        conn.close()

# SCRAPER PRINCIPAL

def scraper(secteurs, villes, source_label, user_id=None):
    tous_prospects = []

    for ville in villes:
        for secteur in secteurs:
            print(f"🔍 Recherche : {secteur} à {ville}")
            places = chercher_places(secteur, ville)

            inserted = 0
            skipped = 0

            for place in places:
                try:
                    details = get_details_place(place)
                    nom = details.get('name', '')
                    telephone = details.get('formatted_phone_number', '')
                    website = details.get('website', '')

                    email = None
                    if website:
                        email = extraire_email_depuis_site(website)

                    if not email:
                        nom_clean = nom.lower().replace(' ', '').replace("'", '')[:20]
                        email = f"contact@{nom_clean}.com"

                    email_valide = valider_email(email)
                    score = calculer_score(secteur, ville, telephone, website, nom)

                    prospect = {
                        'nom': nom,
                        'email': email,
                        'telephone': telephone,
                        'secteur': secteur,
                        'ville': ville,
                        'source': source_label,
                        'score': score,
                        'email_valide': email_valide
                    }

                    resultat = sauvegarder_prospect(prospect)
                    if resultat == 'inserted':
                        inserted += 1
                        tous_prospects.append(prospect)
                        print(f"✅ {nom} | {ville} | Score: {score} | Email: {email}")
                    elif resultat == 'skipped':
                        skipped += 1
                        print(f"⏭️ Doublon ignoré : {nom} | {ville}")

                    time.sleep(0.5)

                except Exception as e:
                    print(f"❌ Erreur : {e}")
                    continue

            # Trace cette combinaison secteur+ville dans l'historique (inséré + ignoré)
            if user_id is not None and (inserted + skipped) > 0:
                enregistrer_historique(user_id, secteur, ville, inserted, skipped, 'completed')

    return tous_prospects

# LANCEMENT

if __name__ == "__main__":
    tous_prospects = []

    # Récupère --user-id N s'il est fourni (passé par le backend), et nettoie argv
    user_id = None
    args = sys.argv[1:]
    if '--user-id' in args:
        idx = args.index('--user-id')
        try:
            user_id = int(args[idx + 1])
        except (IndexError, ValueError):
            user_id = None
        # retire --user-id et sa valeur de la liste d'arguments
        del args[idx:idx + 2]

    if len(args) >= 2:
        secteur = args[0]
        ville = args[1]
        print(f"\n🚀 Mode manuel: {secteur} à {ville}")

        print(f"🔍 Recherche : {secteur} à {ville}")
        places = chercher_places(secteur, ville)

        inserted = 0
        skipped = 0

        for place in places:
            try:
                details = get_details_place(place)
                nom = details.get('name', '')
                telephone = details.get('formatted_phone_number', '')
                website = details.get('website', '')

                email = None
                if website:
                    email = extraire_email_depuis_site(website)

                if not email:
                    nom_clean = nom.lower().replace(' ', '').replace("'", '')[:20]
                    email = f"contact@{nom_clean}.com"

                email_valide = valider_email(email)
                score = calculer_score(secteur, ville, telephone, website, nom)

                prospect = {
                    'nom': nom,
                    'email': email,
                    'telephone': telephone,
                    'secteur': secteur,
                    'ville': ville,
                    'source': 'Google Places',
                    'score': score,
                    'email_valide': email_valide
                }

                resultat = sauvegarder_prospect(prospect)
                if resultat == 'inserted':
                    inserted += 1
                    tous_prospects.append(prospect)
                    print(f"✅ {nom} | {ville} | Score: {score} | Email: {email}")
                elif resultat == 'skipped':
                    skipped += 1
                    print(f"⏭️ Doublon ignoré : {nom} | {ville}")

                time.sleep(0.5)

            except Exception as e:
                print(f"❌ Erreur : {e}")
                continue

        if user_id is not None and (inserted + skipped) > 0:
            enregistrer_historique(user_id, secteur, ville, inserted, skipped, 'completed')
    else:
        print("\n" + "="*50)
        print("PARTIE 1 — Hôtels & Transport au Maroc")
        print("="*50)
        prospects_maroc = scraper(SECTEURS_HOTELS, VILLES_HOTELS, 'Google Maps Maroc', user_id)
        tous_prospects.extend(prospects_maroc)

        print("\n" + "="*50)
        print("PARTIE 2 — Agences & Tour Operators Étrangers")
        print("="*50)
        prospects_etranger = scraper(SECTEURS_AGENCES, VILLES_AGENCES, 'Google Maps Étranger', user_id)
        tous_prospects.extend(prospects_etranger)

        total = len(tous_prospects)
        valides = len([p for p in tous_prospects if p['email_valide']])
        print("\n" + "="*50)
        print("RÉSUMÉ FINAL")
        print("="*50)
        print(f"Total prospects collectés  : {total}")
        print(f"Emails valides             : {valides}")
        print(f"Hôtels Maroc               : {len(prospects_maroc)}")
        print(f"Agences étrangères         : {len(prospects_etranger)}")

    result = {
        'found': len(tous_prospects),
        'prospects': tous_prospects,
        'logs': []
    }

    print(json.dumps(result))