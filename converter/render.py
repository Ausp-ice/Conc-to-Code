"""
HOW TO RUN (from the Edeia folder, in Anaconda Prompt):

    python _a_convert_scripts\\render.py e_rhome.html

This writes _a_convert_scripts\\converted\\e_rhome_new.html (old file name + "_new").
If that file already exists it is left alone, in case it has hand edits; to replace it:

    python _a_convert_scripts\\render.py e_rhome.html --force

Always start the command with "python" -- running the .py file on its own does nothing.
extract.py does not need to be run separately; this script calls it.

Doc drafts (a Google Doc / Word draft converted to HTML, e.g. e_onaara_basic.html) work the
same way -- they're detected automatically and read with extract_basic.py instead:

    python _a_convert_scripts\\render.py e_onaara_basic.html

A trailing "_basic" is dropped from the output name (-> converted\\e_onaara_new.html).
Relations in drafts are linked from characters.csv. Characters owned by Auspice get no
"Owner:" credit line; for someone else's draft, add "--owner THEIRNAME".
Drafts can also fill in Pronunciation, Idea Interpretation, the Story timeline, and
Significant Dates, which old-format files have no equivalent for.

Renders extracted character data (see extract.py) into Morph_a-style NPC profile HTML.

This does NOT try to be pixel-perfect -- it transfers the major, mechanically-mappable
content (Basics using Morph's exact field set, Intro, About, Design, Abilities, Abstraction,
Story, Relations/Fusions, Notes) into the new layout shell, and marks anything it can't
confidently fill in with TBD so a human pass can finish it. A CONVERSION NOTES comment is
written at the top of every output file listing what was guessed/dropped/unmapped.
"""
import re
import unicodedata
from pathlib import Path
from extract import extract
from extract_basic import extract_basic, is_basic_draft, EDEIA_SPECIES

TBD = 'TBD'
PROMINENCE_GUIDE_URL = 'https://www.edeia-ideation.com/lore-guide/setting#h.sk4c1oj7ow4v'

def esc(s):
    return s if s else ''

def first(basics, *labels):
    d = {l.lower(): v for l, v in basics}
    for l in labels:
        l = l.lower()
        if l in d and d[l].strip():
            return d[l]
    return None

def stat_box(label, value, index=0):
    side = 'pr-lg-1' if index % 2 == 0 else 'pl-lg-1'
    return f'''										<div class="col-lg-6 col-12 {side} mb-2 row no-gutters">
											<div class="col-12" style="border:solid 1px {{ACCENT}}; padding:12px">
												<div class="mb-1 text-uppercase" style="font-size:14px; font-weight:900"><i class="fa-sharp fa-solid fa-sparkle fa-fw" style="color:{{ACCENT}}"></i> {label}</div>
												<div style="font-weight:100; line-height:120%">{value if value else TBD}</div>
											</div>
										</div>'''

def build_basics(d, notes):
    b = d['basics_raw']
    name = first(b, 'Name', 'Names', 'Known As') or TBD
    ideas = first(b, 'Ideas', 'Idea') or TBD
    prominence = first(b, 'Prominence') or TBD
    if '<a ' not in prominence:
        prominence = f'<a href="{PROMINENCE_GUIDE_URL}">{prominence}</a>'
    origin = first(b, 'Origin') or TBD
    gender = first(b, 'Gender') or TBD
    pronouns = first(b, 'Pronouns') or TBD
    species = first(b, 'Species')
    if not species and Path(d['source_file']).name.startswith('e_'):
        species = EDEIA_SPECIES
    species = species or TBD
    masterlist = first(b, 'Masterlist') or TBD
    prev_species = first(b, 'Previous Species', 'Previous Form') or TBD
    era = first(b, 'Era of Birth', 'Era') or TBD
    theme = first(b, 'Theme', 'Themes')
    if not theme and d['playlist_tracks']:
        theme = ', '.join(f'<a href="{t["href"]}">{t["title"]}</a>' for t in d['playlist_tracks'])
    theme = theme or TBD
    sig_dates = first(b, 'Significant Dates', 'Age/Dates', 'Dates', 'Age') or TBD

    # pronunciation and CW have their own spots (name badge / top of Intro), not the grid
    mapped_labels = {'name', 'names', 'known as', 'ideas', 'idea', 'prominence', 'origin',
                      'gender', 'pronouns', 'species', 'masterlist', 'previous species',
                      'previous form', 'era of birth', 'era', 'theme', 'themes',
                      'significant dates', 'age/dates', 'dates', 'age', 'pronunciation',
                      'cw', 'cws', 'content warning', 'content warnings'}
    leftover = [(l, v) for l, v in b if l.lower() not in mapped_labels]
    if leftover:
        notes.append('UNMAPPED BASICS FIELDS (from old file, not carried into the new Basics '
                      'grid -- fold these in manually wherever they fit, e.g. Intro/About/Notes):')
        for l, v in leftover:
            notes.append(f'  - {l}: {re.sub("<[^>]+>", "", v)}')

    fields = [
        ('Name', name), ('Idea', ideas), ('Prominence', prominence), ('Origin', origin),
        ('Gender', gender), ('Pronouns', pronouns), ('Species', species), ('Masterlist', masterlist),
        ('Previous Species', prev_species), ('Era of Birth', era), ('Themes', theme),
        ('Significant Dates', sig_dates),
    ]
    return '\n'.join(stat_box(l, v, i) for i, (l, v) in enumerate(fields)), name, pronouns

BLOCK_START_RE = re.compile(r'^\s*<(p|ul|ol|div)[\s>]')

def p_join(paras, empty_ok=True):
    if not paras:
        return f'<p>{TBD}</p>' if not empty_ok else ''
    # already-complete block elements (lists / sub-headers from doc drafts) aren't re-wrapped
    return '\n'.join(p if BLOCK_START_RE.match(p) else f'<p>{p}</p>' for p in paras)

def build_pronunciation(d):
    p = first(d['basics_raw'], 'Pronunciation')
    if not p:
        return f'{TBD} pronunciation'
    return re.sub(r'^\[|\]$', '', re.sub(r'<[^>]+>', '', p).strip())

def build_cw(d):
    cw = first(d['basics_raw'], 'CW', 'CWs', 'Content Warning', 'Content Warnings')
    if not cw:
        return ''
    return f'<p class="font-italic" style="color:{{ACCENT}}"><strong>CW:</strong> {cw}</p>\n'

def build_interpretation(d, notes):
    paras = d.get('idea_interpretation') or []
    if not paras:
        notes.append('No Idea Interpretation writeup found -- left as TBD.')
    return p_join(paras, empty_ok=False)

def build_intro_quote(d):
    """The old About-box tagline is repurposed as the in-character spoken quote,
    now living in the Intro block (per the e_auspice_a.html layout)."""
    quote = d['about_tagline']
    if quote:
        quote = re.sub(r'^"|"$', '', quote.strip())
    return quote if quote else f'{TBD} - add an in-character quote'

def build_intro(d):
    return build_cw(d) + p_join(d['intro_paragraphs'], empty_ok=False)

def build_about(d, name, notes):
    paras = d['about_paragraphs']
    if not paras:
        notes.append(f'No "{d["about_title_found"] or "About"}" section paragraphs found -- About box left as {TBD}.')
        paras = [TBD]
    return p_join(paras, empty_ok=False)

def build_playlist(d, notes):
    tracks = d['playlist_tracks']
    if not tracks:
        notes.append('No Playlist entries found -- Playlist box left with a single TBD row.')
        tracks = [{'title': TBD, 'href': '#', 'youtube_id': ''}]
    else:
        notes.append('Playlist rows carry over the title/link and the old template\'s hidden YouTube '
                      'play-button iframe where one was found. Album art and artist have no equivalent '
                      'in the old template -- add the art image src and artist line by hand for each track.')
    rows = []
    for t in tracks:
        title = t['title'] or TBD
        href = t['href'] or '#'
        youtube_id = t.get('youtube_id') or ''
        if youtube_id:
            iframe_src = f'https://www.youtube.com/embed/{youtube_id}?controls=0'
        else:
            iframe_src = ''
            notes.append(f'Playlist track "{title}" had no YouTube embed in the old file -- play '
                         f'button iframe left blank, add the video id by hand.')
        rows.append(f'''									<div class="col-12 p-0 row no-gutters mb-2">
										<div class="col-2 align-item-center">
											<img src="">
										</div>
										<div class="col-9 my-auto text-left px-2" style="display:block; line-height:120%">
											<div class="text-truncate"><a href="{href}" style="color:#FFF">{title}</a></div>
											<div class="text-truncate faded" style="font-size:10px; color:#FFF">{TBD}</div>
										</div>
										<div class="col-1 align-items-center" style="position:relative">
											<i class="fa-solid fa-play fa-fw" style="color:{{ACCENT}}"></i>
											<div class="d-flex justify-content-center align-items-center" style="position:absolute; top:0; right:0; bottom:0; left:0; opacity:.0001; overflow:hidden; z-index:10">
												<iframe src="{iframe_src}" frameborder="0" style="height:250%; min-height:250px; width:100%"></iframe>
											</div>
										</div>
									</div>''')
    return '\n'.join(rows)

DESIGN_PLACEHOLDER_FIELDS = ['Height', 'Voice', 'References']
DESIGN_DESCRIPTION_LABELS = {'text description', 'description', 'design description'}

def build_design(d, notes):
    # a "Text Description:" field reads better as a plain paragraph above the notes list
    description = [v for l, v in d['design_fields'] if l.lower() in DESIGN_DESCRIPTION_LABELS]
    fields = [(l, v) for l, v in d['design_fields'] if l.lower() not in DESIGN_DESCRIPTION_LABELS]
    description_html = '\n'.join(f'''									<p>{v}</p>''' for v in description)
    # no design fields in the source -> placeholder rows to fill in by hand
    if not fields:
        notes.append(f'No Design fields found -- placeholder {", ".join(DESIGN_PLACEHOLDER_FIELDS)} '
                     f'rows inserted as {TBD}.')
        fields = [(l, TBD) for l in DESIGN_PLACEHOLDER_FIELDS]
    field_rows = []
    for label, value in fields:
        label = label or TBD
        field_rows.append(f'''									<div class="col-12 mb-2 align-items-center">
										<span class="text-uppercase">{label}</span>
										<hr class="flex-fill mx-2 my-0" style="background-color:{{ACCENT}}">
										<span style="font-weight:400">{value}</span>
									</div>''')
    if not d['design_notes']:
        notes.append(f'No Design notes found -- design notes list left with a single {TBD} bullet.')
    notes_html = '\n'.join(
        f'''										<li class="mb-1"><span class="fa-li"><i class="fa-solid fa-chevron-right fa-xs" style="color:{{ACCENT}}"></i></span>{n}</li>'''
        for n in d['design_notes']
    ) or f'''										<li class="mb-1"><span class="fa-li"><i class="fa-solid fa-chevron-right fa-xs" style="color:{{ACCENT}}"></i></span>{TBD}</li>'''
    titles = ' / '.join(t.replace('Design', '').replace('-', '').strip() for t in d['design_titles'] if t.replace('Design', '').strip())
    return '\n'.join(field_rows), description_html, notes_html, titles

def build_ability_box(title, paras):
    body = p_join(paras, empty_ok=False)
    return f'''								<div class="col-12 p-0 mb-3 row no-gutters">
									<div class="col-12 p-3" style="border:solid 1px {{ACCENT}}">
										<div class="mb-2 text-uppercase" style="font-size:18px; font-weight:900"><i class="fa-sharp fa-solid fa-sparkle fa-fw" style="color:{{ACCENT}}"></i> {title}</div>
										<div class="col-12 p-0" style="font-weight:100; line-height:120%">
											<div class="col-12 p-0 my-2 row no-gutters" style="font-size:10px">
												<div class="px-1 mr-1" style="background-color:{{ACCENT}}">{TBD} tag</div>
											</div>
										</div>
										<div class="col-12 p-0" style="line-height:120%;">
{body}
										</div>
									</div>
								</div>'''

def build_abilities(d, name, notes):
    boxes = []
    if d['abilities']:
        for title, paras in d['abilities']:
            boxes.append(build_ability_box(title, paras))
    elif d['abilities_preamble']:
        boxes.append(build_ability_box(name, d['abilities_preamble']))
    else:
        notes.append('No Abilities/Magic/Powers section found in the old file -- Abilities box left as TBD.')
        boxes.append(build_ability_box(TBD, [TBD]))
    # doc drafts: paragraphs before the first ability (e.g. notes on pre-Actualization magic)
    intro = d.get('abilities_intro') or []
    if intro and d['abilities']:
        boxes.insert(0, f'''								<div class="col-12 p-0 mb-3">
{p_join(intro)}
								</div>''')
    return '\n'.join(boxes)

def build_abstraction(d):
    return p_join(d['abstraction_paragraphs'], empty_ok=False)

def build_story(d, notes):
    lead = p_join(d['story_lead'], empty_ok=False)
    if not d['story_lead'] and not d['story_eras'] and not d['story_more']:
        notes.append('No Story content found -- Story box left as TBD.')
        lead = f'<p>{TBD}</p>'
    elif not d['story_lead']:
        # everything was inside the old "Full Story" collapse; don't show a stray TBD above it
        lead = ''
    eras_html = ''
    if d['story_eras'] or d['story_more']:
        blocks = []
        # un-headed "Full Story" paragraphs (no era sub-headers) go first, flush left
        if d['story_more']:
            blocks.append(p_join(d['story_more']))
        for title, dates, paras in d['story_eras']:
            dates_line = f'''
										<span class="font-italic" style="color:{{ACCENT}}">{dates}</span>''' if dates else ''
            blocks.append(f'''							<div class="my-2">
								<div class="col-12 p-0 mt-3 mb-2">
									<p style="line-height:150%">
										<span class="text-uppercase" style="font-size:14px; font-weight:900; color:{{ACCENT}}">{title}</span><br>{dates_line}
									</p>
								</div>
								<div style="margin-left:25px">
{p_join(paras, empty_ok=False)}
								</div>
							</div>''')
        eras_html = f'''
						<div class="accordion p-0 mt-3" id="accordion">
							<a class="btn border-0 p-0" data-toggle="collapse" data-target="#storycollapse">
								<span class="font-italic" style="font-weight:100; color:{{ACCENT}}"> Read more... <i class="fa-regular fa-chevron-down fa-xs fa-fw"></i></span>
							</a>
						</div>
						<div class="collapse" id="storycollapse" data-parent="#accordion">
							<div class="my-2">
{chr(10).join(blocks)}
							</div>
						</div>'''
    timeline = d.get('story_timeline') or [f'{TBD} -- add a dated timeline here']
    timeline_html = '\n'.join(
        f'''                            <li class="mb-1"><span class="fa-li"><i class="fa-solid fa-chevron-right fa-xs" style="color:{{ACCENT}}"></i></span>{t}</li>'''
        for t in timeline)
    return f'''					<ul class="fa-ul">
{timeline_html}
                        </ul>

{lead}
{eras_html}'''

def build_extra_sections(d):
    """Doc-draft sections with no slot in the layout (e.g. "Followers"): one full-width box
    each, sub-headers styled like Story era titles, placed after Story."""
    boxes = []
    for title, lead, subs in d.get('extra_sections') or []:
        sub_html = '\n'.join(f'''						<div class="col-12 p-0 mt-3 mb-2">
							<p class="text-uppercase" style="font-size:14px; font-weight:900; color:{{ACCENT}}">{sub_title}</p>
						</div>
						<div style="margin-left:25px">
{p_join(paras)}
						</div>''' for sub_title, paras in subs)
        boxes.append(f'''
				<div class="col-12 p-3 mb-2 justify-content-center row no-gutters" style="border:solid 1px {{ACCENT}}">
					<div class="col-12 mb-3 align-items-center">
						<p class="text-uppercase" style="font-size:26px; font-weight:900; color:{{ACCENT}}">{title}</p>
						<hr class="flex-fill ml-2" style="background-color:#fff; margin-right:-10px">
						<i class="fa-sharp fa-solid fa-sparkle" style="font-size:30px"></i>
					</div>
					<div class="col-12" style="line-height:130%">
{p_join(lead)}
{sub_html}
					</div>
				</div>''')
    return '\n'.join(boxes)

def build_relation_entry(e, first_in_block=False):
    owner_line = ''
    if e['owner_name']:
        owner_line = f'<br>\n\t\t\t\t\t\t\t\t\t\t\t{e["owner_label"]} <a href="{e["owner_href"]}">{e["owner_name"]}</a>'
    more_html = ''
    if e.get('more'):
        # collapse ids must be unique per entry or one "read more" toggles another
        slug = unicodedata.normalize('NFKD', e['name']).encode('ascii', 'ignore').decode()
        collapse_id = 'collapse' + (re.sub(r'[^a-z0-9]', '', slug.lower()) or str(abs(hash(e['href']))))
        more_body = '\n'.join(
            f'<p>{m}</p>' if m is not None else f'<hr style="background-color:{{ACCENT}}">'
            for m in e['more']
        )
        more_html = f'''
									<div class="accordion p-0 mt-3" id="accordion">
										<a class="btn border-0 p-0" data-toggle="collapse" data-target="#{collapse_id}">
											<span class="font-italic" style="font-weight:100; color:{{ACCENT}}"> Read more... <i class="fa-regular fa-chevron-down fa-xs fa-fw"></i></span>
										</a>
									</div>
									<div class="collapse pt-3" id="{collapse_id}" data-parent="#accordion">
{more_body}
									</div>'''
    # entries are spaced by a top margin on all but the first, so the last one sits flush
    spacing = '' if first_in_block else ' mt-3'
    return f'''								<div class="col-12 p-0{spacing}">
									<img src="{e['img'] or ''}" style="height:100px; width:100px; object-fit:cover; object-position:center; border:1px solid {{ACCENT}};" class="float-left p-2 mr-3">
									<p class="text-uppercase" style="font-size:20px; font-weight:100; letter-spacing:0"><a href="{e['href']}">{e['name']}</a></p>
									<p class="font-italic text-uppercase" style="margin-top:-10px; font-size:12px">{e['relation'] or TBD}{owner_line}</p>
{p_join(e['paragraphs'], empty_ok=False)}{more_html}
								</div>'''

def build_relation_block(entries):
    return '\n'.join(build_relation_entry(e, first_in_block=(i == 0))
                     for i, e in enumerate(entries)) or f'<p>{TBD}</p>'

def build_relations(d, notes):
    internal = d['relations_internal']
    other = d['relations_other']
    if not internal and not other:
        notes.append('No Relations entries found.')
    return build_relation_block(internal), build_relation_block(other)

def build_fusions(d):
    return build_relation_block(d['fusions'])

def build_trivia(d):
    items = d['trivia'] or [TBD]
    return '\n'.join(
        f'''							<li class="mb-1"><span class="fa-li"><i class="fa-solid fa-chevron-right fa-xs" style="color:{{ACCENT}}"></i></span>{t}</li>'''
        for t in items
    )

def build_carousel(images_left, base_url, id_suffix):
    if not images_left:
        images_left = [{'url': '', 'href': base_url or '#'}]
    dots = '\n'.join(
        f'\t\t\t\t\t\t\t\t<li data-target="#carousel-{id_suffix}" data-slide-to="{i}" class="{"active" if i==0 else ""}" style="background-color:{{ACCENT}}"></li>'
        for i in range(len(images_left))
    )
    slides = []
    for i, img in enumerate(images_left):
        label = 'Main' if i == 0 else f'Alt {i}'
        active = ' active' if i == 0 else ''
        href = img.get('href') or base_url or '#'
        slides.append(f'''									<div class="carousel-item{active} h-100" style="min-height:300px">
										<div style="height:100%; min-height:300px; background-image:url({img['url']}); background-size:contain; background-repeat:no-repeat; background-position:center; position:relative">
											<div class="col-12 text-center row no-gutters justify-content-center" style="position:absolute; bottom:35px">
												<div class="col-12" style="text-shadow:0 0 25px {{ACCENT}},0 0 15px {{ACCENT}}, 0 0 5px {{ACCENT}}">
													<a href="{href}" class="tooltipster" title="view full image in gallery"><i class="fa-solid fa-image fa-fw"></i></a>
													<a href="https://toyhou.se/Auspice" class="tooltipster" title="design by Auspice"><i class="fa-solid fa-palette fa-fw"></i></a>
													<a href="https://toyhou.se/Auspice" class="tooltipster" title="art by Auspice"><i class="fa-solid fa-paintbrush fa-fw"></i></a>
												</div>
												<p class="text-uppercase" style="font-size:20px; font-weight:900; text-shadow:0 0 25px {{ACCENT}},0 0 15px {{ACCENT}}, 0 0 5px {{ACCENT}}">{label}</p>
											</div>
										</div>
									</div>''')
    return dots, '\n'.join(slides)

VOID_TAGS = {'area', 'base', 'br', 'col', 'embed', 'hr', 'img', 'input', 'link', 'meta',
             'source', 'track', 'wbr'}
# opening one of these implicitly closes an open <p>, as browsers do
CLOSES_P = {'address', 'article', 'aside', 'blockquote', 'div', 'dl', 'fieldset', 'figure',
            'footer', 'form', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'header', 'hr', 'ol', 'p',
            'pre', 'section', 'table', 'ul'}
TAG_RE = re.compile(r'<(/?)([a-zA-Z][\w-]*)')

def reindent(html):
    """Re-indent every line with tabs to match tag nesting depth. Only leading whitespace
    changes -- lines are never split or joined, so long paragraphs stay on one line.
    Comment bodies are left exactly as written; a line continuing a tag that started on an
    earlier line (or text continuing a paragraph) is indented one level deeper."""
    stack = []
    in_comment = False
    out = []
    for line in html.split('\n'):
        if in_comment:
            out.append(line)
            if '-->' in line:
                in_comment = False
            continue
        text = line.strip()
        if not text:
            out.append('')
            continue
        indent = None
        i = 0
        while i < len(text):
            if text.startswith('<!--', i):
                if indent is None:
                    indent = len(stack)
                end = text.find('-->', i + 4)
                if end == -1:
                    in_comment = True
                    break
                i = end + 3
                continue
            m = TAG_RE.match(text, i)
            if not m:
                if indent is None and not text[i].isspace():
                    indent = len(stack)
                i += 1
                continue
            closing, name = m.group(1) == '/', m.group(2).lower()
            # find the tag's end, skipping any '>' inside quoted attribute values
            j, quote = m.end(), None
            while j < len(text) and (quote or text[j] != '>'):
                if text[j] in '"\'':
                    quote = None if quote == text[j] else (quote or text[j])
                j += 1
            self_closing = text[j - 1:j] == '/'
            if closing:
                if name in stack:
                    while stack.pop() != name:
                        pass
            else:
                if stack and ((stack[-1] == 'p' and name in CLOSES_P) or (stack[-1] == 'li' and name == 'li')):
                    stack.pop()
                if indent is None:
                    indent = len(stack)
                if name not in VOID_TAGS and not self_closing:
                    stack.append(name)
            i = j + 1
        if indent is None:
            indent = len(stack)
        out.append('\t' * indent + text)
    return '\n'.join(out)

TEMPLATE = '''<!----

{conversion_notes}

---->

<div class="col-12 p-0 row no-gutters justify-content-center">

	
	<div class="col-12 pt-2 justify-content-center row no-gutters" style="font-size: 13px; letter-spacing: 1px; text-transform: uppercase; text-decoration: none;background-color:#000;">
		<a href="{base_url}/gallery" class="quicklink" style="margin-right: 12px;">Gallery</a>
		<a href="{base_url}/literatures" class="quicklink" style="margin-right: 12px;">Library</a>
		<a href="{base_url}/links" class="quicklink" style="margin-right: 12px;">Links</a>
		<a href="{base_url}/worlds" class="quicklink" style="margin-right: 12px;">Worlds</a>
		<a href="{base_url}/comments" class="quicklink" style="margin-right: 12px;">Comments</a>
	</div>

	<div class="col-12 p-0 row no-gutters justify-content-center" style="position:relative">
		<div class="col-12 pb-4 justify-content-center row no-gutters" style="background-color:#000; color:#fff; font-family:helvetica; position:relative">
            <div class="col-md-12 mb-3" >
                <div class="h-100" style="background-color: rgba(1,1,1,.90); margin-top:10px">
                    <div style="background-image: url('{header_image}');
                    background-size: cover; background-position: center; min-height: 300px;" class="h-100"><a href="{base_url}/gallery" class="link-tag" style="position: absolute; top: 0; right: 0; bottom: 0; left: 0; width: 100%; height: 100%;"></a></div>
                </div>
            </div>
			<div class="col-12" style="position:absolute; top:0px; left:0; background:linear-gradient(180deg,#000 10%, rgba(0, 0, 0, 0) 75%); height:100px"></div>
			<div class="col-12" style="position:absolute; top:120px; left:0; background:linear-gradient(0deg,#000 25%, rgba(0, 0, 0, 0) 75%); height:200px"></div>
			<div class="col-12 justify-content-center row no-gutters px-lg-5 px-4" style="z-index:10">
				<div class="col-12 p-0 mb-2 justify-content-center row no-gutters">
					<div class="col-lg-4 col-12 col-md-8 text-center" style="background-color:#000; border-radius:250px 250px 0 0; border-top: solid 2px {{ACCENT}}; padding-top:70px; padding-bottom:50px; margin-top:-230px">
						<div class="text-uppercase" style="font-size:32px; font-weight:900; text-shadow:0 0 25px {{ACCENT}},0 0 15px {{ACCENT}}, 0 0 5px {{ACCENT}}">{name}</div>
						<div style="line-height:100%">
							<p><span style="color:{{ACCENT}}">[{pronunciation}]</span></p>
							<i class="fa-sharp fa-solid fa-sparkle mb-3" style="font-size:50px"></i>
							<p>{pronouns}</p>
						</div>
					</div>
				</div>

				<div class="col-12 p-3 mb-2 justify-content-center row no-gutters" style="border:solid 1px {{ACCENT}}">
					<div class="col-12 mb-3 align-items-center">
						<i class="fa-sharp fa-solid fa-sparkle" style="font-size:30px"></i>
						<hr class="flex-fill mr-2" style="background-color:#fff; margin-left:-10px">
						<p class="text-uppercase" style="font-size:26px; font-weight:900; color:{{ACCENT}}">Intro</p>
					</div>
					<div class="col-12 justify-content-center" style="line-height:130%">
						<div class="col-lg-11 col-12 text-center">
{intro}
						</div>
					</div>
				</div>

				<div class="col-12 p-0 pt-3 mb-2 justify-content-center row no-gutters" style="margin-top:-10px">
					<div class="col-lg-5 mb-lg-0 mb-2" style="background-image:url({focal_image}); background-size:cover; background-position:center; min-height:400px; border: solid 1px {{ACCENT}}; position:relative">
						<div style="position:absolute; bottom:10px; left:10px">
							<a href="https://toyhou.se/Auspice" class="tooltipster" title="design by Auspice"><i class="fa-solid fa-palette fa-fw"></i></a>
							<a href="https://toyhou.se/Auspice" class="tooltipster" title="focal art by Auspice"><i class="fa-solid fa-paintbrush fa-fw"></i></a>
						</div>
					</div>

					<div class="col-lg-7 pl-lg-2 p-0">
						<div class="col-12 p-3 h-100" style="background: linear-gradient(0deg,#41546d 10%, #1d2635 90%); border:solid 1px {{ACCENT}}">
							<div class="col-12 p-0 row no-gutters">
								<div class="col-12 mb-3 align-items-center">
									<p class="text-uppercase" style="font-size:26px; font-weight:900; color:{{ACCENT}}">Basics</p>
									<hr class="flex-fill ml-2" style="background-color:#fff; margin-right:-10px">
									<i class="fa-sharp fa-solid fa-sparkle" style="font-size:30px"></i>
								</div>
								<div class="col-12" style="line-height:130%">
									<div class="col-12 px-1 row no-gutters" style="font-size:12px">
{basics}
									</div>
								</div>
							</div>
						</div>
					</div>
				</div>
				<div class="col-12 p-0 mb-2 justify-content-center row no-gutters">
					<div class="col-12 text-center px-lg-4 px-3 py-4" style="position:relative">
						<div class="text-uppercase" style="font-size:24px; font-weight:900; text-shadow:0 0 25px {{ACCENT}},0 0 15px {{ACCENT}}, 0 0 5px {{ACCENT}}">Idea Interpretation</div>
						<div style="line-height:120%;">
							<p class="font-italic" style="color:{{ACCENT}}">{ideas}</p>
							<i class="fa-sharp fa-solid fa-sparkle mb-3" style="font-size:40px"></i>
							<p></p>
							<div class="p-0" style="text-align:left">
{interpretation}
							</div>
						</div>
						<div style="position:absolute; top:0; left:0; border-top:solid 1px {{ACCENT}}; border-left:solid 1px {{ACCENT}}; height:70px; width:70px"></div>
						<div style="position:absolute; bottom:0; right:0; border-bottom:solid 1px {{ACCENT}}; border-right:solid 1px {{ACCENT}}; height:70px; width:70px"></div>
					</div>
				</div>
				<div class="col-12 p-0 mb-2 justify-content-center row no-gutters">

					<div class="col-lg-8 mb-lg-0 mb-2">
						<div class="col-12 p-3 h-100" style="border:solid 1px {{ACCENT}}">
							<div class="col-12 p-0 row no-gutters">
								<div class="col-12 mb-3 align-items-center">
									<p class="text-uppercase" style="font-size:26px; font-weight:900; color:{{ACCENT}}">About</p>
									<hr class="flex-fill ml-2" style="background-color:#fff; margin-right:-10px">
									<i class="fa-sharp fa-solid fa-sparkle" style="font-size:30px"></i>
								</div>
                                <div class="col-12 p-0 mb-4">
									<i class="fa-duotone fa-solid fa-quote-left" style="color:{{ACCENT}}; font-size:50px; margin-top:-10px"></i>
									<p class="font-italic" style="margin-left:30px; margin-top:-30px">{intro_quote}</p>
								</div>
								<div class="col-12" style="line-height:130%">
{about_paragraphs}
								</div>
							</div>
						</div>
					</div>

					<div class="col-lg-4 pl-lg-2 p-0">
						<div class="col-12 p-3 h-100" style="background: linear-gradient(0deg,#41546d 10%, #1d2635 90%); border:solid 1px {{ACCENT}}">
							<div class="col-12 p-0 row no-gutters">
								<div class="col-12 mb-3 align-items-center">
									<i class="fa-sharp fa-solid fa-sparkle" style="font-size:30px"></i>
									<hr class="flex-fill mr-2" style="background-color:#fff; margin-left:-10px">
									<p class="text-uppercase" style="font-size:26px; font-weight:900; color:{{ACCENT}}">Playlist</p>
								</div>
								<div class="col-12" style="line-height:130%">
{playlist}
								</div>
							</div>
						</div>
					</div>
				</div>

				<div class="col-12 p-0 mb-2 justify-content-center row no-gutters">
					<div class="col-lg-6 col-12 pr-lg-1 mb-lg-0 mb-2">
						<div class="col-12 p-3 h-100" style="background: linear-gradient(0deg,#41546d 10%, #1d2635 90%); border:solid 1px {{ACCENT}}">
							<div class="col-12 p-0 row no-gutters">
								<div class="col-12 mb-3 align-items-center">
									<p class="text-uppercase" style="font-size:26px; font-weight:900; color:{{ACCENT}}">Design{design_subtitle}</p>
									<hr class="flex-fill ml-2" style="background-color:#fff; margin-right:-10px">
									<i class="fa-sharp fa-solid fa-sparkle" style="font-size:30px"></i>
								</div>
								<div class="col-12 mb-3 p-0 row no-gutters">
{design_fields}
								</div>
								<div class="col-12" style="line-height:130%">
{design_description}
									<ul class="fa-ul mb-0" style="margin-left:20px">
{design_notes}
									</ul>
								</div>
							</div>
						</div>
					</div>

					<div class="col-lg-6 col-12 pl-lg-1">
						<div class="col-12 p-0 h-100" style="border:solid 1px {{ACCENT}}; min-height:300px">
							<ol class="carousel-indicators">
{carousel_dots}
							</ol>
							<div class="carousel slide h-100" data-interval="false" id="carousel-forms" style="min-height:300px">
								<div class="carousel-inner h-100" style="min-height:300px">
{carousel_slides}
								</div>
							</div>
							<a class="carousel-control-prev" href="#carousel-forms" role="button" data-slide="prev">
								<i class="fa-solid fa-chevron-left fa-fw"></i>
							</a>
							<a class="carousel-control-next" href="#carousel-forms" role="button" data-slide="next">
								<i class="fa-solid fa-chevron-right fa-fw"></i>
							</a>
						</div>
					</div>
				</div>
                
                <div class="col-12 p-0 mb-2 justify-content-center row no-gutters">

					<div class="col-lg-4 mb-lg-0 mb-2" style="background-image:url(); background-size:cover; background-position:center; min-height:400px; border: solid 1px {{ACCENT}}; position:relative">
						<div style="position:absolute; bottom:10px; left:10px">
							<a href="https://toyhou.se/Auspice" class="tooltipster" title="art by Auspice"><i class="fa-solid fa-paintbrush fa-fw"></i></a>
						</div>
					</div>

					<div class="col-lg-8 pl-lg-2 p-0">
						<div class="col-12 p-3 justify-content-center row no-gutters" style="border:solid 1px {{ACCENT}}">
							<div class="col-12 mb-3 align-items-center">
								<i class="fa-sharp fa-solid fa-sparkle" style="font-size:30px"></i>
								<hr class="flex-fill mr-2" style="background-color:#fff; margin-left:-10px">
								<p class="text-uppercase" style="font-size:26px; font-weight:900; color:{{ACCENT}}">Abilities</p>
							</div>
							<div class="col-12 pb-1" style="line-height:130%">

								<div class="col-12 p-0 mb-3 row no-gutters">
									<div class="mr-2 text-uppercase" style="font-weight:900; font-size:22px; color:{{ACCENT}}">General Edeia Abilities</div>
								</div>
								<div class="col-12 p-0 mb-3">
									<p>{name} is capable of the <a href="https://www.edeia-ideation.com/lore-guide/edeiology">general Edeia abilities</a>, including shapeshifting, intangibility, invisibility, their ability to use their Abstraction for teleportation and dimension crossing, energy manipulation, soul manipulation, etc.&nbsp;</p>

								</div>

								<!---- MAIN ABILITY - name + tags, tags hidden here (see below) ---->

								<div class="col-12 p-0 mb-3 row no-gutters">
									<div class="mr-2 text-uppercase" style="font-weight:900; font-size:22px; color:{{ACCENT}}">Idea Magic</div>
								</div>

{abilities}

							
							</div>
						</div>
					</div>


				</div>

				<div class="col-12 p-0 mb-2 justify-content-center row no-gutters">
					<div class="col-lg-7 mb-lg-0 pr-lg-2 mb-2">
						<div class="col-12 p-3 h-100" style="background: linear-gradient(0deg,#41546d 10%, #1d2635 90%); border:solid 1px {{ACCENT}}">
							<div class="col-12 p-0 row no-gutters">
								<div class="col-12 mb-3 align-items-center">
									<p class="text-uppercase" style="font-size:26px; font-weight:900; color:{{ACCENT}}">Abstraction</p>
									<hr class="flex-fill ml-2" style="background-color:#fff; margin-right:-10px">
									<i class="fa-sharp fa-solid fa-sparkle" style="font-size:30px"></i>
								</div>
								<div class="col-12" style="line-height:130%">
									{abstraction}
								</div>
							</div>
						</div>
					</div>
					<div class="col-lg-5 p-0" style="background-image:url({abstraction_image}); background-size:cover; background-position:center; min-height:300px; border: solid 1px {{ACCENT}}; position:relative">
						<div style="position:absolute; bottom:10px; left:10px">
							<a href="https://toyhou.se/Auspice" class="tooltipster" title="art by Auspice"><i class="fa-solid fa-paintbrush fa-fw"></i></a>
						</div>
					</div>
				</div>

				<div class="col-12 p-3 mb-2 justify-content-center row no-gutters" style="border:solid 1px {{ACCENT}}">
					<div class="col-12 mb-3 align-items-center">
						<p class="text-uppercase" style="font-size:26px; font-weight:900; color:{{ACCENT}}">Story</p>
						<hr class="flex-fill ml-2" style="background-color:#fff; margin-right:-10px">
						<i class="fa-sharp fa-solid fa-sparkle" style="font-size:30px"></i>
					</div>
					<div class="col-12" style="line-height:130%">
{story}
					</div>
				</div>
{extra_sections}

				<div class="col-12 p-0 mb-2 justify-content-center row no-gutters" style="position:relative">
					<div class="col-lg-1 col-12 mb-lg-0 mb-2 pr-lg-2 p-0">
						<div class="col-12 p-0 justify-content-center" style="position:sticky; top:calc(50vh - 107px)">
							<ul class="nav row no-gutters">
								<li class="nav-item my-4 mx-lg-0 mx-2">
									<a class="nav-link active text-center" style="color: {{ACCENT}}; transform:rotate(45deg)" data-toggle="tab" href="#internal">
										<span class="card" style="border:solid 1px {{ACCENT}}; border-radius:0">
											<span style="height:75px; width:75px; background-color:#000">
												<span class="justify-content-center align-items-center" style="height:100%">
													<i class="fa-light fa-hand-holding-hand fa-fw" style="transform:rotate(-45deg); font-size:20px"></i>
												</span>
											</span>
										</span>
									</a>
								</li>
								<li class="nav-item my-4 mx-lg-0 mx-2">
									<a class="nav-link text-center" style="color: {{ACCENT}}; transform:rotate(45deg)" data-toggle="tab" href="#other">
										<span class="card" style="border:solid 1px {{ACCENT}}; border-radius:0">
											<span style="height:75px; width:75px; background-color:#000">
												<span class="justify-content-center align-items-center" style="height:100%">
													<i class="fa-light fa-handshake-angle fa-fw" style="transform:rotate(-45deg); font-size:20px"></i>
												</span>
											</span>
										</span>
									</a>
								</li>
							</ul>
						</div>
					</div>
					<div class="col-lg-11 col-12 pl-lg-4" style="position:relative">
						<div class="col-12 p-3 h-100" style="background: linear-gradient(0deg,#41546d 10%, #1d2635 90%); border:solid 1px {{ACCENT}}">
							<div class="col-12 p-0 row no-gutters">
								<div class="col-12 mb-3 align-items-center">
									<i class="fa-sharp fa-solid fa-sparkle" style="font-size:30px"></i>
									<hr class="flex-fill mr-2" style="background-color:#fff; margin-left:-10px">
									<p class="text-uppercase" style="font-size:26px; font-weight:900; color:{{ACCENT}}">Relations</p>
								</div>
								<div class="col-12" style="line-height:130%">
									<div class="tab-content">
										<div class="tab-pane fade active show" id="internal">
											<div class="col-12 p-0 text-right mb-3" style="margin-top:-20px; font-size:14px">
												<p class="text-uppercase">Internal Relations</p>
											</div>
{relations_internal}
										</div>
										<div class="tab-pane fade" id="other">
											<div class="col-12 p-0 text-right mb-3" style="margin-top:-20px; font-size:14px">
												<p class="text-uppercase">Relations with Others</p>
											</div>
{relations_other}
										</div>
									</div>
								</div>
							</div>
						</div>
					</div>
				</div>
{fusions_block}

                
                <div class="col-12 p-0 mb-2 justify-content-center row no-gutters">
					<div class="col-lg-4 mb-lg-0 mb-2" style="background-image:url(); background-size:cover; background-position:center; min-height:350px; border: solid 1px {{ACCENT}}; position:relative">
						<div style="position:absolute; bottom:10px; left:10px">
							<a href="https://toyhou.se/Auspice" class="tooltipster" title="art by Auspice"><i class="fa-solid fa-paintbrush fa-fw"></i></a>
						</div>
					</div>

					<div class="col-lg-5 mb-lg-0 px-lg-2 mb-2">
						<div class="col-12 p-3 h-100" style="border:solid 1px {{ACCENT}}">
							<div class="col-12 p-0 row no-gutters">
								<div class="col-12 mb-3 align-items-center">
									<p class="text-uppercase" style="font-size:26px; font-weight:900; color:{{ACCENT}}">Notes</p>
									<hr class="flex-fill ml-2" style="background-color:#fff; margin-right:-10px">
									<i class="fa-sharp fa-solid fa-sparkle" style="font-size:30px"></i>
								</div>
								<div class="col-12 mb-2 px-0" style="line-height:130%">
									<ul class="fa-ul mb-0" style="margin-left:20px">
{trivia}
									</ul>
								</div>
							</div>
						</div>
					</div>

					<div class="col-lg-3 p-0" style="background-image:url(); background-size:contain; background-position:center; background-repeat: no-repeat; min-height:350px; border: solid 1px {{ACCENT}}; position:relative">
						<div style="position:absolute; bottom:10px; left:10px">
							<a href="https://toyhou.se/Auspice" class="tooltipster" title="art by Auspice"><i class="fa-solid fa-paintbrush fa-fw"></i></a>
						</div>
					</div>
				</div>

				<div class="col-12 my-3 justify-content-center row no-gutters">
					<p class="faded text-uppercase" style="font-size:10px; letter-spacing:0.5px"> <a href="https://toyhou.se/40210928.g17-actualized-f2u-c">Code</a> by <a href="https://toyhou.se/inkracht" class="tooltipster" title="rustbqr / inkracht"><i class="fa-regular fa-bowl-chopsticks-noodles fa-fw"></i></a> layout by <a href="https://toyhou.se/Auspice" class="tooltipster" title="Auspice"><i class="fa-regular fa-table-layout fa-fw"></i></a>
					</p>
				</div>
			</div>
		</div>
	</div>
</div>
'''

FUSIONS_BLOCK = '''
				<div class="col-12 p-0 mb-2 justify-content-center row no-gutters">
					<div class="col-lg-6 col-12 pr-lg-1 mb-lg-0 mb-2">
						<div class="col-12 p-3 h-100" style="background: linear-gradient(0deg,#41546d 10%, #1d2635 90%); border:solid 1px {{ACCENT}}">
							<div class="col-12 p-0 row no-gutters">
								<div class="col-12 mb-3 align-items-center">
									<p class="text-uppercase" style="font-size:26px; font-weight:900; color:{{ACCENT}}">Fusions</p>
									<hr class="flex-fill ml-2" style="background-color:#fff; margin-right:-10px">
									<i class="fa-sharp fa-solid fa-sparkle" style="font-size:30px"></i>
								</div>
								<div class="col-12" style="line-height:130%">
{fusions}
								</div>
							</div>
						</div>
					</div>
					<div class="col-lg-6 col-12 pl-lg-1">
						<div class="col-12 p-0 h-100" style="border:solid 1px {{ACCENT}}; min-height:300px">
							<ol class="carousel-indicators">
{fusion_carousel_dots}
							</ol>
							<div class="carousel slide h-100" data-interval="false" id="carousel-fusions" style="min-height:300px">
								<div class="carousel-inner h-100" style="min-height:300px">
{fusion_carousel_slides}
								</div>
							</div>
							<a class="carousel-control-prev" href="#carousel-fusions" role="button" data-slide="prev">
								<i class="fa-solid fa-chevron-left fa-fw"></i>
							</a>
							<a class="carousel-control-next" href="#carousel-fusions" role="button" data-slide="next">
								<i class="fa-solid fa-chevron-right fa-fw"></i>
							</a>
						</div>
					</div>
				</div>
'''

def render(path, owner=''):
    """owner: your toyhou.se username -- relations to your own characters then get no
    "Owner:" credit line (drafts only; an "Owner:" field in the draft does the same)."""
    notes = []
    raw = Path(path).read_text(encoding='utf-8')
    if is_basic_draft(raw):
        d = extract_basic(path, owner)
        notes.append('Read as a DOC DRAFT (extract_basic.py).')
        notes.extend(d['extract_notes'])
        if d['accent'] == '#6286c4':
            notes.append('No "Accent:" field in the draft -- default accent #6286c4 used.')
    else:
        d = extract(path)
    accent = d['accent']
    base_url = d['base_url'] or f'{TBD}-base-url'

    basics_html, name, pronouns = build_basics(d, notes)
    intro_html = build_intro(d)
    intro_quote = build_intro_quote(d)
    ideas = first(d['basics_raw'], 'Ideas', 'Idea') or TBD
    about_paras = build_about(d, name, notes)
    playlist_html = build_playlist(d, notes)
    design_fields_html, design_description_html, design_notes_html, design_subtitle_extra = build_design(d, notes)
    design_subtitle = f' - {design_subtitle_extra}' if design_subtitle_extra else ''
    abilities_html = build_abilities(d, name, notes)
    abstraction_html = build_abstraction(d)
    story_html = build_story(d, notes)
    relations_internal_html, relations_other_html = build_relations(d, notes)

    images = d['images']
    focal_image = images[0]['url'] if images else ''
    header_image = images[1]['url'] if len(images) > 1 else focal_image
    abstraction_image = images[2]['url'] if len(images) > 2 else focal_image
    leftover_images = images[3:] if len(images) > 3 else []
    if leftover_images:
        notes.append(f'{len(leftover_images)} additional image(s) found beyond focal/header/abstraction '
                      f'-- dumped into the alt-forms carousel as placeholder slides; relabel/reorder manually.')
    else:
        notes.append('No extra images found for the alt-forms carousel -- placeholder slide inserted, add real ones manually.')
    carousel_dots, carousel_slides = build_carousel(leftover_images, base_url, 'forms')

    if not images:
        notes.append('NO IMAGES were found in the source file at all -- header/focal/abstraction '
                      'image URLs are all blank. Fill in manually.')

    if not d['fusions']:
        notes.append(f'No Fusions section found in the old file -- Fusions block left as {TBD} (fill in or delete by hand).')
    fusion_carousel_dots, fusion_carousel_slides = build_carousel([], base_url, 'fusions')
    notes.append('No image data exists for fusion-specific alt forms -- the Fusions carousel is a '
                  'single TBD placeholder slide; add real images manually.')
    fusions_block = FUSIONS_BLOCK.format(
        fusions=build_fusions(d), fusion_carousel_dots=fusion_carousel_dots,
        fusion_carousel_slides=fusion_carousel_slides,
    )

    trivia_html = build_trivia(d)

    if not base_url:
        notes.append('Could not determine the toyhou.se base URL (no "/gallery#" links found) -- quicklinks are placeholders.')

    notes.append(f'Source file: {d["source_file"]}')
    notes.append(f'Accent colour carried over from old file: {accent}')
    by_hand = ['name-badge icon', 'all "design by / art by" image credits']
    if not first(d['basics_raw'], 'Pronunciation'):
        by_hand.insert(0, 'Pronunciation')
    if not d.get('idea_interpretation'):
        by_hand.append('the Idea Interpretation writeup')
    if not d.get('story_timeline'):
        by_hand.append('the Story timeline bullets')
    notes.append(f'Not in the source file, left as TBD / defaults -- fill in by hand: {", ".join(by_hand)}.')

    conversion_notes = '\n'.join(notes)

    html = TEMPLATE.format(
        conversion_notes=conversion_notes,
        base_url=base_url,
        header_image=header_image,
        name=name,
        pronouns=pronouns,
        pronunciation=build_pronunciation(d),
        interpretation=build_interpretation(d, notes),
        extra_sections=build_extra_sections(d),
        TBD=TBD,
        intro=intro_html,
        intro_quote=intro_quote,
        focal_image=focal_image,
        basics=basics_html,
        ideas=ideas,
        about_paragraphs=about_paras,
        playlist=playlist_html,
        design_subtitle=design_subtitle,
        design_fields=design_fields_html,
        design_description=design_description_html,
        design_notes=design_notes_html,
        carousel_dots=carousel_dots,
        carousel_slides=carousel_slides,
        abilities=abilities_html,
        abstraction=abstraction_html,
        abstraction_image=abstraction_image,
        story=story_html,
        relations_internal=relations_internal_html,
        relations_other=relations_other_html,
        fusions_block=fusions_block,
        trivia=trivia_html,
    )
    html = html.replace('{ACCENT}', accent)
    return reindent(html)

if __name__ == '__main__':
    import sys

    args = sys.argv[1:]
    force = '--force' in args
    owner = 'Auspice'  # local runs are your own drafts; the website asks for a username instead
    if '--owner' in args:
        i = args.index('--owner')
        owner = args[i + 1] if i + 1 < len(args) else ''
        del args[i:i + 2]
    args = [a for a in args if a != '--force']
    if len(args) != 1:
        sys.exit('Usage: python _a_convert_scripts\\render.py <old_profile.html> [--force] [--owner NAME]')

    src = Path(args[0])
    out_dir = Path(__file__).resolve().parent / 'converted'
    stem = re.sub(r'_basic$', '', src.stem)
    out_path = out_dir / f'{stem}_new.html'
    if out_path.exists() and not force:
        sys.exit(f'{out_path} already exists -- not overwriting (it may have hand edits). '
                 f'Add --force to replace it.')

    html = render(src, owner)
    out_dir.mkdir(exist_ok=True)
    out_path.write_text(html, encoding='utf-8')
    print(f'Wrote {out_path}')
