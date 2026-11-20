import fitz
import re
import sys

sys.stdout.reconfigure(encoding='utf-8')

EM_BLANK = r"D:\BaiduNetdiskDownload\b站电机学课程配套资料(纪真-十万伏特皮卡丘)\b站电机学配套(空白版可打印自己做题).pdf"
doc = fitz.open(EM_BLANK)

cur_ch = ""
cur_sec = ""

for pno in range(4, len(doc)):  # starts p.5
    page = doc[pno]
    lines = [l.strip() for l in page.get_text().splitlines() if l.strip()]
    for ln in lines:
        if re.match(r'^第[一二三四五六七八九十]+章', ln):
            cur_ch = ln
            print(f"\n=== [p.{pno+1}] {cur_ch} ===")
        elif re.match(r'^第[一二三四五六七八九十]+节', ln):
            cur_sec = ln
            print(f"  -- [p.{pno+1}] {cur_sec}")
        elif re.match(r'^(二[\.、]\s*习题|课后习题|习题\s*[:：]?|题目\s*[:：]?|练习\s*[:：]?)', ln):
            print(f"    * [p.{pno+1}] HEADER: {ln[:60]}")
        elif re.match(r'^\d+\s*[\.、．]\s*[（(](单选|多选|判断|填空)', ln):
            print(f"    + [p.{pno+1}] Q: {ln[:55]}")
        elif re.match(r'^(例题|【例|例\s*\d)', ln):
            print(f"    @ [p.{pno+1}] EX: {ln[:65]}")
