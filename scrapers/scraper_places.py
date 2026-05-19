import requests #appeler l'api google places et visiter les sites web des prospects pour extraire les emails
import pymysql #connecter python a mysql
import re #expressions regulieres de python pour extraire les emails et verifier leur format
import time #pause entre chaque prospect
from dotenv import load_dotenv #lie et charge le fichier .env
import os #acceder aux valeurs du .env
import dns.resolver #demander au dns si un email et son domaine existent
import smtplib #se connecter aux serveurs mail smtp
import socket #gere les connexions reaseau

load_dotenv() #transforme les variables dans .env en variables utilisables dans le code (os.getenv("DB_HOST")  → "localhost")

GOOGLE_API_KEY = os.getenv('GOOGLE_API_KEY') #ne change pas dans le code

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
    return pymysql.connect( #retourne une nouvelle con
        host=os.getenv('DB_HOST'),
        port=int(os.getenv('DB_PORT')), #convertit le string en entier
        user=os.getenv('DB_USER'),
        password=os.getenv('DB_PASSWORD'),
        database=os.getenv('DB_NAME'),
        charset='utf8mb4' #supporte tous les caracteres speciaux
    )

# VALIDATION EMAIL

def verifier_dns(email):
    domaine = email.split('@')[1] #split divise l'email autour de @ et retourne une liste puis on prend le deuxieme element comme domaine
    try:
        records = dns.resolver.resolve(domaine, 'MX') #les enregistrement mx pour savoir quel est le serveur
        return True, str(records[0].exchange) #chercher les serveurs mail et choisir le premier element
    except:
        return False, None #si le serveur n'est pas trouve return false,none

def verifier_smtp(email, mx_serveur):
    try:
        serveur = smtplib.SMTP(timeout=10) #se le serveur ne repond pas en 10s on abandonne
        serveur.connect(mx_serveur) #se connecter au serveur mail du domaine
        serveur.helo('gmail.com') #se presenter envoyant hello pour que gmail.com pour paraitre legitime
        serveur.mail('test@gmail.com')# envoyer un message test
        code, message = serveur.rcpt(email)#demander si la livraison de l'email a cette adresse est possible
        serveur.quit() #fermer la connexion sntp
        return code == 250 #250 est true les autres sont fausses
    except:
        return False

def valider_email(email):
    # Couche 1 — Format
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    if not bool(re.match(pattern, email)):
        print(f"   ❌ Format invalide : {email}")
        return False

    # Couche 2 — DNS
    dns_valide, mx_serveur = verifier_dns(email)
    if not dns_valide:
        print(f"   ❌ Domaine inexistant : {email}")
        return False

    # Couche 3 — SMTP
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

# APPEL GOOGLE PLACES API (NEW)

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
    if data.get('error'):
        print(f"❌ Erreur API : {data.get('error', {}).get('message')}")
        return []
    return data.get('places', [])

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
        conn.commit()
        return True
    except Exception as e:
        print(f"Erreur sauvegarde : {e}")
        return False
    finally:
        conn.close()

# LOG SCRAPING

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

# SCRAPER PRINCIPAL

def scraper(secteurs, villes, source_label):
    tous_prospects = []

    for ville in villes:
        for secteur in secteurs:
            print(f"🔍 Recherche : {secteur} à {ville}")
            places = chercher_places(secteur, ville)

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

                    if sauvegarder_prospect(prospect):
                        tous_prospects.append(prospect)
                        print(f"✅ {nom} | {ville} | Score: {score} | Email: {email}")

                    time.sleep(0.5)

                except Exception as e:
                    print(f"❌ Erreur : {e}")
                    continue

    return tous_prospects

# LANCEMENT

if __name__ == "__main__":
    tous_prospects = []

    # PARTIE 1 — Hôtels, Riads, Transport au Maroc
    print("\n" + "="*50)
    print("PARTIE 1 — Hôtels & Transport au Maroc")
    print("="*50)
    prospects_maroc = scraper(SECTEURS_HOTELS, VILLES_HOTELS, 'Google Maps Maroc')
    tous_prospects.extend(prospects_maroc)
    logger_scraping('Google Maps Maroc', len(prospects_maroc),
                    len([p for p in prospects_maroc if p['email_valide']]), 'succès')

    # PARTIE 2 — Agences & Tour Operators étrangers
    print("\n" + "="*50)
    print("PARTIE 2 — Agences & Tour Operators Étrangers")
    print("="*50)
    prospects_etranger = scraper(SECTEURS_AGENCES, VILLES_AGENCES, 'Google Maps Étranger')
    tous_prospects.extend(prospects_etranger)
    logger_scraping('Google Maps Étranger', len(prospects_etranger),
                    len([p for p in prospects_etranger if p['email_valide']]), 'succès')

    # RÉSUMÉ FINAL
    total = len(tous_prospects)
    valides = len([p for p in tous_prospects if p['email_valide']])
    print("\n" + "="*50)
    print("RÉSUMÉ FINAL")
    print("="*50)
    print(f"Total prospects collectés  : {total}")
    print(f"Emails valides             : {valides}")
    print(f"Hôtels Maroc               : {len(prospects_maroc)}")
    print(f"Agences étrangères         : {len(prospects_etranger)}")