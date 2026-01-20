"""HTML Parser module for DDUnlimited Search."""

import re
from urllib.parse import urljoin
from bs4 import BeautifulSoup

import config


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

        # If no quality found in text, try to detect from section context
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
