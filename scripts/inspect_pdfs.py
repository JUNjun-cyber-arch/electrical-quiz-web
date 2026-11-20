import fitz
import re
import sys
from collections import Counter

sys.stdout.reconfigure(encoding='utf-8')

PE_ANS = r"D:\BaiduNetdiskDownload\b站电力电子课程配套资料(纪真-十万伏特皮卡丘)\b站电力电子配套习题-纪真十万伏特皮卡丘_带答案版.pdf"
EM_BLANK = r"D:\BaiduNetdiskDownload\b站电机学课程配套资料(纪真-十万伏特皮卡丘)\b站电机学配套(空白版可打印自己做题).pdf"
EM_ANS = r"D:\BaiduNetdiskDownload\b站电机学课程配套资料(纪真-十万伏特皮卡丘)\b站电机学配套（讲后带板书和答案-仅参考,不打印）.pdf"

def inspect_images(path, label):
    doc = fitz.open(path)
    xref_counts = Counter()
    size_counts = Counter()
    for p in doc:
        for img in p.get_images(full=True):
            xref = img[0]
            w, h = img[2], img[3]
            xref_counts[xref] += 1
            size_counts[(w, h)] += 1
    print(f"=== {label} ({len(doc)} pages) ===")
    print("Top repeated image sizes:", size_counts.most_common(6))
    print("Top repeated xrefs:", xref_counts.most_common(6))

inspect_images(PE_ANS, "PE_ANS")
inspect_images(EM_BLANK, "EM_BLANK")
inspect_images(EM_ANS, "EM_ANS")

# Check PE question numbering across all pages
doc_pe = fitz.open(PE_ANS)
pe_lines = []
for i, p in enumerate(doc_pe):
    for line in p.get_text().splitlines():
        s = line.strip()
        if re.match(r'^\d+\s*[\.、．]', s):
            pe_lines.append((i+1, s[:60]))
print(f"\nPE lines matching ^num.: {len(pe_lines)}")
for x in pe_lines[:15]:
    print(" ", x)
print("  ...")
for x in pe_lines[-10:]:
    print(" ", x)
