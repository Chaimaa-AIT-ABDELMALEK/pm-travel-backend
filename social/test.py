from emails.email_service import obtenir_position_rotation

for plateforme in ['instagram', 'facebook', 'linkedin']:
    pos = obtenir_position_rotation(plateforme)
    print(f"{plateforme}: position {pos}/6")