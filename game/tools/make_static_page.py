"""Assemble the server-free demo page from game/client/dist (run after `npm run build`).

Writes game/client/artifact/index.html (page content without html/head/body wrappers, CSS inlined)
and artifact/files.json (published path -> source path under game/client).
"""
import glob, json, os, re
from pathlib import Path

C = Path(__file__).resolve().parents[1] / "client"
d = C / "dist"
html = (d / "index.html").read_text()
css_file = re.search(r'href="\./(assets/[^"]+\.css)"', html).group(1)
js_file = re.search(r'src="\./(assets/[^"]+\.js)"', html).group(1)
css = re.sub(r'url\((["\']?)(?:\.\./|\./|/)?assets/', r'url(\1assets/', (d / css_file).read_text())
body = re.sub(r'<script type="module"[^>]*></script>', '', html[html.index("<body>") + 6: html.index("</body>")])
page = f"""<title>Goated Ground &amp; Pound</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Barlow:wght@500;700&family=Kanit:ital,wght@1,800&display=swap" rel="stylesheet">
<style>
/* layout: one fixed 1280x720 game stage scaled to fit the window; a single dark arena look by design */
:root {{ --ground: #0e0d15; --ink: #ffffff; --steel: #9ea5b1; --blood: #ff3b4e; --crimson: #7d0c1b; --display: 'Kanit', 'Arial Black', sans-serif; --body: 'Barlow', system-ui, sans-serif; color-scheme: dark; }}
html, body {{ height: 100%; }}
{css}
</style>
{body.strip()}
<script type="module" src="./{js_file}"></script>
"""
(C / "artifact").mkdir(exist_ok=True)
(C / "artifact" / "index.html").write_text(page)
files = {}
for p in sorted(glob.glob(str(d / "**" / "*"), recursive=True)):
    rel = os.path.relpath(p, d)
    if os.path.isdir(p) or rel == "index.html" or rel.endswith(".css") or rel.startswith("golden"):
        continue
    files[rel] = f"dist/{rel}"
(C / "artifact" / "files.json").write_text(json.dumps(files))
print(json.dumps(files))
print(len(files), "files,", round(sum((d / k).stat().st_size for k in files) / 1e6, 1), "MB; css urls:", sorted(set(re.findall(r'url\(([^)]+)\)', css)))[:4], "...")
