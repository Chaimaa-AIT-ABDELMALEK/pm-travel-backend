from openai import OpenAI
from dotenv import load_dotenv
import os
import requests
import pymysql
from datetime import datetime, timedelta
import json

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

    # Limites de caractères par plateforme
    limites = {
        'instagram': 2200,
        'facebook': 500,
        'linkedin': 700,
        'tiktok': 300
    }
    limite = limites.get(plateforme, 500)

    # Ton par plateforme
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
            {
                "role": "system",
                "content": "Tu es un expert en marketing digital pour le tourisme marocain."
            },
            {
                "role": "user",
                "content": prompt
            }
        ],
        max_tokens=600,
        temperature=0.8
    )

    return response.choices[0].message.content.strip()

# ─────────────────────────────────────────
# GÉNÉRATION IMAGE AVEC DALL-E
# ─────────────────────────────────────────

def generer_image_post(theme):
    theme_info = THEMES_TOURISTIQUES.get(theme, THEMES_TOURISTIQUES['medina'])

    prompts_images = {
        'desert': "Stunning Sahara desert landscape at golden sunset, Morocco, sand dunes, camel silhouette, warm colors, professional travel photography",
        'medina': "Beautiful Marrakech medina street, colorful souks, traditional Moroccan architecture, lanterns, vibrant colors, professional photography",
        'montagne': "Atlas Mountains Morocco, green valleys, traditional Berber village, snow peaks, dramatic landscape, professional travel photography",
        'gastronomie': "Traditional Moroccan food spread, tajine, colorful spices, couscous, mint tea, beautiful ceramic plates, professional food photography",
        'luxe': "Luxury Moroccan riad courtyard, pool, roses, tiles zellige, elegant decor, soft lighting, professional architecture photography",
        'aventure': "Adventure quad biking in Moroccan desert, action shot, dust, sunset, exciting outdoor activity, professional photography"
    }

    image_prompt = prompts_images.get(
        theme,
        "Beautiful Morocco landscape, travel photography, vibrant colors"
    )

    response = openai_client.images.generate(
        model="dall-e-3",
        prompt=image_prompt,
        size="1024x1024",
        quality="standard",
        n=1
    )

    image_url = response.data[0].url
    return image_url

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
    """
    Génère un post complet.
    Si theme=None, utilise le thème courant de la plateforme.
    """
    
    # Si aucun thème spécifié, utilise la rotation automatique
    if theme is None:
        theme = obtenir_theme_courant(plateforme)
    
    print(f"\n🎨 Génération post {plateforme} — thème: {theme}")

    if not date_publication:
        date_publication = datetime.now() + timedelta(hours=1)

    # Générer le contenu texte
    contenu = generer_contenu_post(plateforme, theme, langue)
    print(f"   ✅ Contenu généré ({len(contenu)} caractères)")

    # Générer l'image
    image_url = generer_image_post(theme)
    print(f"   ✅ Image générée")

    # Récupérer les hashtags du thème
    hashtags = THEMES_TOURISTIQUES.get(
        theme,
        THEMES_TOURISTIQUES['medina']
    )['hashtags']

    # Sauvegarder dans MySQL
    post_id = sauvegarder_post(
        plateforme,
        contenu,
        image_url,
        hashtags,
        theme,
        langue,
        date_publication
    )
    
    # IMPORTANT: Avancer au thème suivant après la génération
    incrementer_theme_index(plateforme)
    
    position = obtenir_position_rotation(plateforme)
    print(f"   📊 Prochaine position: {position}/6 pour {plateforme}")

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
    """
    Génère automatiquement un calendrier de posts pour toute la semaine.
    3 posts par jour sur différentes plateformes.
    
    IMPORTANT: Chaque plateforme utilise sa propre rotation de thèmes!
    """
    plateformes = ['instagram', 'facebook', 'linkedin']
    langues = ['français', 'anglais', 'espagnol']

    posts_generes = []
    maintenant = datetime.now()

    print("\n" + "="*60)
    print("🎯 GÉNÉRATION CALENDRIER HEBDOMADAIRE INTELLIGENTE")
    print("="*60)

    # 7 jours × 3 posts = 21 posts pour la semaine
    for jour in range(7):
        jour_nom = ['Lundi', 'Mardi', 'Mercredi', 'Jeudi', 'Vendredi', 'Samedi', 'Dimanche'][jour]
        print(f"\n📅 {jour_nom}")
        print("-" * 60)
        
        for plateforme in plateformes:
            # Heure de publication optimale par plateforme
            heures_optimales = {
                'instagram': 18,  # 18h
                'facebook': 12,   # 12h
                'linkedin': 9     # 9h
            }
            heure = heures_optimales.get(plateforme, 12)

            date_pub = maintenant.replace(
                hour=heure, minute=0, second=0
            ) + timedelta(days=jour)

            # LA CLÉ: Pas de thème spécifié!
            # La fonction utilisera la rotation automatique
            theme = obtenir_theme_courant(plateforme)
            langue = langues[jour % len(langues)]

            post = generer_post_complet(plateforme, theme, langue, date_pub)
            posts_generes.append(post)

    print("\n" + "="*60)
    print(f"✅ CALENDRIER COMPLET GÉNÉRÉ: {len(posts_generes)} posts")
    print("="*60)
    
    return posts_generes
# ─────────────────────────────────────────
# METTRE À JOUR STATUT POST
# ─────────────────────────────────────────

def mettre_a_jour_statut_post(post_id, statut):
    conn = connect_db()
    try:
        with conn.cursor() as cursor:
            cursor.execute("""
                UPDATE posts_sociaux SET statut = %s WHERE id = %s
            """, (statut, post_id))
            cursor.execute("""
                UPDATE calendrier_editorial SET statut = %s WHERE post_id = %s
            """, (
                'publié' if statut == 'publié' else statut,
                post_id
            ))
        conn.commit()
    finally:
        conn.close()

# ─────────────────────────────────────────
# LOGGER ACTION
# ─────────────────────────────────────────

def logger_action(post_id, plateforme, action, resultat):
    conn = connect_db()
    try:
        with conn.cursor() as cursor:
            cursor.execute("""
                INSERT INTO logs_sociaux
                (post_id, plateforme, action, resultat)
                VALUES (%s, %s, %s, %s)
            """, (post_id, plateforme, action, resultat))
        conn.commit()
    finally:
        conn.close()
        # ─────────────────────────────────────────
# GESTION DE LA ROTATION DES THÈMES
# ─────────────────────────────────────────

def obtenir_theme_courant(plateforme):
    """
    Récupère le thème actuel pour une plateforme
    basé sur son index de rotation.
    """
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
                # Si la plateforme n'existe pas, créer une entrée
                cursor.execute("""
                    INSERT INTO rotation_themes (plateforme)
                    VALUES (%s)
                """, (plateforme,))
                conn.commit()
                return list(THEMES_TOURISTIQUES.keys())[0]
            
            theme_index = result[0]
            themes_list = json.loads(result[1])
            
            # Récupérer le thème à cet index
            theme = themes_list[theme_index % len(themes_list)]
            return theme
            
    finally:
        conn.close()


def incrementer_theme_index(plateforme):
    """
    Avance au thème suivant pour une plateforme.
    Se réinitialise automatiquement à 0 après le dernier thème.
    """
    conn = connect_db()
    try:
        with conn.cursor() as cursor:
            cursor.execute("""
                UPDATE rotation_themes
                SET theme_index = (theme_index + 1) % 6
                WHERE plateforme = %s
            """, (plateforme,))
            conn.commit()
            print(f"   ✅ Index avancé pour {plateforme}")
            
    finally:
        conn.close()


def obtenir_tous_les_themes(plateforme):
    """
    Récupère la liste complète des thèmes pour une plateforme.
    """
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


def obtenir_position_rotation(plateforme):
    """
    Récupère la position actuelle dans la rotation.
    Utile pour afficher: "Theme 2/6"
    """
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