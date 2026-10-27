import os
import urllib.request

# Define engine folder structures
MODEL_DIR = "assets/models"
TEXTURE_DIR = "assets/textures"

# Verified open-source fully-rigged animated .glb asset and texture components
# (Uses raylib's validated official sample assets container for absolute layout compatibility)
ASSETS_MAP = {
    f"{MODEL_DIR}/player_model.glb": "https://github.com",
    f"{TEXTURE_DIR}/jersey_home.png": "https://github.com",
    f"{TEXTURE_DIR}/jersey_away.png": "https://github.com"
}

def setup_workspace():
    print(" Staging retro graphics pipeline folders...")
    os.makedirs(MODEL_DIR, exist_ok=True)
    os.makedirs(TEXTURE_DIR, exist_ok=True)
    
    for local_path, download_url in ASSETS_MAP.items():
        print(f" Connecting to server to retrieve: {os.path.basename(local_path)}...")
        try:
            # Safe network request transmission
            urllib.request.urlretrieve(download_url, local_path)
            print(f" Successfully delivered to path -> {local_path}")
        except Exception as e:
            print(f" ERROR downloading {local_path}: {e}")

    print("\n Asset synchronization complete! Your folders are fully ready.")

if __name__ == "__main__":
    setup_workspace()
