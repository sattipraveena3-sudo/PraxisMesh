const state = { selectedRunId: null, selectedRun: null, poller: null };

const $ = (selector) => document.querySelector(selector);
const escapeHtml = (value = '') => String(value).replace(/[&<>'"]/g, (character) => ({
  '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#39;', '"': '&quot;'
}[character]));

async function api(path, options = {}) {
  const response = await fetch(path, {
    headers: { 'Content-Type': 'application/json', ...(options.headers || {}) },
    ...options,
  });
  const contentType = response.headers.get('content-type') || '';
  const payload = contentType.includes('json') ? await response.json() : await response.text();
  if (!response.ok) throw new Error(payload.detail || payload || `Request failed (${response.status})`);
  return payload;
}

function toast(message, error = false) {
  const element = $('#toast');
  element.textContent = message;
  element.className = `toast show${error ? ' error' : ''}`;
  clearTimeout(toast.timer);
  toast.timer = setTimeout(() => { element.className = 'toast'; }, 3300);
}

function chip(status) {
  return `<span class="status-chip ${escapeHtml(status)}">${escapeHtml(status.replaceAll('_', ' '))}</span>`;
}

function formatDate(value) {
  if (!value) return '—';
  return new Intl.DateTimeFormat(undefined, {
    month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit'
  }).format(new Date(value));
}

async function loadMetrics() {
  const metrics = await api('/api/metrics');
  $('#metric-total').textContent = metrics.runs_total;
  $('#metric-success').textContent = `${Math.round(metrics.success_rate * 100)}%`;
  $('#metric-approvals').textContent = metrics.pending_approvals;
  $('#metric-events').textContent = metrics.audit_events;
  $('#integrity-label').textContent = metrics.audit_integrity ? 'Chain verified' : 'Integrity warning';
  $('#integrity-label').style.color = metrics.audit_integrity ? 'var(--mint)' : 'var(--red)';
}

async function loadRuns(selectNewest = false) {
  const data = await api('/api/runs?limit=50');
  $('#run-count').textContent = data.count;
  const list = $('#run-list');
  if (!data.items.length) {
    list.innerHTML = '<div class="empty-state">No runs yet. Launch the first verified objective.</div>';
    return;
  }
  list.innerHTML = data.items.map((run) => `
    <button class="run-item ${run.id === state.selectedRunId ? 'active' : ''}" data-run-id="${run.id}">
      <div class="run-top"><span class="run-id">${run.id}</span>${chip(run.status)}</div>
      <p>${escapeHtml(run.goal)}</p>
      <time>${formatDate(run.created_at)} · ${run.plan?.steps?.length || 0} steps</time>
    </button>
  `).join('');
  list.querySelectorAll('[data-run-id]').forEach((button) => {
    button.addEventListener('click', () => selectRun(button.dataset.runId));
  });
  if (selectNewest && data.items[0]) await selectRun(data.items[0].id);
}

async function selectRun(runId) {
  state.selectedRunId = runId;
  document.querySelectorAll('.run-item').forEach((item) => item.classList.toggle('active', item.dataset.runId === runId));
  await loadSelectedRun();
}

async function loadSelectedRun() {
  if (!state.selectedRunId) return;
  const [run, events, artifacts] = await Promise.all([
    api(`/api/runs/${state.selectedRunId}`),
    api(`/api/runs/${state.selectedRunId}/events`),
    api(`/api/runs/${state.selectedRunId}/artifacts`),
  ]);
  state.selectedRun = run;
  renderRun(run);
  renderEvents(events.items);
  renderArtifacts(artifacts.items);
}

function renderRun(run) {
  $('#run-detail-empty').hidden = true;
  $('#run-detail').hidden = false;
  $('#detail-run-id').textContent = `${run.id} · ${run.planner} planner`;
  $('#detail-goal').textContent = run.goal;
  const status = $('#detail-status');
  status.className = `status-chip ${run.status}`;
  status.textContent = run.status.replaceAll('_', ' ');
  $('#plan-rationale').textContent = run.plan?.rationale || 'Planning did not complete.';

  const steps = run.plan?.steps || [];
  $('#step-flow').innerHTML = steps.map((step, index) => `
    <article class="step-node ${step.status}">
      <div class="step-number">${step.status === 'succeeded' ? '✓' : String(index + 1).padStart(2, '0')}</div>
      <div class="step-copy">
        <strong>${escapeHtml(step.name)}</strong>
        <small>${escapeHtml(step.error || step.description)}</small>
      </div>
      <span class="step-tool">${escapeHtml(step.tool)} · ${escapeHtml(step.status)}</span>
    </article>
  `).join('') || '<div class="empty-state">No validated plan is available.</div>';

  const pending = (run.approvals || []).find((approval) => approval.status === 'pending');
  const banner = $('#approval-banner');
  banner.hidden = !pending;
  if (pending) {
    const step = steps.find((item) => item.id === pending.step_id);
    $('#approval-title').textContent = step?.name || pending.step_id;
    $('#approval-reason').textContent = pending.reasons.join(' ');
    $('#approve-button').dataset.approvalId = pending.id;
    $('#deny-button').dataset.approvalId = pending.id;
  }
  const resumable = ['ready', 'created'].includes(run.status);
  $('#resume-button').hidden = !resumable;
}

function renderEvents(events) {
  const stream = $('#event-stream');
  if (!events.length) {
    stream.innerHTML = '<div class="empty-state">No evidence events recorded.</div>';
    return;
  }
  stream.innerHTML = [...events].reverse().map((event) => {
    const detail = event.payload.step_id || event.payload.plan_id || event.payload.stage || 'run-level event';
    return `
      <article class="event-card">
        <div class="event-top"><strong>${escapeHtml(event.event_type)}</strong><time>#${event.sequence}</time></div>
        <p>${escapeHtml(detail)} · ${formatDate(event.created_at)}</p>
        <span class="event-hash">${event.event_hash.slice(0, 16)}… ← ${event.previous_hash.slice(0, 8)}…</span>
      </article>
    `;
  }).join('');
}

function renderArtifacts(items) {
  $('#artifact-section').hidden = !items.length;
  $('#artifact-list').innerHTML = items.map((artifact) => `
    <div class="artifact-item">
      <span>◇ ${escapeHtml(artifact.name)} <small>${artifact.bytes} bytes</small></span>
      <a href="${artifact.download_url}">Download ↗</a>
    </div>
  `).join('');
}

async function decide(decision, approvalId) {
  if (!state.selectedRunId || !approvalId) return;
  try {
    await api(`/api/runs/${state.selectedRunId}/approvals/${approvalId}`, {
      method: 'POST', body: JSON.stringify({ decision, decided_by: 'console-operator', resume: true })
    });
    toast(decision === 'approve' ? 'Action approved. Execution resumed.' : 'Action denied. Run stopped.');
    setTimeout(refreshAll, 350);
  } catch (error) { toast(error.message, true); }
}

async function refreshAll() {
  try {
    await Promise.all([loadMetrics(), loadRuns()]);
    if (state.selectedRunId) await loadSelectedRun();
  } catch (error) { toast(error.message, true); }
}

$('#goal-form').addEventListener('submit', async (event) => {
  event.preventDefault();
  const button = $('#launch-button');
  button.disabled = true;
  button.querySelector('span').textContent = 'Validating plan…';
  try {
    const run = await api('/api/runs', {
      method: 'POST', body: JSON.stringify({ goal: $('#goal-input').value.trim(), auto_start: true })
    });
    state.selectedRunId = run.id;
    toast('Verified run created. Policy engine is evaluating actions.');
    await loadRuns();
    await loadSelectedRun();
  } catch (error) { toast(error.message, true); }
  finally {
    button.disabled = false;
    button.querySelector('span').textContent = 'Launch verified run';
  }
});

$('#approve-button').addEventListener('click', (event) => decide('approve', event.currentTarget.dataset.approvalId));
$('#deny-button').addEventListener('click', (event) => decide('deny', event.currentTarget.dataset.approvalId));
$('#resume-button').addEventListener('click', async () => {
  if (!state.selectedRunId) return;
  await api(`/api/runs/${state.selectedRunId}/execute`, { method: 'POST' });
  toast('Execution resumed.');
  setTimeout(refreshAll, 350);
});
$('#refresh-button').addEventListener('click', refreshAll);
document.querySelectorAll('[data-scroll]').forEach((item) => item.addEventListener('click', () => {
  document.getElementById(item.dataset.scroll)?.scrollIntoView({ behavior: 'smooth' });
}));

async function initialize() {
  try {
    await loadMetrics();
    await loadRuns(true);
    state.poller = setInterval(refreshAll, 3000);
  } catch (error) { toast(`API unavailable: ${error.message}`, true); }
}

initialize();
