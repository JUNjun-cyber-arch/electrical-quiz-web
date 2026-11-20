import fitz
import json
import re
import sys

sys.stdout.reconfigure(encoding='utf-8')

PE_PDF = r"D:\BaiduNetdiskDownload\b站电力电子课程配套资料(纪真-十万伏特皮卡丘)\b站电力电子配套习题-纪真十万伏特皮卡丘_带答案版.pdf"
EM_PDF = r"D:\BaiduNetdiskDownload\b站电机学课程配套资料(纪真-十万伏特皮卡丘)\b站电机学配套(空白版可打印自己做题).pdf"

def scan_pdf_fraction_bars(pdf_path, label):
    doc = fitz.open(pdf_path)
    print(f"=== {label}: pages with math fraction bars (drawings) ===")
    pages_hit = {}
    for pno in range(len(doc)):
        page = doc[pno]
        bars = []
        for dr in page.get_drawings():
            r = dr["rect"]
            w = r.width
            h = r.height
            # Fraction bar: short horizontal segment, not full page header line, inside body
            if 5 <= w <= 160 and h <= 2.2 and r.y0 > 60 and r.y1 < page.rect.height - 50:
                bars.append(r)
        if bars:
            pages_hit[pno + 1] = len(bars)
    print("Pages with short horizontal bars:", pages_hit)
    return pages_hit

def scan_json_fractions(json_path, label, bar_pages):
    d = json.load(open(json_path, encoding='utf-8'))
    print(f"\n=== {label}: JSON questions needing fraction formatting ===")
    hits = []
    for q in d['questions']:
        fields = [('stem', q['stem']), ('ans', q['answer']), ('exp', q.get('explanation', ''))]
        for o in q['options']:
            fields.append((o['key'], o['text']))

        matched = []
        on_bar_page = q['page'] in bar_pages
        for k, v in fields:
            # Check suspicious flattened fractions or math slashes
            is_math_slash = bool(re.search(
                r'(?<!k)(?<!r)(?<!H)(?<!A)(?<!V)(?<!m)\b(?:\d+|[A-Za-zπωαβγδΦφ√][A-Za-z0-9_₀₁₂₃]*|\([^)]+\))\s*/\s*(?:\d+|[A-Za-zπωαβγδΦφ√][A-Za-z0-9_₀₁₂₃]*|\([^)]+\))',
                v
            ))
            # Filter out known non-fractions (voltage ratings, units, capacity ratios, dates)
            if is_math_slash:
                tmp = re.sub(r'\b\d+(?:\.\d+)?/\d+(?:\.\d+)?(?:/\d+)?\s*(?:kV|KV|Kv|V)\b', '', v)
                tmp = re.sub(r'\b\d+/\d+/\d+\b', '', tmp)
                tmp = re.sub(r'\b(?:r/min|H/m|A/Wb|V/m|kV/m|W/m|A/m|kV/kV)\b', '', tmp)
                tmp = re.sub(r'\d+\s*kV/\d+\s*kV', '', tmp, flags=re.I)
                tmp = re.sub(r'导通/关断|高/低压|输入/输出|直流/交流|交流/直流|上升/下降|超前/滞后|铁磁材料/软磁材料|空载/短路', '', tmp)
                is_math_slash = bool(re.search(r'/', tmp))

            is_flat_frac = bool(re.search(
                r'(1\s*\+\s*cos|cos\s*α\s+\d|sin\s*α\s+\d|\b\d\s+\d\s*[UIF]|2\s+2\s*π|\+\s*cos|\b\d\s+U\b|U2\s+1|Ud\s+\d|n1\s+v)',
                v
            ))

            if is_math_slash or is_flat_frac:
                matched.append((k, v))

        if matched or (on_bar_page and any(re.search(r'cos|sin|√|π|α|U|I|X|Z|R|F|n|s|k', o['text']) for o in q['options'])):
            hits.append((q['num'], q['page'], on_bar_page, matched if matched else [('OPTS', [o['text'] for o in q['options']])]))

    print(f"Total flagged in {label}: {len(hits)}")
    for num, pg, on_bar, m in hits:
        print(f"  Q{num} (p.{pg}, bar={on_bar}):")
        for k, v in m:
            print(f"    [{k}] {v}")

pe_bars = scan_pdf_fraction_bars(PE_PDF, "PE")
em_bars = scan_pdf_fraction_bars(EM_PDF, "EM")
scan_json_fractions(r"D:\Antigravity\Electrical_Quiz_Web\public\data\power-electronics.json", "PE", pe_bars)
scan_json_fractions(r"D:\Antigravity\Electrical_Quiz_Web\public\data\electric-machinery.json", "EM", em_bars)
