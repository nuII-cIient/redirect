import re
import base64
import pathlib

SRC = pathlib.Path("/root/novene/public")
OUT = pathlib.Path("/root/novene-singlefile")
HOST = "https://frostedbrowser.cfd"

def read(p):
    return (SRC / p).read_text()

def js_safe(s):
    return s.replace("</script", "<\\/script")

html = read("index.html")

html = re.sub(r'<script>\(function\(s\)\{s\.dataset\.zone.*?</script>\n?', '', html, count=1, flags=re.S)
html = re.sub(r'<script async src="https://www\.googletagmanager\.com[^>]*></script>\n?', '', html, count=1)
html = re.sub(r'<script>\n\s*window\.dataLayer.*?</script>\n?', '', html, count=1, flags=re.S)
assert "al5sm.com" not in html and "googletagmanager" not in html and "dataLayer" not in html

css = read("c/main.css")
html = re.sub(
    r'<link rel="stylesheet" href="/c/main\.css[^"]*">',
    "<style>\n" + css + "\n</style>",
    html,
    count=1,
)

for name in ["lucide.js", "lumi.js", "core.js", "tabs.js", "ai.js", "launch.js", "settings.js", "boot.js"]:
    code = read(f"js/{name}")
    if name == "boot.js":
        code = code.replace('"wss://" + location.host + "/wisp/"', '"wss://frostedbrowser.cfd/wisp/"')
    if name == "ai.js":
        code = code.replace('fetch("/api/ai"', f'fetch("{HOST}/api/ai"')
    tag = re.compile(r'<script src="/js/' + re.escape(name.split(".")[0]) + r'\.js[^"]*"></script>')
    assert tag.search(html), name
    block = "<script>\n" + js_safe(code) + "\n</script>"
    html = tag.sub(lambda _: block, html, count=1)

for sail, pattern in [
    ("sail/scram/scramjet.js", r'<script src="/sail/scram/scramjet\.js"></script>'),
    ("sail/scram/controller.api.js", r'<script src="/sail/scram/controller\.api\.js"></script>'),
]:
    code = js_safe(read(sail))
    tag = re.compile(pattern)
    assert tag.search(html), sail
    block = "<script>\n" + js_safe(code) + "\n</script>"
    html = tag.sub(lambda _: block, html, count=1)

html = html.replace(
    'navigator.serviceWorker.register("/sw.js")',
    'navigator.serviceWorker.register("sw.js")',
)

assert 'src="/js/' not in html
assert 'location.host + "/wisp/"' not in html
assert 'frostedbrowser.cfd/wisp/"' in html
assert 'fetch("/api/ai"' not in html
assert '"/sail/scram/' not in html
assert '"/sw.js"' not in html

import shutil

ENGINE_FILES = [
    ("sw.js", "sw.js"),
    ("scram/controller.sw.js", "scram/controller.sw.js"),
    ("sail/scram/scramjet.js", "sail/scram/scramjet.js"),
    ("sail/scram/controller.inject.js", "sail/scram/controller.inject.js"),
    ("sail/scram/scramjet.wasm", "sail/scram/scramjet.wasm"),
]
for src_rel, dst_rel in ENGINE_FILES:
    data = (SRC / src_rel).read_bytes()
    if src_rel == "sw.js":
        data = data.replace(b'"/scram/controller.sw.js"', b'"scram/controller.sw.js"')
    dst = OUT / dst_rel
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_bytes(data)
    print("engine:", dst_rel, len(data), "bytes")

import base64

page_names = ["changelogs", "credits", "history"]
embedded = {}
main_css = read("c/main.css")
page_css = read("p/p.css")
for name in page_names:
    doc = (SRC / "p" / f"{name}.html").read_text()
    doc = re.sub(
        r'<link rel="stylesheet" href="/c/main\.css[^"]*">',
        "<style>\n" + main_css + "\n</style>",
        doc,
        count=1,
    )
    doc = re.sub(
        r'<link rel="stylesheet" href="/p/p\.css[^"]*">',
        "<style>\n" + page_css + "\n</style>",
        doc,
        count=1,
    )
    assert "/c/main.css" not in doc and "/p/p.css" not in doc, name
    embedded[name] = base64.b64encode(doc.encode()).decode()

def extract_fn(src, name):
    i = src.find(f"function {name}(")
    assert i >= 0, name
    j = src.find("{", i)
    depth = 0
    k = j
    instr = False
    q = None
    while k < len(src):
        ch = src[k]
        if instr:
            if ch == "\\":
                k += 2
                continue
            if ch == q:
                instr = False
        else:
            if ch in "\"'`":
                instr = True
                q = ch
            elif ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    return src[i:k + 1]
        k += 1
    raise AssertionError(name)


tabs_src = read("js/tabs.js")
new_tab = extract_fn(tabs_src, "newBrowserTab")
new_tab = new_tab.replace(
    'iframe.setAttribute("src", "/p/" + earlyPage + ".html");',
    'iframe.removeAttribute("src"); iframe.setAttribute("srcdoc", pageDoc(earlyPage));',
)
show_page = extract_fn(tabs_src, "showPage")
show_page = show_page.replace(
    'tab.iframe.getAttribute("src") !== want',
    'tab.iframe.getAttribute("data-novene-page") !== page',
).replace(
    'fresh.setAttribute("src", want);',
    'fresh.removeAttribute("src"); fresh.setAttribute("srcdoc", pageDoc(page)); fresh.setAttribute("data-novene-page", page);',
).replace(
    '    const want = "/p/" + page + ".html";\n',
    '',
)
assert '"/p/"' not in new_tab and '"/p/"' not in show_page

override_src = (
    "const NOVENE_PAGES = {\n"
    + "".join(f'"{n}": atob("{embedded[n]}"),\n' for n in page_names)
    + "};\n"
    + "function pageDoc(name) { return NOVENE_PAGES[name] || \"\"; }\n"
    + new_tab
    + "\n"
    + show_page
)

xhtml = html
xhtml = xhtml.replace("<html lang=\"en\">", '<html xmlns="http://www.w3.org/1999/xhtml" lang="en">', 1)
xhtml = re.sub(
    r"<(meta|link|img|br|hr|input)(\s(?:[^>\"']|\"[^\"]*\"|'[^']*')*?)(?<!/)>",
    r"<\1\2/>",
    xhtml,
)
xhtml = xhtml.replace("<script async src=", '<script async="async" src=')

BOOLEANS = (
    "disabled|checked|selected|readonly|required|autofocus|multiple|open|hidden|"
    "async|defer|allowfullscreen|novalidate|formnovalidate|ismap|itemscope|reversed|"
    "controls|loop|muted|autoplay|playsinline|default"
)


def fix_bare_attrs(s):
    out = []
    i, n = 0, len(s)
    in_tag = False
    quote = None
    while i < n:
        ch = s[i]
        if quote:
            out.append(ch)
            if ch == quote:
                quote = None
            i += 1
            continue
        if ch in "\"'":
            quote = ch
            out.append(ch)
            i += 1
            continue
        if ch == "<":
            in_tag = True
            out.append(ch)
            i += 1
            continue
        if ch == ">":
            in_tag = False
            out.append(ch)
            i += 1
            continue
        if in_tag and (ch == " " or ch == "\t" or ch == "\n"):
            m = re.match(r"\s+(" + BOOLEANS + r")(?=[\s/>])", s[i:])
            if m:
                out.append(" " + m.group(1) + '="' + m.group(1) + '"')
                i += len(m.group(0))
                continue
        out.append(ch)
        i += 1
    return "".join(out)


INLINE_RE = r"^[ \t]*<script((?:\s[^>]*)?)>\n?"


def pull_inline_scripts(s):
    blobs = []
    out = []
    pos = 0
    for m in re.finditer(INLINE_RE, s, flags=re.M):
        if "src=" in m.group(1):
            continue
        term = re.search(r"</script\s*>", s[m.end():])
        assert term, "unclosed inline script"
        out.append(s[pos:m.start()])
        blobs.append(s[m.end():m.end() + term.start()])
        pos = m.end() + term.end()
    out.append(s[pos:])
    return "".join(out), blobs


xhtml, script_blobs = pull_inline_scripts(xhtml)
assert len(script_blobs) == 11, f"expected 11 inline scripts, got {len(script_blobs)}"
assert not re.search(r"^[ \t]*<script(?![^>]*src=)", xhtml, flags=re.M), "stray inline script"
for b in script_blobs:
    assert "</script" not in b.replace("<\\/script", ""), "inline terminator hazard"

xhtml = fix_bare_attrs(xhtml)

script_blobs.append(override_src)
assert "</script" not in override_src.replace("<\\/script", ""), "override terminator hazard"

SHIM_SRC = """(function(){
var XN="http://www.w3.org/1999/xhtml";
var XROOT=null;
try{XROOT=document.querySelector("foreignObject");}catch(XE){}
if(XROOT){
var XCE=document.createElement.bind(document);
var XCENS=document.createElementNS.bind(document);
try{Object.defineProperty(document,"head",{get:function(){return XROOT.querySelector("head")},configurable:true});}catch(XE){}
try{Object.defineProperty(document,"body",{get:function(){return XROOT.querySelector("body")},configurable:true});}catch(XE){}
document.createElement=function(XT,XO){return typeof XT==="string"?XCENS(XN,XT,XO):XCE(XT,XO);};
document.createElementNS=function(XNS,XN2,XO){return (XNS==null||XNS===XN)?XCENS(XN,XN2,XO):XCENS(XNS,XN2,XO);};
}
var XD=null;
try{XD=Object.getOwnPropertyDescriptor(Element.prototype,"innerHTML");}catch(XE){}
if(XD&&XD.set){
var XV=/^(meta|link|img|br|hr|input|source|track|wbr|col|base|area|embed|param|path|circle|rect|line|polyline|polygon|ellipse|use|stop)$/i;
function xfix(s){
return String(s).replace(/<([a-zA-Z][a-zA-Z0-9]*)(\s[^<>]*)?>/g,function(m,t,a){
if(t.charAt(0)==="/")return m;
a=(a||"").replace(/\sallowfullscreen(?=[\s/>])/g,' allowfullscreen="allowfullscreen"');
if(XV.test(t)&&m.charAt(m.length-2)!=="/")return "<"+t+a+"/>";
return m;
});
}
try{Object.defineProperty(Element.prototype,"innerHTML",{set:function(XV2){XD.set.call(this,xfix(XV2));},get:function(){return XD.get.call(this);},configurable:true});}catch(XE){}
}
})();"""

script_blobs.insert(0, SHIM_SRC)

BOOTSTRAP = (
    "<script>\n"
    "window.dataLayer = window.dataLayer || [];\n"
    "var NOVENE_BLOBS=[\n"
    + "".join('"' + base64.b64encode(b.encode()).decode() + '",\n' for b in script_blobs)
    + "];\n"
    'var NOVENE_SLOT=document.getElementsByTagName("head")[0]||document.documentElement;\n'
    "for (var NOVENE_K in NOVENE_BLOBS){"
    'var NOVENE_EL=document.createElementNS("http://www.w3.org/1999/xhtml","script");'
    "NOVENE_EL.text=atob(NOVENE_BLOBS[NOVENE_K]);"
    "NOVENE_SLOT.appendChild(NOVENE_EL);"
    "}\n</script>"
)
assert "<" not in BOOTSTRAP.replace("<script>", "").replace("</script>", "")
assert "&" not in BOOTSTRAP and "]]>" not in BOOTSTRAP
m = re.search(r"(?m)^[ \t]*</body>", xhtml)
assert m, "no body close"
xhtml = xhtml[:m.start()] + BOOTSTRAP + "\n" + xhtml[m.start():]

xhtml = re.sub(r"&(?!(?:lt|gt|amp|quot|apos|#\d+|#x[0-9a-fA-F]+);)", "&amp;", xhtml)

xhtml_lines = [l for l in xhtml.split("\n") if not l.strip().lower().startswith("<!doctype")]
xhtml = "\n".join(xhtml_lines)

svg = (
    '<svg xmlns="http://www.w3.org/2000/svg" xmlns:xhtml="http://www.w3.org/1999/xhtml" width="100%" height="100%">\n'
    '<foreignObject width="100%" height="100%" requiredExtensions="http://www.w3.org/1999/xhtml">\n'
    + xhtml
    + '\n</foreignObject>\n</svg>\n'
)
(OUT / "study.svg").write_text(svg)

print("study.svg bytes:", len(svg))
