/**
 * Chat — POST /api/chat, structured cards, khôi phục lịch sử PostgreSQL.
 */
const API_BASE = '';

const GREETING =
  'Chào bạn! Mình là Cam chuyên viên tư vấn hướng nghiệp IT. ' +
  'Mình có thể giúp bạn xây dựng lộ trình học tập, tìm kiếm khóa học phù hợp, ' +
  'hoặc giải đáp các kỹ năng cần thiết cho từng vị trí. ' +
  'Bạn đang quan tâm đến mảng nào trong ngành IT?';

const SUGGESTIONS = [
  'Làm Backend Developer cần học những gì?',
  'So sánh Frontend và Backend Developer',
  'Khóa Python nào phù hợp cho người mới?',
];
const FALLBACK_SUGGESTIONS = [
  'Mình nên bắt đầu lộ trình học từ đâu?',
  'Bạn có thể gợi ý kỹ năng cần ưu tiên không?',
];

const CHAT_INPUT_MAX_HEIGHT = 180;
const CHAT_INPUT_MIN_HEIGHT = 24;

function getChatInput() {
  return document.getElementById('chatInput');
}

function resizeChatInput(el) {
  if (!el) return;
  if (typeof CSS !== 'undefined' && CSS.supports('field-sizing', 'content')) {
    el.style.height = '';
    el.style.overflowY = el.scrollHeight > CHAT_INPUT_MAX_HEIGHT ? 'auto' : 'hidden';
    return;
  }
  el.style.height = '0px';
  requestAnimationFrame(() => {
    requestAnimationFrame(() => {
      const scrollH = el.scrollHeight;
      const atMax = scrollH > CHAT_INPUT_MAX_HEIGHT;
      const next = Math.max(
        CHAT_INPUT_MIN_HEIGHT,
        Math.min(scrollH, CHAT_INPUT_MAX_HEIGHT)
      );
      el.style.height = `${next}px`;
      el.style.overflowY = atMax ? 'auto' : 'hidden';
    });
  });
}

function resetChatInput(el) {
  if (!el) return;
  el.value = '';
  el.style.overflowY = 'hidden';
  resizeChatInput(el);
}

function setupSidebarToggle() {
  const toggle = document.getElementById('sidebarToggle');
  const shell = document.getElementById('screenChat');
  const backdrop = document.getElementById('sidebarBackdrop');
  if (!toggle || !shell || !backdrop) return;

  const setOpen = (open) => {
    shell.classList.toggle('sidebar-open', open);
    toggle.setAttribute('aria-expanded', open ? 'true' : 'false');
    toggle.setAttribute('aria-label', open ? 'Đóng lịch sử chat' : 'Mở lịch sử chat');
    backdrop.classList.toggle('show', open);
  };

  toggle.addEventListener('click', () => {
    setOpen(!shell.classList.contains('sidebar-open'));
  });

  shell.querySelector('.chat-main')?.addEventListener('click', () => {
    if (window.matchMedia('(max-width: 768px)').matches) {
      setOpen(false);
    }
  });
  backdrop.addEventListener('click', () => setOpen(false));

  window.addEventListener('resize', () => {
    if (!window.matchMedia('(max-width: 768px)').matches) {
      setOpen(false);
    }
  });
}

function setupChatInput() {
  const inp = getChatInput();
  const sendBtn = document.getElementById('sendBtn');
  if (!inp) return;

  let composing = false;
  inp.addEventListener('compositionstart', () => {
    composing = true;
  });
  inp.addEventListener('compositionend', () => {
    composing = false;
    resizeChatInput(inp);
  });

  inp.addEventListener('input', () => resizeChatInput(inp));
  inp.addEventListener('paste', () => {
    requestAnimationFrame(() => resizeChatInput(inp));
  });

  const trySend = () => {
    sendMsg().catch(() => {});
  };

  if (sendBtn) {
    sendBtn.onclick = null;
    sendBtn.addEventListener('click', (e) => {
      e.preventDefault();
      trySend();
    });
  }

  inp.addEventListener('keydown', (e) => {
    const isEnter = e.key === 'Enter' || e.code === 'Enter';
    if (!isEnter) return;
    if (e.shiftKey) return;
    if (composing || e.isComposing) return;
    e.preventDefault();
    trySend();
  });

  resizeChatInput(inp);
}

function getSessionId() {
  const params = new URLSearchParams(window.location.search);
  const fromUrl = params.get('session_id');
  if (fromUrl) {
    localStorage.setItem('chat_session_id', fromUrl);
    return fromUrl;
  }
  let sid = localStorage.getItem('chat_session_id');
  if (!sid) {
    sid = crypto.randomUUID ? crypto.randomUUID() : String(Date.now());
    localStorage.setItem('chat_session_id', sid);
  }
  return sid;
}

function addSidebarItem(text) {
  const hist = document.getElementById('historyList');
  if (!hist) return;
  const current = [...hist.querySelectorAll('.history-item')].find(
    (el) => el.dataset.sessionId === getSessionId()
  );
  if (current) {
    current.dataset.preview = text;
    current.dataset.updatedAt = new Date().toISOString();
    current.textContent = text.length > 22 ? text.slice(0, 22) + '...' : text;
    hist.prepend(current);
    return;
  }
  const el = document.createElement('button');
  el.type = 'button';
  el.className = 'history-item active';
  el.dataset.sessionId = getSessionId();
  el.dataset.preview = text;
  el.dataset.updatedAt = new Date().toISOString();
  el.textContent = text.length > 22 ? text.slice(0, 22) + '...' : text;
  el.title = text;
  el.onclick = () => switchSession(el.dataset.sessionId || '');
  hist.prepend(el);
}

function renderSidebar(items = []) {
  const hist = document.getElementById('historyList');
  if (!hist) return;
  hist.innerHTML = '';
  items.forEach((item) => {
    const el = document.createElement('button');
    el.type = 'button';
    el.className = 'history-item';
    el.dataset.sessionId = item.session_id;
    el.dataset.preview = item.preview || '';
    el.dataset.updatedAt = item.updated_at || '';
    el.title = item.preview || 'Phiên chat';
    el.textContent =
      (item.preview || '').length > 22
        ? (item.preview || '').slice(0, 22) + '...'
        : item.preview || 'Phiên chat';
    if (item.session_id === getSessionId()) {
      el.classList.add('active');
    }
    el.onclick = () => {
      switchSession(item.session_id);
    };
    hist.appendChild(el);
  });
}

async function refreshSessionList() {
  try {
    const res = await fetch(`${API_BASE}/api/sessions?limit=20`);
    if (!res.ok) return;
    const data = await res.json();
    const sessions = Array.isArray(data.sessions) ? data.sessions : [];
    renderSidebar(sessions);
  } catch (err) {
    console.warn('Failed to load session list', err);
  }
}

async function switchSession(sessionId) {
  const sid = (sessionId || '').trim();
  if (!sid || sid === getSessionId()) return;
  localStorage.setItem('chat_session_id', sid);
  updateFormNavLink(sid);
  cleanUrl();
  const box = document.getElementById('chatMsgs');
  if (!box) return;
  box.innerHTML = '';
  const restored = await loadSessionFromServer();
  if (!restored) {
    appendMsg('bot', GREETING);
  }
  await refreshSessionList();
}

function renderSuggestBubbles() {
  const box = document.getElementById('chatMsgs');
  if (!box) return;
  box.querySelectorAll('.suggest-bubble').forEach((b) => b.remove());
  const choices = getFollowupSuggestions();
  if (!choices.length) return;
  choices.forEach((text) => {
    const b = document.createElement('div');
    b.className = 'suggest-bubble';
    b.textContent = text;
    b.onclick = () => useSuggest(b);
    box.appendChild(b);
  });
}

function resetSessionDueToFilter() {
  const sid = crypto.randomUUID ? crypto.randomUUID() : String(Date.now());
  localStorage.setItem('chat_session_id', sid);
  updateFormNavLink(sid);
  cleanUrl();
  return sid;
}

function replaceLastBotWithStructured(structured) {
  const box = document.getElementById('chatMsgs');
  if (!box || !structured) return null;
  const bots = box.querySelectorAll('.msg.bot');
  const last = bots.length ? bots[bots.length - 1] : null;
  const messageId = last?.dataset?.messageId;
  if (last) last.remove();
  const el = appendStructuredReply(structured);
  if (el && messageId) {
    el.dataset.messageId = messageId;
    attachFeedbackBar(el, Number(messageId));
  }
  return el;
}

function formatTimelineMonthLabel(month, index) {
  if (Number.isInteger(month)) return `Tháng ${month}`;
  const parsed = parseInt(String(month ?? '').trim(), 10);
  if (!Number.isNaN(parsed)) return `Tháng ${parsed}`;
  return `Giai đoạn ${index}`;
}

async function loadSessionFromServer() {
  const sid = getSessionId();
  const box = document.getElementById('chatMsgs');
  if (!box) return false;

  try {
    const res = await fetch(
      `${API_BASE}/api/session/${encodeURIComponent(sid)}/messages?limit=50`
    );
    if (!res.ok) {
      return false;
    }
    const data = await res.json();
    if (data.history_hidden) {
      console.info(
        'Session before SESSION_FILTER_AFTER; starting fresh.',
        data.filter_after
      );
      resetSessionDueToFilter();
      return false;
    }
    const messages = data.messages || [];
    if (!messages.length) return false;

    box.innerHTML = '';
    messages.forEach((m) => {
      const role = m.role === 'user' ? 'user' : 'bot';
      const el = appendMsg(role, m.content);
      if (role === 'bot' && m.id && !m.is_error && m.intent !== '_system_error') {
        el.dataset.messageId = String(m.id);
        attachFeedbackBar(el, Number(m.id));
      }
      if (role === 'bot' && (m.is_error || m.intent === '_system_error')) {
        el.dataset.isError = '1';
        const lastUser = getLastUserMessageText();
        if (lastUser) attachRetryBar(el, lastUser);
      }
    });
    return true;
  } catch (err) {
    console.warn('Failed to load session history', err);
    return false;
  }
}

async function initChat() {
  const box = document.getElementById('chatMsgs');
  if (!box) return;

  const params = new URLSearchParams(window.location.search);
  const fromForm = params.get('from') === 'form';
  const sid = getSessionId();
  await refreshSessionList();

  if (fromForm) {
    const structuredRaw = localStorage.getItem('chat_structured');
    const pending = localStorage.getItem('chat_pending_reply');
    const restored = await loadSessionFromServer();
    if (structuredRaw) {
      try {
        replaceLastBotWithStructured(JSON.parse(structuredRaw));
      } catch {
        if (!restored && pending) {
          box.innerHTML = '';
          appendMsg('bot', pending);
        }
      }
    } else if (!restored && pending) {
      box.innerHTML = '';
      appendMsg('bot', pending);
    }
    localStorage.removeItem('chat_structured');
    localStorage.removeItem('chat_pending_reply');
    renderSuggestBubbles();
    cleanUrl();
    return;
  }

  const restored = await loadSessionFromServer();
  if (!restored) {
    box.innerHTML = '';
    appendMsg('bot', GREETING);
    renderSuggestBubbles();
  }
}

function updateFormNavLink(forcedSessionId) {
  const link = document.getElementById('formNavLink');
  if (!link) return;
  const sid = forcedSessionId || getSessionId();
  link.href = `form.html?session_id=${encodeURIComponent(sid)}`;
}

function newChat() {
  const prevSid = localStorage.getItem('chat_session_id');
  const sid = crypto.randomUUID ? crypto.randomUUID() : String(Date.now());
  console.info('Started new chat session', { prevSid, sid });
  localStorage.setItem('chat_session_id', sid);
  localStorage.removeItem('chat_pending_reply');
  localStorage.removeItem('chat_structured');
  const box = document.getElementById('chatMsgs');
  box.innerHTML = '';
  appendMsg('bot', GREETING);
  renderSuggestBubbles();
  resetChatInput(getChatInput());
  refreshSessionList().catch(() => {});
  cleanUrl();
  updateFormNavLink(sid);
}

// Ẩn session_id/from khỏi thanh địa chỉ cho gọn; phiên vẫn được giữ trong localStorage.
function cleanUrl() {
  if (window.location.search) {
    window.history.replaceState({}, '', window.location.pathname);
  }
}

function useSuggest(el) {
  document.getElementById('chatInput').value = el.textContent;
  sendMsg().catch(() => {});
}

async function sendMsg() {
  const inp = getChatInput();
  const sendBtn = document.getElementById('sendBtn');
  const txt = inp ? inp.value.trim() : '';
  if (!txt) return;

  const box = document.getElementById('chatMsgs');
  box.querySelectorAll('.suggest-bubble').forEach((b) => b.remove());
  appendMsg('user', txt);
  resetChatInput(inp);
  addSidebarItem(txt);

  const loading = appendTypingMsg();
  if (sendBtn) sendBtn.disabled = true;

  try {
    const res = await fetch(`${API_BASE}/api/chat`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        message: txt,
        session_id: getSessionId(),
      }),
    });
    if (!res.ok) {
      const errText = await res.text();
      throw new Error(errText || `HTTP ${res.status}`);
    }
    const data = await res.json();

    if (data.session_id) {
      localStorage.setItem('chat_session_id', data.session_id);
    }
    if (data.session) {
      localStorage.setItem('chat_session_meta', JSON.stringify(data.session));
    }

    loading.remove();
    appendBotReply(data);
    refreshSessionList().catch(() => {});
  } catch (e) {
    loading.remove();
    appendErrorMsg('Mình đang tạm mất kết nối. Bạn thử lại sau ít giây nhé.', txt);
    console.error('Chat request failed', e);
  } finally {
    if (sendBtn) sendBtn.disabled = false;
  }
}

function appendBotReply(data) {
  let bubble;
  if (data.structured && data.structured.sections?.length) {
    bubble = appendStructuredReply(data.structured);
  } else {
    bubble = appendMsg('bot', data.reply || 'Không có phản hồi.');
  }
  if (bubble && data.message_id && !data.is_error) {
    bubble.dataset.messageId = String(data.message_id);
    attachFeedbackBar(bubble, data.message_id);
  }
  if (bubble && data.is_error) {
    bubble.dataset.isError = '1';
    const lastUser = getLastUserMessageText();
    if (lastUser) attachRetryBar(bubble, lastUser);
  }

  if (data.action === 'suggest_form' && data.form_url) {
    const wrap = document.createElement('div');
    wrap.className = 'msg bot form-link-wrap';
    wrap.style.marginTop = '0.35rem';

    const a = document.createElement('a');
    a.href = data.form_url.includes('session_id')
      ? data.form_url
      : `${data.form_url}?session_id=${encodeURIComponent(getSessionId())}`;
    a.className = 'chat-btn';
    a.textContent = 'Điền form tư vấn';
    a.style.marginTop = '0.5rem';
    wrap.appendChild(a);
    document.getElementById('chatMsgs').appendChild(wrap);
    scrollToBottom();
  }
  renderSuggestBubbles();
}

async function submitFeedback(messageId, rating, barEl) {
  try {
    const res = await fetch(`${API_BASE}/api/chat/messages/${messageId}/feedback`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ rating }),
    });
    if (!res.ok) throw new Error(await res.text());
    barEl.querySelectorAll('.feedback-btn').forEach((b) => {
      b.disabled = true;
      const active = Number(b.dataset.rating) === rating;
      b.classList.toggle('active', active);
      b.setAttribute('aria-pressed', active ? 'true' : 'false');
    });
  } catch {
    /* ignore — DB may be disabled */
  }
}

function attachFeedbackBar(bubbleEl, messageId) {
  if (!messageId || bubbleEl.dataset.isError === '1' || bubbleEl.querySelector('.feedback-bar')) return;
  const bar = document.createElement('div');
  bar.className = 'feedback-bar';
  const up = document.createElement('button');
  up.type = 'button';
  up.className = 'feedback-btn';
  up.dataset.rating = '1';
  up.title = 'Hữu ích';
  up.setAttribute('aria-label', 'Đánh giá hữu ích');
  up.setAttribute('aria-pressed', 'false');
  up.textContent = '👍';
  up.onclick = () => submitFeedback(messageId, 1, bar);
  const down = document.createElement('button');
  down.type = 'button';
  down.className = 'feedback-btn';
  down.dataset.rating = '-1';
  down.title = 'Chưa hữu ích';
  down.setAttribute('aria-label', 'Đánh giá chưa hữu ích');
  down.setAttribute('aria-pressed', 'false');
  down.textContent = '👎';
  down.onclick = () => submitFeedback(messageId, -1, bar);
  bar.appendChild(up);
  bar.appendChild(down);
  bubbleEl.appendChild(bar);
}

function getLastUserMessageText() {
  const userMsgs = document.querySelectorAll('#chatMsgs .msg.user');
  if (!userMsgs.length) return '';
  return (userMsgs[userMsgs.length - 1].textContent || '').trim();
}

function attachRetryBar(bubbleEl, retryText) {
  if (!retryText || bubbleEl.querySelector('.retry-bar')) return;
  const bar = document.createElement('div');
  bar.className = 'retry-bar';
  const btn = document.createElement('button');
  btn.type = 'button';
  btn.className = 'chat-btn';
  btn.textContent = 'Thử lại';
  btn.addEventListener('click', () => {
    sendRetryMsg(retryText).catch(() => {});
  });
  bar.appendChild(btn);
  bubbleEl.appendChild(bar);
}

async function sendRetryMsg(retryText) {
  const txt = (retryText || '').trim();
  if (!txt) return;

  const box = document.getElementById('chatMsgs');
  const sendBtn = document.getElementById('sendBtn');
  box.querySelectorAll('.suggest-bubble').forEach((b) => b.remove());

  const loading = appendTypingMsg();
  if (sendBtn) sendBtn.disabled = true;

  try {
    const res = await fetch(`${API_BASE}/api/chat`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        message: txt,
        session_id: getSessionId(),
        is_retry: true,
      }),
    });
    if (!res.ok) {
      const errText = await res.text();
      throw new Error(errText || `HTTP ${res.status}`);
    }
    const data = await res.json();

    if (data.session_id) {
      localStorage.setItem('chat_session_id', data.session_id);
    }
    if (data.session) {
      localStorage.setItem('chat_session_meta', JSON.stringify(data.session));
    }

    loading.remove();
    appendBotReply(data);
    refreshSessionList().catch(() => {});
  } catch (e) {
    loading.remove();
    appendErrorMsg('Mình đang tạm mất kết nối. Bạn thử lại sau ít giây nhé.', txt);
    console.error('Chat retry failed', e);
  } finally {
    if (sendBtn) sendBtn.disabled = false;
  }
}

function appendStructuredReply(structured) {
  const box = document.getElementById('chatMsgs');
  const wrap = document.createElement('div');
  wrap.className = 'msg bot structured-wrap';

  if (structured.title) {
    const t = document.createElement('div');
    t.className = 'structured-title';
    t.textContent = structured.title;
    wrap.appendChild(t);
  }

  (structured.sections || []).forEach((sec) => {
    const block = document.createElement('div');
    block.className = 'structured-section';

    if (sec.title) {
      const h = document.createElement('h4');
      h.textContent = sec.title;
      block.appendChild(h);
    }

    if (sec.type === 'summary' && sec.text) {
      const p = document.createElement('div');
      p.className = 'structured-summary';
      p.textContent = sec.text;
      block.appendChild(p);
    }

    if (sec.type === 'skills_gap') {
      appendChipRow(block, 'Đã có', sec.chips_known, 'known');
      const missingChips =
        sec.chips_missing_meta?.length ? sec.chips_missing_meta : sec.chips_missing;
      appendChipRow(block, 'Cần học', missingChips, 'missing');
      appendChipRow(block, 'Nên củng cố', sec.chips_weak, 'weak');
      appendChipRow(block, 'Kỹ năng mềm', sec.chips_soft_skills, 'soft');
      appendChipRow(block, 'Chứng chỉ', sec.chips_certifications, 'cert');
    }

    if (sec.type === 'timeline' && sec.timeline?.length) {
      const ul = document.createElement('ul');
      ul.className = 'timeline-list';
      sec.timeline.forEach((item, idx) => {
        const li = document.createElement('li');
        li.className = 'timeline-item';
        const topics = (item.topics || []).join(', ');
        const monthLabel = formatTimelineMonthLabel(item.month, idx + 1);
        const milestone = item.milestone || '';
        if (topics && milestone) {
          li.innerHTML = `<strong>${monthLabel}</strong>: ${topics}<br><span>${milestone}</span>`;
        } else if (topics) {
          li.innerHTML = `<strong>${monthLabel}</strong>: ${topics}`;
        } else if (milestone) {
          li.innerHTML = `<strong>${monthLabel}</strong>: ${milestone}`;
        } else {
          li.innerHTML = `<strong>${monthLabel}</strong>`;
        }
        if (Array.isArray(item.courses) && item.courses.length) {
          const courseWrap = document.createElement('div');
          courseWrap.className = 'timeline-courses';
          item.courses.forEach((c) => courseWrap.appendChild(buildCourseCard(c)));
          li.appendChild(courseWrap);
        }
        ul.appendChild(li);
      });
      block.appendChild(ul);
      if (sec.estimated_months) {
        const meta = document.createElement('p');
        meta.className = 'structured-summary';
        meta.style.marginTop = '0.5rem';
        meta.textContent = `Dự kiến sẵn sàng đi làm: ~${sec.estimated_months} tháng.`;
        block.appendChild(meta);
      }
    }

    if (sec.type === 'courses' && sec.courses?.length) {
      sec.courses.forEach((c) => block.appendChild(buildCourseCard(c)));
    }

    if (sec.type === 'courses_by_skill' && sec.courses_by_skill?.length) {
      sec.courses_by_skill.forEach((group) => {
        const g = document.createElement('div');
        g.className = 'course-skill-block';
        const h5 = document.createElement('h5');
        h5.className = 'course-skill-title';
        h5.appendChild(document.createTextNode(group.skill || 'Kỹ năng'));
        if (group.priority_badge) {
          const badge = document.createElement('span');
          badge.className = 'rank-badge priority';
          badge.textContent = group.priority_badge;
          h5.appendChild(badge);
        }
        g.appendChild(h5);
        (group.courses || []).forEach((c) => g.appendChild(buildCourseCard(c)));
        if (!(group.courses || []).length) {
          const empty = document.createElement('p');
          empty.className = 'structured-summary';
          empty.textContent = 'Chưa có khóa học trong đồ thị cho kỹ năng này.';
          g.appendChild(empty);
        }
        block.appendChild(g);
      });
    }

    if (sec.type === 'meta' && sec.estimated_months && !block.querySelector('.timeline-list')) {
      const meta = document.createElement('p');
      meta.className = 'structured-summary';
      meta.textContent = `Dự kiến: ~${sec.estimated_months} tháng.`;
      block.appendChild(meta);
    }

    if (sec.type === 'competency_collection') {
      buildCompetencyCollectionBlock(block, sec);
    }

    if (sec.type === 'competency_gap_summary') {
      buildGapSummaryBlock(block, sec);
    }

    if (block.childNodes.length) wrap.appendChild(block);
  });

  box.appendChild(wrap);
  scrollToBottom();
  return wrap;
}

function buildCompetencyCollectionBlock(block, sec) {
  if (Array.isArray(sec.progress) && sec.progress.length) {
    const bar = document.createElement('div');
    bar.className = 'cc-progress';
    sec.progress.forEach((step) => {
      const dot = document.createElement('div');
      dot.className = `cc-step cc-${step.state || 'pending'}`;
      dot.title = step.type_label || step.type_code || '';
      dot.textContent = (step.type_label || step.type_code || '').slice(0, 1);
      bar.appendChild(dot);
    });
    block.appendChild(bar);
  }

  if (sec.hint) {
    const hint = document.createElement('p');
    hint.className = 'cc-hint';
    hint.textContent = sec.hint;
    block.appendChild(hint);
  }

  if (Array.isArray(sec.chips_known) && sec.chips_known.length) {
    const knownRow = document.createElement('div');
    knownRow.className = 'cc-known-row';
    knownRow.innerHTML = '<span class="cc-known-label">Đã ghi:</span> ';
    sec.chips_known.forEach((name) => {
      const chip = document.createElement('span');
      chip.className = 'cc-chip cc-chip-known';
      chip.textContent = `✓ ${name}`;
      knownRow.appendChild(chip);
    });
    block.appendChild(knownRow);
  }

  if (Array.isArray(sec.chips_suggested) && sec.chips_suggested.length) {
    const label = document.createElement('div');
    label.className = 'cc-suggest-label';
    label.textContent = 'Chọn kỹ năng bạn đã biết:';
    block.appendChild(label);

    const chipBox = document.createElement('div');
    chipBox.className = 'cc-chip-row';
    const selected = new Set();
    const ensureSendBtn = () => {
      const btn = block.querySelector('[data-cc-id="submit"]');
      if (btn) btn.disabled = selected.size === 0;
    };
    sec.chips_suggested.forEach((name) => {
      const chip = document.createElement('button');
      chip.type = 'button';
      chip.className = 'cc-chip cc-chip-suggest';
      chip.textContent = name;
      chip.addEventListener('click', () => {
        const key = name.toLowerCase();
        if (selected.has(key)) {
          selected.delete(key);
          chip.classList.remove('selected');
        } else {
          selected.add(key);
          chip.classList.add('selected');
        }
        ensureSendBtn();
      });
      chip.dataset.skillName = name;
      chipBox.appendChild(chip);
    });
    block.appendChild(chipBox);

    const submitRow = document.createElement('div');
    submitRow.className = 'cc-action-row';
    const submit = document.createElement('button');
    submit.type = 'button';
    submit.className = 'chat-btn cc-submit';
    submit.textContent = 'Đã chọn xong →';
    submit.dataset.ccId = 'submit';
    submit.disabled = true;
    submit.addEventListener('click', () => {
      const picks = [...chipBox.querySelectorAll('.cc-chip-suggest.selected')]
        .map((c) => c.dataset.skillName)
        .filter(Boolean);
      if (!picks.length) return;
      sendQuickMessage(picks.join(', '));
    });
    submitRow.appendChild(submit);
    block.appendChild(submitRow);
  }

  if (Array.isArray(sec.actions) && sec.actions.length) {
    const actRow = document.createElement('div');
    actRow.className = 'cc-action-row';
    sec.actions.forEach((act) => {
      const btn = document.createElement('button');
      btn.type = 'button';
      btn.className = 'chat-btn cc-secondary';
      btn.textContent = act.label;
      btn.addEventListener('click', () => sendQuickMessage(act.command || act.label));
      actRow.appendChild(btn);
    });
    block.appendChild(actRow);
  }
}

function buildGapSummaryBlock(block, sec) {
  if (Array.isArray(sec.chips_known) && sec.chips_known.length) {
    appendChipRow(block, '✅ Đã có', sec.chips_known, 'known');
  }
  if (Array.isArray(sec.chips_missing) && sec.chips_missing.length) {
    appendChipRow(block, '📌 Cần học', sec.chips_missing, 'missing');
  }
  if (Array.isArray(sec.actions) && sec.actions.length) {
    const actRow = document.createElement('div');
    actRow.className = 'cc-action-row';
    sec.actions.forEach((act) => {
      if (!act.command) return;
      const btn = document.createElement('button');
      btn.type = 'button';
      btn.className = 'chat-btn cc-secondary';
      btn.textContent = act.label;
      btn.addEventListener('click', () => sendQuickMessage(act.command));
      actRow.appendChild(btn);
    });
    if (actRow.childNodes.length) block.appendChild(actRow);
  }
}

function sendQuickMessage(text) {
  const inp = getChatInput();
  if (!inp) return;
  inp.value = text;
  resizeChatInput(inp);
  sendMsg().catch(() => {});
}

function appendChipRow(parent, label, items, chipClass) {
  if (!items || !items.length) return;
  const rowLabel = document.createElement('div');
  rowLabel.style.fontSize = '0.8rem';
  rowLabel.style.fontWeight = '600';
  rowLabel.style.marginTop = '0.35rem';
  rowLabel.textContent = label;
  parent.appendChild(rowLabel);
  const row = document.createElement('div');
  row.className = 'chip-row';
  items.forEach((item) => {
    const name = typeof item === 'string' ? item : item.name || item.label || '';
    const badgeText =
      typeof item === 'object' && item ? item.priority_badge || item.coverage_badge : null;
    const chip = document.createElement('span');
    chip.className = `chip ${chipClass}`;
    chip.appendChild(document.createTextNode(name));
    if (badgeText) {
      const badge = document.createElement('span');
      badge.className = 'rank-badge';
      badge.textContent = badgeText;
      chip.appendChild(badge);
    }
    row.appendChild(chip);
  });
  parent.appendChild(row);
}

function buildCourseCard(c) {
  const card = document.createElement('div');
  card.className = 'course-card';
  const title = c.title || c.course_name || 'Khóa học';
  if (c.url) {
    const a = document.createElement('a');
    a.href = c.url;
    a.target = '_blank';
    a.rel = 'noopener';
    a.textContent = title;
    card.appendChild(a);
  } else {
    card.appendChild(document.createTextNode(title));
  }
  if (c.coverage_badge) {
    const badge = document.createElement('span');
    badge.className = 'rank-badge coverage';
    badge.textContent = c.coverage_badge;
    card.appendChild(badge);
  }
  const meta = [];
  if (c.organization || c.platform) meta.push(c.organization || c.platform);
  if (c.level) meta.push(c.level);
  if (c.subtitle) meta.push(c.subtitle);
  if (meta.length) {
    const p = document.createElement('div');
    p.style.color = 'var(--muted)';
    p.style.fontSize = '0.8rem';
    p.textContent = meta.join(' · ');
    card.appendChild(p);
  }
  return card;
}

function escapeHtml(s) {
  return String(s)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;');
}

function renderInline(text) {
  let s = escapeHtml(text);
  s = s.replace(/\\([_*`[\]()#+.!-])/g, '$1');
  s = s.replace(/`([^`]+)`/g, (_, c) => `<code>${c}</code>`);
  s = s.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>');
  s = s.replace(/__([^_]+)__/g, '<strong>$1</strong>');
  s = s.replace(/(^|[^*])\*([^*\n]+)\*/g, '$1<em>$2</em>');
  s = s.replace(
    /\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)/g,
    '<a href="$2" target="_blank" rel="noopener noreferrer">$1</a>'
  );
  return s;
}

// Bộ render Markdown tối giản, an toàn (escape HTML trước khi format)
// dùng cho tin nhắn của bot để không hiển thị ký tự #, *, ** thô.
function renderMarkdown(md) {
  const lines = String(md == null ? '' : md).replace(/\r\n/g, '\n').split('\n');
  let html = '';
  let listType = null;
  let para = [];

  const flushPara = () => {
    if (para.length) {
      html += '<p>' + para.map(renderInline).join('<br>') + '</p>';
      para = [];
    }
  };
  const closeList = () => {
    if (listType) {
      html += `</${listType}>`;
      listType = null;
    }
  };

  for (const raw of lines) {
    const line = raw.replace(/\s+$/, '');
    const heading = line.match(/^\s*(#{1,6})\s+(.*)$/);
    const bullet = line.match(/^\s*[-*+]\s+(.*)$/);
    const ordered = line.match(/^\s*\d+[.)]\s+(.*)$/);

    if (heading) {
      flushPara();
      closeList();
      const level = Math.min(heading[1].length + 2, 6);
      html += `<h${level}>${renderInline(heading[2])}</h${level}>`;
    } else if (bullet) {
      flushPara();
      if (listType !== 'ul') {
        closeList();
        html += '<ul>';
        listType = 'ul';
      }
      html += `<li>${renderInline(bullet[1])}</li>`;
    } else if (ordered) {
      flushPara();
      if (listType !== 'ol') {
        closeList();
        html += '<ol>';
        listType = 'ol';
      }
      html += `<li>${renderInline(ordered[1])}</li>`;
    } else if (line.trim() === '') {
      flushPara();
      closeList();
    } else {
      closeList();
      para.push(line);
    }
  }
  flushPara();
  closeList();
  return html;
}

function appendMsg(type, text) {
  const box = document.getElementById('chatMsgs');
  const d = document.createElement('div');
  d.className = 'msg ' + type;
  if (type === 'bot') {
    d.classList.add('markdown-body');
    d.innerHTML = renderMarkdown(text);
  } else {
    d.innerText = text;
  }
  d.style.animation = 'fadeIn 0.3s ease both';
  box.appendChild(d);
  scrollToBottom();
  return d;
}

function appendTypingMsg() {
  const box = document.getElementById('chatMsgs');
  const d = document.createElement('div');
  d.className = 'msg bot typing-msg';
  d.setAttribute('aria-label', 'Mình đang trả lời');
  d.innerHTML = `
    <span class="typing-label">Mình đang trả lời</span>
    <span class="typing-dots" aria-hidden="true">
      <span></span><span></span><span></span>
    </span>
  `;
  box.appendChild(d);
  scrollToBottom();
  return d;
}

function appendErrorMsg(message, retryText) {
  const box = document.getElementById('chatMsgs');
  const wrap = document.createElement('div');
  wrap.className = 'msg bot';
  wrap.textContent = message;

  if (retryText) {
    const retry = document.createElement('button');
    retry.type = 'button';
    retry.className = 'chat-btn';
    retry.textContent = 'Thử lại';
    retry.style.marginTop = '0.5rem';
    retry.addEventListener('click', () => {
      const inp = getChatInput();
      if (!inp) return;
      inp.value = retryText;
      resizeChatInput(inp);
      sendMsg().catch(() => {});
    });
    wrap.appendChild(document.createElement('br'));
    wrap.appendChild(retry);
  }

  box.appendChild(wrap);
  scrollToBottom();
}

function scrollToBottom() {
  const box = document.getElementById('chatMsgs');
  if (!box) return;
  requestAnimationFrame(() => {
    box.scrollTop = box.scrollHeight;
  });
}

function bootChat() {
  setupSidebarToggle();
  setupChatInput();
  updateFormNavLink();
  initChat();
}

function getFollowupSuggestions() {
  const box = document.getElementById('chatMsgs');
  if (!box) return [];
  const allMessages = box.querySelectorAll('.msg');
  if (!allMessages.length) return SUGGESTIONS;
  const lastBot = [...allMessages].reverse().find((el) => el.classList.contains('bot'));
  if (!lastBot) return FALLBACK_SUGGESTIONS;
  const txt = (lastBot.textContent || '').toLowerCase();
  if (txt.includes('lộ trình') || txt.includes('tháng')) {
    return ['Mốc 30 ngày đầu tiên nên làm gì?', 'Cho mình checklist tuần này'];
  }
  if (txt.includes('khóa học') || txt.includes('course')) {
    return ['So sánh 2 khóa học phù hợp nhất', 'Ưu tiên khóa miễn phí trước'];
  }
  if (txt.includes('kỹ năng') || txt.includes('skills')) {
    return ['Mình thiếu kỹ năng nào quan trọng nhất?', 'Gợi ý bài tập để luyện kỹ năng này'];
  }
  return FALLBACK_SUGGESTIONS;
}

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', bootChat);
} else {
  bootChat();
}
