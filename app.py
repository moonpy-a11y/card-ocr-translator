import io
import argparse
from urllib.parse import urlparse
from PIL import Image, ImageOps
from google.cloud import vision
from google.cloud import translate_v2 as translate
from google.cloud import storage

def download_from_bucket(gcs_uri):
    """Downloads an image from a GCS bucket into memory."""
    print(f"[*] Fetching image from {gcs_uri}...")
    parsed_url = urlparse(gcs_uri)
    if parsed_url.scheme != 'gs':
        raise ValueError("URI must start with gs://")
        
    bucket_name = parsed_url.netloc
    blob_name = parsed_url.path.lstrip('/')

    storage_client = storage.Client()
    bucket = storage_client.bucket(bucket_name)
    blob = bucket.blob(blob_name)
    return blob.download_as_bytes()

def fix_mirrored_image_bytes(image_bytes):
    """Flips the image horizontally."""
    print("[*] Processing and flipping image...")
    with Image.open(io.BytesIO(image_bytes)) as img:
        if img.mode != 'RGB':
            img = img.convert('RGB')
        flipped_img = ImageOps.mirror(img)
        byte_array = io.BytesIO()
        flipped_img.save(byte_array, format='JPEG')
        return byte_array.getvalue()

def extract_text(content):
    """Detects text using Cloud Vision API."""
    print("[*] Sending to Google Cloud Vision API...")
    client = vision.ImageAnnotatorClient()
    image = vision.Image(content=content)
    response = client.text_detection(image=image)
    texts = response.text_annotations
    
    if response.error.message:
        raise Exception(response.error.message)
    return texts[0].description if texts else ""

def translate_text(text, target_language='en'):
    """Translates text using Cloud Translation API."""
    print(f"[*] Translating text to '{target_language}'...")
    translate_client = translate.Client()
    if isinstance(text, bytes):
        text = text.decode("utf-8")
    result = translate_client.translate(text, target_language=target_language)
    return result["translatedText"]

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("gcs_uri", help="GCS path (e.g., gs://my-bucket/card.jpg)")
    parser.add_argument("--target_lang", default="en", help="Target language code")
    args = parser.parse_args()

    try:
        raw_image_bytes = download_from_bucket(args.gcs_uri)
        fixed_image_content = fix_mirrored_image_bytes(raw_image_bytes)
        extracted_text = extract_text(fixed_image_content)
        
        print("\n--- Extracted Text ---")
        print(extracted_text)
        
        if extracted_text.strip():
            translated = translate_text(extracted_text, args.target_lang)
            print("\n--- Translated Text ---")
            print(translated)
        else:
            print("\n[!] No text found in the image.")
    except Exception as e:
        print(f"\n[!] An error occurred: {e}")

if __name__ == "__main__":
    main()
