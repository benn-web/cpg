#!/usr/bin/env python3
"""Inject verified computed values as cached <v> into formula cells, preserving all
formatting/validation/CF/charts. Text-surgical (only touches cells that have <f>).

Values are computed with the `formulas` library (used because LibreOffice headless
recalc is unavailable in this environment). Also rewrites bare XLOOKUP( to its Excel
storage form _xlfn._xlws.XLOOKUP( so the delivered file evaluates in Excel.

Usage: python inject_cache.py <src.xlsx> [out.xlsx]   (default out: <src>_cached.xlsx)
"""
import warnings, re, shutil, zipfile, os, sys
warnings.filterwarnings("ignore")
import formulas
import numpy as np

SRC = sys.argv[1] if len(sys.argv) > 1 else "Income_Forecast.xlsx"
OUT = sys.argv[2] if len(sys.argv) > 2 else (os.path.splitext(SRC)[0] + "_cached.xlsx")

# 1) compute all values
xl = formulas.ExcelModel().loads(SRC).finish()
sol = xl.calculate()

def extract(v):
    try: v = v.value
    except Exception: pass
    if isinstance(v, np.ndarray):
        v = v.ravel()[0] if v.size else ""
    if isinstance(v, np.generic):
        v = v.item()
    return v

# map (SHEETNAME_UPPER, CELLREF) -> value
cellmap = {}
key_re = re.compile(r"^'?\[[^\]]+\]([^'!]+)'?!\$?([A-Z]+)\$?(\d+)$")
for k, v in sol.items():
    m = key_re.match(k)
    if not m:
        continue
    sheet, col, row = m.group(1).upper(), m.group(2), m.group(3)
    cellmap[(sheet, f"{col}{row}")] = extract(v)

# 2) map worksheet xml files -> sheet name (upper)
shutil.copy(SRC, OUT)
zin = zipfile.ZipFile(OUT)
names = zin.namelist()
wb_xml = zin.read("xl/workbook.xml").decode("utf-8")
rels_xml = zin.read("xl/_rels/workbook.xml.rels").decode("utf-8")
rid_to_target = {}
for rel in re.findall(r'<Relationship\b[^>]*/?>', rels_xml):
    rid_m = re.search(r'Id="([^"]+)"', rel)
    tgt_m = re.search(r'Target="([^"]+)"', rel)
    if rid_m and tgt_m:
        rid_to_target[rid_m.group(1)] = tgt_m.group(1)
sheet_name_to_file = {}
for nm, rid in re.findall(r'<sheet[^>]*name="([^"]+)"[^>]*r:id="([^"]+)"', wb_xml):
    tgt = rid_to_target.get(rid, "")
    if tgt and not tgt.startswith("/"):
        tgt = "xl/" + tgt
    sheet_name_to_file[nm.upper()] = tgt.lstrip("/")

def esc(s):
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

def fmt_num(x):
    if isinstance(x, bool):
        return None  # handled separately
    if isinstance(x, int):
        return str(x)
    f = float(x)
    if f == int(f) and abs(f) < 1e15:
        return str(int(f))
    return repr(f)

CELL_RE_CACHE = {}
def inject_sheet(text, sheet_upper):
    count = 0
    # iterate cells present in map for this sheet
    for (sh, ref), val in cellmap.items():
        if sh != sheet_upper:
            continue
        # formula cells (openpyxl emits an empty <v /> we overwrite):
        # <c r="REF" ...><f...>...</f><v /></c>
        pat = re.compile(r'(<c r="' + re.escape(ref) + r'"([^>]*)>)(<f[^>]*>.*?</f>|<f[^>]*/>)'
                         r'(<v\s*/>|<v>.*?</v>)?(</c>)', re.S)
        m = pat.search(text)
        if not m:
            continue
        open_tag, attrs, ftag, close = m.group(1), m.group(2), m.group(3), m.group(5)
        if ' t="' in attrs:
            attrs_clean = re.sub(r'\s+t="[^"]*"', '', attrs)
        else:
            attrs_clean = attrs
        v = val
        if isinstance(v, bool):
            new_open = f'<c r="{ref}"{attrs_clean} t="b">'
            vtag = f'<v>{1 if v else 0}</v>'
        elif isinstance(v, str):
            new_open = f'<c r="{ref}"{attrs_clean} t="str">'
            vtag = f'<v>{esc(v)}</v>'
        elif v is None:
            new_open = f'<c r="{ref}"{attrs_clean} t="str">'
            vtag = '<v></v>'
        else:
            num = fmt_num(v)
            new_open = f'<c r="{ref}"{attrs_clean}>'
            vtag = f'<v>{num}</v>'
        repl = new_open + ftag + vtag + close
        text = text[:m.start()] + repl + text[m.end():]
        count += 1
    return text, count

# 3) rewrite the zip
tmp = "Income_Forecast_cached_tmp.xlsx"
total = 0
with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as zout:
    for item in zin.infolist():
        data = zin.read(item.filename)
        # is this a worksheet we have a name for?
        this_sheet = None
        for sname, fpath in sheet_name_to_file.items():
            if fpath == item.filename:
                this_sheet = sname
                break
        if this_sheet is not None:
            text = data.decode("utf-8")
            text, c = inject_sheet(text, this_sheet)
            # Excel stores XLOOKUP as _xlfn._xlws.XLOOKUP; openpyxl wrote it bare.
            # Guarded so an already-prefixed name is never double-prefixed.
            text = re.sub(r'(?<![\w.])XLOOKUP\(', '_xlfn._xlws.XLOOKUP(', text)
            total += c
            data = text.encode("utf-8")
        zout.writestr(item, data)
zin.close()
os.replace(tmp, OUT)
print("cells injected:", total)
