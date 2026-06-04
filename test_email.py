import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from emails.email_service import generer_contenu_email, generer_sujet_email, envoyer_email

# Prospect fictif pour le test
prospect = {
    'nom': 'Test Hotel Marrakech',
    'email': 'chaimaaait2005@gmail.com',
    'secteur': 'hotel',
    'ville': 'Marrakech',
    'score': 85
}

print("🤖 Génération du contenu avec ChatGPT...")
contenu = generer_contenu_email(prospect)
print(f"✅ Contenu généré :\n{contenu}\n")

print("📝 Génération du sujet...")
sujet = generer_sujet_email(prospect)
print(f"✅ Sujet : {sujet}\n")

print("📧 Envoi de l'email à chaimaaait2005@gmail.com...")
succes = envoyer_email(
    'chaimaaait2005@gmail.com',
    sujet,
    contenu,
    prospect['nom']
)

if succes:
    print("✅ Email envoyé ! Vérifie ta boîte Gmail.")
else:
    print("❌ Erreur lors de l'envoi")