#!/usr/bin/env python3
"""
Parse the liturgical calendar PDF text and generate an ICS file.
Two-pass approach to handle multi-line entries properly.
"""

import re
import calendar
from datetime import datetime, timedelta

MONTH_MAP = {
    "JANVIER": 1, "FÉVRIER": 2, "MARS": 3, "AVRIL": 4,
    "MAI": 5, "JUIN": 6, "JUILLET": 7, "AOÛT": 8,
    "SEPTEMBRE": 9, "OCTOBRE": 10, "NOVEMBRE": 11, "DÉCEMBRE": 12,
}

BIBLE_BOOKS = sorted([
    "Gn", "Ex", "Lv", "Nb", "Dt", "Jos", "Jg", "Rt", "1 S", "2 S",
    "1 R", "2 R", "1 Ch", "2 Ch", "Esd", "Ne", "Tb", "Jdt", "Est",
    "1 M", "2 M", "Jb", "Ps", "Pr", "Qo", "Ct", "Sg", "Si",
    "Is", "Jr", "Lm", "Ba", "Ez", "Dn", "Os", "Jl", "Am", "Ab",
    "Jon", "Mi", "Na", "Ha", "So", "Ag", "Za", "Ml",
    "Mt", "Mc", "Lc", "Jn", "Ac", "Rm", "1 Co", "2 Co",
    "Ga", "Ep", "Ph", "Col", "1 Th", "2 Th", "1 Tm", "2 Tm",
    "Tt", "Phm", "He", "Jc", "1 P", "2 P", "1 Jn", "2 Jn", "3 Jn",
    "Jude", "Ap",
], key=len, reverse=True)

# Day line: letter + spaces + number (possibly stuck to next word like "7St")
DAY_RE = re.compile(r"^([LMJVSD])\s+(\d{1,2})(?:\s+|(?=[A-Z]))(.*)")
# Also handle "D 8 32e" format (letter + space + number + space + content)
DAY_RE2 = re.compile(r"^([LMJVSD])\s+(\d{1,2})\s(.*)")
MONTH_RE = re.compile(
    r"(JANVIER|FÉVRIER|MARS|AVRIL|MAI|JUIN|JUILLET|AOÛT|SEPTEMBRE|OCTOBRE|NOVEMBRE|DÉCEMBRE)\s+(\d{4})"
)
ANNEE_RE = re.compile(r"ANNÉE\s+(A/B|A|B)")

BOOK_PATTERN = "|".join(re.escape(b) for b in BIBLE_BOOKS)
READING_RE = re.compile(r"(?:" + BOOK_PATTERN + r")\s+\d")


def is_reading_line(text):
    """Check if a line looks like it's primarily a bible reading reference."""
    text = text.strip()
    if not text:
        return False
    for book in BIBLE_BOOKS:
        if text.startswith(book + " ") and READING_RE.match(text):
            return True
    return False


def starts_with_lowercase(text):
    """Check if text starts with a lowercase letter (continuation text)."""
    text = text.strip()
    if not text:
        return False
    return text[0].islower()


def parse_day_line(stripped):
    """Try to parse a line as a day line. Returns (day_num, rest) or None."""
    m = DAY_RE.match(stripped)
    if m:
        return int(m.group(2)), m.group(3).strip()
    m = DAY_RE2.match(stripped)
    if m:
        return int(m.group(2)), m.group(3).strip()
    return None


def parse_calendar(text_file):
    with open(text_file, "r", encoding="utf-8") as f:
        lines = [l.rstrip("\n") for l in f.readlines()]

    # Pass 1: identify day lines and month contexts
    day_lines = []  # (line_index, month, year, day_num, annee, rest_of_line)
    current_month = None
    current_year = None
    current_annee = ""
    skip_lines = set()

    for i, line in enumerate(lines):
        stripped = line.strip()
        if not stripped:
            continue

        # Month header (may be merged with content like "AOÛT 2026St Alphonse...")
        mm = MONTH_RE.search(line)
        if mm:
            current_month = MONTH_MAP[mm.group(1)]
            current_year = int(mm.group(2))
            am = ANNEE_RE.search(line)
            if am:
                current_annee = "Année " + am.group(1)
            skip_lines.add(i)
            continue

        am = ANNEE_RE.search(stripped)
        if am and len(stripped) < 20:
            current_annee = "Année " + am.group(1)
            skip_lines.add(i)
            continue

        if not current_month:
            continue

        result = parse_day_line(stripped)
        if result:
            day_num, rest = result
            max_day = calendar.monthrange(current_year, current_month)[1]
            if day_num <= max_day:
                day_lines.append((i, current_month, current_year, day_num, current_annee, rest))

    # Pass 2: for each day, determine prefix and suffix lines
    entries = []

    for idx, (line_i, month, year, day_num, annee, rest) in enumerate(day_lines):
        # Prefix lines: between previous day and this day
        if idx > 0:
            prev_line_i = day_lines[idx - 1][0]
        else:
            prev_line_i = -1

        prefix_texts = []
        for j in range(prev_line_i + 1, line_i):
            if j in skip_lines:
                continue
            txt = lines[j].strip()
            if not txt:
                continue
            # Gap line between previous day and current day.
            # Is it a suffix of previous day or prefix of current day?
            #
            # Rules:
            # - Reading lines -> suffix of previous day
            # - Lines starting with lowercase -> suffix (continuation of prev text)
            # - Lines starting with uppercase name text -> prefix for this day
            if is_reading_line(txt) or starts_with_lowercase(txt):
                # Suffix for previous day (will be picked up in the previous day's suffix pass)
                pass
            else:
                prefix_texts.append(txt)

        # Suffix lines: between this day and next day
        if idx < len(day_lines) - 1:
            next_line_i = day_lines[idx + 1][0]
        else:
            next_line_i = len(lines)

        suffix_texts = []
        for j in range(line_i + 1, next_line_i):
            if j in skip_lines:
                continue
            txt = lines[j].strip()
            if not txt:
                continue
            # Gap line between this day and next day.
            # Rules:
            # - Reading lines -> suffix for this day
            # - Lines starting with lowercase -> suffix for this day (continuation)
            # - Lines starting with uppercase -> check if prefix for next day
            if is_reading_line(txt) or starts_with_lowercase(txt):
                suffix_texts.append(txt)
            else:
                # Uppercase text: could be prefix for next day
                # Only treat as prefix if it's within 2 lines of the next day
                if idx < len(day_lines) - 1:
                    dist_to_next = day_lines[idx + 1][0] - j
                    if dist_to_next <= 3:
                        # This is a prefix for the next day, skip
                        continue
                suffix_texts.append(txt)

        # Build full text: prefix + rest + suffix
        all_parts = prefix_texts + ([rest] if rest else []) + suffix_texts
        full_text = " ".join(all_parts)
        full_text = re.sub(r"\s{2,}", " ", full_text).strip()

        name, readings = split_name_readings(full_text)

        # Clean up "e " artifacts from superscripts like "15 e DIMANCHE" -> "15e DIMANCHE"
        name = re.sub(r"(\d+)\s*e\s+(DIMANCHE|dimanche)", r"\1e \2", name)

        entries.append({
            "date": datetime(year, month, day_num),
            "name": name.strip(),
            "readings": readings.strip(),
            "annee": annee,
        })

    # Post-processing: manual corrections for PDF layout edge cases
    corrections = {
        "2026-04-29": {
            "name": "Ste Catherine de Sienne, vierge et docteur de l'Église, copatronne de l'Europe (FÊTE)",
            "readings": "1 Jn 1, 5 – 2, 2 ; Mt 11, 25-30",
        },
        "2026-06-22": {
            "name": "De la férie ; ou St Jean Fisher, évêque, et St Thomas More, martyrs ; ou St Paulin de Nole, évêque",
            "readings": "2 R 17, 5-8.13-15a.18 ; Mt 7, 1-5",
        },
        "2026-06-27": {
            "name": "De la férie ; ou St Cyrille d'Alexandrie, évêque et docteur de l'Église ; ou Bse Vierge Marie",
            "readings": "Lm 2, 2.10-14.18-19 ; Mt 8, 5-17",
        },
        "2026-06-28": {
            "name": "13e DIMANCHE DU TEMPS ORDINAIRE (Psautier semaine I)",
            "readings": "2 R 4, 8-11.14-16a ; Rm 6, 3b-4.8-11 ; Mt 10, 37-42",
        },
        "2026-06-30": {
            "name": "De la férie ; ou les saints premiers martyrs de l'Église de Rome",
            "readings": "Am 3, 1-8; 4, 11-12 ; Mt 8, 23-27",
        },
        "2026-08-01": {
            "name": "St Alphonse-Marie de Liguori, évêque et docteur de l'Église (Mémoire)",
            "readings": "Jr 26, 11-16.24 ; Mt 14, 1-12",
        },
        "2026-10-14": {
            "name": "De la férie ; ou St Calliste Ier, pape et martyr",
        },
        "2026-11-07": {
            "readings": "Ph 4, 10-19 ; Lc 16, 9-15",
        },
        "2026-11-08": {
            "readings": "Sg 6, 12-16 ; 1 Th 4, 13-18 ; Mt 25, 1-13",
        },
        "2026-11-15": {
            "readings": "Pr 31, 10-13.19-20.30-31 ; 1 Th 5, 1-6 ; Mt 25, 14-30",
        },
        "2026-12-08": {
            "name": "IMMACULÉE CONCEPTION DE LA BIENHEUREUSE VIERGE MARIE (SOLENNITÉ)",
            "readings": "Gn 3, 9-15.20 ; Ep 1, 3-6.11-12 ; Lc 1, 26-38",
        },
    }

    for entry in entries:
        key = entry["date"].strftime("%Y-%m-%d")
        if key in corrections:
            for field, value in corrections[key].items():
                entry[field] = value

    return entries


def split_name_readings(content):
    """Split content into liturgical name and bible readings."""
    if not content:
        return "", ""

    # Check for "Veillée pascale :" or "Jour :" prefix
    for prefix in ["Veillée pascale :", "Jour :"]:
        idx = content.find(prefix)
        if idx > 0:
            return content[:idx].strip(), content[idx:].strip()

    # Find all bible reference matches
    matches = list(READING_RE.finditer(content))
    if not matches:
        return content, ""

    # Find the best split point: first bible ref with meaningful name before it
    for match in matches:
        pos = match.start()
        name_part = content[:pos].strip()
        if len(name_part) >= 5:
            name_part = re.sub(r"\s*;\s*$", "", name_part)
            return name_part, content[pos:].strip()

    if matches[0].start() < 5:
        return content, ""

    return content[:matches[0].start()].strip(), content[matches[0].start():].strip()


def escape_ics(text):
    text = text.replace("\\", "\\\\")
    text = text.replace(";", "\\;")
    text = text.replace(",", "\\,")
    text = text.replace("\n", "\\n")
    return text


def fold_line(line):
    """Fold long lines per ICS spec (max 75 octets per line)."""
    result = []
    while len(line.encode("utf-8")) > 75:
        cut = 75
        while cut > 0 and len(line[:cut].encode("utf-8")) > 75:
            cut -= 1
        if cut == 0:
            cut = 1
        result.append(line[:cut])
        line = " " + line[cut:]
    result.append(line)
    return "\r\n".join(result)


def generate_ics(entries, output_file):
    now = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")

    ics_lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//Calendrier Liturgique//FR",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        "X-WR-CALNAME:Calendrier Liturgique 2026",
        "X-WR-TIMEZONE:Europe/Paris",
    ]

    for entry in entries:
        date_str = entry["date"].strftime("%Y%m%d")
        next_day = (entry["date"] + timedelta(days=1)).strftime("%Y%m%d")
        uid = f"liturgique-{date_str}@calendrier2026"

        desc_parts = []
        if entry["readings"]:
            desc_parts.append(entry["readings"])
        if entry["annee"]:
            desc_parts.append(entry["annee"])
        description = "\\n".join(desc_parts)

        ics_lines.append("BEGIN:VEVENT")
        ics_lines.append(f"DTSTART;VALUE=DATE:{date_str}")
        ics_lines.append(f"DTEND;VALUE=DATE:{next_day}")
        ics_lines.append(f"DTSTAMP:{now}")
        ics_lines.append(f"UID:{uid}")
        ics_lines.append(fold_line(f"SUMMARY:{escape_ics(entry['name'])}"))
        if description:
            ics_lines.append(fold_line(f"DESCRIPTION:{escape_ics(description)}"))
        ics_lines.append("TRANSP:TRANSPARENT")
        ics_lines.append("END:VEVENT")

    ics_lines.append("END:VCALENDAR")

    with open(output_file, "w", encoding="utf-8") as f:
        f.write("\r\n".join(ics_lines) + "\r\n")


def main():
    import os
    base_dir = os.path.dirname(os.path.abspath(__file__))
    text_file = os.path.join(base_dir, "calendrier_raw.txt")
    output_file = os.path.join(base_dir, "calendrier_liturgique_2026.ics")

    entries = parse_calendar(text_file)
    entries.sort(key=lambda e: e["date"])

    print(f"Parsed {len(entries)} entries")
    print(f"Date range: {entries[0]['date'].strftime('%Y-%m-%d')} to {entries[-1]['date'].strftime('%Y-%m-%d')}")
    print()

    expected_days = set()
    d = entries[0]["date"]
    end = entries[-1]["date"]
    while d <= end:
        expected_days.add(d.strftime("%Y-%m-%d"))
        d += timedelta(days=1)
    actual_days = {e["date"].strftime("%Y-%m-%d") for e in entries}
    missing = expected_days - actual_days
    if missing:
        print(f"WARNING: Missing {len(missing)} days: {sorted(missing)}")
    else:
        print("All days present!")
    print()

    for e in entries:
        print(f"  {e['date'].strftime('%Y-%m-%d')} | {e['name'][:65]:<65} | {e['readings'][:55]}")

    generate_ics(entries, output_file)
    print(f"\nICS file generated: {output_file}")


if __name__ == "__main__":
    main()
