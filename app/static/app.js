const escapeHTML = value => String(value ?? '').replace(/[&<>"']/g, character => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[character]));
function safeLink(value) {
  try { const url = new URL(value); return url.protocol === 'https:' && url.hostname === 'github.com' ? url.href : '#'; }
  catch { return '#'; }
}
const state = {
  analyses: [],
  selected: null,
};

const elements = {
  form: document.querySelector("#analysis-form"),
  input: document.querySelector("#repository"),
  analyzeButton: document.querySelector("#analyze-button"),
  demoButton: document.querySelector("#demo-button"),
  message: document.querySelector("#message"),
  healthScore: document.querySelector("#health-score"),
  scoreRing: document.querySelector("#score-ring"),
  scoreRingValue: document.querySelector("#score-ring-value"),
  analysisCount: document.querySelector("#analysis-count"),
  ciSuccess: document.querySelector("#ci-success"),
  openActions: document.querySelector("#open-actions"),
  repositoryName: document.querySelector("#repository-name"),
  repositoryLink: document.querySelector("#repository-link"),
  verdict: document.querySelector("#verdict"),
  summary: document.querySelector("#summary"),
  miniMetrics: document.querySelector("#mini-metrics"),
  languageList: document.querySelector("#language-list"),
  historyList: document.querySelector("#history-list"),
  riskList: document.querySelector("#risk-list"),
  actionList: document.querySelector("#action-list"),
  triageList: document.querySelector("#triage-list"),
};

async function request(path, options = {}) {
  const response = await fetch(path, {
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
    ...options,
  });
  const payload = await response.json();
  if (!response.ok) {
    throw new Error(payload.detail || "Request failed.");
  }
  return payload;
}

function setMessage(text = "", type = "") {
  elements.message.textContent = text;
  elements.message.className = `message ${type}`.trim();
}

function formatDate(value) {
  return new Intl.DateTimeFormat("en", {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(value));
}

function renderOverview(overview, analysis) {
  elements.analysisCount.textContent = overview.analyses;
  elements.openActions.textContent = overview.open_actions;
  elements.healthScore.textContent = analysis.score;
  elements.scoreRingValue.textContent = analysis.score;
  elements.scoreRing.style.setProperty("--score", analysis.score);
  elements.ciSuccess.textContent =
    analysis.metrics.ci_success_rate === null ? "N/A" : `${analysis.metrics.ci_success_rate}%`;
}

function renderReport(analysis) {
  state.selected = analysis;
  elements.repositoryName.textContent = analysis.repository;
  elements.repositoryLink.href = safeLink(analysis.repository_url);
  elements.repositoryLink.hidden = !analysis.repository_url;
  elements.verdict.textContent = analysis.verdict;
  elements.summary.textContent = analysis.summary;

  const metrics = [
    ["Stars", analysis.metrics.stars],
    ["Forks", analysis.metrics.forks],
    ["Sampled open issues", analysis.metrics.open_issues],
    ["Days since push", analysis.metrics.days_since_push],
  ];
  elements.miniMetrics.innerHTML = metrics
    .map(
      ([label, value]) => `
        <div class="mini-metric">
          <strong>${escapeHTML(value)}</strong>
          <span>${escapeHTML(label)}</span>
        </div>
      `,
    )
    .join("");

  elements.languageList.innerHTML = analysis.metrics.language_mix.length
    ? analysis.metrics.language_mix
        .map(
          (language) => `
            <div class="language-row">
              <span>${escapeHTML(language.name)}</span>
              <div class="language-track">
                <span style="width:${Math.max(language.share, 2)}%"></span>
              </div>
              <strong>${Number(language.share) || 0}%</strong>
            </div>
          `,
        )
        .join("")
    : '<div class="empty-state">No language data available.</div>';

  elements.riskList.innerHTML = analysis.risks
    .map(
      (risk) => `
        <div class="stack-item">
          <div class="stack-top">
            <strong>${escapeHTML(risk.title)}</strong>
            <span class="severity-pill ${escapeHTML(risk.severity)}">${escapeHTML(risk.severity)}</span>
          </div>
          <p>${escapeHTML(risk.detail)}</p>
        </div>
      `,
    )
    .join("");

  elements.actionList.innerHTML = analysis.actions
    .map(
      (action) => `
        <div class="stack-item">
          <div class="stack-top">
            <strong>${escapeHTML(action.title)}</strong>
            <span class="priority-pill ${escapeHTML(action.priority)}">${escapeHTML(action.priority)}</span>
          </div>
          <p>${escapeHTML(action.why)}</p>
        </div>
      `,
    )
    .join("");

  elements.triageList.innerHTML = analysis.triaged_issues.length
    ? analysis.triaged_issues
        .map(
          (issue) => `
            <a class="triage-row" href="${escapeHTML(safeLink(issue.url))}" target="_blank" rel="noreferrer">
              <span class="issue-number">#${escapeHTML(issue.number)}</span>
              <strong class="issue-title">${escapeHTML(issue.title)}</strong>
              <span class="priority-pill ${escapeHTML(issue.priority)}">${escapeHTML(issue.priority)}</span>
              <span class="issue-meta">${escapeHTML(issue.age_days)}d · ${escapeHTML(issue.comments)} msg</span>
            </a>
          `,
        )
        .join("")
    : '<div class="empty-state">No issues in the available sample; check data completeness above.</div>';
}

function renderHistory() {
  elements.historyList.innerHTML = state.analyses
    .slice(0, 8)
    .map(
      (analysis) => `
        <button class="history-item" data-analysis-id="${escapeHTML(analysis.id)}" type="button">
          <span class="history-top">
            <strong>${escapeHTML(analysis.repository)}</strong>
            <span class="score-pill">${escapeHTML(analysis.score)}</span>
          </span>
          <small>${formatDate(analysis.created_at)} · ${escapeHTML(analysis.verdict)}</small>
        </button>
      `,
    )
    .join("");

  elements.historyList.querySelectorAll("[data-analysis-id]").forEach((button) => {
    button.addEventListener("click", () => {
      const analysis = state.analyses.find((item) => item.id === button.dataset.analysisId);
      if (analysis) {
        renderReport(analysis);
        loadOverview(analysis);
      }
    });
  });
}

async function loadOverview(analysis = state.selected) {
  const overview = await request("/api/overview");
  if (analysis) renderOverview(overview, analysis);
}

async function refresh(preferredAnalysis = null) {
  state.analyses = await request("/api/analyses");
  const analysis = preferredAnalysis || state.analyses[0];
  renderHistory();
  if (analysis) {
    renderReport(analysis);
    await loadOverview(analysis);
  }
}

async function createAnalysis(repository) {
  elements.analyzeButton.disabled = true;
  setMessage(`Analyzing ${repository}…`);
  try {
    const analysis = await request("/api/analyses", {
      method: "POST",
      body: JSON.stringify({ repository }),
    });
    await refresh(analysis);
    setMessage(`Analysis saved for ${escapeHTML(analysis.repository)}.`);
    elements.form.reset();
  } catch (error) {
    setMessage(error.message, "error");
  } finally {
    elements.analyzeButton.disabled = false;
  }
}

elements.form.addEventListener("submit", (event) => {
  event.preventDefault();
  const repository = elements.input.value.trim();
  if (repository) createAnalysis(repository);
});

elements.demoButton.addEventListener("click", async () => {
  setMessage("Creating a fresh demo report…");
  try {
    const analysis = await request("/api/analyses/demo", { method: "POST" });
    await refresh(analysis);
    setMessage("Demo report created.");
  } catch (error) {
    setMessage(error.message, "error");
  }
});

refresh().catch((error) => setMessage(error.message, "error"));

