"""
Extracts structured character data from a plain doc-drafted profile (a Google Doc / Word
draft exported or converted to HTML -- e.g. e_onaara_basic.html) into the same dict shape
extract.py produces, so render.py can turn it into Morph_a-style output.

Expected draft shape (loose -- anything it can't place is reported in the CONVERSION NOTES):

    <p>Onaara, Edeia of Theophagy</p>                      <- optional title line, skipped
    <p><strong>Name:</strong> Onaara<br><strong>Idea:</strong> ...</p>   <- Basics fields
    <p>Onaara is an Edeia representing ...</p>              <- Intro (unlabelled paragraphs)
    <h1>Personality</h1> ...                                <- one <h1> per section
    <h1>Abilities</h1> <h2>Idea Magic</h2> <h3>Ability name</h3> ...
    <h1>History</h1> <ul>timeline</ul> <h2>Era title</h2> ...
    <h1>Relations</h1> <h2>Character name</h2> <p><em>Relation</em></p> ...

Any <h1> section it doesn't recognise (e.g. "Followers") is kept as an extra full-width box.
"""
import re
from pathlib import Path
from bs4 import BeautifulSoup, Tag
from extract import inner_html, guess_base_url, find_background_images

EDEIA_SPECIES = '<a href="https://www.edeia-ideation.com/home">Edeia</a>'

# Labels recognised as Basics fields even when the doc lost its bold formatting.
KNOWN_LABELS = {
    'name', 'names', 'known as', 'pronunciation', 'idea', 'ideas', 'gender', 'pronouns',
    'species', 'origin', 'prominence', 'masterlist', 'previous species', 'previous form',
    'era of birth', 'era', 'theme', 'themes', 'significant dates', 'dates', 'age/dates',
    'age', 'cw', 'cws', 'content warning', 'content warnings', 'quote', 'accent', 'toyhouse',
    'special trait', 'special traits', 'owner',
}

SECTION_KINDS = [
    ('intro', ['intro', 'introduction']),
    ('about', ['personality', 'about', 'overview']),
    ('interpretation', ['idea interpretation', 'interpretation']),
    ('abilities', ['abilities', 'magic', 'powers']),
    ('story', ['history', 'story', 'backstory']),
    ('abstraction', ['abstraction']),
    ('fusions', ['fusions', 'fusion']),
    ('trivia', ['notes', 'trivia']),
    ('design', ['design', 'appearance']),
    ('playlist', ['playlist']),
]

# Story sub-headings that just mean "the long version" rather than naming an era
FULL_STORY_TITLES = {'full story', 'full history', 'read more', 'more'}

def section_kind(title):
    t = title.lower().strip()
    if t.startswith('relations'):
        return 'relations'
    for kind, names in SECTION_KINDS:
        if t in names:
            return kind
    return 'extra'

# ---- Google Docs export cleanup -------------------------------------------------------

GDOCS_REDIRECT_RE = re.compile(r'^https?://(?:www\.)?google\.com/url\?q=([^&]+)')

def normalize(soup):
    """Make Google Docs' "Download as HTML" output look like a clean export: bold/italic
    classes become <strong>/<em>, wrapper spans and redirect links are unwrapped, and
    empty paragraphs are dropped. A no-op on files that are already clean."""
    from urllib.parse import unquote
    bold_classes, italic_classes = set(), set()
    for style in soup.find_all('style'):
        for cls, body in re.findall(r'\.([\w-]+)\s*\{([^}]*)\}', style.get_text()):
            if re.search(r'font-weight:\s*(700|bold)', body):
                bold_classes.add(cls)
            if re.search(r'font-style:\s*italic', body):
                italic_classes.add(cls)
        style.decompose()
    for span in soup.find_all('span'):
        classes = set(span.get('class') or [])
        style = span.get('style', '')
        if classes & bold_classes or re.search(r'font-weight:\s*(700|bold)', style):
            span.wrap(soup.new_tag('strong'))
        if classes & italic_classes or re.search(r'font-style:\s*italic', style):
            span.wrap(soup.new_tag('em'))
        span.unwrap()
    for a in soup.find_all('a', href=True):
        m = GDOCS_REDIRECT_RE.match(a['href'])
        if m:
            a['href'] = unquote(m.group(1))
        if not a.get_text(strip=True) and not a.find('img'):
            a.unwrap()  # empty bookmark anchors
    for tag in soup.find_all(True):
        if tag.name in ('a', 'img'):
            continue
        for attr in ('class', 'style', 'id', 'dir'):
            tag.attrs.pop(attr, None)
    for p in soup.find_all('p'):
        if not p.get_text(strip=True).replace('\xa0', '') and not p.find('img'):
            p.decompose()

# ---- block stream ---------------------------------------------------------------------

def blocks_of(soup, heading_links=None):
    """Flatten the doc into an ordered list of (kind, value) blocks:
    ('h1'|'h2'|'h3', text), ('p', inner_html), ('ul', [li_inner_html, ...]).
    Headings that are links ("<h2><a href=..>Erivis</a></h2>") have their href recorded in
    heading_links[text], since the block itself only keeps the text."""
    out = []
    for el in soup.find_all(['h1', 'h2', 'h3', 'h4', 'p', 'ul', 'ol']):
        if el.find_parent(['ul', 'ol', 'p', 'h1', 'h2', 'h3', 'h4']):
            continue
        if el.name in ('h1', 'h2', 'h3', 'h4'):
            text = el.get_text(' ', strip=True)
            if text:
                out.append(('h3' if el.name == 'h4' else el.name, text))
                a = el.find('a', href=True)
                if a is not None and heading_links is not None:
                    heading_links[text] = a['href']
        elif el.name == 'p':
            html = clean_html(inner_html(el))
            if html:
                out.append(('p', html))
        else:
            items = [clean_html(inner_html(li)) for li in el.find_all('li', recursive=False)]
            items = [i for i in items if i]
            if items:
                out.append(('ul', items))
    return out

def clean_html(html):
    html = re.sub(r'(&nbsp;|\xa0)+$', '', html.strip()).strip()
    html = re.sub(r'(<br\s*/?>\s*)+$', '', html).strip()
    # a link glued to the previous word by the doc export ("the<a href=..>") gets its space back
    html = re.sub(r'(\w)(<a\s)', r'\1 \2', html)
    return html

def split_sections(blocks):
    """-> (preamble_blocks, [(h1_title, blocks), ...])"""
    preamble, sections = [], []
    current = preamble
    for kind, val in blocks:
        if kind == 'h1':
            sections.append((val, []))
            current = sections[-1][1]
        else:
            current.append((kind, val))
    return preamble, sections

def split_sub(blocks, level='h2'):
    """-> (lead_blocks, [(sub_title, blocks), ...]) split on the given heading level."""
    lead, subs = [], []
    current = lead
    for kind, val in blocks:
        if kind == level:
            subs.append((val, []))
            current = subs[-1][1]
        else:
            current.append((kind, val))
    return lead, subs

def to_html_list(blocks):
    """Blocks -> list of html strings for render.p_join (lists and sub-headers are emitted
    as full elements, which p_join leaves unwrapped)."""
    out = []
    for kind, val in blocks:
        if kind == 'p':
            out.append(val)
        elif kind == 'ul':
            items = '\n'.join(
                f'<li class="mb-1"><span class="fa-li"><i class="fa-solid fa-chevron-right fa-xs" '
                f'style="color:{{ACCENT}}"></i></span>{i}</li>' for i in val)
            out.append(f'<ul class="fa-ul" style="margin-left:20px">\n{items}\n</ul>')
        else:
            out.append(f'<p class="text-uppercase" style="font-size:14px; font-weight:900; '
                       f'color:{{ACCENT}}">{val}</p>')
    return out

# ---- labelled "Label: value" lines ----------------------------------------------------

STRONG_LABEL_RE = re.compile(r'^\s*<(strong|b)>\s*([^<]{1,40}?)\s*:?\s*</\1>\s*:?\s*(.*)$', re.S)
PLAIN_LABEL_RE = re.compile(r'^\s*([A-Za-z][A-Za-z /&\'-]{0,30}?)\s*:\s*(.+)$', re.S)

def parse_label_line(line_html):
    """'<strong>Name:</strong> Onaara' -> ('Name', 'Onaara'), else None. Bold labels are
    always accepted; un-bolded ones only if they are a known Basics label."""
    m = STRONG_LABEL_RE.match(line_html)
    if m:
        return m.group(2).strip(), m.group(3).strip()
    m = PLAIN_LABEL_RE.match(line_html)
    if m and m.group(1).strip().lower() in KNOWN_LABELS:
        return m.group(1).strip(), m.group(2).strip()
    return None

def label_lines(p_html):
    """Split a paragraph on <br> and parse each line; None if any line isn't a label."""
    lines = [l for l in re.split(r'<br\s*/?>', p_html) if l.strip()]
    pairs = [parse_label_line(l) for l in lines]
    if not pairs or any(p is None for p in pairs):
        return None
    return pairs

QUOTED_RE = re.compile(r'^\s*(?:"|&quot;|&ldquo;|“)(.+?)(?:"|&quot;|&rdquo;|”)\s*$', re.S)

def quoted_text(p_html):
    """'<em>"Hi. I'm Nester."</em>' -> "Hi. I'm Nester." (quote marks and the outer
    italics stripped), or None if the paragraph isn't wholly a quotation."""
    m = ITALIC_ONLY_RE.match(p_html)
    inner = m.group(2) if m else p_html
    m = QUOTED_RE.match(inner)
    return m.group(1).strip() if m else None

def looks_like_title(p_html):
    text = re.sub(r'<[^>]+>', '', p_html).strip()
    return len(text) < 80 and not re.search(r'[.!?:]$', text)

# ---- relations ------------------------------------------------------------------------

CHARACTERS_CSV = Path(__file__).with_name('characters.csv')
_characters = None

def name_slug(name):
    return re.sub(r'[^a-z0-9]', '', name.lower())

def load_characters():
    """characters.csv (name, toyhouse, image, owner) -> {name slug: row}. Read once."""
    global _characters
    if _characters is None:
        _characters = {}
        if CHARACTERS_CSV.exists():
            import csv
            with CHARACTERS_CSV.open(encoding='utf-8', newline='') as f:
                for row in csv.DictReader(f):
                    if (row.get('name') or '').strip():
                        _characters[name_slug(row['name'])] = {k: (v or '').strip() for k, v in row.items()}
    return _characters

def lookup_profile(name, folder):
    """Find this character in characters.csv, or failing that its existing profile in the
    Edeia folder (e_<name>.html etc.), so relation entries come pre-linked.
    -> (toyhouse url, image url, owner username, where it was found) or blanks + None."""
    slug = name_slug(name)
    row = load_characters().get(slug)
    if row:
        return row.get('toyhouse', ''), row.get('image', ''), row.get('owner', ''), CHARACTERS_CSV.name
    for cand in (f'e_{slug}_a.html', f'e_{slug}.html', f'npc_{slug}_a.html', f'npc_{slug}.html'):
        path = folder / cand
        if path.exists():
            raw = path.read_text(encoding='utf-8', errors='ignore')
            imgs = find_background_images(BeautifulSoup(raw, 'html.parser'))
            return guess_base_url(raw) or '', (imgs[0]['url'] if imgs else ''), '', cand
    return '', '', '', None

ITALIC_ONLY_RE = re.compile(r'^\s*<(em|i)>(.*)</\1>\s*$', re.S)

def parse_relations(blocks, folder, notes, heading_links, own_owner=''):
    """own_owner: the draft's "Owner:" field -- relations owned by the same person get no
    "Owner:" credit line."""
    entries = []
    _lead, subs = split_sub(blocks, 'h2')
    for name, sub in subs:
        relation = ''
        if sub and sub[0][0] == 'p':
            m = ITALIC_ONLY_RE.match(sub[0][1])
            if m:
                relation = m.group(2).strip()
                sub = sub[1:]
        href, img, owner, found = lookup_profile(name, folder)
        if owner.lower() == own_owner.lower():
            owner = ''
        heading_href = heading_links.get(name)
        if heading_href:
            href = heading_href  # a link written into the draft wins over the lookup
        if found:
            taken = 'image' if heading_href else 'link and image'
            notes.append(f'Relation "{name}": {taken} taken from {found} -- check them.')
        elif heading_href:
            notes.append(f'Relation "{name}": link taken from the draft heading; not in the '
                         f'character list -- add image by hand.')
        else:
            notes.append(f'Relation "{name}": not in the character list -- add link and image by hand.')
        entries.append({
            'img': img, 'name': name, 'href': href, 'relation': relation,
            'owner_label': 'Owner:' if owner else '', 'owner_name': owner,
            'owner_href': f'https://toyhou.se/{owner}' if owner else '',
            'paragraphs': to_html_list(sub), 'more': [],
        })
    return entries

# ---- main -----------------------------------------------------------------------------

def is_basic_draft(raw):
    """True for a doc-style draft: plain <h1> sections and none of the old toyhouse
    template's header bars."""
    return bool(re.search(r'<h1[\s>]', raw, re.I)) and 'justify-content-between' not in raw

def extract_basic(path, owner=''):
    """owner: the draft author's toyhou.se username (an "Owner:" field in the draft wins)."""
    path = Path(path)
    raw = path.read_text(encoding='utf-8')
    soup = BeautifulSoup(raw, 'html.parser')
    normalize(soup)
    notes = []

    data = {
        'accent': '#6286c4', 'bg': 'rgba(1,1,1,.90)', 'source_file': str(path),
        'basics_raw': [], 'intro_paragraphs': [], 'about_title_found': None,
        'about_tagline': '', 'about_paragraphs': [], 'playlist_tracks': [],
        'design_titles': [], 'design_fields': [], 'design_notes': [],
        'abilities_title_found': None, 'abilities_preamble': [], 'abilities': [],
        'abstraction_paragraphs': [], 'story_lead': [], 'story_eras': [], 'story_more': [],
        'relations_internal': [], 'relations_other': [], 'fusions': [], 'trivia': [],
        'images': [], 'base_url': None,
        # draft-only extras (render.py reads these with .get(), old extract.py omits them)
        'idea_interpretation': [], 'abilities_intro': [], 'story_timeline': [],
        'extra_sections': [], 'extract_notes': notes,
    }

    heading_links = {}
    preamble, sections = split_sections(blocks_of(soup, heading_links))

    # a draft that opens with an <h1> title ("<h1>Nester</h1>") instead of a title <p>:
    # that "section" is really the preamble (Basics fields + Intro)
    if not preamble and sections and section_kind(sections[0][0]) == 'extra':
        title, preamble = sections.pop(0)
        notes.append(f'Title heading "{title}" skipped (not used by the layout).')

    # ---- preamble: title line, Basics fields, Intro ----
    for i, (kind, val) in enumerate(preamble):
        pairs = label_lines(val) if kind == 'p' else None
        if pairs:
            data['basics_raw'].extend(pairs)
        elif i == 0 and kind == 'p' and looks_like_title(val):
            notes.append(f'Title line "{re.sub("<[^>]+>", "", val)}" skipped (not used by the layout).')
        else:
            data['intro_paragraphs'].extend(to_html_list([(kind, val)]))

    basics = {l.lower(): v for l, v in data['basics_raw']}
    accent = re.sub(r'<[^>]+>', '', basics.get('accent', '')).strip()
    if accent:
        data['accent'] = accent
    if basics.get('toyhouse'):
        m = re.search(r'href="([^"]+)"', basics['toyhouse'])
        data['base_url'] = (m.group(1) if m else re.sub(r'<[^>]+>', '', basics['toyhouse'])).strip().rstrip('/')
    if basics.get('quote'):
        data['about_tagline'] = basics['quote']
    owner = (re.sub(r'<[^>]+>', '', basics.get('owner', '')).strip() or owner).strip().lstrip('@')
    data['basics_raw'] = [(l, v) for l, v in data['basics_raw']
                          if l.lower() not in ('accent', 'toyhouse', 'quote', 'owner')]
    # (Species defaults to Edeia for e_ files in render.py, for drafts and old files alike)

    # ---- h1 sections ----
    for title, blocks in sections:
        kind = section_kind(title)

        if kind == 'intro':
            data['intro_paragraphs'].extend(to_html_list(blocks))

        elif kind == 'about':
            data['about_title_found'] = title
            # an opening quoted paragraph ('<p><em>"Hi. I'm Nester..."</em></p>') is the
            # in-character quote, unless a "Quote:" field already supplied one
            if blocks and blocks[0][0] == 'p' and not data['about_tagline']:
                quote = quoted_text(blocks[0][1])
                if quote:
                    data['about_tagline'] = quote
                    blocks = blocks[1:]
                    notes.append(f'Opening quoted paragraph of "{title}" used as the in-character quote.')
            data['about_paragraphs'].extend(to_html_list(blocks))

        elif kind == 'interpretation':
            data['idea_interpretation'].extend(to_html_list(blocks))

        elif kind == 'abilities':
            data['abilities_title_found'] = title
            # ability boxes are <h3>s if the draft uses them, otherwise <h2>s
            level = 'h3' if any(k == 'h3' for k, _ in blocks) else 'h2'
            current = None
            skipping = False
            for k, v in blocks:
                if k == 'h2' and v.lower() == 'general edeia abilities':
                    skipping = True  # boilerplate -- the layout already has this paragraph
                    current = None
                    continue
                if k == 'h2' and level == 'h3':
                    skipping = False  # e.g. "Idea Magic" wrapper heading
                    current = None
                    if v.lower() != 'idea magic':
                        notes.append(f'Abilities sub-group "{v}" flattened -- its abilities are '
                                     f'listed under Idea Magic.')
                    continue
                if k == level:
                    skipping = False
                    current = (v, [])
                    data['abilities'].append(current)
                    continue
                if skipping:
                    continue
                if current is None:
                    data['abilities_intro'].extend(to_html_list([(k, v)]))
                else:
                    current[1].extend(to_html_list([(k, v)]))

        elif kind == 'story':
            lead, eras = split_sub(blocks, 'h2')
            for k, v in lead:
                if k == 'ul' and not data['story_timeline']:
                    data['story_timeline'] = v
                else:
                    data['story_lead'].extend(to_html_list([(k, v)]))
            for t, b in eras:
                if t.lower().strip(' :') in FULL_STORY_TITLES:
                    # plain un-headed paragraphs inside the "Read more" collapse
                    data['story_more'].extend(to_html_list(b))
                else:
                    data['story_eras'].append((t, '', to_html_list(b)))

        elif kind == 'abstraction':
            data['abstraction_paragraphs'].extend(to_html_list(blocks))

        elif kind == 'relations':
            entries = parse_relations(blocks, path.parent, notes, heading_links, owner)
            key = 'relations_other' if 'other' in title.lower() else 'relations_internal'
            data[key].extend(entries)

        elif kind == 'fusions':
            data['fusions'].extend(parse_relations(blocks, path.parent, notes, heading_links, owner))

        elif kind == 'trivia':
            for k, v in blocks:
                data['trivia'].extend(v if k == 'ul' else ([v] if k == 'p' else []))

        elif kind == 'design':
            data['design_titles'].append(title)
            for k, v in blocks:
                pairs = label_lines(v) if k == 'p' else None
                if pairs:
                    data['design_fields'].extend(pairs)
                elif k == 'ul':
                    data['design_notes'].extend(v)
                elif k == 'p':
                    data['design_notes'].append(v)

        elif kind == 'playlist':
            for k, v in blocks:
                for item in (v if k == 'ul' else [v] if k == 'p' else []):
                    m = re.search(r'<a href="([^"]+)"[^>]*>(.*?)</a>', item)
                    href, title_ = (m.group(1), m.group(2)) if m else ('', re.sub(r'<[^>]+>', '', item))
                    yt = re.search(r'(?:youtube\.com/watch\?v=|youtu\.be/)([A-Za-z0-9_-]{6,})', href)
                    data['playlist_tracks'].append(
                        {'title': title_, 'href': href, 'youtube_id': yt.group(1) if yt else ''})

        else:
            lead, subs = split_sub(blocks, 'h2')
            data['extra_sections'].append((title, to_html_list(lead),
                                           [(t, to_html_list(b)) for t, b in subs]))
            notes.append(f'Section "{title}" has no slot in the layout -- added as its own '
                         f'full-width box after Story; move or restyle by hand if needed.')

    return data

if __name__ == '__main__':
    import sys, json
    print(json.dumps(extract_basic(sys.argv[1]), indent=2, default=str)[:8000])
