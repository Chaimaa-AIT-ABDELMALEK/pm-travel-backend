from openai import OpenAI
import sendgrid
from sendgrid.helpers.mail import Mail
from dotenv import load_dotenv
import os
import pymysql
from datetime import datetime, timedelta
import json

load_dotenv()

# ─────────────────────────────────────────
# CLIENTS API
# ─────────────────────────────────────────

openai_client = OpenAI(
    api_key=os.getenv('OPENAI_API_KEY')
)

sg_client = sendgrid.SendGridAPIClient(
    api_key=os.getenv('SENDGRID_API_KEY')
)

# ─────────────────────────────────────────
# CONNEXION BASE DE DONNÉES
# ─────────────────────────────────────────

def connect_db():
    return pymysql.connect(
        host=os.getenv('DB_HOST'),
        port=int(os.getenv('DB_PORT')),
        user=os.getenv('DB_USER'),
        password=os.getenv('DB_PASSWORD'),
        database=os.getenv('DB_NAME'),
        charset='utf8mb4'
    )
# ─────────────────────────────────────────
# THÈMES TOURISTIQUES PM TRAVEL
# ─────────────────────────────────────────

THEMES_TOURISTIQUES = {
    'desert': {
        'description': 'circuits désert Sahara Merzouga dunes coucher soleil',
        'hashtags': ['#Sahara', '#Merzouga', '#MarocDesert']
    },
    'medina': {
        'description': 'médina Marrakech souks riads architecture',
        'hashtags': ['#Marrakech', '#Medina', '#Riad']
    },
    'montagne': {
        'description': 'montagnes Atlas randonnée villages berbères',
        'hashtags': ['#AtlasMountains', '#Hiking', '#BerberVillage']
    },
    'gastronomie': {
        'description': 'cuisine marocaine tajine couscous épices',
        'hashtags': ['#MarocCuisine', '#Tajine', '#Couscous']
    },
    'luxe': {
        'description': 'séjours luxe riads palais spa exclusifs',
        'hashtags': ['#LuxuryMorocco', '#RiadLuxe', '#SpaMaroc']
    },
    'aventure': {
        'description': 'aventure quad buggy escalade sports extrêmes',
        'hashtags': ['#AdventureMorocco', '#Quad', '#ExtremeTravel']
    }
}
# ─────────────────────────────────────────
# DÉTECTION DE LANGUE
# ─────────────────────────────────────────

def detecter_langue(ville):
    villes_anglais = [
        'new york', 'los angeles', 'miami',
        'chicago', 'toronto', 'montreal'
    ]
    villes_espagnol = [
        'mexico city', 'buenos aires', 'bogota',
        'santiago', 'lima', 'sao paulo', 'rio de janeiro'
    ]
    ville_lower = ville.lower()
    if any(v in ville_lower for v in villes_anglais):
        return 'anglais'
    if any(v in ville_lower for v in villes_espagnol):
        return 'espagnol'
    return 'français'

# ─────────────────────────────────────────
# GÉNÉRATION EMAIL AVEC CHATGPT API
# ─────────────────────────────────────────

def generer_contenu_email(prospect):
    langue = detecter_langue(prospect['ville'])

    if langue == 'anglais':
        instruction_langue = "Write the email in English."
    elif langue == 'espagnol':
        instruction_langue = "Escribe el email en español."
    else:
        instruction_langue = "Écris l'email en français."

    prompt = f"""
    Tu es un expert en marketing pour PM Travel, une agence de voyage
    marocaine professionnelle basée à Marrakech spécialisée dans le
    tourisme culturel, les circuits désert, et les séjours de luxe.

    Écris un email de prospection B2B professionnel et personnalisé
    pour ce prospect :
    - Nom : {prospect['nom']}
    - Secteur : {prospect['secteur']}
    - Ville : {prospect['ville']}
    - Score de pertinence : {prospect['score']}/100

    Règles importantes :
    - {instruction_langue}
    - Ton chaleureux mais professionnel
    - Propose un partenariat concret et avantageux
    - Mentionne des avantages spécifiques selon leur secteur
    - Termine avec un appel à l'action clair
    - Maximum 150 mots
    - Ne mets pas de signature ni d'objet

    Retourne UNIQUEMENT le corps de l'email, rien d'autre.
    """

    response = openai_client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {
                "role": "system",
                "content": "Tu es un expert en marketing B2B pour une agence de voyage marocaine."
            },
            {
                "role": "user",
                "content": prompt
            }
        ],
        max_tokens=500,
        temperature=0.7
    )

    return response.choices[0].message.content

def generer_sujet_email(prospect):
    langue = detecter_langue(prospect['ville'])

    if langue == 'anglais':
        instruction = "Generate a catchy email subject in English."
    elif langue == 'espagnol':
        instruction = "Genera un asunto de email atractivo en español."
    else:
        instruction = "Génère un objet d'email accrocheur en français."

    prompt = f"""
    {instruction}

    Pour une agence de voyage marocaine PM Travel qui contacte :
    - {prospect['nom']}
    - Secteur : {prospect['secteur']}
    - Ville : {prospect['ville']}

    Maximum 10 mots. Retourne UNIQUEMENT l'objet, rien d'autre.
    """

    response = openai_client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {
                "role": "system",
                "content": "Tu génères des sujets d'emails marketing accrocheurs."
            },
            {
                "role": "user",
                "content": prompt
            }
        ],
        max_tokens=50,
        temperature=0.8
    )

    return response.choices[0].message.content.strip()

# ─────────────────────────────────────────
# TEMPLATE HTML EMAIL
# ─────────────────────────────────────────

def construire_html_email(contenu, nom_prospect):
    contenu_html = contenu.replace('\n', '<br>')

    return f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
    </head>
    <body style="margin:0; padding:0; background-color:#f5f5f5; font-family: Arial, sans-serif;">
        <table width="100%" cellpadding="0" cellspacing="0">
            <tr>
                <td align="center" style="padding: 40px 0;">
                    <table width="600" cellpadding="0" cellspacing="0"
                        style="background:#ffffff; border-radius:8px; overflow:hidden;">

                        <!-- HEADER -->
                        <tr>
                            <td style="background:#1D9E75; padding:30px 40px;">
                                <h1 style="color:#ffffff; margin:0; font-size:22px;">
                                    PM Travel Agency
                                </h1>
                                <p style="color:#E1F5EE; margin:5px 0 0; font-size:14px;">
                                    Marrakech, Maroc — Tourisme & Partenariats
                                </p>
                            </td>
                        </tr>

                        <!-- CORPS -->
                        <tr>
                            <td style="padding:40px;">
                                <p style="color:#333333; font-size:15px; line-height:1.7; margin:0;">
                                    {contenu_html}
                                </p>
                            </td>
                        </tr>

                        <!-- SIGNATURE -->
                        <tr>
                            <td style="padding:0 40px 30px;">
                                <table cellpadding="0" cellspacing="0">
                                    <tr>
                                        <td style="border-left:3px solid #1D9E75; padding-left:15px;">
                                            <p style="margin:0; font-size:14px; font-weight:bold; color:#333;">
                                                Équipe PM Travel
                                            </p>
                                            <p style="margin:3px 0 0; font-size:13px; color:#666;">
                                                contact@pmtravel.ma
                                            </p>
                                            <p style="margin:3px 0 0; font-size:13px; color:#666;">
                                                +212 5XX-XXXXXX
                                            </p>
                                        </td>
                                    </tr>
                                </table>
                            </td>
                        </tr>

                        <!-- FOOTER -->
                        <tr>
                            <td style="background:#f9f9f9; padding:20px 40px;
                                border-top:1px solid #eee;">
                                <p style="margin:0; font-size:11px; color:#999; text-align:center;">
                                    PM Travel Agency — Marrakech, Maroc<br>
                                    Vous recevez cet email car votre établissement
                                    correspond à nos critères de partenariat.<br>
                                    <a href="#" style="color:#1D9E75; text-decoration:none;">
                                        Se désinscrire
                                    </a>
                                </p>
                            </td>
                        </tr>

                    </table>
                </td>
            </tr>
        </table>
    </body>
    </html>
    """

# ─────────────────────────────────────────
# ENVOI EMAIL VIA SENDGRID
# ─────────────────────────────────────────

def envoyer_email(destinataire, sujet, contenu_texte, nom_prospect):
    html = construire_html_email(contenu_texte, nom_prospect)

    message = Mail(
        from_email=os.getenv('SENDGRID_FROM_EMAIL'),
        to_emails=destinataire,
        subject=sujet,
        html_content=html
    )

    try:
        response = sg_client.send(message)
        status = response.status_code
        print(f"🔍 SendGrid response status: {status}")
        # Succès pour tous les codes 2xx
        if 200 <= status < 300:
            print(f"   ✅ Email envoyé à {destinataire}")
            return True
        else:
            print(f"   ❌ Échec envoi à {destinataire} — code {status}")
            return False
    except Exception as e:
        print(f"   ❌ Erreur SendGrid : {e}")
        return False
    html = construire_html_email(contenu_texte, nom_prospect)

    message = Mail(
        from_email=os.getenv('SENDGRID_FROM_EMAIL'),
        to_emails=destinataire,
        subject=sujet,
        html_content=html
    )

    try:
        response = sg_client.send(message)
        status = response.status_code
        # ✅ Succès pour tous les codes 2xx (200, 201, 202, etc.)
        succes = 200 <= status < 300
        if succes:
            print(f"   ✅ Email envoyé à {destinataire} (status {status})")
        else:
            print(f"   ❌ Échec envoi à {destinataire} — code {status}")
        return succes
    except Exception as e:
        print(f"   ❌ Erreur SendGrid : {e}")
        return False
    
# ─────────────────────────────────────────
# SAUVEGARDER EMAIL ENVOYÉ
# ─────────────────────────────────────────

def sauvegarder_email(campagne_id, prospect_id, email, sujet, contenu, statut):
    """Sauvegarde un email envoyé dans la table emails_envoyes"""
    conn = connect_db()
    try:
        with conn.cursor() as cursor:
            cursor.execute("""
                INSERT INTO emails_envoyes
                (campagne_id, prospect_id, email_destinataire, sujet, contenu, statut, date_envoi)
                VALUES (%s, %s, %s, %s, %s, %s, NOW())
            """, (campagne_id, prospect_id, email, sujet, contenu, statut))
        conn.commit()
        print(f"   ✅ Email sauvegardé en base (prospect {prospect_id})")
        return True
    except Exception as e:
        print(f"   ❌ Erreur sauvegarde email : {e}")
        return False
    finally:
        conn.close()

# ─────────────────────────────────────────
# CRÉER SÉQUENCE DE RELANCE
# ─────────────────────────────────────────

def creer_sequence(campagne_id, prospect_id):
    conn = connect_db()
    try:
        with conn.cursor() as cursor:
            cursor.execute("""
                INSERT INTO sequences_email
                (campagne_id, prospect_id, etape, prochaine_relance, statut)
                VALUES (%s, %s, 1, %s, 'actif')
            """, (
                campagne_id,
                prospect_id,
                datetime.now() + timedelta(days=3)
            ))
        conn.commit()
    except Exception as e:
        print(f"Erreur séquence : {e}")
    finally:
        conn.close()
# ─────────────────────────────────────────
# GESTION DE LA ROTATION DES THÈMES
# ─────────────────────────────────────────

def obtenir_theme_courant(plateforme):
    """Récupère le thème actuel pour une plateforme"""
    conn = connect_db()
    try:
        with conn.cursor() as cursor:
            cursor.execute("""
                SELECT theme_index, themes_list
                FROM rotation_themes
                WHERE plateforme = %s
            """, (plateforme,))
            
            result = cursor.fetchone()
            if not result:
                cursor.execute("""
                    INSERT INTO rotation_themes (plateforme)
                    VALUES (%s)
                """, (plateforme,))
                conn.commit()
                return list(THEMES_TOURISTIQUES.keys())[0]
            
            theme_index = result[0]
            themes_list = json.loads(result[1])
            theme = themes_list[theme_index % len(themes_list)]
            return theme
    finally:
        conn.close()


def incrementer_theme_index(plateforme):
    """Avance au thème suivant"""
    conn = connect_db()
    try:
        with conn.cursor() as cursor:
            cursor.execute("""
                UPDATE rotation_themes
                SET theme_index = (theme_index + 1) % 18
                WHERE plateforme = %s
            """, (plateforme,))
            conn.commit()
    finally:
        conn.close()


def obtenir_position_rotation(plateforme):
    """Récupère la position actuelle dans la rotation"""
    conn = connect_db()
    try:
        with conn.cursor() as cursor:
            cursor.execute("""
                SELECT theme_index
                FROM rotation_themes
                WHERE plateforme = %s
            """, (plateforme,))
            
            result = cursor.fetchone()
            return result[0] if result else 0
    finally:
        conn.close()


def obtenir_tous_les_themes(plateforme):
    """Récupère la liste des thèmes"""
    conn = connect_db()
    try:
        with conn.cursor() as cursor:
            cursor.execute("""
                SELECT themes_list
                FROM rotation_themes
                WHERE plateforme = %s
            """, (plateforme,))
            
            result = cursor.fetchone()
            if result:
                return json.loads(result[0])
            return list(THEMES_TOURISTIQUES.keys())
    finally:
        conn.close()