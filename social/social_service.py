from openai import OpenAI
from dotenv import load_dotenv
import os
import requests
import pymysql
from datetime import datetime, timedelta
import json
import base64

load_dotenv()

# ─────────────────────────────────────────
# CLIENT OPENAI
# ─────────────────────────────────────────

openai_client = OpenAI(
    api_key=os.getenv('OPENAI_API_KEY')
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
        'hashtags': ['#Sahara', '#Merzouga', '#MarocDesert', '#Dunes', '#SunsetSahara', '#MoroccoTravel', '#DesertTour']
    },
    'medina': {
        'description': 'médina Marrakech souks riads architecture traditionnelle',
        'hashtags': ['#Marrakech', '#Medina', '#Riad', '#Souk', '#MarocCulture', '#VisitMorocco', '#MarrakechLife']
    },
    'montagne': {
        'description': 'montagnes Atlas randonnée villages berbères nature',
        'hashtags': ['#AtlasMountains', '#Hiking', '#BerberVillage', '#Nature', '#MoroccoNature', '#Trekking']
    },
    'gastronomie': {
        'description': 'cuisine marocaine tajine couscous épices saveurs',
        'hashtags': ['#MarocCuisine', '#Tajine', '#Couscous', '#FoodMorocco', '#MoroccanFood', '#Gastronomie']
    },
    'luxe': {
        'description': 'séjours luxe riads palais spa expériences exclusives',
        'hashtags': ['#LuxuryMorocco', '#RiadLuxe', '#MarocLuxe', '#SpaMaroc', '#ExclusiveTravel', '#5StarMorocco']
    },
    'aventure': {
        'description': 'aventure quad buggy escalade sports extrêmes Maroc',
        'hashtags': ['#AdventureMorocco', '#Quad', '#MarocAventure', '#ExtremeTravel', '#OutdoorMorocco']
    }
}


# ─────────────────────────────────────────
# GÉNÉRATION IMAGE
# ─────────────────────────────────────────

import random

def generer_image_post(theme):
    """
    Génère une image aléatoire unique pour chaque post
    Utilise Picsum (gratuit, fiable, pas d'API key)
    """
    # IDs d'images qui ressemblent à des photos de voyage
    # (paysages, désert, montagnes, architecture, nourriture, luxe)
    images_par_theme = {
        'desert': [104, 105, 106, 107, 108, 109, 110, 111, 112],
        'medina': [113, 114, 115, 116, 117, 118, 119, 120],
        'montagne': [121, 122, 123, 124, 125, 126, 127, 128],
        'gastronomie': [129, 130, 131, 132, 133, 134, 135],
        'luxe': [136, 137, 138, 139, 140, 141, 142],
        'aventure': [143, 144, 145, 146, 147, 148, 149, 150]
    }
    
    # Prend les IDs du thème, ou tous si thème non trouvé
    ids_disponibles = images_par_theme.get(theme, list(range(1, 200)))
    
    # Choisit un ID aléatoire
    image_id = random.choice(ids_disponibles)
    
    # Format fixe 800x600 (bon pour Instagram/Facebook)
    url = f"https://picsum.photos/id/{image_id}/800/600.jpg"
    
    print(f"   🖼️ Image générée pour thème '{theme}': {url}")
    return url

# ─────────────────────────────────────────
# GÉNÉRATION CONTENU AVEC CHATGPT
# ─────────────────────────────────────────

def generer_contenu_post(plateforme, theme, langue='français'):
    theme_info = THEMES_TOURISTIQUES.get(theme, THEMES_TOURISTIQUES['medina'])

    if langue == 'anglais':
        instruction_langue = "Write the post in English."
    elif langue == 'espagnol':
        instruction_langue = "Escribe el post en español."
    else:
        instruction_langue = "Écris le post en français."

    limites = {
        'instagram': 2200,
        'facebook': 500,
        'linkedin': 700,
        'tiktok': 300
    }
    limite = limites.get(plateforme, 500)

    tons = {
        'instagram': 'inspirant et visuel avec des emojis',
        'facebook': 'chaleureux et engageant pour une communauté',
        'linkedin': 'professionnel et informatif pour des partenaires B2B',
        'tiktok': 'dynamique court et accrocheur pour les jeunes'
    }
    ton = tons.get(plateforme, 'engageant')

    prompt = f"""
    Tu es le community manager de PM Travel Agency, une agence de voyage
    marocaine professionnelle basée à Marrakech.

    Crée un post {plateforme} sur le thème : {theme_info['description']}

    Règles :
    - {instruction_langue}
    - Ton {ton}
    - Maximum {limite} caractères
    - Inclus un appel à l'action
    - Ne mets PAS les hashtags dans le texte — ils seront ajoutés séparément
    - Mentionne PM Travel naturellement dans le texte

    Retourne UNIQUEMENT le texte du post, rien d'autre.
    """

    response = openai_client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": "Tu es un expert en marketing digital pour le tourisme marocain."},
            {"role": "user", "content": prompt}
        ],
        max_tokens=600,
        temperature=0.8
    )

    return response.choices[0].message.content.strip()

# ─────────────────────────────────────────
# SAUVEGARDER POST DANS MYSQL
# ─────────────────────────────────────────

def sauvegarder_post(plateforme, contenu, image_url, hashtags, theme, langue, date_publication):
    conn = connect_db()
    try:
        with conn.cursor() as cursor:
            cursor.execute("""
                INSERT INTO posts_sociaux
                (plateforme, contenu, image_url, hashtags, statut,
                date_publication, theme, langue)
                VALUES (%s, %s, %s, %s, 'planifié', %s, %s, %s)
            """, (
                plateforme,
                contenu,
                image_url,
                json.dumps(hashtags),
                date_publication,
                theme,
                langue
            ))
            post_id = cursor.lastrowid

            cursor.execute("""
                INSERT INTO calendrier_editorial
                (post_id, date_planifiee, plateforme, statut)
                VALUES (%s, %s, %s, 'planifié')
            """, (post_id, date_publication, plateforme))

        conn.commit()
        print(f"   ✅ Post sauvegardé — ID: {post_id} | {plateforme} | {theme}")
        return post_id
    except Exception as e:
        print(f"   ❌ Erreur sauvegarde post : {e}")
        return None
    finally:
        conn.close()

# ─────────────────────────────────────────
# GÉNÉRER UN POST COMPLET
# ─────────────────────────────────────────

def generer_post_complet(plateforme, theme=None, langue='français', date_publication=None):
    if theme is None:
        theme = obtenir_theme_courant(plateforme)
    
    print(f"\n🎨 Génération post {plateforme} — thème: {theme}")

    if not date_publication:
        date_publication = datetime.now() + timedelta(hours=1)

    contenu = generer_contenu_post(plateforme, theme, langue)
    print(f"   ✅ Contenu généré ({len(contenu)} caractères)")

    image_url = generer_image_post(theme)
    print(f"   ✅ Image générée: {image_url[:80]}...")

    hashtags = THEMES_TOURISTIQUES.get(theme, THEMES_TOURISTIQUES['medina'])['hashtags']

    post_id = sauvegarder_post(plateforme, contenu, image_url, hashtags, theme, langue, date_publication)
    
    incrementer_theme_index(plateforme)
    
    position = obtenir_position_rotation(plateforme)
    print(f"   📊 Prochaine position: {position+1}/6 pour {plateforme}")

    return {
        'id': post_id,
        'plateforme': plateforme,
        'contenu': contenu,
        'image_url': image_url,
        'hashtags': hashtags,
        'theme': theme,
        'langue': langue,
        'date_publication': str(date_publication)
    }

# ─────────────────────────────────────────
# GÉNÉRER CALENDRIER HEBDOMADAIRE
# ─────────────────────────────────────────

def generer_calendrier_semaine():
    plateformes = ['instagram', 'facebook', 'linkedin']
    langues = ['français', 'anglais', 'espagnol']

    posts_generes = []
    maintenant = datetime.now()

    print("\n" + "="*60)
    print("🎯 GÉNÉRATION CALENDRIER HEBDOMADAIRE")
    print("="*60)

    for jour in range(7):
        jour_nom = ['Lundi', 'Mardi', 'Mercredi', 'Jeudi', 'Vendredi', 'Samedi', 'Dimanche'][jour]
        print(f"\n📅 {jour_nom}")
        
        for plateforme in plateformes:
            heures_optimales = {'instagram': 18, 'facebook': 12, 'linkedin': 9}
            heure = heures_optimales.get(plateforme, 12)

            date_pub = maintenant.replace(hour=heure, minute=0, second=0) + timedelta(days=jour)

            theme = obtenir_theme_courant(plateforme)
            langue = langues[jour % len(langues)]

            post = generer_post_complet(plateforme, theme, langue, date_pub)
            posts_generes.append(post)

    print("\n" + "="*60)
    print(f"✅ {len(posts_generes)} posts générés")
    print("="*60)
    
    return posts_generes

# ─────────────────────────────────────────
# GESTION DE LA ROTATION DES THÈMES
# ─────────────────────────────────────────

def obtenir_theme_courant(plateforme):
    conn = connect_db()
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT theme_index, themes_list FROM rotation_themes WHERE plateforme = %s", (plateforme,))
            result = cursor.fetchone()
            if not result:
                cursor.execute("INSERT INTO rotation_themes (plateforme) VALUES (%s)", (plateforme,))
                conn.commit()
                return list(THEMES_TOURISTIQUES.keys())[0]
            
            theme_index = result[0]
            themes_list = json.loads(result[1])
            return themes_list[theme_index % len(themes_list)]
    finally:
        conn.close()

def incrementer_theme_index(plateforme):
    conn = connect_db()
    try:
        with conn.cursor() as cursor:
            cursor.execute("UPDATE rotation_themes SET theme_index = (theme_index + 1) %% 6 WHERE plateforme = %s", (plateforme,))
            conn.commit()
    finally:
        conn.close()

def obtenir_position_rotation(plateforme):
    conn = connect_db()
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT theme_index FROM rotation_themes WHERE plateforme = %s", (plateforme,))
            result = cursor.fetchone()
            return result[0] if result else 0
    finally:
        conn.close()