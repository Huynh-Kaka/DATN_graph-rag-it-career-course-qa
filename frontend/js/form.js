const API_BASE = '';

const WEEKLY_TIME_MAP = {
  '< 5 giờ/tuần': 'lt5',
  '5–10 giờ/tuần': '5to10',
  '10–20 giờ/tuần': '10to20',
  '> 20 giờ/tuần': 'gt20',
};

const state = {
  step: 0,
  background: '',
  role: '',
  level: '',
  target_role_text: '',
  role_match_ok: false,
  role_suggestions: [],
  skills: [],
  skill_profile: {
    ProgrammingLanguage: [],
    Framework: [],
    Platform: [],
    Tool: [],
    Knowledge: [],
    Softskill: [],
    Certification: [],
  },
  goals: [],
  time: '',
  question: '',
};

const SKILL_PROFILE_FIELDS = [
  { key: 'ProgrammingLanguage', label: 'Programming Language' },
  { key: 'Framework', label: 'Framework' },
  { key: 'Platform', label: 'Platform' },
  { key: 'Tool', label: 'Tool' },
  { key: 'Knowledge', label: 'Knowledge' },
  { key: 'Softskill', label: 'Softskill' },
  { key: 'Certification', label: 'Certification' },
];

const steps = [
  {
    id: 'background',
    label: 'Bước 1 / 4 — Xuất phát điểm',
    title: 'Bạn đang ở đâu trong hành trình IT?',
    sub: 'Giúp hệ thống hiểu đúng bối cảnh của bạn.',
    type: 'single',
    key: 'background',
    options: [
      { val: 'student', label: '🎓 Sinh viên năm 1–3' },
      { val: 'grad', label: '🎓 Sinh viên năm 4 / sắp ra trường' },
      { val: 'fresher', label: '💼 Fresher (0–1 năm kinh nghiệm)' },
      { val: 'career_switch', label: '🔄 Đang đi làm, muốn chuyển sang IT' },
      { val: 'self_taught', label: '📚 Tự học IT ngoài giờ' },
    ],
  },
  {
    id: 'role',
    label: 'Bước 2 / 4 — Mục tiêu nghề nghiệp',
    title: 'Bạn muốn trở thành gì?',
    sub: 'Chọn vai trò bạn hướng tới. Chưa chắc thì chọn gần nhất.',
    type: 'single',
    key: 'role',
    options: [
      { val: 'backend', label: 'Backend Developer' },
      { val: 'frontend', label: 'Frontend Developer' },
      { val: 'fullstack', label: 'Fullstack Developer' },
      { val: 'data', label: 'Data Analyst / Data Scientist' },
      { val: 'devops', label: 'DevOps / Cloud Engineer' },
      { val: 'mobile', label: 'Mobile Developer' },
      { val: 'pm', label: 'IT Project Manager / BA' },
      { val: 'other', label: 'Chưa rõ / khác' },
    ],
    extra: {
      key: 'level',
      label: 'Mục tiêu cụ thể hơn',
      placeholder: 'VD: Muốn vào công ty product, làm remote...',
      optional: true,
    },
  },
  {
    id: 'skills',
    label: 'Bước 3 / 4 — Kỹ năng & thời gian',
    title: 'Bạn đã biết gì rồi?',
    sub: 'Chọn tất cả những gì bạn đã học qua, dù chưa thành thạo.',
    type: 'multi',
    key: 'skills',
    options: [
      { val: 'python', label: 'Python' },
      { val: 'js', label: 'JavaScript' },
      { val: 'java', label: 'Java / C#' },
      { val: 'sql', label: 'SQL' },
      { val: 'html_css', label: 'HTML / CSS' },
      { val: 'git', label: 'Git' },
      { val: 'linux', label: 'Linux cơ bản' },
      { val: 'excel', label: 'Excel / Google Sheets' },
      { val: 'none', label: 'Chưa biết gì' },
    ],
    extra: {
      key: 'time',
      label: 'Bạn có thể học bao nhiêu giờ/tuần?',
      type: 'select',
      options: Object.keys(WEEKLY_TIME_MAP),
    },
  },
  {
    id: 'goals',
    label: 'Bước 4 / 4 : Mong muốn gì từ hệ thống',
    title: 'Bạn muốn hệ thống tư vấn gì cho bạn?',
    sub: 'Chọn những điều bạn muốn nhận được.',
    type: 'multi',
    key: 'goals',
    options: [
      { val: 'roadmap', label: '🗺️ Lộ trình học cụ thể' },
      { val: 'skills_gap', label: '🔍 Phân tích điểm còn thiếu' },
      { val: 'courses', label: '📖 Gợi ý khoá học phù hợp' },
      { val: 'job_tips', label: '💼 Tips tìm việc / làm portfolio' },
      { val: 'timeline', label: '📅 Dự tính thời gian sẵn sàng đi làm' },
    ],
    extra: {
      key: 'question',
      label: 'Câu hỏi cụ thể của bạn',
      placeholder: 'VD: Cần học gì để vào công ty product trong 6 tháng?',
      optional: true,
    },
  },
];

function getSessionId() {
  const params = new URLSearchParams(window.location.search);
  return params.get('session_id') || localStorage.getItem('chat_session_id') || '';
}

function getProfileId() {
  return localStorage.getItem('chat_profile_id') || '';
}

function showError(msg) {
  const errEl = document.getElementById('formError');
  errEl.textContent = msg;
  errEl.style.display = 'block';
}

function hideError() {
  const errEl = document.getElementById('formError');
  errEl.style.display = 'none';
}

function setFormSubmitting(isSubmitting) {
  const envelope = document.querySelector('.form-envelope');
  const shell = document.querySelector('.form-envelope-content');
  const overlay = document.getElementById('formLoading');
  const btn = document.getElementById('btn-submit');
  const backLink = document.getElementById('backLink');

  if (envelope) {
    envelope.classList.toggle('form-is-submitting', isSubmitting);
  }
  if (shell) {
    shell.classList.toggle('form-is-submitting', isSubmitting);
  }
  if (overlay) {
    overlay.hidden = !isSubmitting;
    overlay.setAttribute('aria-busy', isSubmitting ? 'true' : 'false');
  }
  if (btn) {
    btn.disabled = isSubmitting;
    btn.setAttribute('aria-busy', isSubmitting ? 'true' : 'false');
    if (isSubmitting) {
      if (!btn.dataset.originalText) {
        btn.dataset.originalText = btn.textContent || 'Gửi & nhận tư vấn ↗';
      }
      btn.textContent = 'Đang phân tích hồ sơ…';
    } else if (btn.dataset.originalText) {
      btn.textContent = btn.dataset.originalText;
    }
  }
  document.querySelectorAll('#formApp .btn-back, #formApp .btn-next').forEach((el) => {
    el.disabled = isSubmitting;
  });
  if (backLink) {
    if (isSubmitting) {
      if (!backLink.dataset.prevHref) {
        backLink.dataset.prevHref = backLink.getAttribute('href') || 'chat.html';
      }
      backLink.removeAttribute('href');
      backLink.classList.add('is-disabled');
    } else {
      if (backLink.dataset.prevHref) {
        backLink.setAttribute('href', backLink.dataset.prevHref);
      }
      backLink.classList.remove('is-disabled');
    }
  }
}

function stepLabelText(stepIndex) {
  if (stepIndex >= steps.length) return 'Xác nhận';
  return steps[stepIndex].label;
}

function renderProgress() {
  const el = document.getElementById('prog');
  const labelEl = document.getElementById('stepLabel');
  const current = Math.min(state.step + 1, steps.length);
  el.innerHTML = steps
    .map((_, i) => {
      let cls = 'seg';
      if (i < state.step) cls += ' done';
      else if (i === state.step) cls += ' active';
      return `<div class="${cls}"></div>`;
    })
    .join('');
  el.setAttribute('aria-valuenow', String(current));
  if (labelEl) {
    labelEl.textContent = stepLabelText(state.step);
  }
}

function canProceed() {
  const s = steps[state.step];
  if (s.type === 'single') {
    if (!state[s.key]) return false;
    if (s.key === 'role' && state.role === 'other') {
      return !!state.target_role_text.trim();
    }
    return true;
  }
  if (s.type === 'multi') return state[s.key].length > 0;
  return true;
}

function parseCommaLines(value) {
  return (value || '')
    .split(/[,\n]+/g)
    .map((x) => x.trim())
    .filter(Boolean);
}

async function verifyCustomRole(name) {
  const raw = (name || '').trim();
  state.target_role_text = raw;
  if (!raw) {
    state.role_match_ok = false;
    state.role_suggestions = [];
    renderStep();
    return;
  }
  try {
    const res = await fetch(
      `${API_BASE}/api/advisory/roles/search?q=${encodeURIComponent(raw)}&limit=6`
    );
    const data = await res.json().catch(() => ({}));
    state.role_match_ok = !!data.exact;
    state.role_suggestions = Array.isArray(data.suggestions) ? data.suggestions : [];
  } catch {
    state.role_match_ok = false;
    state.role_suggestions = [];
  }
  renderStep();
}

function renderRoleValidation() {
  if (state.role !== 'other') return '';
  const value = state.target_role_text || '';
  const ok = state.role_match_ok && value.trim();
  const suggestions = state.role_suggestions || [];
  return `<div class="section-gap">
    <label class="field-label" for="other-role">Vị trí bạn muốn hướng tới <span class="required-tag">*</span></label>
    <input type="text" id="other-role" placeholder="VD: QA Engineer, Data Engineer..." value="${value.replace(/"/g, '&quot;')}"/>
    <p class="helper-text left"> hệ thống sẽ ưu tiên role có trong dữ liệu, nhưng bạn vẫn có thể tiếp tục nếu chưa khớp.</p>
    ${
      ok
        ? '<p class="helper-text ok left">Đã khớp với dữ liệu Neo4j.</p>'
        : value.trim()
          ? '<p class="helper-text warn left">Chưa thấy role này trong dữ liệu hiện có, tư vấn sẽ dựa thêm vào mô tả của bạn.</p>'
          : ''
    }
    ${
      !ok && suggestions.length
        ? `<div class="suggestion-wrap">${suggestions
            .map((s) => `<button type="button" class="suggestion-chip" data-suggest="${s.replace(/"/g, '&quot;')}">${s}</button>`)
            .join('')}</div>`
        : ''
    }
  </div>`;
}

function renderSkillProfileInputs() {
  return `<div class="section-gap">
    <label class="field-label">Nhập thêm kỹ năng bạn đã biết (tuỳ chọn, càng chi tiết càng tư vấn sâu)</label>
    <div class="skill-profile-grid">
      ${SKILL_PROFILE_FIELDS.map((f) => {
        const v = (state.skill_profile?.[f.key] || []).join(', ');
        return `<div class="skill-profile-item">
          <label class="field-label" for="skill-${f.key}">${f.label}</label>
          <input type="text" id="skill-${f.key}" data-skill-key="${f.key}" placeholder="VD: ${f.label === 'Programming Language' ? 'Python, Java' : '...' }" value="${v.replace(/"/g, '&quot;')}"/>
        </div>`;
      }).join('')}
    </div>
    <p class="helper-text left">Ngăn cách nhiều mục bằng dấu phẩy (,).</p>
  </div>`;
}

function renderSelect(key, opts) {
  const val = state[key] || '';
  return `<select id="sel-${key}" aria-label="${key}">
    <option value="">— chọn —</option>
    ${opts.map((o) => `<option value="${o}" ${val === o ? 'selected' : ''}>${o}</option>`).join('')}
  </select>`;
}

function labelOf(key, val) {
  const s = steps.find((x) => x.key === key || (x.extra && x.extra.key === key));
  if (!s) return val;
  if (s.key === key) {
    if (Array.isArray(val)) {
      return val.map((v) => (s.options.find((o) => o.val === v) || { label: v }).label);
    }
    return (s.options.find((o) => o.val === val) || { label: val }).label;
  }
  return val;
}

function captureExtraFields() {
  const s = steps[state.step];
  if (!s || !s.extra) return;
  const ex = s.extra;
  if (ex.type === 'select') {
    const el = document.getElementById(`sel-${ex.key}`);
    if (el) state[ex.key] = el.value;
  } else {
    const el = document.getElementById(`extra-${ex.key}`);
    if (el) state[ex.key] = el.value;
  }
}

function renderStep() {
  hideError();
  if (state.step >= steps.length) {
    renderReview();
    return;
  }

  const s = steps[state.step];
  const isMulti = s.type === 'multi';
  const proceed = canProceed();
  let html = `<h2 class="question-heading">${s.title}</h2>
  <p class="question-subtitle">${s.sub}</p>
  <div class="options-grid" role="group" aria-label="${s.title}">`;

  s.options.forEach((o) => {
    const selVal = isMulti ? state[s.key] : [state[s.key]];
    const sel = selVal.includes(o.val);
    const cls = isMulti
      ? sel
        ? 'option-btn multi selected'
        : 'option-btn multi'
      : sel
        ? 'option-btn selected'
        : 'option-btn';
    html += `<div class="${cls}" data-val="${o.val}" data-key="${s.key}" data-multi="${isMulti}" tabindex="0" role="button">${o.label}</div>`;
  });
  html += '</div>';

  if (s.key === 'role') {
    html += renderRoleValidation();
  }

  if (s.extra) {
    const ex = s.extra;
    html += `<div class="section-gap"><label class="field-label" for="${ex.type === 'select' ? `sel-${ex.key}` : `extra-${ex.key}`}">${ex.label}${
      ex.optional ? '<span class="optional-tag">tuỳ chọn</span>' : ''
    }</label>`;
    if (ex.type === 'select') {
      html += renderSelect(ex.key, ex.options);
    } else {
      html += `<textarea id="extra-${ex.key}" rows="2" placeholder="${ex.placeholder || ''}">${state[ex.key] || ''}</textarea>`;
    }
    html += '</div>';
  }

  if (s.key === 'skills') {
    html += renderSkillProfileInputs();
  }

  const showBack = state.step > 0;
  html += `<div class="nav">
    ${showBack ? '<button type="button" class="btn-back" id="btn-back" aria-label="Quay lại bước trước">←</button>' : ''}
    <div class="nav-actions">
      <button type="button" class="btn-next" id="btn-next" ${proceed ? '' : 'disabled'}>Tiếp theo →</button>
      ${
        proceed
          ? ''
          : `<p class="helper-text" id="stepHelper">${
              isMulti ? 'Chọn ít nhất một mục để tiếp tục' : 'Chọn một mục để tiếp tục'
            }</p>`
      }
    </div>
  </div>`;

  document.getElementById('formApp').innerHTML = html;

  document.querySelectorAll('.option-btn').forEach((c) => {
    const activate = () => {
      const k = c.dataset.key;
      const v = c.dataset.val;
      const multi = c.dataset.multi === 'true';
      if (multi) {
        const arr = state[k];
        const idx = arr.indexOf(v);
        if (v === 'none') {
          state[k] = arr.includes('none') ? [] : ['none'];
        } else {
          const noIdx = arr.indexOf('none');
          if (noIdx > -1) arr.splice(noIdx, 1);
          if (idx > -1) arr.splice(idx, 1);
          else arr.push(v);
        }
      } else {
        state[k] = v;
      }
      renderStep();
    };
    c.addEventListener('click', activate);
    c.addEventListener('keydown', (e) => {
      if (e.key === 'Enter' || e.key === ' ') {
        e.preventDefault();
        activate();
      }
    });
  });

  const otherRoleInput = document.getElementById('other-role');
  if (otherRoleInput) {
    otherRoleInput.addEventListener('input', (e) => {
      state.target_role_text = e.target.value || '';
      state.role_match_ok = false;
    });
    otherRoleInput.addEventListener('blur', (e) => {
      verifyCustomRole(e.target.value || '');
    });
  }
  document.querySelectorAll('.suggestion-chip').forEach((btn) => {
    btn.addEventListener('click', () => {
      const val = btn.dataset.suggest || '';
      state.target_role_text = val;
      verifyCustomRole(val);
    });
  });

  document.querySelectorAll('[data-skill-key]').forEach((input) => {
    input.addEventListener('input', (e) => {
      const key = e.target.dataset.skillKey;
      state.skill_profile[key] = parseCommaLines(e.target.value || '');
    });
  });

  document.getElementById('btn-next')?.addEventListener('click', () => {
    captureExtraFields();
    state.step += 1;
    renderProgress();
    renderStep();
  });
  document.getElementById('btn-back')?.addEventListener('click', () => {
    state.step -= 1;
    renderProgress();
    renderStep();
  });
}

function renderReview() {
  renderProgress();
  const roleLabel = labelOf('role', state.role);
  const bgLabel = labelOf('background', state.background);
  const skillLabels = labelOf('skills', state.skills);
  const goalLabels = labelOf('goals', state.goals);

  let html = `<h2 class="question-heading">Kiểm tra trước khi gửi</h2>
  <p class="question-subtitle">Mọi thứ trông ổn chưa?</p>
  <div class="review-card">
    <div class="review-row"><span class="review-key">Xuất phát điểm</span><span class="review-val">${bgLabel}</span></div>
    <div class="review-row"><span class="review-key">Vai trò mục tiêu</span><span class="review-val">${roleLabel}</span></div>
    ${state.level ? `<div class="review-row"><span class="review-key">Mục tiêu cụ thể</span><span class="review-val">${state.level}</span></div>` : ''}
    ${state.target_role_text ? `<div class="review-row"><span class="review-key">Role mong muốn</span><span class="review-val">${state.target_role_text}</span></div>` : ''}
    <div class="review-row"><span class="review-key">Đã biết</span><div class="badge-group">${skillLabels.map((l) => `<span class="badge">${l}</span>`).join('')}</div></div>
    ${
      SKILL_PROFILE_FIELDS.map((f) => {
        const vals = state.skill_profile[f.key] || [];
        if (!vals.length) return '';
        return `<div class="review-row"><span class="review-key">${f.label}</span><div class="badge-group">${vals
          .map((v) => `<span class="badge">${v}</span>`)
          .join('')}</div></div>`;
      }).join('')
    }
    ${state.time ? `<div class="review-row"><span class="review-key">Thời gian học</span><span class="review-val">${state.time}</span></div>` : ''}
    <div class="review-row"><span class="review-key">Muốn hệ thống tư vấn</span><div class="badge-group">${goalLabels.map((l) => `<span class="badge">${l}</span>`).join('')}</div></div>
    ${state.question ? `<div class="review-row"><span class="review-key">Câu hỏi riêng</span><span class="review-val" style="max-width:240px">${state.question}</span></div>` : ''}
  </div>
  <div class="nav">
    <button type="button" class="btn-back" id="btn-back2" aria-label="Quay lại bước trước">←</button>
    <div class="nav-actions">
      <button type="button" class="btn-submit" id="btn-submit">Gửi & nhận tư vấn ↗</button>
    </div>
  </div>`;

  document.getElementById('formApp').innerHTML = html;
  document.getElementById('btn-back2').addEventListener('click', () => {
    state.step = steps.length - 1;
    renderProgress();
    renderStep();
  });
  document.getElementById('btn-submit').addEventListener('click', submitForm);
}

async function submitForm() {
  hideError();
  const btn = document.getElementById('btn-submit');
  if (btn?.disabled) return;
  setFormSubmitting(true);
  // Cho trình duyệt kịp vẽ overlay trước khi await fetch (tránh “đứng im”).
  await new Promise((resolve) => {
    requestAnimationFrame(() => requestAnimationFrame(resolve));
  });

  const known_skills = state.skills.includes('none') ? [] : [...state.skills];
  const detailedSkills = SKILL_PROFILE_FIELDS.flatMap((f) =>
    (state.skill_profile[f.key] || []).map((v) => `${f.key}:${v}`)
  );
  const chatSessionId = getSessionId();
  const payload = {
    background: state.background,
    role: state.role,
    role_note: state.level?.trim() || null,
    target_role_text: state.target_role_text?.trim() || null,
    known_skills: [...known_skills, ...detailedSkills],
    skill_profile: state.skill_profile,
    goals: [...state.goals],
    weekly_time: state.time ? WEEKLY_TIME_MAP[state.time] || state.time : null,
    initial_question: state.question?.trim() || null,
    session_id: chatSessionId || null,
  };

  try {
    const res = await fetch(`${API_BASE}/api/advisory/start`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      const detail = data.detail;
      const msg =
        typeof detail === 'string'
          ? detail
          : detail?.message || JSON.stringify(detail) || `HTTP ${res.status}`;
      throw new Error(msg);
    }
    if (data.profile_id) {
      localStorage.setItem('chat_profile_id', data.profile_id);
    }
    if (data.session_id) {
      localStorage.setItem('chat_session_id', data.session_id);
    }
    localStorage.setItem('chat_pending_reply', data.reply || '');
    if (data.structured) {
      localStorage.setItem('chat_structured', JSON.stringify(data.structured));
    } else {
      localStorage.removeItem('chat_structured');
    }
    if (data.advice) {
      localStorage.setItem('chat_advice', JSON.stringify(data.advice));
    }
    const redirectSid = data.session_id || chatSessionId;
    window.location.href = `chat.html?session_id=${encodeURIComponent(
      redirectSid
    )}&from=form`;
  } catch (err) {
    showError(err.message || 'Không gửi được form. Kiểm tra backend và thử lại.');
    setFormSubmitting(false);
  }
}

document.addEventListener('DOMContentLoaded', () => {
  const params = new URLSearchParams(window.location.search);
  const sid = getSessionId();
  const back = document.getElementById('backLink');
  if (sid && back) {
    back.href = `chat.html?session_id=${encodeURIComponent(sid)}`;
  }
  console.info('Advisory form loaded', {
    urlSessionId: params.get('session_id'),
    resolvedSid: sid,
  });
  renderProgress();
  renderStep();
});
