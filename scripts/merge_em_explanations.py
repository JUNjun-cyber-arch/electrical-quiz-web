import json
import os
import re
import sys

sys.stdout.reconfigure(encoding='utf-8')

EM_JSON = r"D:\Antigravity\Electrical_Quiz_Web\public\data\electric-machinery.json"
EXP_DIR = r"D:\Antigravity\Electrical_Quiz_Web\scripts\em_explanations"

SUPPORTED_CMDS = {
    'frac', 'sqrt', 'text', 'mathrm', 'operatorname', 'left', 'right',
    'sin', 'cos', 'tan', 'cot', 'log', 'ln', 'max', 'min', 'rms',
    'alpha', 'beta', 'gamma', 'delta', 'theta', 'lambda', 'mu', 'pi',
    'rho', 'sigma', 'phi', 'varphi', 'omega', 'eta', 'tau',
    'Delta', 'Sigma', 'sum', 'int', 'Phi', 'Omega',
    'cdot', 'times', 'pm', 'mp', 'approx', 'le', 'leq', 'ge', 'geq',
    'ne', 'neq', 'propto', 'angle', 'sim', 'cdots', 'ldots', 'infty',
    'to', 'rightarrow', 'circ', '%', ',', ';', 'quad'
}

def check_math_syntax(qid, text):
    errs = []
    if '$$' in text:
        errs.append(f"{qid}: contains forbidden $$")
    if text.count('$') % 2 != 0:
        errs.append(f"{qid}: odd number of $")
    for m in re.finditer(r'\$([^$]+)\$', text):
        expr = m.group(1)
        depth = 0
        for ch in expr:
            if ch == '{':
                depth += 1
            elif ch == '}':
                depth -= 1
                if depth < 0:
                    errs.append(f"{qid}: unbalanced }} in {expr[:50]}")
                    break
        if depth != 0:
            errs.append(f"{qid}: unbalanced {{ in {expr[:50]}")
        if '/' in expr:
            errs.append(f"{qid}: slash '/' inside math: {expr[:60]}")
        for cm in re.finditer(r'\\([a-zA-Z]+|[^a-zA-Z\s])', expr):
            cmd = cm.group(1)
            if cmd not in SUPPORTED_CMDS:
                errs.append(f"{qid}: unsupported LaTeX cmd \\{cmd}")
    outside = re.sub(r'\$[^$]*\$', ' ', text)
    cleaned = re.sub(
        r'(?:r/min|H/m|A/Wb|V/m|kV/m|W/m|A/m|kV/kV|高/低|高/中/低|中/低压|高/低压|一次/二次|定/转子|空载/短路|过励/欠励|滞后/超前|超前/滞后|正/负|增/减|大/小|同步/异步|电动/发电|发/电动|升压/降压|串/并联|星/三角|Y/Δ|Y/d|220/110/35kV|242/121/11kV|110/220kV|220/500kV|110/330kV|110/500kV|330/121/11kV|220/121kV|500/242kV|110/11kV|10/0\.4kV|25000/220|100/100/50|4/2140|铁磁材料/软磁材料|恒定/交变|直流/交流|交流/直流|起动/运行|启动/运行|正序/负序)',
        '', outside, flags=re.I
    )
    if '/' in cleaned:
        idx = cleaned.find('/')
        errs.append(f"{qid}: suspicious slash outside math: {cleaned[max(0, idx-15):idx+20]}")
    return errs

def main():
    d = json.load(open(EM_JSON, encoding='utf-8'))
    merged = {}
    for i in range(1, 5):
        p = os.path.join(EXP_DIR, f"exp_{i}.json")
        if not os.path.exists(p):
            print(f"MISSING FILE: {p}")
            sys.exit(1)
        part = json.load(open(p, encoding='utf-8'))
        print(f"Loaded exp_{i}.json: {len(part)} entries")
        merged.update(part)

    missing = []
    short_list = []
    syntax_errs = []

    for q in d['questions']:
        qid = q['id']
        exp = merged.get(qid, '').strip()
        if not exp:
            missing.append(qid)
            continue
        if len(exp) < 12:
            short_list.append((qid, exp))
        syntax_errs.extend(check_math_syntax(qid, exp))
        q['explanation'] = exp

    print(f"\nTotal EM questions: {len(d['questions'])}")
    print(f"Merged explanations: {len(merged)}")
    print(f"Missing: {len(missing)} {missing[:10]}")
    print(f"Too short (<12 chars): {len(short_list)} {short_list[:5]}")
    print(f"Syntax/slash issues: {len(syntax_errs)}")
    for e in syntax_errs[:40]:
        print("  -", e)

    if not missing:
        with open(EM_JSON, 'w', encoding='utf-8') as f:
            json.dump(d, f, ensure_ascii=False, indent=2)
        print("Updated:", EM_JSON)

if __name__ == '__main__':
    main()
