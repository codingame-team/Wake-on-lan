import secrets

# Génère une clé secrète de 32 octets (256 bits) et la convertit en une chaîne hexadécimale.
# C'est une méthode recommandée pour les clés secrètes de Flask.
secret_key = secrets.token_hex(32)

print("Clé secrète générée :")
print(secret_key)
print("\nCopiez cette clé et collez-la dans votre fichier .env pour la variable SECRET_KEY.")

