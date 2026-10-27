# Edeia Profile Converter

Turns a Google Docs character draft into Edeia Toyhouse profile code.

Site, profile layout and profile code edits by [Auspice](https://toyhou.se/Auspice); original profile code by [rustbqr / inkracht](https://toyhou.se/inkracht).

**Use it here:** https://Ausp-ice.github.io/edeia-profile-converter/

Paste or upload your draft's HTML, press Convert, and copy the result. The page includes a guide to formatting your draft. Everything runs in your browser using [Pyodide](https://pyodide.org), so your draft is never uploaded anywhere.

## Character list

`converter/characters.csv` fills in relation and fusion entries automatically. Each row has a character's name, toyhou.se link, image link and owner's toyhou.se username. To have a character added, open an issue with those four things.

## Maintaining

The files in `converter/` are copies. Edit the originals in `Edeia/_a_convert_scripts/`, then run:

```
python _a_convert_scripts\build_site.py
```

That command copies the scripts and `characters.csv` here. Add `--add-new` to also add rows for new profiles in the Edeia folder. Commit and push the result; GitHub Pages updates within a minute or two.

To preview locally, run `python -m http.server` in this folder and open http://localhost:8000. Opening `index.html` directly doesn't work, because browsers block it from loading the converter files.
