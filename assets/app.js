// ============================================================
//  Digital Labs Pathways — frontend ↔ backend glue (v2)
// ============================================================

const API_BASE = window.location.origin.includes('localhost')
  ? 'http://localhost:8000'
  : '';

const STORAGE_KEY = 'dlp_session';

// ---------- state ----------
const state = {
  sessionId: null,
  currentStep: 1,
  profile: {},
  conversation: [],
  currentQuestion: null,
  assessmentStage: null,
  github: null,
};

// ---------- API helpers ----------
async function api(path, method = 'GET', body = null) {
  const opts = { method, headers: { 'Content-Type': 'application/json' } };
  if (body) opts.body = JSON.stringify(body);
  try {
    const res = await fetch(`${API_BASE}${path}`, opts);
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      const msg = Array.isArray(err.detail)
        ? (err.detail[0]?.msg || 'Validation error')
        : (err.detail || `Request failed (${res.status})`);
      throw new Error(msg);
    }
    return await res.json();
  } catch (e) {
    console.warn(`[api] ${method} ${path} failed:`, e.message);
    return { _offline: true, error: e.message };
  }
}

// ---------- UI helpers ----------
const $ = (sel) => document.querySelector(sel);
const $$ = (sel) => document.querySelectorAll(sel);

function toggleTheme() {
  const body = document.body;
  const current = body.getAttribute("data-theme");
  body.setAttribute("data-theme", current === "light" ? "dark" : "light");
}

function toast(msg, kind = '') {
  const t = $('#toast');
  t.textContent = msg;
  t.className = `toast visible ${kind}`;
  clearTimeout(toast._timer);
  toast._timer = setTimeout(() => t.classList.remove('visible'), 3000);
}

function flashSave(label = 'Auto-saved') {
  const el = $('#saveIndicator');
  el.textContent = 'Saving…';
  el.className = 'save-indicator visible saving';
  setTimeout(() => {
    el.textContent = label;
    el.className = 'save-indicator visible';
    setTimeout(() => el.classList.remove('visible'), 1500);
  }, 400);
}

function showStep(n) {
  state.currentStep = n;
  $$('.screen').forEach(s => s.classList.remove('active'));
  $(`#screen-${n}`).classList.add('active');
  $$('.step').forEach(s => {
    const stepNum = +s.dataset.step;
    s.classList.toggle('active', stepNum === n);
    s.classList.toggle('done', stepNum < n);
  });
  window.scrollTo({ top: 0, behavior: 'smooth' });
}

function enterFlow() {
  $('#screen-hero').classList.add('hidden');
  $('#flow').classList.remove('hidden');
  showStep(state.currentStep);
}

function exitFlow() {
  $('#flow').classList.add('hidden');
  $('#screen-hero').classList.remove('hidden');
}

// ---------- session lifecycle ----------
function loadSession() {
  const saved = localStorage.getItem(STORAGE_KEY);
  if (!saved) return false;
  try {
    const parsed = JSON.parse(saved);
    Object.assign(state, parsed);
    return !!state.sessionId;
  } catch { return false; }
}

function persistState() {
  localStorage.setItem(STORAGE_KEY, JSON.stringify({
    sessionId: state.sessionId,
    currentStep: state.currentStep,
    profile: state.profile,
    conversation: state.conversation,
    currentQuestion: state.currentQuestion,
    assessmentStage: state.assessmentStage,
    github: state.github,
  }));
}

async function startSession(payload) {
  const res = await api('/api/v1/sessions', 'POST', payload);
  if (res._offline) {
    state.sessionId = 'local-' + Date.now();
    state.currentQuestion = {
      question_id: 'q_pref',
      question_text: 'What kind of questions help you show your best self?',
      question_type: 'mcq',
      options: [
        { id: 'behavioral', label: 'Behavioral (past experiences, how you handled situations)' },
        { id: 'technical', label: 'Technical (problem-solving, coding, system design)' },
        { id: 'creative', label: 'Creative (open-ended, hypothetical scenarios)' },
        { id: 'mixed', label: 'Mixed (a blend of all types)' }
      ]
    };
    state.assessmentStage = 'running';
    toast('Backend offline — running in demo mode', 'error');
  } else {
    state.sessionId = res.session_id || ('local-' + Date.now());
    state.currentQuestion = {
      question_id: res.question_id,
      question_text: res.next_question,
      question_type: res.question_type || 'open',
      options: res.options || null,
    };
    state.assessmentStage = 'running';
    toast('Session started', 'success');
  }
  state.conversation = [];
  persistState();
  return state.sessionId;
}

async function recoverSession(sessionId) {
  const res = await api(`/api/v1/sessions/${sessionId}`);
  if (res._offline) return null;
  return res;
}

// ---------- step 1: profile ----------
function readProfileForm() {
  const skills = $('#skills').value.split(',').map(s => s.trim()).filter(Boolean);
  return {
    full_name: $('#full_name').value.trim() || null,
    email: $('#email').value.trim() || null,
    age: $('#age').value ? parseInt($('#age').value) : null,
    gender: $('#gender').value || null,
    target_role: $('#target_role').value.trim() || null,
    location_preference: null,
    declared_skills: skills.length ? skills : null,
    academics: $('#school').value.trim() ? [{ institution: $('#school').value.trim() }] : null,
  };
}

function fillProfileForm(p) {
  if (!p) return;
  $('#full_name').value = p.full_name || '';
  $('#email').value = p.email || '';
  $('#age').value = p.age || '';
  $('#gender').value = p.gender || '';
  $('#target_role').value = p.target_role || '';
  $('#skills').value = (p.declared_skills || []).join(', ');
  if (p.academics?.[0]?.institution) $('#school').value = p.academics[0].institution;
}

async function saveProfile() {
  if (!state.sessionId) return;
  const data = readProfileForm();
  state.profile = { ...state.profile, ...data };
  const res = await api(`/api/v1/sessions/${state.sessionId}/profile`, 'PATCH', data);
  persistState();
  flashSave();
  return res;
}

// ---------- step 2: github ----------
async function analyzeGithub() {
  const username = $('#github_username').value.trim();
  if (!username) {
    toast('Enter a GitHub username first', 'error');
    return false;
  }
  const token = $('#oauth_token').value.trim() || null;
  $('#analyzeGh').disabled = true;
  $('#analyzeGh').textContent = 'Analyzing…';

  const res = await api(
    `/api/v1/sessions/${state.sessionId}/github-analysis`,
    'POST',
    { github_username: username, oauth_token: token }
  );

  $('#analyzeGh').disabled = false;
  $('#analyzeGh').textContent = 'Analyze →';

  const out = $('#ghResult');
  out.classList.remove('hidden');

  if (res._offline) {
    out.innerHTML = `
      <h4>Demo result for @${username}</h4>
      <p>Backend is offline; showing a mock analysis.</p>
      <pre>{
  "top_languages": ["TypeScript", "Python"],
  "repos_analyzed": 12,
  "signals": ["frontend", "api-design", "testing"]
}</pre>`;
    state.github = { username, mock: true };
  } else {
    out.innerHTML = `
      <h4>Analysis complete for @${username}</h4>
      <pre>${JSON.stringify(res, null, 2)}</pre>`;
    state.github = { username, ...res };
  }
  persistState();
  flashSave('GitHub linked');
  return true;
}

// ---------- step 3: assessment (sequential, backend-driven) ----------
function renderAssessment() {
  const list = $('#assessmentList');
  if (!list) return;

  // Build the prior Q&A log (read-only)
  const answeredHtml = state.conversation.map(turn => `
    <div class="q-block" data-qid="${turn.question_id}">
      <div class="q-text">${turn.question_text}</div>
      ${turn.selected_option ? `<div class="mcq-selected"><strong>Selected:</strong> ${turn.selected_option_label || turn.selected_option}</div>` : ''}
      ${turn.user_answer && !turn.selected_option ? `<textarea rows="4" readonly>${turn.user_answer || ''}</textarea>` : ''}
      <div class="q-status saved">✓ Saved</div>
    </div>
  `).join('');

  let currentHtml = '';
  if (state.assessmentStage === 'completed' || !state.currentQuestion) {
    currentHtml = `
      <div class="q-block">
        <div class="q-status saved">✓ Assessment complete — proceed to the final step.</div>
      </div>`;
  } else {
    const q = state.currentQuestion;
    const isMcq = q.question_type === 'mcq';

    let inputHtml = '';
    if (isMcq && q.options) {
      inputHtml = `<div class="mcq-options">
        ${q.options.map(opt => `
          <label class="mcq-option" data-value="${opt.id}">
            <input type="radio" name="mcq_answer" value="${opt.id}" />
            <span class="opt-label">${opt.label}</span>
          </label>
        `).join('')}
      </div>`;
    } else {
      inputHtml = `<textarea rows="4" placeholder="Type your answer…" id="openAnswer"></textarea>`;
    }

    currentHtml = `
      <div class="q-block" id="activeQuestion" data-qid="${q.question_id}" data-type="${q.question_type}">
        <div class="q-text">${q.question_text}</div>
        ${inputHtml}
        <div class="q-status" id="qStatus">Not submitted yet</div>
        <button class="btn btn-primary btn-sm" id="submitAnswerBtn" style="margin-top:10px;">
          Submit Answer →
        </button>
      </div>`;
  }

  list.innerHTML = answeredHtml + currentHtml;

  const submitBtn = $('#submitAnswerBtn');
  if (submitBtn) submitBtn.addEventListener('click', submitCurrentAnswer);
}

async function submitCurrentAnswer() {
  const block = $('#activeQuestion');
  if (!block) return;
  const status = $('#qStatus');
  const btn = $('#submitAnswerBtn');
  const qType = block.dataset.type;

  let answerText = '';
  let selectedOption = null;
  let selectedOptionLabel = null;

  if (qType === 'mcq') {
    const selected = block.querySelector('input[name="mcq_answer"]:checked');
    if (!selected) {
      toast('Please select an option', 'error');
      return;
    }
    selectedOption = selected.value;
    selectedOptionLabel = selected.closest('.mcq-option').querySelector('.opt-label').textContent;
    answerText = selectedOptionLabel; // Store label as answer text
  } else {
    const textarea = block.querySelector('#openAnswer');
    answerText = textarea.value.trim();
    if (!answerText) {
      toast('Please answer the question before submitting', 'error');
      return;
    }
  }

  btn.disabled = true;
  btn.textContent = 'Submitting…';
  status.textContent = 'Saving…';

  const qid = state.currentQuestion.question_id;

  const payload = { question_id: qid, answer_text: answerText };
  if (selectedOption) payload.selected_option = selectedOption;

  const res = await api(
    `/api/v1/sessions/${state.sessionId}/assessment/answer`,
    'POST',
    payload
  );

  // Log the just-answered turn
  state.conversation.push({
    question_id: qid,
    question_text: state.currentQuestion.question_text,
    user_answer: answerText,
    selected_option: selectedOption,
    selected_option_label: selectedOptionLabel,
  });

  if (res._offline) {
    // Offline: cap at 3 local turns, then mark complete
    if (state.conversation.length < 3) {
      const isMcq = state.conversation.length % 2 === 1;
      if (isMcq) {
        state.currentQuestion = {
          question_id: `q_${state.conversation.length + 1}`,
          question_text: 'Which of these best describes your problem-solving approach?',
          question_type: 'mcq',
          options: [
            { id: 'a', label: 'Break it into small steps and tackle systematically' },
            { id: 'b', label: 'Dive in and iterate quickly' },
            { id: 'c', label: 'Research thoroughly before acting' },
            { id: 'd', label: 'Collaborate with others to find the best path' }
          ]
        };
      } else {
        state.currentQuestion = {
          question_id: `q_${state.conversation.length + 1}`,
          question_text: 'How does this choice align with your long-term execution philosophy?',
          question_type: 'open',
          options: null,
        };
      }
      state.assessmentStage = 'running';
    } else {
      state.currentQuestion = null;
      state.assessmentStage = 'completed';
    }
    toast('Saved locally (offline)', 'error');
  } else if (res.stage === 'completed') {
    state.currentQuestion = null;
    state.assessmentStage = 'completed';
    toast('Assessment complete', 'success');
  } else {
    state.currentQuestion = {
      question_id: res.question_id,
      question_text: res.next_question,
      question_type: res.question_type || 'open',
      options: res.options || null,
    };
    state.assessmentStage = 'running';
  }

  persistState();
  flashSave();
  renderAssessment();
}

// ---------- step 4: final additions ----------
async function submitFinal() {
  const note = $('#personal_note').value.trim() || null;
  const links = $('#portfolio_links').value
    .split('\n')
    .map(s => s.trim())
    .filter(Boolean);

  const payload = {
    personal_note: note,
    portfolio_links: links.length ? links : null,
  };

  $('#submitFinal').disabled = true;
  $('#submitFinal').textContent = 'Submitting…';

  // First, save final additions
  const res = await api(
    `/api/v1/sessions/${state.sessionId}/final-additions`,
    'PATCH',
    payload
  );

  // Then, trigger GitHub analysis to move candidate to ready_for_review status
  if (!res._offline && state.github?.username) {
    await api(
      `/api/v1/sessions/${state.sessionId}/github-analysis`,
      'POST',
      { github_username: state.github.username, oauth_token: state.github.oauth_token || null }
    );
  }

  $('#submitFinal').disabled = false;
  $('#submitFinal').textContent = 'Submit Application →';

  state.profile.personal_note = note;
  state.profile.portfolio_links = links;
  persistState();

  const dossier = await recoverSession(state.sessionId);
  renderSummary(dossier);
  showStep(5);
  toast(res._offline ? 'Submitted (demo)' : 'Application submitted!', 'success');
}

// ---------- step 5: summary ----------
function renderSummary(dossier = null) {
  const p = state.profile;
  const gh = state.github;
  const evaluation = dossier?.overall_evaluation;
  const personality = dossier?.personality_and_fit;

  $('#summaryCard').innerHTML = `
    <h4>CANDIDATE</h4>
    <p><strong>${p.full_name || '—'}</strong> · ${p.target_role || '—'}</p>
    <p>${p.email || ''} ${p.age ? '· Age ' + p.age : ''}</p>

    ${p.declared_skills?.length ? `
      <h4>SKILLS</h4>
      <p>${p.declared_skills.join(' · ')}</p>` : ''}

    ${gh?.username ? `
      <h4>GITHUB</h4>
      <p>@${gh.username}</p>` : ''}

    ${state.conversation.length ? `
      <h4>ASSESSMENT</h4>
      <ul>${state.conversation.map(turn =>
        `<li><em>${turn.question_text}</em>${turn.selected_option ? `<br/><strong>Selected:</strong> ${turn.selected_option_label || turn.selected_option}` : `<br/>${turn.user_answer}`}</li>`
      ).join('')}</ul>` : ''}

    ${personality?.ai_summary ? `
      <h4>PERSONALITY & FIT</h4>
      <p>${personality.ai_summary}</p>
      ${personality.core_traits?.length
        ? `<p><strong>Traits:</strong> ${personality.core_traits.join(' · ')}</p>` : ''}` : ''}

    ${evaluation?.star_rating != null ? `
      <h4>AI EVALUATION</h4>
      <p><strong>${evaluation.star_rating} / 5.0</strong></p>
      <p>${evaluation.rating_reasoning || ''}</p>` : ''}

    ${p.personal_note ? `<h4>PERSONAL NOTE</h4><p>${p.personal_note}</p>` : ''}
    ${p.portfolio_links?.length ? `
      <h4>PORTFOLIO</h4>
      <ul>${p.portfolio_links.map(l => `<li><a href="${l}" target="_blank">${l}</a></li>`).join('')}</ul>` : ''}
  `;
}

// ---------- wire everything up ----------
function attachListeners() {
  $('#applyNowBtn').addEventListener('click', handleStart);
  $('#exploreBtn').addEventListener('click', () => {
    document.querySelector('#programs')?.scrollIntoView();
    toast('Programs section coming soon');
  });
  $('#navLoginBtn').addEventListener('click', () => $('#portalEmail').focus());

  $('#portalForm').addEventListener('submit', async (e) => {
    e.preventDefault();
    const saved = localStorage.getItem(STORAGE_KEY);
    if (saved && JSON.parse(saved).sessionId) {
      loadSession();
      renderAssessment();
      enterFlow();
      toast('Welcome back — resuming your session', 'success');
    } else {
      toast('No existing session found. Click "Apply Now" to start.', 'error');
    }
  });

  // step 1
  $('#avatarBtn').addEventListener('click', () => $('#avatarInput').click());
  $('#avatarInput').addEventListener('change', (e) => {
    const f = e.target.files[0];
    if (!f) return;
    const url = URL.createObjectURL(f);
    $('#avatarPreview').innerHTML = `<img src="${url}" alt="avatar"/>`;
  });
  $('#back1').addEventListener('click', () => { exitFlow(); });
  $('#next1').addEventListener('click', async () => {
    if (!$('#full_name').value || !$('#email').value || !$('#target_role').value) {
      toast('Name, email, and target role are required', 'error');
      return;
    }
    await saveProfile();
    showStep(2);
  });

  ['full_name','email','age','gender','target_role','school','skills'].forEach(id => {
    let t = null;
    $('#' + id).addEventListener('input', () => {
      clearTimeout(t);
      t = setTimeout(saveProfile, 800);
    });
  });

  // step 2
  $('#back2').addEventListener('click', () => showStep(1));
  $('#skipGh').addEventListener('click', () => {
    renderAssessment();
    showStep(3);
  });
  $('#analyzeGh').addEventListener('click', async () => {
    const ok = await analyzeGithub();
    if (ok) setTimeout(() => { renderAssessment(); showStep(3); }, 800);
  });

  // step 3
  $('#back3').addEventListener('click', () => showStep(2));
  $('#next3').addEventListener('click', () => {
    if (state.assessmentStage !== 'completed') {
      toast('Please complete the assessment questions first', 'error');
      return;
    }
    showStep(4);
  });

  // step 4
  $('#back4').addEventListener('click', () => showStep(3));
  $('#submitFinal').addEventListener('click', submitFinal);

  // step 5
  $('#startOver').addEventListener('click', () => {
    if (!confirm('This clears your session. Continue?')) return;
    localStorage.removeItem(STORAGE_KEY);
    Object.assign(state, {
      sessionId: null, currentStep: 1, profile: {},
      conversation: [], currentQuestion: null, assessmentStage: null, github: null,
    });
    exitFlow();
  });
}

async function handleStart() {
  const email = $('#portalEmail').value.trim();
  const name = prompt('Quick start — what\'s your full name?');
  if (!name) return;
  const role = prompt('And the role you\'re applying for?');
  if (!role) return;
  const mail = email || prompt('Email?');
  if (!mail) return;

  await startSession({ full_name: name, target_role: role, email: mail });
  state.profile = { full_name: name, target_role: role, email: mail };
  fillProfileForm(state.profile);
  persistState();
  renderAssessment();
  enterFlow();
}

// ---------- boot ----------
document.addEventListener('DOMContentLoaded', async () => {
  attachListeners();

  if (loadSession()) {
    const recovered = await recoverSession(state.sessionId);
    if (recovered && !recovered._offline) {
      Object.assign(state.profile, recovered.biodata || {});
      const history = recovered.personality_and_fit?.conversation_history || [];
      state.conversation = history
        .filter(h => h.user_answer)
        .map(h => ({
          question_id: h.question_id,
          question_text: h.question_text,
          user_answer: h.user_answer,
          selected_option: h.selected_option || null,
          selected_option_label: h.selected_option ? (h.options?.find(o => o.id === h.selected_option)?.label || h.selected_option) : null,
        }));
      const open = history.find(h => !h.user_answer);
      if (open) {
        state.currentQuestion = {
          question_id: open.question_id,
          question_text: open.question_text,
          question_type: open.question_type || 'open',
          options: open.options || null,
        };
        state.assessmentStage = 'running';
      } else if (history.length) {
        state.currentQuestion = null;
        state.assessmentStage = 'completed';
      }
    }
    fillProfileForm(state.profile);
    renderAssessment();
    setTimeout(() => {
      if (confirm('We found a saved session. Resume where you left off?')) {
        enterFlow();
      } else {
        localStorage.removeItem(STORAGE_KEY);
        Object.assign(state, {
          sessionId: null, currentStep: 1, profile: {},
          conversation: [], currentQuestion: null, assessmentStage: null, github: null,
        });
      }
    }, 200);
  }
});
