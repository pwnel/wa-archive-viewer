# Use this script to split large WhatsApp Archives into 
# individual years that can then be loaded into the viewer
# without overloading the browser
import os
import shutil
import zipfile
import re
import sys

def extract_year_from_date(date_str):
    # date_str like '2/23/14' or '23/2/14'
    parts = re.split(r'[/.-]', date_str)
    if len(parts) == 3:
        year = parts[2]
        if len(year) == 2:
            year = '20' + year  # Assume 2000s
        return int(year)
    return None

def extract_year_from_filename(filename):
    parts = filename.split('-')
    if len(parts) >= 3:
        date_part = parts[2]  # e.g., '2025' in '00003761-PHOTO-2025-07-03-14-42-05.jpg'
        if date_part.isdigit() and len(date_part) == 4:
            return int(date_part)
    return None

def process_chat(input_folder, output_folder):
    # Extract prefix and contact
    folder_name = os.path.basename(input_folder)
    prefix = 'WhatsApp Chat - '
    contact_name = folder_name[len(prefix):]
    print(f"Extracted prefix: '{prefix}'")
    print(f"Extracted contact name: '{contact_name}'")

    # Find chat file
    chat_file = os.path.join(input_folder, '_chat.txt')
    if not os.path.exists(chat_file):
        print("Chat file not found")
        return
    print(f"Found chat file: {os.path.basename(chat_file)}")

    # Read lines
    with open(chat_file, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    print(f"Number of lines in chat: {len(lines)}")

    # Group chat lines by year
    year_groups = {}
    current_year = None
    for i, line in enumerate(lines):
        original_line = line.rstrip('\n')
        cleaned_line = original_line.replace('\u200e', '').replace('\u200f', '').replace('\u202f', ' ')
        if cleaned_line.startswith('['):
            date_match = re.match(r'\[([^\,]+),', cleaned_line)
            if date_match:
                date_str = date_match.group(1).strip()
                year = extract_year_from_date(date_str)
                if year:
                    current_year = year
                    if year not in year_groups:
                        year_groups[year] = []
                    year_groups[year].append(original_line)
                else:
                    print(f"No year extracted from date_str '{date_str}' in line {i+1}")
            else:
                print(f"No date match in line {i+1}: {cleaned_line[:50]}...")
                if current_year:
                    year_groups[current_year].append(original_line)
        else:
            if current_year:
                year_groups[current_year].append(original_line)

    print(f"Years from chat: {sorted(year_groups.keys())}")

    # Get all files in input_folder
    all_files = os.listdir(input_folder)
    print(f"Total files in folder: {len(all_files)}")

    # Group media by year from filename
    media_by_year = {}
    for file in all_files:
        if file not in ['_chat.txt', 'files.txt', 'output.txt']:  # Exclude non-media
            year = extract_year_from_filename(file)
            if year:
                if year not in media_by_year:
                    media_by_year[year] = []
                media_by_year[year].append(file)

    print(f"Media years: {sorted(media_by_year.keys())}")

    # Process each year
    years = sorted(set(year_groups.keys()) | set(media_by_year.keys()))
    print(f"All unique years: {years}")
    for year in years:
        print(f"Processing year {year}")
        output_dir = os.path.join(output_folder, str(year))
        os.makedirs(output_dir, exist_ok=True)
        print(f"Created output directory: {output_dir}")

        # Write chat file if exists
        if year in year_groups:
            year_chat = os.path.join(output_dir, '_chat.txt')
            with open(year_chat, 'w', encoding='utf-8') as f:
                for l in year_groups[year]:
                    f.write(l + '\n')
            print(f"Written chat file for {year} with {len(year_groups[year])} lines")

        # Copy media if exists
        media_count = 0
        if year in media_by_year:
            for filename in media_by_year[year]:
                src = os.path.join(input_folder, filename)
                if os.path.exists(src):
                    dst = os.path.join(output_dir, filename)
                    shutil.copy(src, dst)
                    media_count += 1
                else:
                    print(f"Media file not found: {src}")
        print(f"Copied {media_count} media files for {year}")

        # Create ZIP
        zip_name = os.path.join(output_folder, f"{prefix}{contact_name} - {year}.zip")
        with zipfile.ZipFile(zip_name, 'w') as zipf:
            for root, _, files in os.walk(output_dir):
                for file in files:
                    zipf.write(os.path.join(root, file), arcname=file)
        print(f"Created ZIP for {year}: {zip_name}")

        # Remove temp dir
        shutil.rmtree(output_dir)
        print(f"Removed temp dir for {year}")

if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage: python script.py <input_folder> <output_folder>")
        sys.exit(1)
    input_folder = sys.argv[1]
    output_folder = sys.argv[2]
    process_chat(input_folder, output_folder)
