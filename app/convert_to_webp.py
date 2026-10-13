import os
import sqlite3
from pathlib import Path
from PIL import Image
from database import DATABASE_PATH
from config import BASE_DIR, get_images_path

def load_images_path():
    return get_images_path()

def convert_to_webp():
    images_dir = load_images_path()
    print(f"Using images path: {images_dir}")
    
    db_path = DATABASE_PATH
    if not os.path.exists(db_path):
        print(f"Database not found at {db_path}")
        return

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Find all activities with .png in image_path
    cursor.execute("SELECT DISTINCT image_path FROM activities WHERE image_path LIKE '%.png'")
    rows = cursor.fetchall()

    if not rows:
        print("No PNG images found in database.")
        conn.close()
        return

    print(f"Found {len(rows)} images to convert.")
    
    converted_count = 0
    error_count = 0
    total_saved_bytes = 0

    for (old_path,) in rows:
        source_path = Path(old_path)
        if not source_path.is_absolute():
            source_path = BASE_DIR / source_path
        if not source_path.is_file():
            print(f"File not found: {old_path}")
            continue

        try:
            new_path = str(source_path.with_suffix(".webp"))
            
            # Open and save as WebP
            with Image.open(source_path) as img:
                img.save(new_path, "WEBP", quality=80, method=6)
            
            # Calculate savings
            old_size = source_path.stat().st_size
            new_size = os.path.getsize(new_path)
            total_saved_bytes += (old_size - new_size)

            # Update database
            cursor.execute("UPDATE activities SET image_path = ? WHERE image_path = ?", (new_path, old_path))
            
            # Delete old file
            source_path.unlink()
            
            converted_count += 1
            if converted_count % 10 == 0:
                print(f"Converted {converted_count}/{len(rows)}...")

        except Exception as e:
            print(f"Error converting {old_path}: {e}")
            error_count += 1

    conn.commit()
    conn.close()

    print("\nConversion Complete!")
    print(f"Successfully converted: {converted_count}")
    print(f"Errors: {error_count}")
    print(f"Total space saved: {total_saved_bytes / (1024 * 1024):.2f} MB")

if __name__ == "__main__":
    convert_to_webp()
