import bcrypt
from sqlalchemy import create_engine, text
import os
from dotenv import load_dotenv

load_dotenv()

# Connexion automatique à ta base MySQL
DB_URL = f"mysql+pymysql://{os.getenv('DB_USER')}:{os.getenv('DB_PASSWORD')}@{os.getenv('DB_HOST')}:{os.getenv('DB_PORT')}/{os.getenv('DB_NAME')}"
engine = create_engine(DB_URL)

# Tes nouveaux identifiants temporaires de secours
username = "admin"
password_brut = "admin123"

# Génération d'un hash propre et compatible avec ton backend
hashed_password = bcrypt.hashpw(password_brut.encode(), bcrypt.gensalt()).decode()

try:
    with engine.connect() as conn:
        # On insère ou met à jour de force l'utilisateur 'admin' avec le bon hash
        conn.execute(text("""
            INSERT INTO users (username, password, role) 
            VALUES (:username, :password, 'admin')
            ON DUPLICATE KEY UPDATE password = :password, role = 'admin'
        """), {"username": username, "password": hashed_password})
        conn.commit()
    print(f"\n✅ Succès ! Tu peux maintenant te connecter avec :")
    print(f"👉 Identifiant : {username}")
    print(f"👉 Mot de passe : {password_brut}")
except Exception as e:
    print(f"❌ Erreur lors de la mise à jour : {e}")