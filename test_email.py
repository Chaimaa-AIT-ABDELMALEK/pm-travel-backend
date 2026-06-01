from emails.email_service import envoyer_email, sauvegarder_email

# Données de test
prospect = {
    'nom': 'Test Hotel',
    'email': 'prospect@example.com',  # Sera ignoré en test!
    'secteur': 'Hôtel',
    'ville': 'Marrakech',
    'score': 85
}

sujet = "🏨 Partenariat PM Travel - Test"
contenu = "Bonjour,\n\nCeci est un email de test.\n\nCordialement,\nPM Travel"

# Envoyer
succes = envoyer_email(prospect['email'], sujet, contenu, prospect['nom'])

if succes:
    print("✅ Email de test envoyé!")
    print(f"   Vérifiez: {prospect['email']}")
else:
    print("❌ Erreur lors de l'envoi")