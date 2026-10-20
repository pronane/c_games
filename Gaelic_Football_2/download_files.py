import os
from urllib.parse import urljoin, urlparse
from bs4 import BeautifulSoup
import requests

# Target URL
URL = "https://library.pardallgames.com/g/goldeneye-007"
# Folder where images will be saved
OUTPUT_FOLDER = "goldeneye_images"


def download_images():
    # Create the output directory if it doesn't exist
    if not os.path.exists(OUTPUT_FOLDER):
        os.makedirs(OUTPUT_FOLDER)
        print(f"Created directory: {OUTPUT_FOLDER}")

    # Browser-like headers to prevent getting blocked by the server
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        )
    }

    print(f"Fetching page: {URL}")
    try:
        response = requests.get(URL, headers=headers, timeout=15)
        response.raise_for_status()
    except requests.exceptions.RequestException as e:
        print(f"Failed to retrieve the page: {e}")
        return

    # Parse HTML structure
    soup = BeautifulSoup(response.text, "html.parser")

    # Find all <img> tags
    img_tags = soup.find_all("img")
    print(f"Found {len(img_tags)} image tags.")

    downloaded_count = 0

    for img in img_tags:
        # Check 'src', fallback to 'data-src' if the site uses lazy-loading
        img_url = img.get("src") or img.get("data-src")

        if not img_url:
            continue

        # Convert relative URLs (e.g., /img/photo.png) to absolute URLs
        img_url = urljoin(URL, img_url)

        # Extract filename and strip away URL query parameters
        parsed_url = urlparse(img_url)
        filename = os.path.basename(parsed_url.path)

        # Fallback name if the URL path doesn't end cleanly with a filename
        if not filename:
            filename = f"image_{downloaded_count + 1}.png"

        local_path = os.path.join(OUTPUT_FOLDER, filename)

        # Download and save the image file
        try:
            print(f"Downloading: {img_url}")
            img_data = requests.get(img_url, headers=headers, timeout=10).content
            with open(local_path, "wb") as handler:
                handler.write(img_data)
            downloaded_count += 1
        except Exception as e:
            print(f"Could not download {img_url}: {e}")

    print(f"\nFinished! Successfully downloaded {downloaded_count} images.")


if __name__ == "__main__":
    download_images()
