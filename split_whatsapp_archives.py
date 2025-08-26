# split_whatsapp_archives.py
# Split a WhatsApp archive into per-year ZIPs.
# Output names: "<input base> - <YEAR>.zip"

import re
import sys
import shutil
import zipfile
from pathlib import Path

# ---------- Heuristics to find the chat .txt ----------
LIKELY_TXT_NEG = re.compile(r'\b(readme|license|caption|captions?)\b', re.I)

def score_txt_name(name: str) -> int:
    n = name.lower()
    score = 0
    if "chat" in n:
        score += 3
    if "whatsapp" in n:
        score += 3
    if n.endswith("_chat.txt"):
        score += 4
    if "/" in n:
        score += 1
    if LIKELY_TXT_NEG.search(n):
        score -= 3
    score += min(len(n)//20, 3)
    return score

def detect_encoding_and_read(b: bytes) -> str:
    for enc in ["utf-8", "utf-8-sig", "utf-16", "utf-16le", "utf-16be", "iso-8859-1"]:
        try:
            return b.decode(enc)
        except UnicodeDecodeError:
            pass
    return b.decode("utf-8", errors="replace")

def pick_chat_txt_from_zip(zf: zipfile.ZipFile):
    txts = [zi for zi in zf.infolist() if not zi.is_dir() and zi.filename.lower().endswith(".txt")]
    if not txts:
        return None
    if len(txts) == 1:
        return txts[0]
    scored = []
    for zi in txts:
        s = score_txt_name(zi.filename)
        size = getattr(zi, "file_size", 0)
        scored.append((s, size, zi))
    scored.sort(key=lambda t: (t[0], t[1]), reverse=True)
    return scored[0][2]

# ---------- Year extraction / parsing ----------
# Flexible: "[31/12/2019, 15:22] ..." or "12/31/19, 3:45 PM - ..." or "31.12.2019, ..."
DATE_PREFIX = re.compile(r'^\[?(\d{1,2})[./-](\d{1,2})[./-](\d{2,4})')

ATTACH_RE = re.compile(r"<attached:\s*([^>]+)>")
TRAILING_YEAR_RE = re.compile(r"\s*-\s*\d{4}$")

def extract_year_from_line(line: str):
    m = DATE_PREFIX.match(line)
    if not m:
        return None
    year = m.group(3)
    if len(year) == 2:
        year = "20" + year
    return year if re.fullmatch(r"\d{4}", year) else None

def split_lines_by_year(chat_text: str):
    groups = {}
    current_year = None
    for raw in chat_text.splitlines():
        line = raw.rstrip("\n")
        y = extract_year_from_line(line)
        if y:
            current_year = y
            groups.setdefault(y, []).append(line)
        elif current_year:
            groups[current_year].append(line)
    return groups

def gather_attachments(lines):
    atts = set()
    for l in lines:
        m = ATTACH_RE.search(l)
        if m:
            atts.add(m.group(1))
    return atts

# ---------- Media helpers ----------
def build_media_list(zf: zipfile.ZipFile, chosen_txt: zipfile.ZipInfo):
    media = []
    for zi in zf.infolist():
        if zi.is_dir():
            continue
        if zi.filename == chosen_txt.filename:
            continue
        if zi.filename.lower().endswith(".txt"):
            continue
        media.append(zi)
    return media

def build_output_zip_name(out_root: Path, base_name: str, year: str) -> Path:
    stem = base_name[:-4] if base_name.lower().endswith(".zip") else base_name
    stem = TRAILING_YEAR_RE.sub("", stem)  # defensively drop existing "- YYYY"
    return out_root / f"{stem} - {year}.zip"

def write_year_bundle(year: str, lines, out_root: Path, base_name: str,
                      src_zip=None, media_candidates=None):
    tmp = out_root / f"__tmp_{year}"
    tmp.mkdir(parents=True, exist_ok=True)
    (tmp / "_chat.txt").write_text("\n".join(lines), encoding="utf-8")

    if src_zip and media_candidates:
        needed = gather_attachments(lines)
        for zi in media_candidates:
            base = Path(zi.filename).name
            if base in needed:
                with src_zip.open(zi) as src, open(tmp / base, "wb") as dst:
                    shutil.copyfileobj(src, dst)

    out_zip = build_output_zip_name(out_root, base_name, year)
    with zipfile.ZipFile(out_zip, "w", compression=zipfile.ZIP_DEFLATED) as z:
        for p in tmp.iterdir():
            z.write(p, arcname=p.name)
    shutil.rmtree(tmp)

# ---------- Processing modes ----------
def process_zip(input_zip: Path, output_folder: Path):
    print(f"Processing ZIP: {input_zip}")
    with zipfile.ZipFile(input_zip, "r") as zf:
        chosen = pick_chat_txt_from_zip(zf)
        if not chosen:
            print("No .txt found. ZIP contents:")
            for zi in zf.infolist():
                print(" -", zi.filename)
            raise FileNotFoundError("No chat .txt file found in the ZIP.")
        print(f"Selected chat file: {chosen.filename}")
        chat_text = detect_encoding_and_read(zf.read(chosen))
        years = split_lines_by_year(chat_text)
        if not years:
            raise RuntimeError("Parsed 0 messages with recognizable dates.")
        media_candidates = build_media_list(zf, chosen)
        base_name = input_zip.name
        for year in sorted(years.keys()):
            print(f"Writing year {year}: {len(years[year])} lines")
            write_year_bundle(year, years[year], output_folder, base_name, zf, media_candidates)

def process_folder(input_folder: Path, output_folder: Path):
    zips = sorted(input_folder.glob("**/*.zip"))
    if zips:
        for z in zips:
            process_zip(z, output_folder)
        return
    print(f"No ZIPs found; scanning for .txt in {input_folder}")
    txts = [p for p in input_folder.rglob("*.txt") if p.is_file()]
    if not txts:
        raise FileNotFoundError("No .zip or .txt chat file found in the folder.")
    picked = max(txts, key=lambda p: (score_txt_name(str(p)), p.stat().st_size))
    print(f"Selected chat file: {picked}")
    chat_text = detect_encoding_and_read(picked.read_bytes())
    years = split_lines_by_year(chat_text)
    if not years:
        raise RuntimeError("Parsed 0 messages with recognizable dates.")
    base_name = input_folder.name
    for year in sorted(years.keys()):
        print(f"Writing year {year}: {len(years[year])} lines")
        write_year_bundle(year, years[year], output_folder, base_name, None, None)

def process_txt_file(input_txt: Path, output_folder: Path):
    print(f"Processing TXT: {input_txt}")
    chat_text = detect_encoding_and_read(input_txt.read_bytes())
    years = split_lines_by_year(chat_text)
    if not years:
        raise RuntimeError("Parsed 0 messages with recognizable dates.")
    base_name = input_txt.stem
    for year in sorted(years.keys()):
        print(f"Writing year {year}: {len(years[year])} lines")
        write_year_bundle(year, years[year], output_folder, base_name, None, None)

def main():
    if len(sys.argv) != 3:
        print("Usage: python3 split_whatsapp_archives.py <input_path> <output_folder>")
        sys.exit(1)
    in_path = Path(sys.argv[1]).expanduser().resolve()
    out_root = Path(sys.argv[2]).expanduser().resolve()
    out_root.mkdir(parents=True, exist_ok=True)

    if in_path.is_file():
        if in_path.suffix.lower() == ".zip":
            process_zip(in_path, out_root)
        elif in_path.suffix.lower() == ".txt":
            process_txt_file(in_path, out_root)
        else:
            raise FileNotFoundError(f"Unsupported input file type: {in_path.suffix}")
    elif in_path.is_dir():
        process_folder(in_path, out_root)
    else:
        raise FileNotFoundError(f"Input path not found or unsupported: {in_path}")

if __name__ == "__main__":
    main()

