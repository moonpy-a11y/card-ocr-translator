import io
import os
import re
import time
import argparse
from urllib.parse import urlparse
from PIL import Image, ImageOps
from google.cloud import vision
from google.cloud import translate_v2 as translate
from google.cloud import storage

# --- CORE FEATURE: EXECUTION MONITORING ---
# Added latency benchmarks to optimize cloud API processing pipelines.

class Colors:
    HEADER = '\033[38;2;167;139;250m'    
    SYSTEM = '\033[38;2;96;165;250m'     
    ORIGINAL = '\033[38;2;251;146;60m'   
    TRANSLATED = '\033[38;2;52;211;153m' 
    ERROR = '\033[38;2;248;113;113m'     
    BOLD = '\033[1m'
    ENDC = '\033[0m'

def download_from_bucket(gcs_uri):
    parsed_url = urlparse(gcs_uri)
    storage_client = storage.Client()
    bucket = storage_client.bucket(parsed_url.netloc)
    blob = bucket.blob(parsed_url.path.lstrip('/'))
    return blob.download_as_bytes()

def process_image_bytes(image_bytes, flip=True):
    with Image.open(io.BytesIO(image_bytes)) as img:
        if img.mode != 'RGB':
            img = img.convert('RGB')
        img = ImageOps.exif_transpose(img) 
        if flip:
            img = ImageOps.mirror(img)
        byte_array = io.BytesIO()
        img.save(byte_array, format='JPEG')
        return byte_array.getvalue()

def extract_text(content):
    client = vision.ImageAnnotatorClient()
    response = client.text_detection(image=vision.Image(content=content))
    if response.error.message:
        raise Exception(response.error.message)
    return response.text_annotations[0].description if response.text_annotations else ""

def translate_text(text, target_language='en'):
    translate_client = translate.Client()
    lines = [line for line in text.split('\n') if line.strip() != ""]
    results = translate_client.translate(lines, target_language=target_language, format_='text')
    return '\n'.join([r["translatedText"] for r in results])

def inject_a1_note(text, current_count, max_count=4):
    note = " (Niveau für absolute Anfänger, das einen Lernaufwand von etwa 70 bis 80 Stunden erfordert)"
    def replacer(match):
        nonlocal current_count
        if current_count < max_count:
            current_count += 1
            return match.group(0) + note
        return match.group(0)
    return re.sub(r'\bA1\b', replacer, text), current_count

def print_header(filename, is_mirrored, current, total):
    mode_text = "🪞 MIRRORED (Flipping Horizontally)" if is_mirrored else "📸 STRAIGHT (Normal Processing)"
    print(f"\n{Colors.HEADER}{Colors.BOLD}================================================================={Colors.ENDC}")
    print(f"{Colors.BOLD} 🖼️  PROCESSING IMAGE [{current}/{total}]: {filename}{Colors.ENDC}")
    print(f"{Colors.BOLD} 🛠️  MODE: {mode_text}{Colors.ENDC}")
    print(f"\n{Colors.HEADER}{Colors.BOLD}================================================================={Colors.ENDC}")

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("images", nargs='+', help="GCS URIs")
    parser.add_argument("--target_lang", default="en", help="Target language code")
    args = parser.parse_args()

    total_images = len(args.images)
    a1_injection_count = 0  

    for index, item in enumerate(args.images, 1):
        if ":" in item and not item.endswith("gs://"): 
            parts = item.rsplit(':', 1)
            gcs_uri = parts[0]
            mode = parts[1].lower()
        else:
            gcs_uri = item
            mode = "mirrored"

        filename = os.path.basename(urlparse(gcs_uri).path)
        should_flip = (mode != "straight")

        print_header(filename, should_flip, index, total_images)

        try:
            start_time = time.time()

            print(f"{Colors.SYSTEM}[*] Downloading {filename} from bucket...{Colors.ENDC}")
            raw_bytes = download_from_bucket(gcs_uri)
            
            print(f"{Colors.SYSTEM}[*] Processing image layout...{Colors.ENDC}")
            processed_bytes = process_image_bytes(raw_bytes, flip=should_flip)
            
            print(f"{Colors.SYSTEM}[*] Extracting text via Vision API...{Colors.ENDC}")
            extracted_text = extract_text(processed_bytes)
            
            if not extracted_text.strip():
                print(f"{Colors.ERROR}[!] No text found in {filename}. Skipping.{Colors.ENDC}")
                continue

            print(f"{Colors.SYSTEM}[*] Translating to '{args.target_lang}'...{Colors.ENDC}")
            translated_text = translate_text(extracted_text, args.target_lang)
            translated_text, a1_injection_count = inject_a1_note(translated_text, a1_injection_count)

            elapsed_time = time.time() - start_time

            print(f"\n{Colors.ORIGINAL}{Colors.BOLD}📄 --- ORIGINAL EXTRACTED TEXT ---{Colors.ENDC}")
            print(f"{Colors.ORIGINAL}{extracted_text}{Colors.ENDC}")
            
            print(f"\n{Colors.TRANSLATED}{Colors.BOLD}✨ --- TRANSLATED TEXT ---{Colors.ENDC}")
            print(f"{Colors.TRANSLATED}{translated_text}{Colors.ENDC}\n")

            print(f"{Colors.SYSTEM}[*] Latency Meter: Core processing completed in {elapsed_time:.2f} seconds.{Colors.ENDC}")

        except Exception as e:
            print(f"{Colors.ERROR}\n[!] Error processing {filename}: {e}{Colors.ENDC}")

if __name__ == "__main__":
    main()
