"""HTML Parser module for DDUnlimited Search."""

import re
from datetime import datetime
from urllib.parse import urljoin
from bs4 import BeautifulSoup

import config

# Month abbreviation map covering multiple phpBB locales.
# phpBB uses the *forum's* language settings (server-side), which on ddunlimited is Italian.
# The scraping session is tied to one fixed account so the format should be stable,
# but we include other common locales as a safety net.
_IT_MONTHS: dict[str, int] = {
    # Italian
    'gen': 1, 'feb': 2, 'mar': 3, 'apr': 4, 'mag': 5, 'giu': 6,
    'lug': 7, 'ago': 8, 'set': 9, 'ott': 10, 'nov': 11, 'dic': 12,
    # English
    'jan': 1,                     'may': 5, 'jun': 6,
    'jul': 7, 'aug': 8, 'sep': 9, 'oct': 10, 'dec': 12,
    # French
    'avr': 4, 'mai': 5, 'jui': 6, 'aou': 8,
    # Spanish / Portuguese
    'ene': 1, 'abr': 4, 'ago': 8,
    # German
    'jan': 1, 'mrz': 3, 'mai': 5, 'jun': 6, 'jul': 7, 'aug': 8,
    'okt': 10, 'dez': 12,
}


def _parse_post_date(html_soup) -> datetime | None:
    """
    Try to extract the creation date of the first post from a phpBB page.

    Strategies (in order):
    1. <time class="datetime" datetime="ISO-string"> — modern phpBB
    2. Text patterns inside <p class="author"> or <div class="postbody">
       e.g. "Gio Nov 14, 2024  12:00 pm" or "14 nov 2024, 12:00"
    3. Any 4-digit year found in the first post author block as last resort
    """
    # Strategy 1: ISO datetime attribute
    time_tag = html_soup.find('time', attrs={'datetime': True})
    if time_tag:
        raw = time_tag['datetime'].strip()
        for fmt in ('%Y-%m-%dT%H:%M:%S%z', '%Y-%m-%dT%H:%M:%S', '%Y-%m-%d'):
            try:
                dt = datetime.strptime(raw[:19], fmt[:len(raw[:19])])
                return dt.replace(tzinfo=None)
            except ValueError:
                pass

    # Strategy 2: <p class="author"> — ddunlimited format:
    #   da <strong>username</strong> » 21 feb 2026 09:58 pm
    author_p = html_soup.find('p', class_='author')
    if author_p:
        author_text = author_p.get_text(' ', strip=True)
        # Grab everything after the » separator
        after_arrow = author_text.split('»')[-1] if '»' in author_text else author_text

        # "21 feb 2026" or "21 feb 2026 09:58 pm"
        m = re.search(r'(\d{1,2})\s+([a-z]{3})\s+(\d{4})', after_arrow, re.IGNORECASE)
        if m:
            day, month_str, year = int(m.group(1)), m.group(2).lower(), int(m.group(3))
            month = _IT_MONTHS.get(month_str)
            if month:
                try:
                    return datetime(year, month, day)
                except ValueError:
                    pass

        # "Nov 14, 2024" (English phpBB locale)
        m = re.search(r'([a-z]{3})\s+(\d{1,2}),\s+(\d{4})', after_arrow, re.IGNORECASE)
        if m:
            month_str, day, year = m.group(1).lower(), int(m.group(2)), int(m.group(3))
            month = _IT_MONTHS.get(month_str)
            if month:
                try:
                    return datetime(year, month, day)
                except ValueError:
                    pass

        # "21/02/2026" or "02/21/2026" — numeric European / US fallback
        m = re.search(r'(\d{1,2})[/\-.](\d{1,2})[/\-.](\d{4})', after_arrow)
        if m:
            a, b, year = int(m.group(1)), int(m.group(2)), int(m.group(3))
            # Assume DD/MM if first part > 12, else try DD/MM first (European default)
            day, month = (a, b) if a > 12 else (a, b)
            try:
                return datetime(year, month, day)
            except ValueError:
                try:
                    return datetime(year, a, b)  # US fallback MM/DD
                except ValueError:
                    pass

    # Strategy 3: bare 4-digit year anywhere in the author block as last resort
    if author_p:
        m = re.search(r'\b(20\d{2}|19\d{2})\b', author_p.get_text())
        if m:
            try:
                return datetime(int(m.group(1)), 1, 1)
            except ValueError:
                pass

    return None


# Quality patterns to extract
QUALITY_PATTERNS = [
    r'\b(2160p|4K)\b',
    r'\b(1080p|1080i)\b',
    r'\b(720p|720i)\b',
    r'\b(HDTV)\b',
    r'\b(WEB-DL|WEBDL|WEBRip|WEB)\b',
    r'\b(BluRay|BDRip|BRRip)\b',
    r'\b(DVDRip|DVD)\b',
    r'\b(HDCAM|CAM|TS|TELESYNC)\b',
]


def extract_quality(text: str) -> str | None:
    """Extract quality information from text."""
    for pattern in QUALITY_PATTERNS:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return match.group(1).upper()
    return None


def extract_metadata(text: str) -> str | None:
    """Extract metadata from text (content in brackets, technical info)."""
    # Find content in square brackets
    brackets = re.findall(r'\[([^\]]+)\]', text)

    # Find content in parentheses (but not dates or episode info)
    parens = re.findall(r'\(([^)]+)\)', text)
    parens = [p for p in parens if not re.match(r'^\d{4}$', p)]  # Exclude year only

    # Find technical info patterns
    tech_patterns = [
        r'\b(x264|x265|H\.?264|H\.?265|HEVC|AVC)\b',
        r'\b(DTS|AC3|AAC|EAC3|TrueHD|Atmos)\b',
        r'\b(ITA|ENG|SUB|MULTi)\b',
    ]

    tech_info = []
    for pattern in tech_patterns:
        matches = re.findall(pattern, text, re.IGNORECASE)
        tech_info.extend(matches)

    all_metadata = brackets + parens + tech_info
    if all_metadata:
        return ' | '.join(dict.fromkeys(all_metadata))  # Remove duplicates, preserve order
    return None


LANGUAGE_MAP = {
    'italiano': 'ITA', 'inglese': 'ENG', 'francese': 'FRA',
    'tedesco': 'DEU', 'spagnolo': 'SPA', 'portoghese': 'POR',
    'giapponese': 'JPN', 'coreano': 'KOR', 'cinese': 'CHN',
    'russo': 'RUS', 'arabo': 'ARA', 'olandese': 'NLD',
}


def extract_quality_from_icons(parent_tag) -> str | None:
    """Scan all <img> tags in parent for inline quality icons."""
    if not parent_tag:
        return None
    for img in parent_tag.find_all('img'):
        src = img.get('src', '').lower()
        if '4k' in src or 'uhd' in src:
            return '4K'
        if 'full.hd' in src or 'fullhd' in src:
            return '1080p'
        if '.hd.' in src:
            return '720p'
    return None


def parse_post_detail(html: str) -> dict:
    """
    Parse an individual post page and extract rich metadata from h2/h4.

    Returns:
        Dict with keys: quality, metadata, languages, status, raw_info, post_created_at
    """
    soup = BeautifulSoup(html, 'html.parser')
    quality = None
    metadata = None
    languages = None
    status = None
    raw_info = None
    post_created_at = _parse_post_date(soup)

    LANG_CODES = {'ITA','ENG','FRA','DEU','SPA','POR','JPN','KOR','CHN','RUS','ARA','NLD','POL','TUR','SWE','NOR','DAN','FIN'}
    AUDIO_CODECS = {'AC3','DTS','AAC','EAC3','TRUEHD','ATMOS','DD5','FLAC','MP3'}

    # Extract from <h4>: plain text like "WEB, MUX, 720p, X264, AC3 ITA, SUB ITA-ENG, MKV"
    h4 = soup.find('h4')
    if h4:
        h4_text = h4.get_text(strip=True)
        raw_info = h4_text
        quality = extract_quality(h4_text)

        # Parse comma-separated tokens preserving codec+lang and sub+lang associations
        tokens = [t.strip() for t in re.split(r'[,\-–]', h4_text) if t.strip()]
        structured = []
        audio_langs = []
        sub_langs = []

        for token in tokens:
            parts = token.split()
            upper_parts = [p.upper() for p in parts]

            if upper_parts and upper_parts[0] in AUDIO_CODECS:
                codec = upper_parts[0]
                langs = [p for p in upper_parts[1:] if p in LANG_CODES]
                audio_langs.extend(langs)
                structured.append(codec + (' ' + ' '.join(langs) if langs else ''))
            elif upper_parts and upper_parts[0] == 'SUB':
                langs = [p for p in upper_parts[1:] if p in LANG_CODES]
                sub_langs.extend(langs)
                structured.append('SUB ' + ' '.join(langs) if langs else 'SUB')
            else:
                structured.append(token)

        # Store structured metadata with SUBLANG_ prefix for sub languages
        meta_parts = [s for s in structured if s]
        if sub_langs:
            meta_parts = [p for p in meta_parts if not p.upper().startswith('SUB')]
            meta_parts.append('SUB ' + ' '.join(dict.fromkeys(sub_langs)))
        if audio_langs:
            languages = ' | '.join(dict.fromkeys(audio_langs))
        metadata = ' | '.join(dict.fromkeys(meta_parts)) if meta_parts else extract_metadata(h4_text)

    # Extract from <h2> icons
    h2 = soup.find('h2')
    if h2:
        lang_list = []
        extra_meta = []
        for img in h2.find_all('img'):
            src = img.get('src', '').lower()
            title_attr = img.get('title', '')
            alt_attr = img.get('alt', '').lower()

            if 'stv.status.' in src or 'status.' in src:
                status = title_attr or img.get('alt', '') or None
            elif any(lang_key in src for lang_key in ['ita.', 'eng.', 'fra.', 'deu.', 'spa.',
                                                        'por.', 'jpn.', 'kor.', 'chn.', 'rus.']):
                code = LANGUAGE_MAP.get(alt_attr)
                if not code and title_attr:
                    code = LANGUAGE_MAP.get(title_attr.lower())
                if code:
                    lang_list.append(code)
            elif 'source.' in src or 'codec_v.' in src or 'codec_a.' in src or 'cont.' in src:
                label = title_attr or img.get('alt', '')
                if label:
                    extra_meta.append(label)

        if lang_list:
            languages = ' | '.join(dict.fromkeys(lang_list))

        if extra_meta:
            existing = metadata or ''
            combined = (existing + ' | ' + ' | '.join(extra_meta)) if existing else ' | '.join(extra_meta)
            metadata = ' | '.join(dict.fromkeys(combined.split(' | ')))

    return {
        'quality': quality,
        'metadata': metadata,
        'languages': languages,
        'status': status,
        'raw_info': raw_info,
        'post_created_at': post_created_at,
    }


def is_navigation_link(link) -> bool:
    """Check if a link is a navigation letter link (contains only an image)."""
    # Check if link contains only an image with no meaningful text
    img = link.find('img')
    if img:
        text = link.get_text(strip=True)
        # If there's an image and no text (or just whitespace), it's navigation
        if not text:
            return True
        # Check for letter navigation images (lettera.A.png, a.png, etc.)
        src = img.get('src', '')
        if 'lettera.' in src.lower() or re.search(r'/[a-z]\.png$', src.lower()):
            return True
    return False


def detect_section_quality(link) -> str | None:
    """
    Try to detect quality from the surrounding section context.
    Serie TV pages have sections like "HD - Alta Definizione" and "SD - Definizione Standard".
    """
    # Look for quality indicator images next to the link
    # e.g., full.hd.png, serietv.4k_uhd.png
    for sibling in [link.previous_sibling, link.next_sibling]:
        if sibling and hasattr(sibling, 'name') and sibling.name == 'img':
            src = sibling.get('src', '')
            if '4k' in src.lower() or 'uhd' in src.lower():
                return '4K'
            if 'full.hd' in src.lower() or 'fullhd' in src.lower():
                return '1080p'
            if '.hd.' in src.lower():
                return '720p'

    # Walk up the DOM to find section headers
    current = link.parent
    max_depth = 10  # Limit search depth
    depth = 0

    while current and depth < max_depth:
        # Check if we find a quality section header
        text = current.get_text() if hasattr(current, 'get_text') else ''

        # Look for quality indicators in section headers
        if 'HD - Alta Definizione' in text or 'Alta Definizione' in text:
            # Check if it's 4K/FullHD or regular HD
            if '4K' in text or 'UHD' in text:
                return '4K'
            if 'Full' in text:
                return '1080p'
            return '720p'
        if 'SD - Definizione Standard' in text or 'Definizione Standard' in text:
            return 'SD'

        # Also check for bold/strong quality headers
        strongs = current.find_all('strong') if hasattr(current, 'find_all') else []
        for strong in strongs:
            strong_text = strong.get_text()
            if 'HD' in strong_text and 'SD' not in strong_text:
                return '720p'
            if 'SD' in strong_text:
                return 'SD'

        current = current.parent
        depth += 1

    return None


def parse_page(html: str, section: str) -> list[dict]:
    """
    Parse a forum page and extract titles.

    Args:
        html: The HTML content of the page
        section: The section name for these titles

    Returns:
        List of dictionaries with title data
    """
    soup = BeautifulSoup(html, 'html.parser')
    results = []

    # Find all postlink-local links (main title links)
    links = soup.find_all('a', class_='postlink-local')

    for link in links:
        href = link.get('href', '')
        title_text = link.get_text(strip=True)

        # Skip links with no href
        if not href:
            continue

        # Skip navigation letter links (contain only images)
        if is_navigation_link(link):
            continue

        # Skip links with no title text
        if not title_text:
            continue

        # Skip certain links (navigation, non-topic links)
        if 'viewtopic.php' not in href:
            continue

        # Convert relative URL to absolute
        if href.startswith('./'):
            href = href[2:]
        url = urljoin(config.BASE_URL + '/', href)

        # Get the full line context for metadata extraction
        parent = link.parent
        full_text = parent.get_text() if parent else title_text

        # Also check for sibling elements with metadata
        next_sibling = link.next_sibling
        if next_sibling:
            sibling_text = str(next_sibling)
            full_text = title_text + ' ' + sibling_text

        # Extract quality and metadata
        quality = extract_quality(full_text)

        # If no quality found in text, check inline icons in parent
        if not quality:
            quality = extract_quality_from_icons(link.parent)

        # If still no quality, try to detect from section context
        if not quality:
            quality = detect_section_quality(link)

        # If section name includes quality hint, use it as fallback
        if not quality:
            section_lower = section.lower()
            if '4k' in section_lower or 'ultrahd' in section_lower:
                quality = '4K'
            elif 'fullhd' in section_lower or '1080' in section_lower:
                quality = '1080p'
            elif 'hd' in section_lower:
                quality = '720p'
            elif 'sd' in section_lower:
                quality = 'SD'

        metadata = extract_metadata(full_text)

        results.append({
            'title': title_text,
            'url': url,
            'section': section,
            'quality': quality,
            'metadata': metadata,
        })

    return results


def parse_pages_file(filepath: str) -> list[dict]:
    """
    Parse the pages.txt file.

    Format: Section Name | URL | Page Number

    Returns:
        List of dictionaries with section, url, and page info
    """
    pages = []

    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            for line_num, line in enumerate(f, 1):
                line = line.strip()

                # Skip empty lines and comments
                if not line or line.startswith('#'):
                    continue

                parts = [p.strip() for p in line.split('|')]

                if len(parts) < 2:
                    print(f"Warning: Invalid format on line {line_num}: {line}")
                    continue

                section = parts[0]
                url = parts[1]
                page = int(parts[2]) if len(parts) > 2 else 1

                pages.append({
                    'section': section,
                    'url': url,
                    'page': page,
                })
    except FileNotFoundError:
        print(f"Error: Pages file not found: {filepath}")
        return []

    return pages
