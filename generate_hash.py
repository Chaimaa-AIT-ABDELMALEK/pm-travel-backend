import bcrypt

password = "admin123"
hashed = bcrypt.hashpw(password.encode(), bcrypt.gensalt())
print(f"Hash: {hashed.decode()}")