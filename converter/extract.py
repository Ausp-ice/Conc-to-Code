"""
Extracts structured character data from an old-format Edeia NPC toyhouse profile
(the Pinky/Gridsy-derived template family) into a plain dict, so it can be fed
into render.py to produce Morph_a-style output.
"""
import re
import json
from bs4 import BeautifulSoup, Tag, NavigableString

def is_header_like(tag):
    if not isinstance(tag, Tag):
        return False
    cls = tag.get('class') or []
    return 'justify-content-between' in cls and 'text-uppercase' in cls

def header_title(tag):
    span = tag.find('span')
    return span.get_text(' ', strip=True) if span else ''

def find_all_headers(soup):
    """Return list of (title, header_tag) for every section header in doc order."""
    out = []
    for tag in soup.find_all(is_header_like):
        out.append((header_title(tag), tag))
    return out

def find_header(soup, candidates):
    candidates = [c.lower() for c in candidates]
    for title, tag in find_all_headers(soup):
        if title.lower() in candidates:
            return tag
    return None

def find_headers_multi(soup, candidates):
    """Return ALL headers matching candidates (e.g. multiple Design boxes)."""
    candidates = [c.lower() for c in candidates]
    return [tag for title, tag in find_all_headers(soup) if title.lower() in candidates]

def section_siblings(header):
    """All sibling tags after `header`, stopping before the next header-like sibling."""
    sibs = []
    for sib in header.next_siblings:
        if isinstance(sib, Tag):
            if is_header_like(sib):
                break
            sibs.append(sib)
    return sibs

def inner_html(tag):
    if tag is None:
        return ''
    return tag.decode_contents().strip()

def stat_pairs(containers):
    """Find every div.justify-content-between with exactly a label span + value span."""
    pairs = []
    for c in containers:
        for jc in c.find_all(class_=lambda v: v and 'justify-content-between' in v):
            spans = jc.find_all('span', recursive=False)
            if len(spans) == 2:
                label = spans[0].get_text(' ', strip=True)
                value = inner_html(spans[1])
                if label or value.strip():
                    pairs.append((label, value))
    return pairs

YT_ID_RE = re.compile(r'(?:youtube\.com/embed/|youtube\.com/watch\?v=|youtu\.be/)([A-Za-z0-9_-]{6,})')

def parse_playlist_tracks(container):
    """Find playlist rows: div.justify-content-between with a title span (link or text) and a
    media span holding the old template's hidden YouTube play-button iframe."""
    tracks = []
    for jc in container.find_all(class_=lambda v: v and 'justify-content-between' in v):
        spans = jc.find_all('span', recursive=False)
        if len(spans) != 2:
            continue
        title_span, media_span = spans
        a = title_span.find('a')
        title = a.get_text(' ', strip=True) if a else title_span.get_text(' ', strip=True)
        href = a['href'] if a and a.has_attr('href') else ''
        if not title:
            continue
        youtube_id = ''
        iframe = media_span.find('iframe', src=True)
        if iframe:
            m = YT_ID_RE.search(iframe['src'])
            if m:
                youtube_id = m.group(1)
        tracks.append({'title': title, 'href': href, 'youtube_id': youtube_id})
    return tracks

def all_bullets(containers):
    out = []
    for c in containers:
        for li in c.find_all('li'):
            html = inner_html(li)
            if html.strip():
                out.append(html)
    return out

def all_paragraphs(container, exclude_tags=()):
    """All <p> html content within a container, skipping any nested inside excluded subtrees."""
    out = []
    for p in container.find_all('p'):
        if any(p in ex.descendants for ex in exclude_tags):
            continue
        html = inner_html(p)
        if html and html.strip() and html.strip() not in ('&nbsp;',):
            out.append(html)
    return out

def is_subsection_marker(tag):
    """A div/h2 that holds ONLY a single <span> title (no icon), or an <h2> holding only
    plain text -- used for both Abilities sub-headers and Story-era sub-headers in the
    old templates."""
    if not isinstance(tag, Tag) or tag.name not in ('div', 'h2'):
        return False
    cls = tag.get('class') or []
    if 'text-uppercase' not in cls:
        return False
    kids = [c for c in tag.find_all(recursive=False)]
    if not kids:
        return tag.name == 'h2' and bool(tag.get_text(strip=True))
    if len(kids) != 1 or kids[0].name != 'span':
        return False
    return True

def marker_title(tag):
    span = tag.find('span')
    return (span or tag).get_text(' ', strip=True)

def parse_subsections(container):
    """Split a container's content into
    (preamble_paragraphs, [(title, dates, [para_html,...]), ...])
    using is_subsection_marker as the delimiter. `dates` is '' unless the title <h2> is
    directly followed by a single-span <div> subheading (e.g. "1965-1990")."""
    preamble = []
    sections = []
    current_title = None
    current_dates = ''
    current_paras = []
    title_el = None

    def flush():
        nonlocal current_title, current_dates, current_paras
        if current_title is not None:
            sections.append((current_title, current_dates, current_paras))
        current_title = None
        current_dates = ''
        current_paras = []

    candidates = []
    for el in container.find_all(['p', 'div', 'h2']):
        if is_subsection_marker(el):
            candidates.append(('marker', el))
        elif el.name == 'p':
            candidates.append(('p', el))

    for kind, el in candidates:
        if kind == 'marker':
            if (el.name == 'div' and title_el is not None and title_el.name == 'h2'
                    and el.find_previous_sibling() is title_el
                    and not current_dates and not current_paras):
                current_dates = marker_title(el)
                continue
            flush()
            current_title = marker_title(el)
            title_el = el
        else:
            html = inner_html(el)
            if not html.strip():
                continue
            if current_title is None:
                preamble.append(html)
            else:
                current_paras.append(html)
    flush()
    return preamble, sections

IMG_RE = re.compile(r"background-image:\s*url\(\s*'?\"?([^'\")]+)['\"]?\s*\)", re.I)

def find_background_images(soup):
    """Return list of dicts: {url, href} in document order for every background-image div."""
    out = []
    for tag in soup.find_all(style=True):
        m = IMG_RE.search(tag['style'])
        if not m:
            continue
        url = m.group(1)
        href = None
        a = tag.find('a', href=True)
        if a and a['href'].strip():
            href = a['href'].strip()
        out.append({'url': url, 'href': href})
    return out

# Trailing credit on a relation line: "Owner: x", "Co-Owner: x" or "Sona of x" (with the
# bullet / <small> wrapper the old template puts around it). Group 1 is the label as written.
OWNER_RE = re.compile(
    r'\s*(?:&bull;|•)?\s*(?:<small>)?\s*((?:Co-)?Owners?:|Sona of)\s*'
    r'<a href="([^"]+)"[^>]*>([^<]+)</a>.*$', re.I | re.S)

def parse_relation_entries(container):
    """Find repeating character-link blocks: img.rounded-circle + <p> w/ name link + relation + paras."""
    entries = []
    imgs = container.find_all('img', class_=lambda c: c and 'rounded-circle' in c)
    for img in imgs:
        entry_box = img.parent
        img_src = img.get('src', '')
        ps = entry_box.find_all('p', recursive=False)
        if not ps:
            ps = [p for p in entry_box.find_all('p')]
        if not ps:
            continue
        first_p = ps[0]
        name_a = first_p.find('a')
        name = name_a.get_text(' ', strip=True) if name_a else ''
        name_href = name_a['href'] if name_a and name_a.has_attr('href') else ''
        rel_i = first_p.find('i')
        relation_html = inner_html(rel_i) if rel_i else ''
        owner_label, owner_name, owner_href = '', '', ''
        owner_match = OWNER_RE.search(relation_html)
        if owner_match:
            owner_label, owner_href, owner_name = owner_match.group(1, 2, 3)
            relation_html = relation_html[:owner_match.start()].strip()
            relation_html = re.sub(r'<br\s*/?>', '', relation_html).strip()
        br_tags = first_p.find_all('br')
        first_para_html = ''
        if br_tags:
            last_br = br_tags[-1]
            pieces = [str(sib) for sib in last_br.next_siblings]
            first_para_html = ''.join(pieces).strip()
        extra_paras = [inner_html(p) for p in ps[1:]]
        paras = [p for p in ([first_para_html] + extra_paras) if p.strip()]
        if not name.strip():
            continue  # unfilled placeholder entry (empty template stub)
        entries.append({
            'img': img_src, 'name': name, 'href': name_href,
            'relation': relation_html, 'owner_label': owner_label,
            'owner_name': owner_name, 'owner_href': owner_href,
            'paragraphs': paras,
            'more': relation_full_story(entry_box),
        })
    return entries

def relation_full_story(entry_box):
    """The collapsible "Full Story" box belonging to a relation entry, as a list of paragraph
    html strings with None standing in for each <hr> divider. The box is either inside the
    entry itself or the very next sibling after it (before the next character link)."""
    collapse = entry_box.find('div', class_=lambda c: c and 'collapse' in c)
    if collapse is None:
        nxt = entry_box.find_next_sibling()
        if nxt is not None and not nxt.find('img', class_=lambda c: c and 'rounded-circle' in c):
            if 'collapse' in (nxt.get('class') or []):
                collapse = nxt
            else:
                collapse = nxt.find('div', class_=lambda c: c and 'collapse' in c)
    if collapse is None:
        return []
    more = []
    for el in collapse.find_all(['p', 'hr']):
        if el.name == 'hr':
            if more and more[-1] is not None:
                more.append(None)
        elif inner_html(el).strip() and not el.find('a', attrs={'data-toggle': 'collapse'}):
            more.append(inner_html(el))
    while more and more[-1] is None:
        more.pop()
    return more

BASE_URL_RE = re.compile(r'(https://toyhou\.se/[^"\'#]+?)/gallery#')

def guess_base_url(html_text):
    matches = BASE_URL_RE.findall(html_text)
    if not matches:
        return None
    from collections import Counter
    return Counter(matches).most_common(1)[0][0]

ACCENT_RE = re.compile(r'highlight color:\s*-*\s*(#[0-9a-fA-F]{3,6})')
BG_RE = re.compile(r'content background:\s*-*\s*([^\n]+)')

def extract(path):
    raw = open(path, encoding='utf-8').read()
    soup = BeautifulSoup(raw, 'html.parser')

    accent_m = ACCENT_RE.search(raw)
    accent = accent_m.group(1) if accent_m else '#6286c4'
    bg_m = BG_RE.search(raw)
    bg = bg_m.group(1).strip() if bg_m else 'rgba(1,1,1,.90)'

    data = {'accent': accent, 'bg': bg, 'source_file': str(path)}

    # ---- BASICS ----
    basics_header = find_header(soup, ['basics'])
    data['basics_raw'] = stat_pairs(section_siblings(basics_header)) if basics_header else []

    # ---- INTRO ----
    intro_header = find_header(soup, ['intro'])
    data['intro_paragraphs'] = all_paragraphs(_wrap(section_siblings(intro_header))) if intro_header else []

    # ---- ABOUT / PERSONALITY / OVERVIEW ----
    about_header = find_header(soup, ['about', 'personality', 'overview'])
    data['about_title_found'] = header_title(about_header) if about_header else None
    about_container = _wrap(section_siblings(about_header)) if about_header else None
    if about_container:
        tagline_tag = about_container.find('p', class_='text-center')
        data['about_tagline'] = inner_html(tagline_tag) if tagline_tag else ''
        data['about_paragraphs'] = [inner_html(p) for p in about_container.find_all('p')
                                     if p is not tagline_tag and inner_html(p).strip()]
    else:
        data['about_tagline'] = ''
        data['about_paragraphs'] = []

    # ---- PLAYLIST ----
    playlist_header = find_header(soup, ['playlist'])
    playlist_tracks = []
    if playlist_header:
        playlist_tracks = parse_playlist_tracks(_wrap(section_siblings(playlist_header)))
    data['playlist_tracks'] = playlist_tracks

    # ---- DESIGN (possibly multiple boxes, e.g. twin characters) ----
    design_headers = [h for t, h in find_all_headers(soup) if t.lower().startswith('design')]
    design_fields = []
    design_notes = []
    design_titles = []
    for dh in design_headers:
        design_titles.append(header_title(dh))
        sibs = section_siblings(dh)
        design_fields.extend(stat_pairs(sibs))
        design_notes.extend(all_bullets(sibs))
    data['design_titles'] = design_titles
    data['design_fields'] = design_fields
    data['design_notes'] = design_notes

    # ---- ABILITIES / MAGIC / POWERS ----
    ability_header = find_header(soup, ['abilities', 'magic', 'powers'])
    data['abilities_title_found'] = header_title(ability_header) if ability_header else None
    if ability_header:
        container = _wrap(section_siblings(ability_header))
        preamble, subs = parse_subsections(container)
        data['abilities_preamble'] = preamble
        data['abilities'] = [(title, paras) for title, _dates, paras in subs]
    else:
        data['abilities_preamble'] = []
        data['abilities'] = []

    # ---- ABSTRACTION ----
    abstraction_header = None
    for t, h in find_all_headers(soup):
        if 'abstraction' in t.lower():
            abstraction_header = h
            break
    data['abstraction_paragraphs'] = all_paragraphs(_wrap(section_siblings(abstraction_header))) if abstraction_header else []

    # ---- STORY ----
    story_header = find_header(soup, ['story'])
    data['story_lead'] = []
    data['story_eras'] = []
    # paragraphs inside the "Full Story" collapse that sit before (or without) any era
    # sub-headers -- kept apart from story_lead so they stay behind the "Read more"
    data['story_more'] = []
    if story_header:
        container = _wrap(section_siblings(story_header))
        # drop the old "Full Story" toggle button so it isn't picked up as a lead paragraph
        for toggle in container.find_all('a', attrs={'data-toggle': 'collapse'}):
            toggle_p = toggle.find_parent('p')
            if toggle_p:
                toggle_p.decompose()
        collapse =container.find(id=re.compile(r'fullstory|storycollapse', re.I)) or \
                   container.find('div', class_=lambda c: c and 'collapse' in c)
        if collapse:
            data['story_lead'] = all_paragraphs(container, exclude_tags=(collapse,))
            preamble, eras = parse_subsections(collapse)
            data['story_eras'] = eras
            data['story_more'] = preamble
        else:
            preamble, eras = parse_subsections(container)
            data['story_lead'] = preamble
            data['story_eras'] = eras

    # ---- RELATIONS (single, or Internal/Others split) ----
    rel_headers = find_headers_multi(soup, ['relations', 'relations - internal', 'relations - internals',
                                             'relations - others', 'relations - other'])
    data['relations_internal'] = []
    data['relations_other'] = []
    if len(rel_headers) >= 2:
        for h in rel_headers:
            t = header_title(h).lower()
            entries = parse_relation_entries(_wrap(section_siblings(h)))
            if 'other' in t:
                data['relations_other'].extend(entries)
            else:
                data['relations_internal'].extend(entries)
    elif len(rel_headers) == 1:
        entries = parse_relation_entries(_wrap(section_siblings(rel_headers[0])))
        for e in entries:
            (data['relations_other'] if e['owner_name'] else data['relations_internal']).append(e)

    # ---- FUSIONS ----
    fusion_header = find_header(soup, ['fusions', 'fusion'])
    data['fusions'] = parse_relation_entries(_wrap(section_siblings(fusion_header))) if fusion_header else []

    # ---- NOTES / TRIVIA ----
    notes_header = find_header(soup, ['notes', 'trivia'])
    data['trivia'] = all_bullets(section_siblings(notes_header)) if notes_header else []

    # ---- IMAGES ----
    data['images'] = find_background_images(soup)

    # ---- base toyhou.se url ----
    data['base_url'] = guess_base_url(raw)

    return data

def _wrap(tags):
    """Wrap a list of sibling tags in a fake container div (bs4) so find_all works over all of them.
    Uses copy.copy() (bs4's subtree-clone, not deepcopy) so the original soup tree is left
    untouched -- deepcopy pulls in each tag's .parent backreference and re-copies the entire
    ancestor tree along with it, which blows Python's recursion limit on larger profiles."""
    import copy
    soup = BeautifulSoup('<div></div>', 'html.parser')
    container = soup.div
    for t in tags:
        container.append(copy.copy(t))
    return container

if __name__ == '__main__':
    import sys
    p = sys.argv[1]
    d = extract(p)
    print(json.dumps(d, indent=2, default=str)[:8000])
