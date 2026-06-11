# generate_n8n_token.py
import jwt
from datetime import datetime, timedelta

SECRET_KEY = "g8KAVbu1EtWuNbJZ6_NtHpfEeJ-mnBunpQSYkByZgOM"  # ⚠️ remplace par ta vraie valeur JWT_SECRET_KEY dans .env

payload = {
    'user_id': 1,
    'role': 'admin',
    'exp': datetime.utcnow() + timedelta(days=365)  # 1 an
}

token = jwt.encode(payload, SECRET_KEY, algorithm="HS256")
print("TOKEN:", token)