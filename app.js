(() => {
  'use strict';

  const STORAGE_KEY = 'eqw-state-v1';
  const THEME_KEY = 'eqw-color-scheme';

  const COURSES = {
    pe: { id: 'pe', name: '电力电子技术', url: 'data/power-electronics.json' },
    em: { id: 'em', name: '电机学', url: 'data/electric-machinery.json' },
  };

  const TYPE_LABELS = {
    single: '单选题',
    multi: '多选题',
    judge: '判断题',
    fill: '填空题',
    essay: '计算 / 例题',
  };

  const DEFAULT_PERSISTED = {
    course: 'pe',
    settings: {
      instantJudge: true,
      autoNext: false,
    },
    records: {
      pe: {}, // qId -> { answer, correct: boolean, draft?: string, revealed?: boolean }
      em: {},
    },
    favorites: {
      pe: [],
      em: [],
    },
    wrongPool: {
      pe: [], // explicit wrong ids so users can clear mastered wrong items
      em: [],
    },
    lastPos: {
      pe: 0,
      em: 0,
    },
  };

  let persisted = loadPersisted();
  const dataCache = {};

  const ui = {
    course: persisted.course || 'pe',
    mode: 'practice', // practice | study | wrong | fav
    chapter: 'all',
    type: 'all',
    search: '',
    shuffle: false,
    list: [],
    index: 0,
    pendingChoice: null, // temp selection before submitting (for multi or non-instant single)
    autoNextTimer: null,
    lightboxZoom: 1,
  };

  // DOM helpers
  const $ = (sel) => document.querySelector(sel);
  const $$ = (sel) => Array.from(document.querySelectorAll(sel));

  function escapeHtml(str) {
    return String(str ?? '')
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#39;');
  }

  // Zero-dependency LaTeX-subset math renderer for stacked fractions, roots, and sub/sup
  const MATH_SYMS = {
    alpha: 'α', beta: 'β', gamma: 'γ', delta: 'δ', theta: 'θ',
    lambda: 'λ', mu: 'μ', pi: 'π', rho: 'ρ', sigma: 'σ',
    phi: 'φ', varphi: 'φ', omega: 'ω', eta: 'η', tau: 'τ',
    Delta: 'Δ', Sigma: 'Σ', sum: 'Σ', int: '∫',
    Phi: 'Φ', Omega: 'Ω', cdot: '·', times: '×', pm: '±',
    mp: '∓', approx: '≈', le: '≤', leq: '≤', ge: '≥', geq: '≥',
    ne: '≠', neq: '≠', propto: '∝', angle: '∠', sim: '～',
    cdots: '⋯', ldots: '…', infty: '∞', to: '→', rightarrow: '→',
    circ: '°', '%': '%', ',': ' ', ';': ' ', quad: '  ',
  };

  function readBracedGroup(src, idx) {
    while (idx < src.length && src[idx] === ' ') idx++;
    if (idx >= src.length) return ['', idx];
    if (src[idx] === '\\') {
      const m = src.slice(idx + 1).match(/^([a-zA-Z]+|.)/);
      const len = 1 + (m ? m[1].length : 0);
      return [src.slice(idx, idx + len), idx + len];
    }
    if (src[idx] !== '{') return [src[idx], idx + 1];
    let depth = 0;
    let start = idx + 1;
    let i = idx;
    while (i < src.length) {
      if (src[i] === '{') depth++;
      else if (src[i] === '}') {
        depth--;
        if (depth === 0) return [src.slice(start, i), i + 1];
      }
      i++;
    }
    return [src.slice(start), src.length];
  }

  function renderMathExpr(expr) {
    let out = '';
    let i = 0;
    const s = String(expr || '');
    while (i < s.length) {
      const ch = s[i];
      if (ch === ' ' || ch === '\t') {
        i++;
        continue;
      }
      if (ch === '\\') {
        const m = s.slice(i + 1).match(/^([a-zA-Z]+|.)/);
        const cmd = m ? m[1] : '';
        i += 1 + cmd.length;
        if (cmd === 'frac') {
          const [num, next1] = readBracedGroup(s, i);
          const [den, next2] = readBracedGroup(s, next1);
          i = next2;
          out += `<span class="math-frac"><span class="math-num">${renderMathExpr(num)}</span><span class="math-den">${renderMathExpr(den)}</span></span>`;
        } else if (cmd === 'sqrt') {
          const [arg, next1] = readBracedGroup(s, i);
          i = next1;
          out += `<span class="math-sqrt"><span class="math-rad">√</span><span class="math-radicand">${renderMathExpr(arg)}</span></span>`;
        } else if (cmd === 'text') {
          const [arg, next1] = readBracedGroup(s, i);
          i = next1;
          out += `<span class="math-fn">${escapeHtml(arg)}</span>`;
        } else if (cmd === 'left' || cmd === 'right') {
          while (i < s.length && s[i] === ' ') i++;
          const br = s[i] || '';
          i += br ? 1 : 0;
          if (br && br !== '.') {
            out += `<span class="math-paren-tall">${escapeHtml(br)}</span>`;
          }
        } else if (['sin', 'cos', 'tan', 'cot', 'log', 'ln', 'max', 'min', 'rms'].includes(cmd)) {
          out += `<span class="math-fn">${cmd}</span>`;
        } else if (cmd === 'mathrm' || cmd === 'operatorname') {
          const [arg, next1] = readBracedGroup(s, i);
          i = next1;
          out += `<span class="math-fn">${escapeHtml(arg)}</span>`;
        } else if (MATH_SYMS[cmd]) {
          out += `<span class="math-op">${MATH_SYMS[cmd]}</span>`;
        } else {
          out += escapeHtml(cmd);
        }
        continue;
      }
      if (ch === '_' || ch === '^') {
        const tag = ch === '_' ? 'sub' : 'sup';
        const [arg, next1] = readBracedGroup(s, i + 1);
        i = next1;
        if (ch === '^' && arg.trim() === '\\circ') {
          out += `<span class="math-deg">°</span>`;
        } else {
          out += `<${tag}>${renderMathExpr(arg)}</${tag}>`;
        }
        continue;
      }
      if (ch === '{' || ch === '}') {
        i++;
        continue;
      }
      if ('+-=<>'.includes(ch)) {
        out += `<span class="math-op">${escapeHtml(ch === '-' ? '−' : ch)}</span>`;
        i++;
        continue;
      }
      if ('()[]'.includes(ch)) {
        out += `<span class="math-paren">${escapeHtml(ch)}</span>`;
        i++;
        continue;
      }
      if (/[A-Za-z]/.test(ch)) {
        out += `<var>${ch}</var>`;
        i++;
        continue;
      }
      out += escapeHtml(ch);
      i++;
    }
    return out;
  }

  function renderRichText(str) {
    const raw = String(str ?? '');
    if (!raw.includes('$')) return escapeHtml(raw);
    const parts = raw.split(/(\$[^$]+\$)/g);
    return parts
      .map((seg) => {
        if (seg.length >= 2 && seg.startsWith('$') && seg.endsWith('$')) {
          return `<span class="math-inline">${renderMathExpr(seg.slice(1, -1))}</span>`;
        }
        return escapeHtml(seg);
      })
      .join('');
  }

  function loadPersisted() {
    try {
      const raw = localStorage.getItem(STORAGE_KEY);
      if (!raw) return structuredClone(DEFAULT_PERSISTED);
      const obj = JSON.parse(raw);
      return {
        course: obj.course === 'em' ? 'em' : 'pe',
        settings: {
          instantJudge: obj.settings?.instantJudge !== false,
          autoNext: Boolean(obj.settings?.autoNext),
        },
        records: {
          pe: obj.records?.pe && typeof obj.records.pe === 'object' ? obj.records.pe : {},
          em: obj.records?.em && typeof obj.records.em === 'object' ? obj.records.em : {},
        },
        favorites: {
          pe: Array.isArray(obj.favorites?.pe) ? obj.favorites.pe : [],
          em: Array.isArray(obj.favorites?.em) ? obj.favorites.em : [],
        },
        wrongPool: {
          pe: Array.isArray(obj.wrongPool?.pe) ? obj.wrongPool.pe : [],
          em: Array.isArray(obj.wrongPool?.em) ? obj.wrongPool.em : [],
        },
        lastPos: {
          pe: Number.isInteger(obj.lastPos?.pe) ? obj.lastPos.pe : 0,
          em: Number.isInteger(obj.lastPos?.em) ? obj.lastPos.em : 0,
        },
      };
    } catch {
      return structuredClone(DEFAULT_PERSISTED);
    }
  }

  function savePersisted() {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(persisted));
    } catch {
      // Ignore quota or storage restriction errors
    }
  }

  let toastTimer = null;
  function showToast(msg) {
    const el = $('#toast');
    if (!el) return;
    el.textContent = msg;
    el.classList.add('show');
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => el.classList.remove('show'), 2200);
  }

  // Theme management (following modern-web-guidance dark-mode-toggle)
  function applyTheme(choice) {
    const meta = document.querySelector('meta[name="color-scheme"]');
    if (!meta) return;
    if (choice === 'light' || choice === 'dark') {
      meta.content = choice;
      try { localStorage.setItem(THEME_KEY, choice); } catch {}
    } else {
      meta.content = 'light dark';
      try { localStorage.removeItem(THEME_KEY); } catch {}
    }
    syncThemeButtons();
  }

  function getStoredThemeChoice() {
    try {
      const val = localStorage.getItem(THEME_KEY);
      if (val === 'light' || val === 'dark') return val;
    } catch {}
    return 'system';
  }

  function syncThemeButtons() {
    const cur = getStoredThemeChoice();
    const sysDark = window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches;
    $$('[data-theme-choice]').forEach((btn) => {
      const val = btn.dataset.themeChoice;
      btn.classList.toggle('active', val === cur);
      if (val === 'system') {
        btn.textContent = sysDark ? '跟随系统 (深)' : '跟随系统 (浅)';
      }
    });
  }

  window.addEventListener('storage', (e) => {
    if (e.key === THEME_KEY) {
      const meta = document.querySelector('meta[name="color-scheme"]');
      if (meta) meta.content = e.newValue || 'light dark';
      syncThemeButtons();
    }
  });

  // Dialog light-dismiss fallback for browsers without closedby (Safari)
  function setupDialogFallbacks() {
    $$('dialog[closedby="any"]').forEach((dialog) => {
      if (!('closedBy' in HTMLDialogElement.prototype)) {
        dialog.addEventListener('click', (event) => {
          if (event.target !== dialog) return;
          const rect = dialog.getBoundingClientRect();
          const inside =
            rect.top <= event.clientY &&
            event.clientY <= rect.top + rect.height &&
            rect.left <= event.clientX &&
            event.clientX <= rect.left + rect.width;
          if (!inside) dialog.close();
        });
      }
    });

    $$('[data-close-dialog]').forEach((btn) => {
      btn.addEventListener('click', () => {
        const dlg = document.getElementById(btn.dataset.closeDialog);
        if (dlg && dlg.open) dlg.close();
      });
    });
  }

  // Course loading
  async function loadCourse(courseId, silent = false) {
    if (dataCache[courseId]) return dataCache[courseId];
    if (!silent) {
      const stage = $('#question-stage');
      if (stage) stage.innerHTML = '<div class="loading-box">正在加载题库数据…</div>';
    }
    const resp = await fetch(COURSES[courseId].url);
    if (!resp.ok) throw new Error('题库加载失败');
    const json = await resp.json();
    dataCache[courseId] = json;
    const badge = document.getElementById(`count-${courseId}`);
    if (badge) badge.textContent = String(json.total);
    return json;
  }

  function getCourseData() {
    return dataCache[ui.course];
  }

  function getRecords() {
    return persisted.records[ui.course];
  }

  function getFavorites() {
    return persisted.favorites[ui.course];
  }

  function getWrongPool() {
    return persisted.wrongPool[ui.course];
  }

  function buildChapters() {
    const data = getCourseData();
    if (!data) return;
    const records = getRecords();
    const map = new Map();
    for (const q of data.questions) {
      if (!map.has(q.chapter)) map.set(q.chapter, { total: 0, done: 0 });
      const entry = map.get(q.chapter);
      entry.total += 1;
      if (records[q.id]?.answered) entry.done += 1;
    }

    const sidebar = $('#sidebar-chapters');
    const mobileSel = $('#mobile-chapter-select');
    const totalDone = Object.values(records).filter((r) => r.answered).length;

    const chapterItems = [
      { key: 'all', label: '全部章节', done: totalDone, total: data.total },
      ...Array.from(map.entries()).map(([k, v]) => ({ key: k, label: k, done: v.done, total: v.total })),
    ];

    sidebar.innerHTML = chapterItems
      .map(
        (ch) => `
        <button type="button" class="chapter-btn ${ui.chapter === ch.key ? 'active' : ''}" data-chapter="${escapeHtml(ch.key)}">
          <span class="chapter-name" title="${escapeHtml(ch.label)}">${escapeHtml(ch.label)}</span>
          <span class="chapter-meta">${ch.done}/${ch.total}</span>
        </button>`
      )
      .join('');

    mobileSel.innerHTML = chapterItems
      .map(
        (ch) => `<option value="${escapeHtml(ch.key)}" ${ui.chapter === ch.key ? 'selected' : ''}>${escapeHtml(ch.label)} (${ch.done}/${ch.total})</option>`
      )
      .join('');
  }

  function updateStats() {
    const data = getCourseData();
    if (!data) return;
    const records = getRecords();
    const favs = getFavorites();
    const wrongs = getWrongPool();

    const answeredList = Object.values(records).filter((r) => r.answered);
    const done = answeredList.length;
    const right = answeredList.filter((r) => r.correct).length;
    const acc = done > 0 ? `${Math.round((right / done) * 100)}%` : '--';
    const pct = data.total > 0 ? Math.min(100, (done / data.total) * 100) : 0;

    $('#stat-done').textContent = String(done);
    $('#stat-acc').textContent = acc;
    $('#stat-wrong').textContent = String(wrongs.length);
    $('#stat-fav').textContent = String(favs.length);
    $('#progress-fill').style.width = `${pct.toFixed(1)}%`;

    $('#m-stat-done').textContent = `${done}/${data.total}`;
    $('#m-stat-acc').textContent = acc;

    $('#badge-wrong').textContent = String(wrongs.length);
    $('#badge-fav').textContent = String(favs.length);
  }

  function rebuildList(preserveCurrentId = null) {
    const data = getCourseData();
    if (!data) return;
    const favSet = new Set(getFavorites());
    const wrongSet = new Set(getWrongPool());
    const kw = ui.search.trim().toLowerCase();

    let list = data.questions.filter((q) => {
      if (ui.mode === 'wrong' && !wrongSet.has(q.id)) return false;
      if (ui.mode === 'fav' && !favSet.has(q.id)) return false;
      if (ui.chapter !== 'all' && q.chapter !== ui.chapter) return false;
      if (ui.type !== 'all' && q.type !== ui.type) return false;
      if (kw) {
        const hay = `${q.num} ${q.stem} ${q.options.map((o) => o.text).join(' ')} ${q.chapter} ${q.section}`.toLowerCase();
        if (!hay.includes(kw)) return false;
      }
      return true;
    });

    if (ui.shuffle) {
      list = [...list];
      for (let i = list.length - 1; i > 0; i--) {
        const j = Math.floor(Math.random() * (i + 1));
        [list[i], list[j]] = [list[j], list[i]];
      }
    }

    ui.list = list;
    ui.pendingChoice = null;

    if (preserveCurrentId) {
      const found = list.findIndex((q) => q.id === preserveCurrentId);
      ui.index = found >= 0 ? found : 0;
    } else if (ui.mode === 'practice' && ui.chapter === 'all' && ui.type === 'all' && !kw && !ui.shuffle) {
      const savedIdx = persisted.lastPos[ui.course] || 0;
      ui.index = Math.max(0, Math.min(savedIdx, Math.max(0, list.length - 1)));
    } else {
      ui.index = 0;
    }

    renderQuestion();
    buildChapters();
    updateStats();
  }

  function getCurrentQuestion() {
    if (!ui.list.length) return null;
    return ui.list[Math.max(0, Math.min(ui.index, ui.list.length - 1))];
  }

  function saveLastPosIfDefault() {
    if (ui.mode === 'practice' && ui.chapter === 'all' && ui.type === 'all' && !ui.search.trim() && !ui.shuffle) {
      persisted.lastPos[ui.course] = ui.index;
      savePersisted();
    }
  }

  function normalizeFillStr(str) {
    return String(str || '')
      .toLowerCase()
      .replace(/[\s，,、；;。.：:（）()\-]/g, '');
  }

  function checkFillAnswer(userInput, standard) {
    const u = normalizeFillStr(userInput);
    const s = normalizeFillStr(standard);
    if (!u) return false;
    if (u === s) return true;
    // Also accept matching the core part before parenthetical notes in single-blank answers
    const stripped = normalizeFillStr(String(standard).replace(/[（(][^）)]*[）)]/g, ''));
    if (stripped && u === stripped) return true;
    return false;
  }

  function recordResult(q, userAnswer, isCorrect, extra = {}) {
    const records = getRecords();
    records[q.id] = {
      answered: true,
      answer: userAnswer,
      correct: Boolean(isCorrect),
      ...extra,
    };

    const wrongPool = getWrongPool();
    if (!isCorrect) {
      if (!wrongPool.includes(q.id)) wrongPool.push(q.id);
    }

    savePersisted();
    updateStats();
    buildChapters();

    if (isCorrect && persisted.settings.autoNext && ui.mode === 'practice' && ui.index < ui.list.length - 1) {
      clearTimeout(ui.autoNextTimer);
      ui.autoNextTimer = setTimeout(() => {
        goNext();
      }, 700);
    }
  }

  function renderImagesHtml(images, captionPrefix = '') {
    if (!images || !images.length) return '';
    return `
      <div class="q-images">
        ${images
          .map(
            (src, i) => `
          <div class="q-img-wrap" data-lightbox-src="${escapeHtml(src)}" role="button" tabindex="0" aria-label="放大查看配图 ${i + 1}">
            <img src="${escapeHtml(src)}" alt="${escapeHtml(captionPrefix || '题目配图')} ${i + 1}" loading="lazy" decoding="async">
            <span class="q-img-hint">点击放大</span>
          </div>`
          )
          .join('')}
      </div>`;
  }

  function renderQuestion() {
    clearTimeout(ui.autoNextTimer);
    const stage = $('#question-stage');
    const q = getCurrentQuestion();

    updateNavControls();

    if (!q) {
      const emptyMsg =
        ui.mode === 'wrong'
          ? '当前错题本为空，太棒了！'
          : ui.mode === 'fav'
          ? '还没有收藏题目，遇到重点题可以点击「收藏」。'
          : '没有找到符合筛选条件的题目，试试清空搜索词或切换章节。';
      stage.innerHTML = `<div class="empty-box"><h3>暂无题目</h3><p>${escapeHtml(emptyMsg)}</p></div>`;
      return;
    }

    const records = getRecords();
    const rec = records[q.id];
    const isStudy = ui.mode === 'study';
    const showResult = isStudy || Boolean(rec?.answered);
    const inWrongPool = getWrongPool().includes(q.id);

    const typeCls = `type-${q.type}`;
    const typeLabel = TYPE_LABELS[q.type] || '题目';
    const crumb = q.section ? `${q.chapter} · ${q.section}` : q.chapter;

    let bodyHtml = '';

    if (q.type === 'single' || q.type === 'multi') {
      const selectedSet = new Set();
      if (rec?.answered && rec.answer) {
        for (const ch of String(rec.answer)) selectedSet.add(ch);
      } else if (ui.pendingChoice) {
        for (const ch of ui.pendingChoice) selectedSet.add(ch);
      }
      const ansSet = new Set(String(q.answer));

      bodyHtml += `<div class="options-list" role="group" aria-label="题目选项">`;
      for (const opt of q.options) {
        let cls = 'option-btn';
        const isSel = selectedSet.has(opt.key);
        const isRightOpt = ansSet.has(opt.key);

        if (showResult) {
          if (isRightOpt) cls += ' correct';
          else if (isSel && !isRightOpt) cls += ' wrong';
        } else if (isSel) {
          cls += ' selected';
        }

        bodyHtml += `
          <button type="button" class="${cls}" data-opt-key="${escapeHtml(opt.key)}" ${showResult ? 'disabled' : ''}>
            <span class="option-key">${escapeHtml(opt.key)}</span>
            <span class="option-text">${renderRichText(opt.text)}</span>
          </button>`;
      }
      bodyHtml += `</div>`;

      if (!showResult && (q.type === 'multi' || !persisted.settings.instantJudge)) {
        bodyHtml += `
          <div class="q-action-row">
            <button type="button" class="submit-btn" id="btn-submit-choice">提交答案</button>
          </div>`;
      }
    } else if (q.type === 'judge') {
      const judgeOpts = [
        { key: '正确', label: '✓', text: '正确' },
        { key: '错误', label: '✕', text: '错误' },
      ];
      bodyHtml += `<div class="options-list judge-grid" role="group" aria-label="判断选项">`;
      for (const opt of judgeOpts) {
        let cls = 'option-btn';
        const isSel = rec?.answered ? rec.answer === opt.key : ui.pendingChoice === opt.key;
        const isRightOpt = q.answer === opt.key;
        if (showResult) {
          if (isRightOpt) cls += ' correct';
          else if (isSel && !isRightOpt) cls += ' wrong';
        } else if (isSel) {
          cls += ' selected';
        }
        bodyHtml += `
          <button type="button" class="${cls}" data-judge-key="${opt.key}" ${showResult ? 'disabled' : ''}>
            <span class="option-key">${opt.label}</span>
            <span class="option-text">${opt.text}</span>
          </button>`;
      }
      bodyHtml += `</div>`;

      if (!showResult && !persisted.settings.instantJudge) {
        bodyHtml += `
          <div class="q-action-row">
            <button type="button" class="submit-btn" id="btn-submit-judge">提交答案</button>
          </div>`;
      }
    } else if (q.type === 'fill') {
      const val = rec?.answer ?? '';
      bodyHtml += `
        <div class="input-answer-box">
          <input type="text" class="fill-input" id="fill-input" placeholder="输入你的答案（多空可用分号或空格隔开）…" value="${escapeHtml(val)}" ${isStudy ? 'disabled' : ''}>
          ${
            !isStudy
              ? `<div class="q-action-row">
                  <button type="button" class="submit-btn" id="btn-submit-fill">核对答案</button>
                  <button type="button" class="submit-btn secondary" id="btn-reveal-fill">直接看答案</button>
                </div>`
              : ''
          }
        </div>`;
    } else if (q.type === 'essay') {
      const draft = rec?.draft ?? '';
      bodyHtml += `
        <div class="input-answer-box">
          <textarea class="essay-textarea" id="essay-draft" placeholder="可在此记录关键公式、中间步骤或计算结果（自动保存草稿）…">${escapeHtml(draft)}</textarea>
          ${
            !showResult
              ? `<div class="q-action-row">
                  <button type="button" class="submit-btn" id="btn-reveal-essay">展开参考解答${q.answerImages?.length ? '与手写板书' : ''}</button>
                </div>`
              : ''
          }
        </div>`;
    }

    // Feedback / Reference Answer Panel
    let feedbackHtml = '';
    if (showResult) {
      let panelCls = 'feedback-panel';
      let headerText = '参考答案';
      if (!isStudy && rec?.answered) {
        if (q.type === 'essay' && rec.selfRated === false) {
          headerText = '参考解答（请对照自评）';
        } else if (rec.correct) {
          panelCls += ' is-ok';
          headerText = q.type === 'essay' ? '✓ 已标记掌握' : '✓ 回答正确';
        } else {
          panelCls += ' is-err';
          headerText = q.type === 'essay' ? '✗ 已记入错题本（待复习）' : `✗ 回答错误（你的答案：${escapeHtml(rec.answer || '未填')}）`;
        }
      }

      const selfEvalButtons =
        !isStudy && (q.type === 'fill' || q.type === 'essay')
          ? `<div class="q-action-row">
              <button type="button" class="submit-btn ok-btn" id="btn-mark-ok">✓ 标记我答对了 / 已掌握</button>
              <button type="button" class="submit-btn err-btn" id="btn-mark-err">✗ 记入错题本</button>
            </div>`
          : '';

      const retryAndRemoveRow = !isStudy
        ? `<div class="q-action-row">
            <button type="button" class="submit-btn secondary" id="btn-redo-q">重做本题</button>
            ${inWrongPool ? `<button type="button" class="submit-btn secondary" id="btn-remove-wrong">移出错题本</button>` : ''}
          </div>`
        : '';

      feedbackHtml = `
        <div class="${panelCls}">
          <div class="feedback-header">
            <span>${headerText}</span>
            <span class="q-num-badge">原资料 p.${q.page}</span>
          </div>
          <div>
            <strong>标准答案：</strong>
            <div class="ans-value">${renderRichText(q.answer)}</div>
          </div>
          ${q.explanation ? `<div class="feedback-explain"><div class="explain-title">💡 解题解析</div><div class="explain-body">${renderRichText(q.explanation)}</div></div>` : ''}
          ${
            q.answerImages && q.answerImages.length
              ? `<div class="ans-images-block">
                  <div class="ans-images-title">原版手写板书解答（点击可全屏放大）</div>
                  ${renderImagesHtml(q.answerImages, '手写板书解答')}
                </div>`
              : ''
          }
          ${selfEvalButtons}
          ${retryAndRemoveRow}
        </div>`;
    }

    stage.innerHTML = `
      <article class="question-card">
        <div class="q-meta">
          <div class="q-tags">
            <span class="tag ${typeCls}">${typeLabel}</span>
            <span class="q-chapter-crumb">${escapeHtml(crumb)}</span>
          </div>
          <span class="q-num-badge">第 ${q.num} 题</span>
        </div>
        <h2 class="q-stem">${renderRichText(q.stem)}</h2>
        ${renderImagesHtml(q.images, '题目配图')}
        ${bodyHtml}
        ${feedbackHtml}
      </article>`;

    bindQuestionEvents(q);
  }

  function bindQuestionEvents(q) {
    // Choice buttons
    $$('[data-opt-key]').forEach((btn) => {
      btn.addEventListener('click', () => {
        const key = btn.dataset.optKey;
        if (q.type === 'single') {
          if (persisted.settings.instantJudge) {
            recordResult(q, key, key === q.answer);
            renderQuestion();
          } else {
            ui.pendingChoice = key;
            renderQuestion();
          }
        } else {
          const cur = new Set(ui.pendingChoice ? String(ui.pendingChoice) : '');
          if (cur.has(key)) cur.delete(key);
          else cur.add(key);
          ui.pendingChoice = Array.from(cur).sort().join('');
          renderQuestion();
        }
      });
    });

    const btnSubChoice = $('#btn-submit-choice');
    if (btnSubChoice) {
      btnSubChoice.addEventListener('click', () => {
        if (!ui.pendingChoice) {
          showToast('请先选择答案');
          return;
        }
        const chosen = String(ui.pendingChoice);
        recordResult(q, chosen, chosen === q.answer);
        ui.pendingChoice = null;
        renderQuestion();
      });
    }

    // Judge buttons
    $$('[data-judge-key]').forEach((btn) => {
      btn.addEventListener('click', () => {
        const key = btn.dataset.judgeKey;
        if (persisted.settings.instantJudge) {
          recordResult(q, key, key === q.answer);
          renderQuestion();
        } else {
          ui.pendingChoice = key;
          renderQuestion();
        }
      });
    });

    const btnSubJudge = $('#btn-submit-judge');
    if (btnSubJudge) {
      btnSubJudge.addEventListener('click', () => {
        if (!ui.pendingChoice) {
          showToast('请先选择正确或错误');
          return;
        }
        recordResult(q, ui.pendingChoice, ui.pendingChoice === q.answer);
        ui.pendingChoice = null;
        renderQuestion();
      });
    }

    // Fill input
    const fillInput = $('#fill-input');
    const submitFill = () => {
      const val = fillInput ? fillInput.value.trim() : '';
      if (!val) {
        showToast('请输入答案，或点“直接看答案”');
        return;
      }
      const ok = checkFillAnswer(val, q.answer);
      recordResult(q, val, ok);
      renderQuestion();
    };
    $('#btn-submit-fill')?.addEventListener('click', submitFill);
    fillInput?.addEventListener('keydown', (e) => {
      if (e.key === 'Enter') {
        e.preventDefault();
        submitFill();
      }
    });
    $('#btn-reveal-fill')?.addEventListener('click', () => {
      const val = fillInput ? fillInput.value.trim() : '';
      recordResult(q, val, false);
      renderQuestion();
    });

    // Essay draft & reveal
    const essayDraft = $('#essay-draft');
    if (essayDraft) {
      essayDraft.addEventListener('input', () => {
        const records = getRecords();
        const prev = records[q.id] || { answered: false, answer: '', correct: false };
        records[q.id] = { ...prev, draft: essayDraft.value };
        savePersisted();
      });
    }
    $('#btn-reveal-essay')?.addEventListener('click', () => {
      const draftVal = essayDraft ? essayDraft.value : '';
      const records = getRecords();
      records[q.id] = {
        answered: true,
        answer: draftVal,
        draft: draftVal,
        correct: false,
        selfRated: false,
      };
      savePersisted();
      updateStats();
      buildChapters();
      renderQuestion();
    });

    // Self-evaluation buttons (fill & essay)
    $('#btn-mark-ok')?.addEventListener('click', () => {
      const records = getRecords();
      const prev = records[q.id] || {};
      recordResult(q, prev.answer || '', true, { draft: prev.draft || '', selfRated: true });
      const wp = getWrongPool();
      const wi = wp.indexOf(q.id);
      if (wi >= 0) wp.splice(wi, 1);
      savePersisted();
      updateStats();
      renderQuestion();
      showToast('已标记为掌握');
    });

    $('#btn-mark-err')?.addEventListener('click', () => {
      const records = getRecords();
      const prev = records[q.id] || {};
      recordResult(q, prev.answer || '', false, { draft: prev.draft || '', selfRated: true });
      renderQuestion();
      showToast('已加入错题本');
    });

    // Redo & remove from wrong
    $('#btn-redo-q')?.addEventListener('click', () => {
      const records = getRecords();
      const prevDraft = records[q.id]?.draft || '';
      delete records[q.id];
      if (q.type === 'essay' && prevDraft) {
        records[q.id] = { answered: false, draft: prevDraft };
      }
      ui.pendingChoice = null;
      savePersisted();
      updateStats();
      buildChapters();
      renderQuestion();
    });

    $('#btn-remove-wrong')?.addEventListener('click', () => {
      const wp = getWrongPool();
      const idx = wp.indexOf(q.id);
      if (idx >= 0) {
        wp.splice(idx, 1);
        savePersisted();
        showToast('已移出错题本');
        if (ui.mode === 'wrong') {
          rebuildList();
        } else {
          updateStats();
          renderQuestion();
        }
      }
    });

    // Lightbox images
    $$('[data-lightbox-src]').forEach((wrap) => {
      const open = () => openLightbox(wrap.dataset.lightboxSrc);
      wrap.addEventListener('click', open);
      wrap.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault();
          open();
        }
      });
    });
  }

  function updateNavControls() {
    const total = ui.list.length;
    const posStr = total ? `${ui.index + 1} / ${total}` : '0 / 0';
    const posShort = total ? `${ui.index + 1}/${total}` : '0/0';

    $('#nav-pos-desk').textContent = posStr;
    $('#nav-pos-mob').textContent = posShort;
    $('#m-progress-text').textContent = posStr;

    const noPrev = ui.index <= 0 || total === 0;
    const noNext = ui.index >= total - 1 || total === 0;
    $('#btn-prev-desk').disabled = noPrev;
    $('#btn-prev-mob').disabled = noPrev;
    $('#btn-next-desk').disabled = noNext;
    $('#btn-next-mob').disabled = noNext;

    const q = getCurrentQuestion();
    const isFav = q ? getFavorites().includes(q.id) : false;

    const favDesk = $('#btn-fav-desk');
    favDesk.textContent = isFav ? '★ 已收藏' : '☆ 收藏';
    favDesk.classList.toggle('fav-active', isFav);

    const favMob = $('#btn-fav-mob');
    $('#dock-star').textContent = isFav ? '★' : '☆';
    favMob.classList.toggle('fav-active', isFav);
  }

  function goPrev() {
    if (ui.index > 0) {
      ui.index -= 1;
      ui.pendingChoice = null;
      saveLastPosIfDefault();
      renderQuestion();
      window.scrollTo({ top: 0, behavior: 'smooth' });
    }
  }

  function goNext() {
    if (ui.index < ui.list.length - 1) {
      ui.index += 1;
      ui.pendingChoice = null;
      saveLastPosIfDefault();
      renderQuestion();
      window.scrollTo({ top: 0, behavior: 'smooth' });
    }
  }

  function toggleFavorite() {
    const q = getCurrentQuestion();
    if (!q) return;
    const favs = getFavorites();
    const idx = favs.indexOf(q.id);
    if (idx >= 0) {
      favs.splice(idx, 1);
      showToast('已取消收藏');
    } else {
      favs.push(q.id);
      showToast('已加入收藏夹');
    }
    savePersisted();
    updateStats();
    if (ui.mode === 'fav' && idx >= 0) {
      rebuildList();
    } else {
      updateNavControls();
    }
  }

  // Answer Sheet Dialog
  function openSheet() {
    const dlg = $('#sheet-dialog');
    const grid = $('#sheet-grid');
    const records = getRecords();
    const favSet = new Set(getFavorites());
    $('#sheet-subtitle').textContent = `当前筛选共 ${ui.list.length} 题 · 点击题号跳转`;

    grid.innerHTML = ui.list
      .map((q, i) => {
        const rec = records[q.id];
        let cls = 'sheet-cell';
        if (rec?.answered) cls += rec.correct ? ' ok' : ' err';
        if (i === ui.index) cls += ' cur';
        if (favSet.has(q.id)) cls += ' has-fav';
        return `<button type="button" class="${cls}" data-jump-idx="${i}" title="第 ${q.num} 题">${q.num}</button>`;
      })
      .join('');

    grid.querySelectorAll('[data-jump-idx]').forEach((cell) => {
      cell.addEventListener('click', () => {
        ui.index = Number(cell.dataset.jumpIdx);
        ui.pendingChoice = null;
        saveLastPosIfDefault();
        dlg.close();
        renderQuestion();
        window.scrollTo({ top: 0, behavior: 'smooth' });
      });
    });

    dlg.showModal();
  }

  // Lightbox Dialog
  function applyLightboxZoom() {
    const img = $('#lightbox-img');
    img.style.transform = `scale(${ui.lightboxZoom})`;
    $('#lb-zoom-label').textContent = `${Math.round(ui.lightboxZoom * 100)}%`;
  }

  function openLightbox(src) {
    ui.lightboxZoom = 1;
    const img = $('#lightbox-img');
    img.src = src;
    applyLightboxZoom();
    $('#lightbox-dialog').showModal();
  }

  // Settings & Import/Export
  function openSettings() {
    syncThemeButtons();
    $('#opt-instant').checked = persisted.settings.instantJudge;
    $('#opt-autonext').checked = persisted.settings.autoNext;
    $('#settings-dialog').showModal();
  }

  function exportProgressFile() {
    const payload = {
      app: 'Electrical_Quiz_Web',
      version: 1,
      exportedAt: new Date().toISOString(),
      data: persisted,
    };
    const blob = new Blob([JSON.stringify(payload, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `electrical-quiz-backup-${new Date().toISOString().slice(0, 10)}.json`;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
    showToast('已导出进度备份文件');
  }

  function importProgressFile(file) {
    const reader = new FileReader();
    reader.onload = () => {
      try {
        const parsed = JSON.parse(String(reader.result));
        const incoming = parsed.data || parsed;
        if (!incoming.records || (!incoming.records.pe && !incoming.records.em)) {
          throw new Error('格式无效');
        }
        persisted = {
          ...structuredClone(DEFAULT_PERSISTED),
          ...incoming,
          settings: { ...DEFAULT_PERSISTED.settings, ...(incoming.settings || {}) },
          records: { pe: incoming.records.pe || {}, em: incoming.records.em || {} },
          favorites: { pe: incoming.favorites?.pe || [], em: incoming.favorites?.em || [] },
          wrongPool: { pe: incoming.wrongPool?.pe || [], em: incoming.wrongPool?.em || [] },
          lastPos: { pe: incoming.lastPos?.pe || 0, em: incoming.lastPos?.em || 0 },
        };
        savePersisted();
        rebuildList();
        showToast('进度导入成功！');
      } catch {
        showToast('导入失败：请选择有效的备份 JSON 文件');
      }
    };
    reader.readAsText(file);
  }

  // Course Switch
  async function switchCourse(courseId) {
    ui.course = courseId;
    persisted.course = courseId;
    savePersisted();

    ui.chapter = 'all';
    ui.type = 'all';
    ui.search = '';
    ui.shuffle = false;
    $('#type-filter').value = 'all';
    $('#search-input').value = '';
    $('#btn-shuffle').setAttribute('aria-pressed', 'false');

    $$('.course-tab').forEach((btn) => {
      const active = btn.dataset.course === courseId;
      btn.classList.toggle('active', active);
      btn.setAttribute('aria-pressed', String(active));
    });

    try {
      await loadCourse(courseId);
      rebuildList();
    } catch (err) {
      $('#question-stage').innerHTML = `<div class="empty-box"><h3>题库加载失败</h3><p>${escapeHtml(err.message)}</p></div>`;
    }
  }

  // Event Wiring
  function initEvents() {
    setupDialogFallbacks();

    $$('.course-tab').forEach((btn) => {
      btn.addEventListener('click', () => {
        if (btn.dataset.course !== ui.course) switchCourse(btn.dataset.course);
      });
    });

    $$('.mode-pill').forEach((btn) => {
      btn.addEventListener('click', () => {
        ui.mode = btn.dataset.mode;
        $$('.mode-pill').forEach((b) => {
          const active = b === btn;
          b.classList.toggle('active', active);
          b.setAttribute('aria-selected', String(active));
        });
        rebuildList();
      });
    });

    $('#sidebar-chapters').addEventListener('click', (e) => {
      const btn = e.target.closest('[data-chapter]');
      if (!btn) return;
      ui.chapter = btn.dataset.chapter;
      rebuildList();
    });

    $('#mobile-chapter-select').addEventListener('change', (e) => {
      ui.chapter = e.target.value;
      rebuildList();
    });

    $('#type-filter').addEventListener('change', (e) => {
      ui.type = e.target.value;
      rebuildList();
    });

    let searchTimer = null;
    $('#search-input').addEventListener('input', (e) => {
      clearTimeout(searchTimer);
      searchTimer = setTimeout(() => {
        ui.search = e.target.value;
        rebuildList();
      }, 180);
    });

    $('#btn-shuffle').addEventListener('click', (e) => {
      ui.shuffle = !ui.shuffle;
      e.currentTarget.setAttribute('aria-pressed', String(ui.shuffle));
      rebuildList();
      showToast(ui.shuffle ? '已开启乱序刷题' : '已恢复顺序刷题');
    });

    $('#btn-prev-desk').addEventListener('click', goPrev);
    $('#btn-next-desk').addEventListener('click', goNext);
    $('#btn-prev-mob').addEventListener('click', goPrev);
    $('#btn-next-mob').addEventListener('click', goNext);

    $('#btn-fav-desk').addEventListener('click', toggleFavorite);
    $('#btn-fav-mob').addEventListener('click', toggleFavorite);

    $('#btn-sheet-top').addEventListener('click', openSheet);
    $('#btn-sheet-desk').addEventListener('click', openSheet);
    $('#btn-sheet-mob').addEventListener('click', openSheet);

    $('#btn-settings').addEventListener('click', openSettings);

    $$('[data-theme-choice]').forEach((btn) => {
      btn.addEventListener('click', () => applyTheme(btn.dataset.themeChoice));
    });

    $('#opt-instant').addEventListener('change', (e) => {
      persisted.settings.instantJudge = e.target.checked;
      savePersisted();
      renderQuestion();
    });

    $('#opt-autonext').addEventListener('change', (e) => {
      persisted.settings.autoNext = e.target.checked;
      savePersisted();
    });

    $('#btn-export-file').addEventListener('click', exportProgressFile);
    $('#btn-import-trigger').addEventListener('click', () => $('#import-file-input').click());
    $('#import-file-input').addEventListener('change', (e) => {
      const f = e.target.files?.[0];
      if (f) importProgressFile(f);
      e.target.value = '';
    });

    $('#btn-reset-course').addEventListener('click', () => {
      const name = COURSES[ui.course].name;
      if (!confirm(`确定要清空《${name}》的全部做题记录、错题本和进度吗？此操作无法撤销。`)) return;
      persisted.records[ui.course] = {};
      persisted.wrongPool[ui.course] = [];
      persisted.lastPos[ui.course] = 0;
      savePersisted();
      $('#settings-dialog').close();
      rebuildList();
      showToast(`已清空《${name}》答题记录`);
    });

    // Lightbox zoom controls
    $('#lb-zoom-in').addEventListener('click', () => {
      ui.lightboxZoom = Math.min(3, +(ui.lightboxZoom + 0.35).toFixed(2));
      applyLightboxZoom();
    });
    $('#lb-zoom-out').addEventListener('click', () => {
      ui.lightboxZoom = Math.max(0.6, +(ui.lightboxZoom - 0.35).toFixed(2));
      applyLightboxZoom();
    });
    $('#lb-zoom-reset').addEventListener('click', () => {
      ui.lightboxZoom = 1;
      applyLightboxZoom();
    });

    // Keyboard shortcuts (desktop)
    document.addEventListener('keydown', (e) => {
      const tag = document.activeElement?.tagName;
      if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT') return;
      if ($('#sheet-dialog').open || $('#settings-dialog').open || $('#lightbox-dialog').open) return;

      if (e.key === 'ArrowLeft') {
        e.preventDefault();
        goPrev();
      } else if (e.key === 'ArrowRight') {
        e.preventDefault();
        goNext();
      } else if (['1', '2', '3', '4', '5'].includes(e.key)) {
        const q = getCurrentQuestion();
        if (!q || ui.mode === 'study') return;
        const idx = Number(e.key) - 1;
        if (q.type === 'single' || q.type === 'multi') {
          const btn = $$(`[data-opt-key]`)[idx];
          if (btn && !btn.disabled) btn.click();
        } else if (q.type === 'judge' && idx < 2) {
          const btn = $$(`[data-judge-key]`)[idx];
          if (btn && !btn.disabled) btn.click();
        }
      } else if (e.key === 'Enter') {
        const sub = $('#btn-submit-choice') || $('#btn-submit-judge');
        if (sub) sub.click();
      }
    });
  }

  async function boot() {
    initEvents();
    syncThemeButtons();
    await switchCourse(ui.course);
    // Preload the other course count quietly in background
    const other = ui.course === 'pe' ? 'em' : 'pe';
    loadCourse(other, true).catch(() => {});
  }

  boot();
})();
