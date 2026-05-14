import requests
import pymysql
import re
import time
from dotenv import load_dotenv
import os

load_dotenv()
GOOGLE_API_KEY = os.getenv('GOOGLE_API_KEY')
print(f"Clé API : {GOOGLE_API_KEY}")

GOOGLE_API_KEY = os.getenv('GOOGLE_API_KEY')

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

def calculer_score(secteur, ville, telephone, website, nom):
    score = 0

    # Score par secteur
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

    # Score par ville
    villes_scores = {
        'marrakech': 30,
        'casablanca': 25,
        'agadir': 20,
        'fes': 20
    }
    for v, points in villes_scores.items():
        if v in ville.lower():
            score += points
            break

    # Bonus site web
    if website:
        score += 10

    # Bonus téléphone
    if telephone:
        score += 5

    # Bonus nom professionnel
    mots_pro = ['hotel', 'riad', 'resort', 'lodge', 'tours', 'travel', 'voyages']
    if any(mot in nom.lower() for mot in mots_pro):
        score += 5

    return score

def chercher_places(query, ville):
    url = "https://places.googleapis.com/v1/places:searchText"
    headers = {
        'Content-Type': 'application/json',
        'X-Goog-Api-Key': GOOGLE_API_KEY,
        'X-Goog-FieldMask': 'places.displayName,places.formattedAddress,places.nationalPhoneNumber,places.websiteUri,places.id'
    }
    body = {
        "textQuery": f"{query} {ville}",
        "languageCode": "fr"
    }
    res = requests.post(url, headers=headers, json=body)
    data = res.json()
    print(f"Status : {res.status_code}")
    return data.get('places', [])

def get_details_place(place):
    return {
        'name': place.get('displayName', {}).get('text', ''),
        'formatted_phone_number': place.get('nationalPhoneNumber', ''),
        'website': place.get('websiteUri', ''),
        'formatted_address': place.get('formattedAddress', '')
    }
def extraire_email_depuis_site(website):
    try:
        res = requests.get(website, timeout=5)
        emails = re.findall(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', res.text)
        if emails:
            return emails[0]
    except:
        pass
    return None

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

def scraper_google_maps(secteurs, villes):
    tous_prospects = []

    for ville in villes:
        for secteur in secteurs:
            print(f"🔍 Recherche : {secteur} à {ville}")
            places = chercher_places(secteur, ville)

            for place in places:
                try:
                    details = get_details_place(place)
                    nom = details.get('name', place.get('name', ''))
                    telephone = details.get('formatted_phone_number', '')
                    website = details.get('website', '')
                    adresse = details.get('formatted_address', '')

                    # Extraire email depuis le site web
                    email = None
                    if website:
                        email = extraire_email_depuis_site(website)

                    # Si pas d'email trouvé, générer un email générique
                    if not email:
                        nom_clean = nom.lower().replace(' ', '').replace("'", '')
                        email = f"contact@{nom_clean[:20]}.com"

                    email_valide = valider_email(email)
                    score = calculer_score(
                        secteur,
                        ville,
                        details.get('formatted_phone_number', ''),
                        details.get('website', ''),
                        details.get('name', '')
                    ) 

                    prospect = {
                        'nom': nom,
                        'email': email,
                        'telephone': telephone,
                        'secteur': secteur,
                        'ville': ville,
                        'source': 'Google Maps',
                        'score': score,
                        'email_valide': email_valide
                    }

                    if sauvegarder_prospect(prospect):
                        tous_prospects.append(prospect)
                        print(f"✅ {nom} — {email} — Score: {score}")

                    time.sleep(0.5)

                except Exception as e:
                    print(f"❌ Erreur pour {place.get('name', '')} : {e}")
                    continue

    return tous_prospects

if __name__ == "__main__":
    secteurs = ['hotel', 'riad', 'tour operator', 'agence de voyage', 'transport touristique']
    villes = ['Marrakech', 'Casablanca', 'Agadir', 'Fes']

    print("🚀 Démarrage du scraping Google Maps...")
    prospects = scraper_google_maps(secteurs, villes)
    valides = [p for p in prospects if p['email_valide']]
    logger_scraping('Google Maps', len(prospects), len(valides), 'succès')
    print(f"\n✅ Scraping terminé :")
    print(f"   Total collectés  : {len(prospects)}")
    print(f"   Emails valides   : {len(valides)}")