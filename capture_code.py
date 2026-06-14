import requests
import webbrowser
import http.server
import urllib.parse
import threading

CLIENT_ID = "77gv64f21qe5eu"
CLIENT_SECRET = input("Collez votre Client Secret LinkedIn: ")

auth_code = None

class Handler(http.server.SimpleHTTPRequestHandler):
    def do_GET(self):
        global auth_code
        parsed = urllib.parse.urlparse(self.path)
        params = urllib.parse.parse_qs(parsed.query)
        
        if 'code' in params:
            auth_code = params['code'][0]
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"Success! Token received. You can close this window.")
        elif 'error' in params:
            error = params['error'][0]
            error_desc = params.get('error_description', [''])[0]
            print(f"\n❌ Erreur: {error}")
            print(f"   {error_desc}")
            self.send_response(400)
            self.end_headers()
            self.wfile.write(b"Error occurred. Check terminal.")
            global server_running
            server_running = False
        else:
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"Waiting for authorization...")

# Lance le serveur
server = http.server.HTTPServer(('localhost', 8000), Handler)
thread = threading.Thread(target=server.serve_forever)
thread.daemon = True
thread.start()

# Utilise uniquement r_liteprofile (le scope de base)
auth_url = f"https://www.linkedin.com/oauth/v2/authorization?response_type=code&client_id={CLIENT_ID}&redirect_uri=http://localhost:8000/callback&scope=r_liteprofile"
print("\n🔑 Ouverture de LinkedIn pour autorisation...")
print("📌 Scopes demandés: r_liteprofile (lecture profil uniquement)")
webbrowser.open(auth_url)

# Attend le code
import time
timeout = 60  # 60 secondes max
start = time.time()
while auth_code is None and (time.time() - start) < timeout:
    time.sleep(1)

server.shutdown()

if auth_code:
    print("\n⏳ Génération du token...")
    response = requests.post(
        "https://www.linkedin.com/oauth/v2/accessToken",
        data={
            "grant_type": "authorization_code",
            "code": auth_code,
            "client_id": CLIENT_ID,
            "client_secret": CLIENT_SECRET,
            "redirect_uri": "http://localhost:8000/callback"
        }
    )
    
    if response.status_code == 200:
        data = response.json()
        print("\n" + "="*60)
        print("✅ VOTRE ACCESS TOKEN :")
        print("="*60)
        print(data['access_token'])
        print("="*60)
        print(f"\n⏰ Expire dans {data['expires_in']} secondes ({data['expires_in']//86400} jours)")
        
        # Sauvegarde
        with open('linkedin_token.txt', 'w') as f:
            f.write(data['access_token'])
        print("\n💾 Token sauvegardé dans linkedin_token.txt")
    else:
        print(f"\n❌ Erreur: {response.text}")
else:
    print("\n❌ Timeout - Aucun code reçu")