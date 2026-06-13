from cryptography.fernet import Fernet

# Génère une clé Fernet valide
new_key = Fernet.generate_key().decode()
print(f"Votre nouvelle clé ENCRYPTION_KEY : {new_key}")