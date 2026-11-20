import fitz
import json
import os
import re
import sys
import io
from collections import Counter
from PIL import Image

sys.stdout.reconfigure(encoding='utf-8')

EM_BLANK = r"D:\BaiduNetdiskDownload\b站电机学课程配套资料(纪真-十万伏特皮卡丘)\b站电机学配套(空白版可打印自己做题).pdf"
EM_ANS = r"D:\BaiduNetdiskDownload\b站电机学课程配套资料(纪真-十万伏特皮卡丘)\b站电机学配套（讲后带板书和答案-仅参考,不打印）.pdf"
OUT_JSON = r"D:\Antigravity\Electrical_Quiz_Web\public\data\electric-machinery.json"
IMG_DIR = r"D:\Antigravity\Electrical_Quiz_Web\public\assets\images\em"

os.makedirs(IMG_DIR, exist_ok=True)

CHAR_REPLACEMENTS = {
    '\uf06d': 'μ', '\uf077': 'ω', '\uf061': 'α', '\uf062': 'β',
    '\uf067': 'γ', '\uf066': 'φ', '\uf06a': 'φ', '\uf070': 'π',
    '\uf057': 'Ω', '\uf046': 'Φ', '\uf0b1': '±', '\uf0b0': '°',
    '\uf0d7': '×', '\uf0a3': '≤', '\uf0b3': '≥', '\uf0b9': '≠',
    '\uf0bb': '≈', '\uf0ae': '→', '\u00a0': ' ', '\u3000': ' ',
    # Cambria Math / WPS shifted glyphs
    'ƿ': 'U', 'ǈ': 'd', 'ǅ': 'a', 'ǆ': 'b', 'ǂ': 'X', 'Ƭ': 'B',
    'Ƴ': 'I', 'ؼ': 'π', 'Ǚ': 'u', '푠': 's', 'Ǎ': 'i', 'ǒ': 'n',
    'م': 'ω', 'ǘ': 't', 'º': '°', 'µ': 'μ', '∽': '～', '−': '-',
    '푖': 'i', 'Ǘ': 's', 'Ƽ': 'R', 'Ƶ': 'K', 'ظ': 'μ', '＝': '=',
    '＞': '>', '＜': '<', 'ℜ': 'R', '＇': "'", '′': "'",
    'ư': 'F', 'Ǐ': 'k', 'Ǜ': 'w', '㎡': 'm²',
}

def clean_text(s):
    for k, v in CHAR_REPLACEMENTS.items():
        s = s.replace(k, v)
    s = re.sub(r'[ \t]+', ' ', s)
    return s.strip()

def save_image(doc, xref, out_name):
    out_path = os.path.join(IMG_DIR, out_name)
    if os.path.exists(out_path):
        return out_name
    base = doc.extract_image(xref)
    im = Image.open(io.BytesIO(base["image"]))
    if im.mode in ("RGBA", "P"):
        bg = Image.new("RGB", im.size, (255, 255, 255))
        if im.mode == "P":
            im = im.convert("RGBA")
        bg.paste(im, mask=im.split()[-1])
        im = bg
    elif im.mode != "RGB":
        im = im.convert("RGB")
    if im.width > 1200:
        ratio = 1200 / im.width
        im = im.resize((1200, int(im.height * ratio)), Image.Resampling.LANCZOS)
    im.save(out_path, "WEBP", quality=86, method=4)
    return out_name

def render_page_crop(doc, pno_1based, out_name, clip_y_ratio=(0.06, 0.96)):
    out_path = os.path.join(IMG_DIR, out_name)
    if os.path.exists(out_path):
        return out_name
    page = doc[pno_1based - 1]
    rect = page.rect
    clip = fitz.Rect(rect.x0 + 18, rect.y0 + rect.height * clip_y_ratio[0],
                     rect.x1 - 18, rect.y0 + rect.height * clip_y_ratio[1])
    pix = page.get_pixmap(dpi=155, clip=clip)
    im = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
    if im.width > 1200:
        ratio = 1200 / im.width
        im = im.resize((1200, int(im.height * ratio)), Image.Resampling.LANCZOS)
    im.save(out_path, "WEBP", quality=84, method=4)
    return out_name

def extract_em_lines(doc):
    xref_pages = {}
    for pno in range(len(doc)):
        for info in doc[pno].get_image_info(xrefs=True):
            xr = info['xref']
            xref_pages.setdefault(xr, set()).add(pno)
    ignored_xrefs = {xr for xr, ps in xref_pages.items() if len(ps) > 10}

    items = []
    for pno in range(4, len(doc)):
        page = doc[pno]
        page_items = []
        d = page.get_text("dict")
        for b in d["blocks"]:
            if b["type"] == 0:
                for line in b["lines"]:
                    y0 = line["bbox"][1]
                    if y0 < 50:
                        continue
                    vis_parts = []
                    white_parts = []
                    for sp in line["spans"]:
                        t = clean_text(sp["text"])
                        if not t:
                            continue
                        if sp["color"] == 0xffffff:
                            white_parts.append(t)
                        else:
                            vis_parts.append(t)
                    vis_txt = clean_text(" ".join(vis_parts))
                    white_txt = clean_text(" ".join(white_parts))
                    full_txt = clean_text("".join(sp["text"] for sp in line["spans"]))
                    if not full_txt:
                        continue
                    if "哔哩哔哩：纪真" in full_txt or "空间动态QQ" in full_txt:
                        continue
                    if re.fullmatch(r'\d{1,3}', full_txt) and (y0 < 85 or y0 > page.rect.height - 55):
                        continue
                    page_items.append((y0, line["bbox"][0], 'text', pno + 1, {
                        'vis': vis_txt,
                        'white': white_txt,
                        'full': full_txt
                    }))

        for info in page.get_image_info(xrefs=True):
            xr = info['xref']
            bbox = info['bbox']
            if xr in ignored_xrefs or bbox[1] < 50:
                continue
            if (bbox[2] - bbox[0]) < 25 or (bbox[3] - bbox[1]) < 18:
                continue
            page_items.append((bbox[1], bbox[0], 'img', pno + 1, (xr, bbox)))

        page_items.sort(key=lambda x: (round(x[0] / 3) * 3, x[1]))
        items.extend(page_items)

    return items

def parse_em():
    doc = fitz.open(EM_BLANK)
    doc_ans = fitz.open(EM_ANS)
    items = extract_em_lines(doc)

    cur_chapter = "第一章 磁路和磁性材料"
    cur_section = ""
    in_exercise = False
    sub_fill_mode = False
    raw_qs = []
    cur_q = None

    ch_re = re.compile(r'^(第[一二三四五六七八九十]+章)\s*(.+)$')
    sec_re = re.compile(r'^(第[一二三四五六七八九十]+节)\s*(.+)$')
    lecture_heading_re = re.compile(r'^([一二三四五六七八九十]+、|总结\s*[:：]|笔记区?\s*[:：]|注\s*[:：]|思考\s*[:：]|例题\s*\d|【例\d|可以总结为)')
    ex_header_re = re.compile(r'^(二[\.、]\s*习题|课后习题|习题\s*[:：]?|题目\s*[:：]?)$')
    q_tagged_re = re.compile(r'^(\d+)\s*[\.。．、]+\s*([（(]\s*(?:单选|多选|判断|填空)\s*[)）].*|「较难」.*)$')
    q_plain_re = re.compile(r'^(\d+)\s*[\.。．、]+\s*(.*)$')

    # Merge stray standalone digits followed by ".text"
    merged_items = []
    i = 0
    while i < len(items):
        cur = items[i]
        if cur[2] == 'text' and re.fullmatch(r'\d{1,2}', cur[4]['full']) and i + 1 < len(items):
            nxt = items[i + 1]
            if nxt[2] == 'text' and nxt[3] == cur[3] and re.match(r'^[\.、．]', nxt[4]['full']):
                combined = {
                    'vis': (cur[4]['vis'] + nxt[4]['vis']).strip(),
                    'white': (cur[4]['white'] + ' ' + nxt[4]['white']).strip(),
                    'full': (cur[4]['full'] + nxt[4]['full']).strip()
                }
                merged_items.append((cur[0], cur[1], 'text', cur[3], combined))
                i += 2
                continue
        merged_items.append(cur)
        i += 1

    # Non-question summary lines on p.87-88 to ignore
    NON_QUESTION_SUBSTRS = [
        'V 形曲线',
        '该曲线称为V形曲线',
        '该曲线称为V 形曲线',
        '有功的源头是原动机',
        '调节原动机是调节有功的直接手段',
        '调节励磁电流是调节无功的直接手段',
        '有功 - 原动机、无功 - 励磁电流的配合调节',
        '有功-原动机、无功-励磁电流的配合调节',
    ]

    for _, _, kind, pno, val in merged_items:
        if kind == 'img':
            xref, bbox = val
            if in_exercise and cur_q is not None:
                cur_q['raw_imgs'].append((pno, xref))
            continue

        vis = val['vis']
        white = val['white']
        full = val['full']

        # Fix typo on p.113 where option "B.Ist..." was typed as "8.Ist..."
        if pno == 113 and full.startswith('8.Ist'):
            vis = 'B.' + vis[2:]
            full = 'B.' + full[2:]

        if any(sub in full for sub in NON_QUESTION_SUBSTRS):
            if cur_q:
                raw_qs.append(cur_q)
                cur_q = None
            in_exercise = False
            continue

        m_ch = ch_re.match(full)
        if m_ch and '....' not in full:
            if cur_q:
                raw_qs.append(cur_q)
                cur_q = None
            in_exercise = False
            sub_fill_mode = False
            cur_chapter = f"{m_ch.group(1)} {m_ch.group(2).strip()}"
            cur_section = ""
            continue

        m_sec = sec_re.match(full)
        if m_sec:
            if cur_q:
                raw_qs.append(cur_q)
                cur_q = None
            in_exercise = False
            sub_fill_mode = False
            cur_section = f"{m_sec.group(1)} {m_sec.group(2).strip()}"
            continue

        if ex_header_re.match(full):
            if cur_q:
                raw_qs.append(cur_q)
                cur_q = None
            in_exercise = True
            sub_fill_mode = False
            continue

        if in_exercise and pno == 11 and full == '一、填空题':
            sub_fill_mode = True
            continue
        if in_exercise and pno == 11 and full == '二、选择题':
            if cur_q:
                raw_qs.append(cur_q)
                cur_q = None
            sub_fill_mode = False
            continue

        if in_exercise and lecture_heading_re.match(full):
            if cur_q:
                raw_qs.append(cur_q)
                cur_q = None
            in_exercise = False
            sub_fill_mode = False
            continue

        m_qt = q_tagged_re.match(full)
        if m_qt:
            in_exercise = True
            if cur_q:
                raw_qs.append(cur_q)
            cur_q = {
                'num_local': int(m_qt.group(1)),
                'chapter': cur_chapter,
                'section': cur_section,
                'page': pno,
                'lines': [(vis, white, full)],
                'raw_imgs': [],
                'hint_type': None
            }
            continue

        if in_exercise:
            m_qp = q_plain_re.match(full)
            if m_qp:
                num_val = int(m_qp.group(1))
                if num_val <= 30 and (
                    cur_q is None or num_val == cur_q['num_local'] + 1 or num_val == 1 or abs(num_val - cur_q['num_local']) <= 3
                ):
                    if cur_q:
                        raw_qs.append(cur_q)
                    cur_q = {
                        'num_local': num_val,
                        'chapter': cur_chapter,
                        'section': cur_section,
                        'page': pno,
                        'lines': [(vis, white, full)],
                        'raw_imgs': [],
                        'hint_type': 'fill' if sub_fill_mode else None
                    }
                    continue

            if cur_q is not None:
                cur_q['lines'].append((vis, white, full))

    if cur_q:
        raw_qs.append(cur_q)

    parsed = []

    for idx, rq in enumerate(raw_qs):
        lines = list(rq['lines'])
        v0, w0, f0 = lines[0]
        v0 = re.sub(r'^\d+\s*[\.。．、]+\s*', '', v0)
        f0 = re.sub(r'^\d+\s*[\.。．、]+\s*', '', f0)
        lines[0] = (v0, w0, f0)

        answer = ""
        inline_white_answers = []
        body_vis_lines = []

        for vis, white, full in lines:
            m_ans = re.match(r'^答案\s*[:：;；]?\s*(.+)$', full)
            if m_ans:
                cand = m_ans.group(1).strip()
                if cand:
                    answer = cand
                continue
            if re.match(r'^答案\s*[:：]?$', full):
                continue

            if white:
                m_wa = re.match(r'^答案\s*[:：;；]?\s*(.+)$', white)
                if m_wa:
                    if not answer and m_wa.group(1).strip():
                        answer = m_wa.group(1).strip()
                else:
                    inline_white_answers.append(white)

            if vis:
                body_vis_lines.append(vis)

        opt_start_re = re.compile(r'^([A-E])\s*[\.。．、,，:：·\s]\s*(.*)$')
        opt_nodelim_re = re.compile(r'^([A-E])([\u4e00-\u9fa5\dΦ].*)$')

        stem_parts = []
        options = []
        in_options = False

        for ln in body_vis_lines:
            multi_opt = re.split(r'(?=(?:^|\s)[A-E]\s*[\.、．·]\s*)', ln)
            multi_opt = [x.strip() for x in multi_opt if x.strip()]
            if len(multi_opt) >= 2 and all(re.match(r'^[A-E]\s*[\.、．·]', x) for x in multi_opt):
                in_options = True
                for mo in multi_opt:
                    m = opt_start_re.match(mo)
                    if m:
                        options.append([m.group(1), m.group(2).strip()])
                continue

            m_opt = opt_start_re.match(ln)
            expected_letter = chr(ord('A') + len(options))
            if m_opt and (m_opt.group(1) == expected_letter or (in_options and m_opt.group(1) in 'ABCDE')):
                if not in_options and m_opt.group(1) == 'A' and not stem_parts:
                    stem_parts.append(ln)
                else:
                    in_options = True
                    options.append([m_opt.group(1), m_opt.group(2).strip()])
                continue

            if in_options:
                m_nd = opt_nodelim_re.match(ln)
                if m_nd and m_nd.group(1) == expected_letter:
                    options.append([m_nd.group(1), m_nd.group(2).strip()])
                    continue
                if options:
                    options[-1][1] = (options[-1][1] + " " + ln).strip()
                else:
                    stem_parts.append(ln)
            else:
                stem_parts.append(ln)

        stem = "".join(
            (p if (i == 0 or re.search(r'[\u4e00-\u9fa5（(]$', stem_parts[i-1]) or re.match(r'^[\u4e00-\u9fa5）)，。？！；：、]', p)) else " " + p)
            for i, p in enumerate(stem_parts)
        ).strip()

        # Strip leading stray dot or explicit type tag (also handle 「较难」（单选）)
        stem = re.sub(r'^[\.。、]\s*', '', stem)
        explicit_type = rq['hint_type']
        m_type = re.match(r'^(「较难」\s*)?[（(]\s*(单选|多选|判断|填空)\s*[)）]\s*[\.。]?\s*', stem)
        if m_type:
            prefix = m_type.group(1) or ''
            t_map = {'单选': 'single', '多选': 'multi', '判断': 'judge', '填空': 'fill'}
            explicit_type = t_map[m_type.group(2)]
            stem = (prefix + stem[m_type.end():]).strip()

        stem = re.sub(r'[（(]\s*[)）]', '（ ）', stem)

        if not answer and inline_white_answers:
            answer = "；".join(inline_white_answers)

        ans_clean = answer.strip().rstrip('。.;；')

        qtype = explicit_type
        if not qtype:
            if options:
                letters = re.findall(r'[A-E]', ans_clean.upper())
                qtype = 'multi' if len(letters) > 1 else 'single'
            elif ans_clean in ('正确', '错误', '对', '错', '√', '×', 'T', 'F', 'A', 'B'):
                qtype = 'judge'
            else:
                qtype = 'fill'

        # Special fix: p.95 judge question mistagged as single with no options
        if qtype == 'single' and not options and ans_clean.upper() in ('A', 'B', '正确', '错误', '对', '错'):
            qtype = 'judge'

        if qtype in ('single', 'multi'):
            letters = sorted(set(re.findall(r'[A-E]', ans_clean.upper())))
            ans_norm = "".join(letters)
            if len(letters) > 1:
                qtype = 'multi'
        elif qtype == 'judge':
            if ans_clean.upper() == 'A' or any(k in ans_clean for k in ('对', '正', '√', 'T', '是')):
                ans_norm = '正确'
            elif ans_clean.upper() == 'B' or any(k in ans_clean for k in ('错', '×', 'F', '否')):
                ans_norm = '错误'
            else:
                ans_norm = ans_clean
        else:
            ans_norm = ans_clean

        img_paths = []
        seen_xrefs = set()
        for pno_i, xr in rq['raw_imgs']:
            if xr in seen_xrefs:
                continue
            seen_xrefs.add(xr)
            fname = f"em_q{idx+1:03d}_p{pno_i}_x{xr}.webp"
            save_image(doc, xr, fname)
            img_paths.append(f"assets/images/em/{fname}")

        opt_objs = [{'key': k, 'text': re.sub(r'[;；。\.]$', '', v).strip()} for k, v in options]

        q_obj = {
            'id': f"em-{idx+1:03d}",
            'num': idx + 1,
            'chapter': rq['chapter'],
            'section': rq['section'],
            'type': qtype,
            'stem': stem,
            'options': opt_objs,
            'answer': ans_norm,
            'explanation': '',
            'images': img_paths,
            'answerImages': [],
            'page': rq['page']
        }

        # Targeted verified fixes for missing answers / formula options in original blank PDF
        if rq['page'] == 11:
            if '磁通恒定的磁路称为' in stem:
                q_obj['stem'] = '磁通恒定的磁路称为（ ），磁通随时间变化的磁路称为（ ）。'
                q_obj['answer'] = '直流磁路（恒定磁路）；交流磁路（交变磁路）'
            elif '常用的铁芯材料' in stem:
                q_obj['answer'] = '硅钢片（铁磁材料/软磁材料）'
            elif '铁磁材料的磁导率' in stem:
                q_obj['answer'] = '很大（远大于真空磁导率）；很小（近似等于真空磁导率 μ₀）'
            elif '与电路中的电动势作用相同' in stem:
                q_obj['answer'] = '磁动势'
            elif '叠片接缝增大' in stem:
                q_obj['answer'] = 'A'
                q_obj['explanation'] = '接缝增大意味着气隙长度增加，空气磁导率远小于铁芯，总磁阻随之增加。'
            elif '周围的气隙中' in stem:
                q_obj['answer'] = 'A'
                q_obj['explanation'] = '自然界不存在绝对的磁绝缘体，气隙和铁芯周围同样存在磁场（漏磁通与主气隙磁通）。'
            elif '应用叠加原理' in stem:
                q_obj['answer'] = 'A'
                q_obj['explanation'] = '叠加原理仅适用于线性系统（线性磁路，磁导率为常数）。'
            elif '叠片越厚' in stem:
                q_obj['answer'] = 'A'
                q_obj['explanation'] = '铁芯叠片越厚，涡流回路截面积越大、等效电阻越小，涡流损耗越大（P_e ∝ d²）。'
        elif rq['page'] == 38 and '三相变压器组不宜采用' in stem:
            q_obj['answer'] = 'C'
            q_obj['explanation'] = '三相组式变压器各相磁路独立，Yy 接法无三次谐波电流流通路径，三次谐波磁通畅通导致相电势严重畸变。'
        elif rq['page'] == 48 and '自耦变的变比通常小于' in stem:
            q_obj['stem'] = '（2024 届本科第二批）自耦变压器的变比通常小于（ ）。'
            q_obj['options'] = [
                {'key': 'A', 'text': '3:1'},
                {'key': 'B', 'text': '4:1'},
                {'key': 'C', 'text': '2:1'},
                {'key': 'D', 'text': '5:1'},
            ]
            q_obj['answer'] = 'A'
            q_obj['explanation'] = '自耦变压器变比过大时经济效益显著下降且高低压绝缘配合困难，电力系统中变比一般不超过 3（常用 2~3 以内）。'
        elif rq['page'] == 55 and '单相绕组的基波磁动势是' in stem:
            q_obj['stem'] = '单相绕组的基波磁动势是（ ），它可以分解成大小（ ）、转向（ ）、转速（ ）的两个旋转磁动势。'
            q_obj['answer'] = '脉振磁动势；相等（均为最大幅值的一半）；相反；相同'
        elif rq['page'] == 55 and '当ia=10A' in stem.replace(' ', ''):
            q_obj['stem'] = '三相对称绕组通以三相对称电流，顺时针相序（a-b-c-a），其中 i_a = 10 sin(ωt)，当 i_a = 10A 时，三相基波合成磁动势的幅值应位于（ ）。'
            q_obj['answer'] = 'A 相绕组轴线正方向'
            q_obj['explanation'] = '三相合成旋转磁动势的幅值总是重合于电流达到正最大值的那一相绕组轴线处。'
        elif rq['page'] == 55 and '当ia=-5A' in stem.replace(' ', ''):
            q_obj['stem'] = '三相对称绕组通以三相对称电流，顺时针相序（a-b-c-a），其中 i_a = 10 sin(ωt)，当 i_a = -5A（处于下降半周，ωt = 210°）时，三相基波合成磁动势的幅值应位于（ ）。'
            q_obj['answer'] = 'B 相绕组轴线负方向（或随 ωt=330° 时位于 C 相负方向，取决于过零方向）'
            q_obj['explanation'] = '当 ωt = 210° 时 i_a = -5A，i_b = 10 sin(90°) = +10A（正最大），合成磁动势幅值位于 B 相轴线；若 ωt = 330° 则 i_c = +10A 位于 C 相轴线。'
        elif rq['page'] == 57 and '3 次空间磁动势波的合成幅值为' in stem:
            q_obj['options'] = [
                {'key': 'A', 'text': '$0$'},
                {'key': 'B', 'text': '$\\frac{1}{3}F_1\\frac{k_{w3}}{k_{w1}}$'},
                {'key': 'C', 'text': '$F_1\\frac{k_{w3}}{k_{w1}}$'},
            ]
            q_obj['answer'] = 'A'
            q_obj['explanation'] = '对称三相绕组中，各相 3 次及 3 的倍数次谐波合成磁动势相互抵消，总合成幅值为 0。'
        elif rq['page'] == 57 and 'v 次谐波磁动势的转速为' in stem:
            q_obj['options'] = [
                {'key': 'A', 'text': '$n_1$'},
                {'key': 'B', 'text': '$v n_1$'},
                {'key': 'C', 'text': '$\\frac{n_1}{v}$'},
            ]
        elif rq['page'] == 69 and '空载电动势E0 为' in stem:
            q_obj['answer'] = 'C'
            q_obj['explanation'] = '相电压 $U_{N\\varphi} = \\frac{10.5}{\\sqrt{3}} = 6.062\\text{kV}$，额定电流 $I_N = \\frac{25000}{\\sqrt{3}\\times 10.5\\times 0.8} \\approx 1718\\text{A}$，$I_N X_s \\approx 12.03\\text{kV}$；由相量图得 $E_{0\\varphi} \\approx 16.4\\text{kV}$。'
        elif rq['page'] == 94 and any('600r/min 93' in o['text'] for o in q_obj['options']):
            for o in q_obj['options']:
                o['text'] = o['text'].replace('600r/min 93', '600r/min')
        elif rq['page'] == 98 and '定、转子磁动势相对静止' in stem:
            q_obj['stem'] = '定、转子磁动势相对静止是一切电机能正常运行的必要条件。（ ）'

        parsed.append(q_obj)

    # Render reference board-solution images from EM_ANS for the 5 classic worked examples
    ex1_plate = save_image(doc, 340, "em_ex01_nameplate_p17.webp")
    ex1_sol = render_page_crop(doc_ans, 17, "em_ex01_sol_p17.webp", (0.06, 0.72))
    ex2_sol = render_page_crop(doc_ans, 45, "em_ex02_sol_p45.webp", (0.06, 0.94))
    ex3_sol = render_page_crop(doc_ans, 46, "em_ex03_sol_p46.webp", (0.06, 0.55))
    ex4_sol = render_page_crop(doc_ans, 74, "em_ex04_sol_p74.webp", (0.42, 0.96))

    # Build the 5 worked examples / calculation problems requested by the user
    examples = [
        {
            'id': 'em-ex-01',
            'num': len(parsed) + 1,
            'chapter': '第二章 变压器',
            'section': '第三节 变压器的型号与额定值（典型计算例题）',
            'type': 'essay',
            'stem': '【典型例题·铭牌额定值计算】结合图示配电变压器铭牌参数，对该配电变压器的型号含义、额定容量、高/低压侧额定线电压与相电压、额定线电流及变比进行完整计算分析。',
            'options': [],
            'answer': '（1）读铭牌参数：三相油浸式配电变压器，查看图示铭牌中的额定容量 $S_N$、联结组标号、高/低压额定线电压 $U_{1N}$ / $U_{2N}$ 与阻抗电压 $u_k\\%$；\n（2）三相变压器额定线电流公式：$I_{1N} = \\frac{S_N}{\\sqrt{3}U_{1N}}$，$I_{2N} = \\frac{S_N}{\\sqrt{3}U_{2N}}$；\n（3）具体数值代入与相量联结核对请展开下方原版手写板书解答图核对。',
            'explanation': '三相变压器铭牌上的额定电压和额定电流均指线值，计算时切记分母带 √3。',
            'images': [f'assets/images/em/{ex1_plate}'],
            'answerImages': [f'assets/images/em/{ex1_sol}'],
            'page': 16
        },
        {
            'id': 'em-ex-02',
            'num': len(parsed) + 2,
            'chapter': '第二章 变压器',
            'section': '第八节 三绕组与自耦变压器（典型例题 1）',
            'type': 'single',
            'stem': '【典型例题 1】（2016 届本科第一批）一台额定电压为 220/110/35kV，额定容量为 120MVA 的自耦变压器，如果低压侧向中压侧传输 40MVA，且功率因数相同，则高压侧可传输至中压侧的最大功率为（ ）。',
            'options': [
                {'key': 'A', 'text': '40MVA'},
                {'key': 'B', 'text': '60MVA'},
                {'key': 'C', 'text': '80MVA'},
                {'key': 'D', 'text': '20MVA'},
            ],
            'answer': 'A',
            'explanation': '效益系数 $k_a = 1 - \\frac{U_2}{U_1} = 1 - \\frac{110}{220} = 0.5$，公共绕组额定容量 $= k_a S_N = 60\\text{MVA}$。低压侧向中压侧传 $40\\text{MVA}$ 全部经公共绕组，若高压侧向中压侧传 $S_{12}$，公共绕组中两电流同向叠加，故 $0.5 S_{12} + 40 \\le 60 \\to S_{12} \\le 40\\text{MVA}$。',
            'images': [],
            'answerImages': [f'assets/images/em/{ex2_sol}'],
            'page': 47
        },
        {
            'id': 'em-ex-03',
            'num': len(parsed) + 3,
            'chapter': '第二章 变压器',
            'section': '第八节 三绕组与自耦变压器（典型例题 1 扩展）',
            'type': 'essay',
            'stem': '【典型例题 1 扩展】一台额定电压为 220/110/35kV，额定容量为 120MVA 的自耦变压器，如果低压侧向中压侧传输 40MVA，且功率因数相同，则当高压侧向中压侧传输最大功率（40MVA）时，求此时：①串联绕组负荷；②公共绕组负荷；③低压绕组负荷；④高压向中压的传导负荷。',
            'options': [],
            'answer': '①串联绕组负荷 = k_a · S_12 = 0.5 × 40 = 20MVA；\n②公共绕组负荷 = 40 + 0.5 × 40 = 60MVA（达到公共绕组满载上限）；\n③低压绕组负荷 = 40MVA；\n④高压向中压的传导负荷 = (1 - k_a) · S_12 = 0.5 × 40 = 20MVA。',
            'explanation': '详细功率流向与计算过程可展开下方原版手写板书图核对。',
            'images': [],
            'answerImages': [f'assets/images/em/{ex2_sol}'],
            'page': 47
        },
        {
            'id': 'em-ex-04',
            'num': len(parsed) + 4,
            'chapter': '第二章 变压器',
            'section': '第八节 三绕组与自耦变压器（典型例题 2）',
            'type': 'essay',
            'stem': '【典型例题 2】（出自《发电厂电气主系统》第 3 版 许珉等编 P294 例 9-6）已知容量为 150MVA 的三相三绕组自耦变压器，额定电压为 242/121/11kV，容量比为 100/100/50，低压侧接有 60MW、功率因数为 0.8 的发电机一台，各侧功率因数相等。试求：\n(1) 发电机和 110kV 系统各向 220kV 系统传输功率 75MVA，计算各绕组的负荷和相应的绕组情况；\n(2) 如果 220kV 系统向 110kV 系统传输功率 75MVA，低压侧的发电机还可以向 110kV 系统传输多少功率？',
            'options': [],
            'answer': '效益系数 $k_a = 1 - \\frac{121}{242} = 0.5$，各绕组额定容量：串联绕组 = 公共绕组 = 低压绕组 = $0.5 \\times 150 = 75\\text{MVA}$；发电机视在功率 $S_G = \\frac{60}{0.8} = 75\\text{MVA}$。\n(1) 发电机(75MVA) + 110kV(75MVA) → 220kV(150MVA)：串联绕组负荷 = 0.5×150 = 75MVA，低压绕组 = 75MVA，公共绕组中中→高与低→高电磁功率反向抵消：|75 - 0.5×150| = 0MVA（公共绕组零负荷，最有利运行方式）；\n(2) 220kV → 110kV 传输 75MVA 时，公共绕组已承担电磁负荷 0.5×75 = 37.5MVA，且低→中电流与高→中公共绕组电流同向叠加，故发电机最多还可向 110kV 系统传输 75 - 37.5 = 37.5MVA（有功 30MW）。',
            'explanation': '完整分步推演请参考下方原版手写板书图。',
            'images': [],
            'answerImages': [f'assets/images/em/{ex2_sol}', f'assets/images/em/{ex3_sol}'],
            'page': 47
        },
        {
            'id': 'em-ex-05',
            'num': len(parsed) + 5,
            'chapter': '第四章 同步电机',
            'section': '同步电抗与短路比（典型例题 6-3）',
            'type': 'essay',
            'stem': '【典型例题 6-3】（出自汤蕴璆《电机学》第 5 版 P270）有一台 25000kW、10.5kV（Y 联结）、$\\cos\\varphi = 0.8$（滞后）的汽轮发电机，从空载和短路试验中得到下列数据：\n• 空载特性上查得：相电压 $U_{N\\varphi} = \\frac{10.5}{\\sqrt{3}}\\text{kV}$ 时，$I_{f0} = 155\\text{A}$；\n• 短路特性上查得：$I = I_N = 1718\\text{A}$ 时，$I_{fk} = 280\\text{A}$；\n• 气隙线上查得：$E_0 = \\frac{22.4}{\\sqrt{3}}\\text{kV}$ 时，$I_f = 280\\text{A}$。\n试求同步电抗的不饱和值及饱和值的标幺值和实际值，以及短路比 $K_c$。',
            'options': [],
            'answer': '基准阻抗 $Z_N = \\frac{U_{N\\varphi}}{I_N} = \\frac{10500}{\\sqrt{3}\\times 1718} \\approx 3.53\\Omega$：\n（1）不饱和同步电抗实际值：$X_d(\\text{不饱和}) = \\frac{E_0(\\text{气隙线})}{I_N} = \\frac{22400}{\\sqrt{3}\\times 1718} \\approx 7.53\\Omega$；\n不饱和标幺值：$X_d^*(\\text{不饱和}) = \\frac{7.53}{3.53} = \\frac{22.4}{10.5} \\approx 2.13$；\n（2）饱和同步电抗标幺值：$X_d^*(\\text{饱和}) = \\frac{I_{fk}}{I_{f0}} = \\frac{280}{155} \\approx 1.81$；\n饱和实际值：$X_d(\\text{饱和}) = 1.81 \\times 3.53 \\approx 6.38\\Omega$；\n（3）短路比：$K_c = \\frac{I_{f0}}{I_{fk}} = \\frac{155}{280} \\approx 0.554$（即 $K_c = \\frac{1}{X_d^*(\\text{饱和})}$）。',
            'explanation': '注意短路比 $K_c = \\frac{1}{X_d^*(\\text{饱和})}$，不饱和值一定要从气隙线（线性延长线）读取电动势！可展开下方原版手写板书图核对。',
            'images': [],
            'answerImages': [f'assets/images/em/{ex4_sol}'],
            'page': 76
        },
    ]

    # Insert examples into their corresponding chapters cleanly (or keep sequential order by chapter & page)
    all_qs = parsed + examples
    # Sort stably by chapter order, then page, then original order
    ch_order = {
        '第一章 磁路和磁性材料': 1,
        '第二章 变压器': 2,
        '第三章 交流电机理论的共同问题': 3,
        '第四章 同步电机': 4,
        '第五章 感应电机': 5,
    }
    all_qs.sort(key=lambda q: (ch_order.get(q['chapter'], 99), q['page'], 0 if not q['id'].startswith('em-ex') else 1))
    for i, q in enumerate(all_qs):
        q['num'] = i + 1
        q['id'] = f"em-{i+1:03d}"

    # Final Audit
    issues = []
    for q in all_qs:
        if not q['answer']:
            issues.append(f"Q{q['num']} (p.{q['page']}): MISSING ANSWER | {q['stem'][:40]}")
        if q['type'] in ('single', 'multi') and len(q['options']) < 2:
            issues.append(f"Q{q['num']} (p.{q['page']}): TOO FEW OPTIONS ({len(q['options'])})")
        if q['type'] in ('single', 'multi') and q['answer']:
            opt_keys = {o['key'] for o in q['options']}
            for ch in q['answer']:
                if ch not in opt_keys:
                    issues.append(f"Q{q['num']} (p.{q['page']}): ANS '{q['answer']}' NOT IN {opt_keys}")

    print(f"EM total (incl. 5 worked examples): {len(all_qs)} | Types: {Counter(q['type'] for q in all_qs)}")
    print(f"Chapters: {Counter(q['chapter'] for q in all_qs)}")
    print(f"Audit issues: {len(issues)}")
    for iss in issues:
        print("  -", iss)

    all_txt = "".join(q['stem'] + "".join(o['text'] for o in q['options']) + q['answer'] + q['explanation'] for q in all_qs)
    weird = Counter(c for c in all_txt if ord(c) > 127 and not ('\u4e00' <= c <= '\u9fff') and c not in '，。？！：；、“”‘’（）【】《》—…·°±×÷≤≥≠≈→←↑↓ΩΦαβγδθλμπρωφΔΣ√²³¹⁰⁻⁺₀₁₂₃₄₅₆₇₈₉℃％～∙・①②③④⑤「」στ•')
    print("Remaining unusual chars in EM:", weird.most_common(20))

    with open(OUT_JSON, 'w', encoding='utf-8') as f:
        json.dump({
            'courseId': 'em',
            'courseName': '电机学',
            'source': 'B站纪真（十万伏特皮卡丘）电机学配套习题与典型例题（第1–5章）',
            'total': len(all_qs),
            'questions': all_qs
        }, f, ensure_ascii=False, indent=2)
    print("Saved clean EM JSON:", OUT_JSON)

if __name__ == '__main__':
    parse_em()
