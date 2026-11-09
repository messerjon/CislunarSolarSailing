"""Assemble the Cislunar Sail Explorer into one self-contained HTML file.

    python interactive/build.py                       -> interactive/cislunar_sail_explorer.html (standalone page)
    python interactive/build.py --fragment OUT.html   -> also writes the body-only variant used for publishing

data.js (exported from the Python simulator by export_data.py), engine.js and src/app.js are inlined; three.js r128
and its OrbitControls / Line2 helpers load from jsDelivr.
"""
import argparse, os, re

HERE = os.path.dirname(os.path.abspath(__file__))
CDN = "https://cdn.jsdelivr.net/npm/three@0.128.0/"
LIBS = ["build/three.min.js", "examples/js/controls/OrbitControls.js", "examples/js/lines/LineSegmentsGeometry.js",
        "examples/js/lines/LineGeometry.js", "examples/js/lines/LineMaterial.js", "examples/js/lines/LineSegments2.js",
        "examples/js/lines/Line2.js"]


def read(*p):
    with open(os.path.join(HERE, *p), encoding="utf-8") as fh:
        return fh.read()


def inline(js):
    return "<script>\n" + js.replace("</script", "<\\/script") + "\n</script>"


def build():
    tpl = read("src", "explorer.html")
    head = tpl.split("<!-- @HEAD -->", 1)[1].split("<!-- @BODY -->", 1)[0].strip()
    body = tpl.split("<!-- @BODY -->", 1)[1].split("<!-- @SCRIPTS -->", 1)[0].strip()
    scripts = "\n".join('<script src="%s%s"></script>' % (CDN, lib) for lib in LIBS)
    scripts += "\n" + inline(read("data.js")) + "\n" + inline(read("engine.js")) + "\n" + inline(read("src", "app.js"))
    fragment = head + "\n" + body + "\n" + scripts + "\n"
    page = ('<!doctype html>\n<html lang="en">\n<head>\n<meta charset="utf-8">\n'
            '<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">\n'
            + head + "\n</head>\n<body>\n" + body + "\n" + scripts + "\n</body>\n</html>\n")
    return page, fragment


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--fragment", help="also write the body-only variant (no doctype/html/head/body) to this path")
    a = ap.parse_args()
    page, fragment = build()
    out = os.path.join(HERE, "cislunar_sail_explorer.html")
    with open(out, "w", encoding="utf-8") as fh:
        fh.write(page)
    print("wrote", out, "%.0f KB" % (len(page.encode()) / 1024))
    if a.fragment:
        with open(a.fragment, "w", encoding="utf-8") as fh:
            fh.write(fragment)
        print("wrote", a.fragment, "%.0f KB" % (len(fragment.encode()) / 1024))
