import fitz
import json
import os
import re
import sys
import io
from collections import Counter
from PIL import Image

sys.stdout.reconfigure(encoding='utf-8')

PE_ANS = r"D:\BaiduNetdiskDownload\b站电力电子课程配套资料(纪真-十万伏特皮卡丘)\b站电力电子配套习题-纪真十万伏特皮卡丘_带答案版.pdf"
OUT_JSON = r"D:\Antigravity\Electrical_Quiz_Web\public\data\power-electronics.json"
IMG_DIR = r"D:\Antigravity\Electrical_Quiz_Web\public\assets\images\pe"

os.makedirs(IMG_DIR, exist_ok=True)

CHAR_REPLACEMENTS = {
    '\uf06d': 'μ', '\uf077': 'ω', '\uf061': 'α', '\uf062': 'β',
    '\uf067': 'γ', '\uf066': 'φ', '\uf070': 'π', '\uf057': 'Ω',
    '\uf046': 'Φ', '\uf0b1': '±', '\uf0b0': '°', '\uf0d7': '×',
    '\uf0a3': '≤', '\uf0b3': '≥', '\uf0b9': '≠', '\uf0bb': '≈',
    '\uf0ae': '→', '\u00a0': ' ', '\u3000': ' ',
    # Cambria Math / WPS shifted glyphs
    'ƿ': 'U', 'ǈ': 'd', 'ǅ': 'a', 'ǆ': 'b', 'ǂ': 'X', 'Ƭ': 'B',
    'Ƴ': 'I', 'ؼ': 'π', 'Ǚ': 'u', '푠': 's', 'Ǎ': 'i', 'ǒ': 'n',
    'م': 'ω', 'ǘ': 't', 'º': '°', 'µ': 'μ', '∽': '～', '−': '-',
}

def clean_text(s):
    for k, v in CHAR_REPLACEMENTS.items():
        s = s.replace(k, v)
    s = re.sub(r'[ \t]+', ' ', s)
    return s.strip()

def extract_stream(pdf_path):
    doc = fitz.open(pdf_path)
    items = []

    xref_pages = {}
    for pno in range(len(doc)):
        for info in doc[pno].get_image_info(xrefs=True):
            xr = info['xref']
            xref_pages.setdefault(xr, set()).add(pno)
    ignored_xrefs = {xr for xr, ps in xref_pages.items() if len(ps) > 10}

    for pno in range(1, len(doc)):  # skip cover page 0
        page = doc[pno]
        page_items = []
        d = page.get_text("dict")
        for b in d["blocks"]:
            if b["type"] == 0:
                for line in b["lines"]:
                    y0 = line["bbox"][1]
                    if y0 < 52:
                        continue
                    txt = clean_text("".join(span["text"] for span in line["spans"]))
                    if not txt:
                        continue
                    if "哔哩哔哩：纪真" in txt or "空间动态QQ" in txt or txt == "纪真—十万伏特皮卡丘":
                        continue
                    if re.fullmatch(r'\d{1,3}', txt) and (y0 < 90 or y0 > page.rect.height - 65):
                        continue
                    page_items.append((y0, line["bbox"][0], 'text', pno + 1, txt))

        for info in page.get_image_info(xrefs=True):
            xr = info['xref']
            bbox = info['bbox']
            if xr in ignored_xrefs or bbox[1] < 52:
                continue
            if (bbox[2] - bbox[0]) < 25 or (bbox[3] - bbox[1]) < 18:
                continue
            page_items.append((bbox[1], bbox[0], 'img', pno + 1, (xr, bbox)))

        page_items.sort(key=lambda x: (round(x[0] / 3) * 3, x[1]))
        items.extend(page_items)

    return doc, items

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

# Exact overrides for formula/fill/essay questions verified against source PDF
PE_OVERRIDES = {
    18: {
        'options': [
            {'key': 'A', 'text': '见图 A'},
            {'key': 'B', 'text': '见图 B'},
            {'key': 'C', 'text': '见图 C'},
            {'key': 'D', 'text': '见图 D'},
        ],
    },
    34: {
        'options': [
            {'key': 'A', 'text': '电感电流稳定'},
            {'key': 'B', 'text': '电容电压稳定'},
            {'key': 'C', 'text': '一个周期之内电感电压有正有负，且为正的面积与为负的面积相等'},
            {'key': 'D', 'text': '一个周期之内电容电流有正有负，且为正的面积与为负的面积相等'},
        ],
    },
    36: {
        'stem': '平衡的电力电子电路中，电感需要遵循什么原则（ ）',
        'options': [
            {'key': 'A', 'text': '伏秒平衡'},
            {'key': 'B', 'text': '荷电平衡'},
            {'key': 'C', 'text': '电感电流一个完整周期内必须不断增加'},
            {'key': 'D', 'text': '电感电流一个完整周期内不能一直增加'},
        ],
    },
    45: {
        'stem': '如图所示，当晶闸管流过图示（半波整流导通角为0°）波形的电流时，额定电流为100A的晶闸管，实际允许通过的电流平均值为（ ）？',
        'options': [
            {'key': 'A', 'text': '90.7A'},
            {'key': 'B', 'text': '70.7A'},
            {'key': 'C', 'text': '100A'},
            {'key': 'D', 'text': '157A'},
        ],
    },
    49: {
        'stem': '如图波形所示，当晶闸管流过导通角为90°的半波整流时，若选取的晶闸管额定电流为100A，则实际使用时允许流过的最大平均电流为（ ）？',
        'options': [
            {'key': 'A', 'text': '90.7A'},
            {'key': 'B', 'text': '70.7A'},
            {'key': 'C', 'text': '100A'},
            {'key': 'D', 'text': '157A'},
        ],
    },
    64: {
        'type': 'fill',
        'stem': '写出下列电力电子器件的英文缩写：①晶闸管：（ ）；②电力晶体管：（ ）；③门极可关断晶闸管：（ ）；④电力场效应晶体管：（ ）；⑤绝缘栅双极性晶体管：（ ）',
        'answer': 'SCR；GTR(BJT)；GTO；MOSFET；IGBT',
    },
    65: {
        'stem': '下列电气符号中，GTO 的电气符号是（ ）。',
        'options': [
            {'key': 'A', 'text': '见图 A'},
            {'key': 'B', 'text': '见图 B'},
            {'key': 'C', 'text': '见图 C'},
            {'key': 'D', 'text': '见图 D'},
        ],
    },
    84: {
        'options': [
            {'key': 'A', 'text': '$0.45U_2\\cos\\alpha$'},
            {'key': 'B', 'text': '$0.45U_2\\frac{1+\\cos\\alpha}{2}$'},
            {'key': 'C', 'text': '$0.9U_2\\cos\\alpha$'},
            {'key': 'D', 'text': '$0.9U_2\\frac{1+\\cos\\alpha}{2}$'},
        ],
    },
    85: {
        'options': [
            {'key': 'A', 'text': '$0.45U_2\\cos\\alpha$'},
            {'key': 'B', 'text': '$0.45U_2\\frac{1+\\cos\\alpha}{2}$'},
            {'key': 'C', 'text': '$0.9U_2\\cos\\alpha$'},
            {'key': 'D', 'text': '$0.9U_2\\frac{1+\\cos\\alpha}{2}$'},
        ],
    },
    86: {
        'options': [
            {'key': 'A', 'text': '$0.9U_2\\cos\\alpha$'},
            {'key': 'B', 'text': '$1.17U_2\\frac{1+\\cos\\alpha}{2}$'},
            {'key': 'C', 'text': '$1.17U_2\\cos\\alpha$'},
            {'key': 'D', 'text': '$0.9U_2\\frac{1+\\cos\\alpha}{2}$'},
        ],
    },
    87: {
        'options': [
            {'key': 'A', 'text': '$0.9U_2\\cos\\alpha$'},
            {'key': 'B', 'text': '$1.17U_2\\frac{1+\\cos\\alpha}{2}$'},
            {'key': 'C', 'text': '$1.17U_2\\cos\\alpha$'},
            {'key': 'D', 'text': '$0.675U_2\\left[1+\\cos\\left(\\frac{\\pi}{6}+\\alpha\\right)\\right]$'},
        ],
    },
    88: {
        'options': [
            {'key': 'A', 'text': '$1.17U_2\\cos\\alpha$'},
            {'key': 'B', 'text': '$2.34U_2\\frac{1+\\cos\\alpha}{2}$'},
            {'key': 'C', 'text': '$2.34U_2\\cos\\alpha$'},
            {'key': 'D', 'text': '$2.34U_2\\left[1+\\cos\\left(\\frac{\\pi}{3}+\\alpha\\right)\\right]$'},
        ],
    },
    91: {
        'stem': '三相半波全控整流电路带阻感性负载，变压器二次侧相电压有效值为 $U_2 = 220\\text{V}$，控制角为 $\\alpha = 30^\\circ$，输出的直流电压平均值为（ ）。',
        'options': [
            {'key': 'A', 'text': '74.25V'},
            {'key': 'B', 'text': '85.7V'},
            {'key': 'C', 'text': '171.5V'},
            {'key': 'D', 'text': '223V'},
        ],
    },
    94: {
        'stem': '三相半波全控整流电路带阻感负载，变压器二次侧相电压有效值为 $U_2 = 220\\text{V}$，控制角为 $\\alpha = 60^\\circ$，输出的直流电压平均值为（ ）。',
        'options': [
            {'key': 'A', 'text': '277V'},
            {'key': 'B', 'text': '85.7V'},
            {'key': 'C', 'text': '171.5V'},
            {'key': 'D', 'text': '128.7V'},
        ],
    },
    150: {
        'stem': '单相桥式全控整流电路带电阻负载，电源电压为 $u_2(t) = \\sqrt{2}U_2\\sin(\\omega t)$，控制角 $\\alpha = 30^\\circ$ 时触发晶闸管导通。则当（ ）时晶闸管关断，关断的原因为（ ）',
    },
    167: {
        'options': [
            {'key': 'A', 'text': '$\\frac{\\sqrt{2}}{2}U_2$，$\\frac{\\sqrt{2}}{2}U_2$'},
            {'key': 'B', 'text': '$\\sqrt{2}U_2$，$\\frac{\\sqrt{2}}{2}U_2$'},
            {'key': 'C', 'text': '$\\frac{\\sqrt{2}}{2}U_2$，$\\sqrt{2}U_2$'},
            {'key': 'D', 'text': '$\\sqrt{2}U_2$，$\\sqrt{2}U_2$'},
        ],
    },
    168: {
        'options': [
            {'key': 'A', 'text': '$\\frac{\\sqrt{2}}{2}U_2$，$\\frac{\\sqrt{2}}{2}U_2$'},
            {'key': 'B', 'text': '$\\sqrt{2}U_2$，$\\frac{\\sqrt{2}}{2}U_2$'},
            {'key': 'C', 'text': '$\\frac{\\sqrt{2}}{2}U_2$，$\\sqrt{2}U_2$'},
            {'key': 'D', 'text': '$\\sqrt{2}U_2$，$\\sqrt{2}U_2$'},
        ],
    },
    170: {
        'options': [
            {'key': 'A', 'text': '$\\frac{\\sqrt{2}}{2}U_2$，$\\frac{\\sqrt{2}}{2}U_2$'},
            {'key': 'B', 'text': '$\\sqrt{6}U_2$，$\\sqrt{6}U_2$'},
            {'key': 'C', 'text': '$\\sqrt{6}U_2$，$\\sqrt{2}U_2$'},
            {'key': 'D', 'text': '$\\sqrt{2}U_2$，$\\sqrt{6}U_2$'},
        ],
    },
    171: {
        'options': [
            {'key': 'A', 'text': '$\\frac{\\sqrt{2}}{2}U_2$，$\\frac{\\sqrt{2}}{2}U_2$'},
            {'key': 'B', 'text': '$\\sqrt{6}U_2$，$\\sqrt{6}U_2$'},
            {'key': 'C', 'text': '$\\sqrt{6}U_2$，$\\sqrt{2}U_2$'},
            {'key': 'D', 'text': '$\\sqrt{2}U_2$，$\\sqrt{6}U_2$'},
        ],
    },
    174: {
        'options': [
            {'key': 'A', 'text': '是瞬时功率的平均值'},
            {'key': 'B', 'text': '是瞬时功率的最大峰值'},
            {'key': 'C', 'text': '是瞬时功率的均方根值'},
            {'key': 'D', 'text': '是瞬时功率的正、负交变的最大峰值'},
        ],
    },
    190: {
        'stem': '三相半波整流，考虑变压器漏感 $X_B$ 的存在，输出电压下降值 $\\Delta U_d$ 为（ ）',
        'options': [
            {'key': 'A', 'text': '$\\frac{2}{2\\pi}X_B I_d$'},
            {'key': 'B', 'text': '$\\frac{3}{2\\pi}X_B I_d$'},
            {'key': 'C', 'text': '$\\frac{4}{2\\pi}X_B I_d$'},
            {'key': 'D', 'text': '$\\frac{6}{2\\pi}X_B I_d$'},
        ],
    },
    195: {
        'options': [
            {'key': 'A', 'text': '$U_a$'},
            {'key': 'B', 'text': '$U_b$'},
            {'key': 'C', 'text': '$\\frac{U_a + U_b}{2}$'},
            {'key': 'D', 'text': '$\\frac{U_a - U_b}{2}$'},
        ],
        'answer': 'C',
    },
    204: {
        'options': [
            {'key': 'A', 'text': '相位相同'},
            {'key': 'B', 'text': '相差 $\\frac{\\pi}{6}$'},
            {'key': 'C', 'text': '相差 $\\frac{\\pi}{3}$'},
            {'key': 'D', 'text': '相差 $\\pi$'},
        ],
    },
    209: {
        'type': 'essay',
        'stem': '【单相桥式半控带续流二极管】有一大电感负载采用单相桥式半控带续流二极管的整流电路供电，电路如图所示。负载电阻为 5Ω，输入电压为 220V，晶闸管控制角 α = 60°，求流过晶闸管、二极管的电流平均值及有效值。',
        'answer': '$U_d = 149\\text{V}$；$I_d = 30\\text{A}$；$I_{VT1,d} = 10\\text{A}$；$I_{VD} = 10\\text{A}$；$I_{VT,\\text{rms}} = 17.3\\text{A}$；$I_{VD,\\text{rms}} = 17.3\\text{A}$',
    },
    210: {
        'type': 'essay',
        'stem': '【晶闸管串联的单相桥式半控】有一大电感负载采用单相半控桥式带续流二极管的整流电路供电，电路如图所示。负载电阻为 5Ω，输入电压为 220V，晶闸管控制角 α = 60°，求流过晶闸管、二极管的电流平均值及有效值。',
        'answer': '$U_d = 149\\text{V}$；$I_d = 30\\text{A}$；$I_{VT1,d} = 10\\text{A}$；$I_{VD} = 20\\text{A}$；$I_{VT,\\text{rms}} = 17.3\\text{A}$；$I_{VD,\\text{rms}} = 24.5\\text{A}$',
    },
    211: {
        'type': 'essay',
        'stem': '【三相桥式全控带反电动势负载】三相桥式全控整流电路，$U_2 = 220\\text{V}$，$\\alpha = \\frac{\\pi}{3}$。反电动势负载，$E_M = 100\\text{V}$，$R = 20\\Omega$，$L$ 值极大。计算直流输出电压 $U_d$、电流 $I_d$、变压器二次电流有效值 $I_{2,\\text{rms}}$。',
        'answer': '$U_d = 257.4\\text{V}$；$I_d = 7.87\\text{A}$；$I_{2,\\text{rms}} = 6.43\\text{A}$',
    },
    212: {
        'type': 'essay',
        'stem': '【变压器漏抗对整流电路影响】三相桥式全控整流电路，$U_2 = 220\\text{V}$，$\\alpha = 0^\\circ$。阻感性负载，$R = 5\\Omega$，$L$ 值极大。变压器漏抗折算到二次侧为 $X_B = 0.3\\Omega$，计算直流输出电压 $U_d$、电流 $I_d$、换相压降 $\\Delta U_d$、换相重叠角 $\\gamma$。',
        'answer': '$U_d = 486.9\\text{V}$；$I_d = 97.38\\text{A}$；换相压降 $\\Delta U_d = 27.9\\text{V}$；换相重叠角 $\\gamma = 26.93^\\circ$',
    },
    215: {
        'type': 'fill',
        'stem': '功率器件的换流方式包括器件换流、电网换流、负载换流及强迫换流，其中后三种换流方式主要是针对（ ）而言的。',
        'answer': '晶闸管',
    },
    216: {
        'type': 'fill',
        'stem': '有源逆变电路交流侧连接（ ），无源逆变电路的交流侧连接（ ）；电压型逆变电路直流侧并联（ ），电流型逆变电路直流侧串联（ ）。',
        'answer': '交流电网；负载；大电容；大电感',
    },
    250: {
        'type': 'essay',
        'stem': '「数学基础」写出下图单相全桥逆变电路输出方波的傅里叶展开式。',
        'answer': '$u_o(\\omega t) = \\frac{4U_d}{\\pi}\\left[\\sin(\\omega t) + \\frac{1}{3}\\sin(3\\omega t) + \\frac{1}{5}\\sin(5\\omega t) + \\cdots\\right]$（仅含奇次谐波）',
    },
    261: {
        'stem': '电压型三相桥式逆变电路，当 VT1、VT2、VT6 导通时，输出 A 相的相电压为（ ）。',
        'options': [
            {'key': 'A', 'text': '$\\frac{1}{3}U_d$'},
            {'key': 'B', 'text': '$-\\frac{1}{3}U_d$'},
            {'key': 'C', 'text': '$\\frac{2}{3}U_d$'},
            {'key': 'D', 'text': '$-\\frac{2}{3}U_d$'},
        ],
    },
    262: {
        'stem': '电压型三相桥式逆变电路，当 VT1、VT2、VT6 导通时，输出 B 相的相电压为（ ）。',
        'options': [
            {'key': 'A', 'text': '$\\frac{1}{3}U_d$'},
            {'key': 'B', 'text': '$-\\frac{1}{3}U_d$'},
            {'key': 'C', 'text': '$\\frac{2}{3}U_d$'},
            {'key': 'D', 'text': '$-\\frac{2}{3}U_d$'},
        ],
    },
    263: {
        'options': [
            {'key': 'A', 'text': '$U_d$'},
            {'key': 'B', 'text': '$-U_d$'},
            {'key': 'C', 'text': '$0$'},
            {'key': 'D', 'text': '$-\\frac{2}{3}U_d$'},
        ],
    },
    264: {
        'options': [
            {'key': 'A', 'text': '$U_d$'},
            {'key': 'B', 'text': '$-U_d$'},
            {'key': 'C', 'text': '$0$'},
            {'key': 'D', 'text': '$-\\frac{2}{3}U_d$'},
        ],
    },
    267: {
        'type': 'essay',
        'stem': '「数学基础」写出下图三相电压型逆变电路（180°导电）相电压阶梯波与线电压矩形波的傅里叶展开式。',
        'answer': '相电压：$u_{UN}(\\omega t) = \\frac{2U_d}{\\pi}\\left[\\sin(\\omega t) + \\frac{1}{5}\\sin(5\\omega t) + \\frac{1}{7}\\sin(7\\omega t) + \\frac{1}{11}\\sin(11\\omega t) + \\cdots\\right]$（仅含 $6k\\pm 1$ 次谐波）\n线电压：$u_{UV}(\\omega t) = \\frac{2\\sqrt{3}U_d}{\\pi}\\left[\\sin(\\omega t+30^\\circ) - \\frac{1}{5}\\sin 5(\\omega t+30^\\circ) - \\frac{1}{7}\\sin 7(\\omega t+30^\\circ) + \\frac{1}{11}\\sin 11(\\omega t+30^\\circ) + \\cdots\\right]$（不含 3 的倍数次谐波）',
    },
    287: {
        'type': 'fill',
        'stem': '三相电压型逆变电路在未采用 PWM 控制时，输出线电压波形中所含的谐波次数为（ ）次，谐波幅值与谐波次数成（ ）关系；而采用双极性 SPWM 调制后，输出电压的谐波特点为：不含（ ）谐波，并且谐波主要分布在（ ）附近。',
        'answer': '6k±1；反比；低次；ωc, 2ωc, 3ωc...（载波频率及其倍频）',
    },
    298: {
        'type': 'judge',
        'stem': '比起自然采样法，规则采样法的计算非常简单，计算量大大减少（ ）',
        'answer': '正确',
    },
    303: {
        'type': 'fill',
        'stem': '直流斩波电路按照输入电压与输出电压的高低变化来分类有（ ）斩波电路、（ ）斩波电路和（ ）斩波电路。',
        'answer': '降压；升压；升降压',
    },
    304: {
        'type': 'fill',
        'stem': '升压斩波电路之所以能使输出电压高于电源电压，关键有两个原因：一是 L 储能之后具有使（ ）的作用；二是电容 C 可将输出电压（ ）。',
        'answer': '电压泵升；保持住',
    },
    305: {
        'type': 'essay',
        'stem': '在图示的 Boost 升压斩波电路中，已知 $U_S = 50\\text{V}$，负载电阻 $R = 20\\Omega$，$L$ 值和 $C$ 值极大，采用脉宽调制控制方式，当 $T = 40\\mu\\text{s}$，$t_{\\text{on}} = 25\\mu\\text{s}$ 时，计算输出电压平均值 $U_o$、输出电流平均值 $I_o$。',
        'answer': '$U_o = U_S \\cdot \\frac{T}{T - t_{\\text{on}}} = 50 \\times \\frac{40}{15} \\approx 133.3\\text{V}$；$I_o = \\frac{U_o}{R} \\approx 6.67\\text{A}$',
    },
    306: {
        'type': 'essay',
        'stem': '在图中的 Buck 降压斩波电路带电动机反电动势负载中，已知 $U_S = 200\\text{V}$，$R = 10\\Omega$，$L$ 值极大，$E_M = 30\\text{V}$。采用脉宽调制控制方式，当 $T = 50\\mu\\text{s}$，$t_{\\text{on}} = 20\\mu\\text{s}$ 时，计算输出电压平均值 $U_o$、输出电流平均值 $I_o$。',
        'answer': '$U_o = U_S \\cdot \\frac{t_{\\text{on}}}{T} = 200 \\times \\frac{20}{50} = 80\\text{V}$；$I_o = \\frac{U_o - E_M}{R} = \\frac{80 - 30}{10} = 5\\text{A}$',
    },
    307: {
        'type': 'fill',
        'stem': '直流斩波电路在改变负载的直流电压时，常用的控制方式有（ ）、（ ）和（ ）三种。',
        'answer': '定频调宽控制(PWM)；等宽调频控制(PFM)；脉宽与频率同时控制(混合调制)',
    },
    308: {
        'type': 'single',
        'answer': 'B',
    },
    312: {
        'type': 'judge',
        'stem': '单相交流调压电路，带电感性负载时，不能用窄脉冲触发，应采用宽脉冲（ ）。',
        'answer': '正确',
    },
    313: {
        'options': [
            {'key': 'A', 'text': '$\\frac{\\pi}{6}$'},
            {'key': 'B', 'text': '$\\frac{\\pi}{3}$'},
            {'key': 'C', 'text': '$\\frac{2\\pi}{3}$'},
            {'key': 'D', 'text': '$\\frac{\\pi}{2}$'},
        ],
    },
    322: {
        'type': 'essay',
        'stem': '某单相反并联调功电路，采用过零触发控制，负载为大惯性环节。若全导通时电压 $U_2 = 220\\text{V}$，负载电阻 $R = 1\\Omega$，在设定周期 $T_c$ 内，使晶闸管导通 $0.3\\text{s}$，断开 $0.2\\text{s}$，计算送到电阻负载上的有效电压 $U_o$ 和平均功率 $P$。',
        'answer': '$T_c = 0.3 + 0.2 = 0.5\\text{s}$，占空比 $M = \\frac{0.3}{0.5} = 0.6$；\n负载电压有效值 $U_o = U_2 \\sqrt{\\frac{t_{\\text{on}}}{T_c}} = 220 \\times \\sqrt{0.6} \\approx 170.41\\text{V}$；\n负载平均功率 $P = \\frac{U_o^2}{R} = \\frac{U_2^2}{R} \\cdot \\frac{t_{\\text{on}}}{T_c} = 220^2 \\times 0.6 = 29040\\text{W} = 29.04\\text{kW}$。',
    },
    325: {
        'stem': '晶闸管投切电容（Thyristor Switched Capacitor, TSC）是典型的（ ）应用技术。',
    },
    332: {
        'type': 'judge',
        'stem': '交-交直接变频器只能使输出的频率小于输入频率，而不能大于输入频率（ ）。',
        'answer': '正确',
    },
    333: {
        'options': [
            {'key': 'A', 'text': '$\\frac{1}{6} \\sim \\frac{1}{4}$，10Hz'},
            {'key': 'B', 'text': '$\\frac{1}{3} \\sim \\frac{1}{2}$，20Hz'},
            {'key': 'C', 'text': '1 倍，50Hz'},
            {'key': 'D', 'text': '2～3 倍，100Hz'},
        ],
    },
    334: {
        'options': [
            {'key': 'A', 'text': '二者都可以可逆运行，实现功率双向传输'},
            {'key': 'B', 'text': '交-交变频器最大变频范围为电网频率 $\\frac{1}{2}$ 以下，变频范围有限制'},
            {'key': 'C', 'text': '交-直-交变频器最大变频范围为电网频率 $\\frac{1}{2}$ 以下，变频范围有限制'},
            {'key': 'D', 'text': '交-交变频器一般只适用于低速大容量拖动场合'},
        ],
    },
}

def parse_pe():
    doc, items = extract_stream(PE_ANS)

    cur_chapter = "第1章 认识电力电子技术"
    cur_section = ""
    raw_qs = []
    cur_q = None
    expected_num = 1

    ch_re = re.compile(r'^第\s*(\d+)\s*章\s*(.+)$')
    q_start_re = re.compile(r'^(\d+)\s*[\.。．、]\s*(.*)$')

    for _, _, kind, pno, val in items:
        if kind == 'img':
            xref, bbox = val
            if cur_q is not None:
                cur_q['raw_imgs'].append((pno, xref))
            continue

        line = val
        m_ch = ch_re.match(line)
        if m_ch:
            cur_chapter = f"第{m_ch.group(1)}章 {m_ch.group(2).strip()}"
            cur_section = ""
            continue

        if re.match(r'^[一二三四五六七八九十]+、', line) or re.match(r'^\d+\.\d+\s*\S', line):
            if not re.match(r'^\d+\.\d+\s*[VvAaWwΩkKmM%]', line):
                cur_section = line
                continue
        if re.match(r'^\d+、', line):
            num_val = int(re.match(r'^(\d+)、', line).group(1))
            if num_val < expected_num - 2 and len(line) < 35 and '（' not in line and '(' not in line:
                cur_section = line
                continue

        m_q = q_start_re.match(line)
        if m_q:
            num = int(m_q.group(1))
            rest = m_q.group(2).strip()
            is_new_q = False
            if abs(num - expected_num) <= 3:
                is_new_q = True
            elif num > expected_num and num <= expected_num + 10 and (
                re.search(r'^[（(](单选|多选|判断|填空)[)）]', rest) or '（' in rest or '(' in rest
            ):
                is_new_q = True
            if is_new_q:
                if cur_q is not None:
                    raw_qs.append(cur_q)
                cur_q = {
                    'num': num,
                    'chapter': cur_chapter,
                    'section': cur_section,
                    'page': pno,
                    'lines': [rest] if rest else [],
                    'raw_imgs': []
                }
                expected_num = num + 1
                continue

        if cur_q is not None:
            cur_q['lines'].append(line)

    if cur_q is not None:
        raw_qs.append(cur_q)

    parsed = []
    issues = []

    for idx, rq in enumerate(raw_qs):
        qnum = rq['num']
        full_lines = list(rq['lines'])

        answer = ""
        explanation = ""
        ans_lines_idx = set()

        for i, ln in enumerate(full_lines):
            m_ans = re.match(r'^答案\s*[:：;；]?\s*(.*)$', ln)
            if m_ans:
                rest = m_ans.group(1).strip()
                m_exp = re.search(r'解析\s*[:：]\s*(.+)$', rest)
                if m_exp:
                    explanation = m_exp.group(1).strip()
                    rest = rest[:m_exp.start()].strip()
                answer = rest
                ans_lines_idx.add(i)
                if not answer and i + 1 < len(full_lines):
                    answer = full_lines[i + 1].strip()
                    ans_lines_idx.add(i + 1)
            elif re.match(r'^解析\s*[:：]', ln):
                explanation = (explanation + " " + re.sub(r'^解析\s*[:：]\s*', '', ln)).strip()
                ans_lines_idx.add(i)
                # capture trailing lines of explanation
                j = i + 1
                while j < len(full_lines) and not re.match(r'^[A-E][\.\s、]', full_lines[j]):
                    explanation = (explanation + full_lines[j]).strip()
                    ans_lines_idx.add(j)
                    j += 1

        body_lines = []
        for i, ln in enumerate(full_lines):
            if i in ans_lines_idx:
                continue
            m_exp = re.search(r'解析\s*[:：]\s*(.+)$', ln)
            if m_exp:
                explanation = (explanation + " " + m_exp.group(1).strip()).strip()
                ln = ln[:m_exp.start()].strip()
            m_inline = re.search(r'答案\s*[:：;；]\s*(.+)$', ln)
            if m_inline:
                if not answer:
                    answer = m_inline.group(1).strip()
                ln = ln[:m_inline.start()].strip()
            if ln:
                body_lines.append(ln)

        opt_start_re = re.compile(r'^([A-E])\s*[\.。．、,，:：·\s]\s*(.*)$')
        opt_nodelim_re = re.compile(r'^([A-E])([\u4e00-\u9fa5\d].*)$')

        stem_parts = []
        options = []
        in_options = False

        for ln in body_lines:
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

        explicit_type = None
        m_type = re.match(r'^[（(]\s*(单选|多选|判断|填空|填空题|简答题)\s*[)）]\s*', stem)
        if m_type:
            t_map = {'单选': 'single', '多选': 'multi', '判断': 'judge', '填空': 'fill', '填空题': 'fill', '简答题': 'essay'}
            explicit_type = t_map[m_type.group(1)]
            stem = stem[m_type.end():].strip()

        leaked = []
        def strip_leaked(m):
            inner = m.group(2).strip()
            if re.fullmatch(r'[A-E]{1,5}', inner) and options:
                leaked.append(inner)
                return m.group(1) + "  " + m.group(3)
            if inner in ('对', '错', '正确', '错误', '√', '×', 'T', 'F'):
                leaked.append(inner)
                return m.group(1) + "  " + m.group(3)
            return m.group(0)

        stem = re.sub(r'([（(])\s*([^()（）]{1,6})\s*([)）])', strip_leaked, stem)
        m_broken = re.search(r'[（(]\s*(对|错|正确|错误|[A-E]{1,4})\s*$', stem)
        if m_broken:
            leaked.append(m_broken.group(1))
            stem = stem[:m_broken.start()] + "（ ）"
        stem = re.sub(r'[（(]\s*[)）]', '（ ）', stem)

        if not answer and leaked:
            answer = leaked[-1]

        ans_clean = answer.strip().rstrip('。.;；')
        qtype = explicit_type
        if not qtype:
            if options:
                letters = re.findall(r'[A-E]', ans_clean.upper())
                qtype = 'multi' if len(letters) > 1 else 'single'
            elif ans_clean in ('正确', '错误', '对', '错', '√', '×', 'T', 'F'):
                qtype = 'judge'
            else:
                qtype = 'fill'

        if qtype in ('single', 'multi'):
            letters = sorted(set(re.findall(r'[A-E]', ans_clean.upper())))
            ans_norm = "".join(letters)
            if len(letters) > 1:
                qtype = 'multi'
        elif qtype == 'judge':
            if any(k in ans_clean for k in ('错', '×', 'F', '否', '假')):
                ans_norm = '错误'
            elif any(k in ans_clean for k in ('对', '正', '√', 'T', '是', '真')):
                ans_norm = '正确'
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
            fname = f"pe_q{qnum:03d}_p{pno_i}_x{xr}.webp"
            save_image(doc, xr, fname)
            img_paths.append(f"assets/images/pe/{fname}")

        opt_objs = [{'key': k, 'text': re.sub(r'[;；。\.]$', '', v).strip()} for k, v in options]

        q_obj = {
            'id': f"pe-{idx+1:03d}",
            'num': qnum,
            'chapter': rq['chapter'],
            'section': rq['section'],
            'type': qtype,
            'stem': stem,
            'options': opt_objs,
            'answer': ans_norm,
            'explanation': explanation,
            'images': img_paths,
            'page': rq['page']
        }

        # Apply verified overrides
        if qnum in PE_OVERRIDES:
            q_obj.update(PE_OVERRIDES[qnum])

        parsed.append(q_obj)

        # Audit
        if not q_obj['answer']:
            issues.append(f"Q{qnum}: MISSING ANSWER")
        if q_obj['type'] in ('single', 'multi') and len(q_obj['options']) < 2:
            issues.append(f"Q{qnum}: TOO FEW OPTIONS ({len(q_obj['options'])})")
        if q_obj['type'] in ('single', 'multi') and q_obj['answer']:
            opt_keys = {o['key'] for o in q_obj['options']}
            for ch in q_obj['answer']:
                if ch not in opt_keys:
                    issues.append(f"Q{qnum}: ANSWER '{q_obj['answer']}' NOT IN {opt_keys}")

    print(f"PE total: {len(parsed)} | Types: {Counter(q['type'] for q in parsed)}")
    print(f"Audit issues: {len(issues)}")
    for iss in issues:
        print("  -", iss)

    all_txt = "".join(q['stem'] + "".join(o['text'] for o in q['options']) + q['answer'] + q['explanation'] for q in parsed)
    weird = Counter(c for c in all_txt if ord(c) > 127 and not ('\u4e00' <= c <= '\u9fff') and c not in '，。？！：；、“”‘’（）【】《》—…·°±×÷≤≥≠≈→←↑↓ΩΦαβγδθλμπρωφΔΣ√²³¹⁰⁻⁺₀₁₂₃₄₅₆₇₈₉℃％～∙・①②③④⑤「」Ⅲ')
    print("Remaining unusual chars:", weird.most_common(20))

    with open(OUT_JSON, 'w', encoding='utf-8') as f:
        json.dump({
            'courseId': 'pe',
            'courseName': '电力电子技术',
            'source': 'B站纪真（十万伏特皮卡丘）电力电子技术配套习题（第1–7章）',
            'total': len(parsed),
            'questions': parsed
        }, f, ensure_ascii=False, indent=2)
    print("Saved clean PE JSON:", OUT_JSON)

if __name__ == '__main__':
    parse_pe()
