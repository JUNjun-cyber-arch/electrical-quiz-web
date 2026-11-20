import json
import os
import re
import sys

sys.stdout.reconfigure(encoding='utf-8')

PE_JSON = r"D:\Antigravity\Electrical_Quiz_Web\public\data\power-electronics.json"
EXP_DIR = r"D:\Antigravity\Electrical_Quiz_Web\scripts\pe_explanations"

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
    # Check $$
    if '$$' in text:
        errs.append(f"{qid}: contains forbidden $$")
    # Check even number of $
    if text.count('$') % 2 != 0:
        errs.append(f"{qid}: odd number of $")
    # Check each $...$ block
    for m in re.finditer(r'\$([^$]+)\$', text):
        expr = m.group(1)
        # Check brace balance
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
        # Check math slash inside $...$
        if '/' in expr:
            errs.append(f"{qid}: slash '/' inside math: {expr[:60]}")
        # Check unknown commands
        for cm in re.finditer(r'\\([a-zA-Z]+|[^a-zA-Z\s])', expr):
            cmd = cm.group(1)
            if cmd not in SUPPORTED_CMDS:
                errs.append(f"{qid}: unsupported LaTeX cmd \\{cmd}")
    # Check stray math slash outside $...$ (ignore allowed units & Chinese pairs)
    outside = re.sub(r'\$[^$]*\$', ' ', text)
    # Remove known allowed slashes (units & word pairs)
    cleaned = re.sub(
        r'(?:V/μs|V/us|A/μs|A/us|kV/μs|r/min|rad/s|H/m|A/Wb|开通/关断|导通/关断|关断/开通|正/负|高/低|输入/输出|直流/交流|交流/直流|升压/降压|降压/升压|整流/逆变|单/双|上/下|串/并联|单相/三相|半波/全波|全控/半控|有源/无源|电压/电流|电压型/电流型|连续/断续|阻性/阻感|阻感/电阻|电阻/阻感|主电路/控制电路|强电/弱电|可控/不可控|全控/半控|半控/全控|正组/反组|正向/反向|大/小|增/减|高/中/低|10/0\.4kV|220/380V|AC/DC|DC/AC|DC/DC|AC/AC|PWM/PFM|GTR/BJT|SCR/GTO|IGBT/MOSFET)',
        '', outside, flags=re.I
    )
    if '/' in cleaned:
        errs.append(f"{qid}: suspicious slash outside math: {cleaned[max(0, cleaned.find('/')-15):cleaned.find('/')+20]}")
    return errs

def main():
    d = json.load(open(PE_JSON, encoding='utf-8'))
    merged = {}
    for i in range(1, 6):
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

    print(f"\nTotal PE questions: {len(d['questions'])}")
    print(f"Merged explanations: {len(merged)}")
    print(f"Missing: {len(missing)} {missing[:10]}")
    print(f"Too short (<12 chars): {len(short_list)} {short_list[:5]}")
    print(f"Syntax/slash issues: {len(syntax_errs)}")
    for e in syntax_errs[:40]:
        print("  -", e)

    if not missing:
        with open(PE_JSON, 'w', encoding='utf-8') as f:
            json.dump(d, f, ensure_ascii=False, indent=2)
        print("Updated:", PE_JSON)

if __name__ == '__main__':
    main()
