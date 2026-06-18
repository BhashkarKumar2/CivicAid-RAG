const form = document.querySelector("#askForm");
const results = document.querySelector("#results");
const statusBadge = document.querySelector("#status");
const dataSourceBadge = document.querySelector("#dataSource");
const profileScore = document.querySelector("#profileScore");
const profileMeter = document.querySelector("#profileMeter");
const profileHint = document.querySelector("#profileHint");
const summaryStrip = document.querySelector("#summaryStrip");
const examplesContainer = document.querySelector("#examples");
const submitLabel = document.querySelector("#submitLabel");

const fallbackExamples = [
  {
    label: "Scholarship",
    question: "I am a 21 year old OBC student from Bihar. Which scholarship can I get?",
    profile: { age: 21, state: "Bihar", occupation: "student", income: 180000, category: "OBC" },
  },
  {
    label: "Health cover",
    question: "My family income is low. Which health scheme can help with hospital treatment?",
    profile: { age: 40, state: "Bihar", occupation: "worker", income: 100000, category: "SC" },
  },
  {
    label: "Farmer support",
    question: "I am a farmer and need government income support.",
    profile: { age: 38, state: "Punjab", occupation: "farmer", income: 220000, category: "General" },
  },
  {
    label: "Business loan",
    question: "I am a woman entrepreneur and need a business loan.",
    profile: { age: 29, state: "Kerala", occupation: "entrepreneur", income: 500000, category: "SC", gender: "female" },
  },
];

function getSessionId() {
  const existing = localStorage.getItem("civicaid-session-id");
  if (existing) return existing;
  const created = crypto.randomUUID ? crypto.randomUUID() : `session-${Date.now()}-${Math.random().toString(16).slice(2)}`;
  localStorage.setItem("civicaid-session-id", created);
  return created;
}

const sessionId = getSessionId();

function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>"']/g, (char) => {
    const entities = {
      "&": "&amp;",
      "<": "&lt;",
      ">": "&gt;",
      '"': "&quot;",
      "'": "&#39;",
    };
    return entities[char];
  });
}

function numberOrNull(value) {
  return value === "" ? null : Number(value);
}

function valueOrNull(value) {
  return value.trim() === "" ? null : value.trim();
}

async function fetchJson(url, options) {
  const response = await fetch(url, options);
  let body = null;
  try {
    body = await response.json();
  } catch {
    body = null;
  }
  if (!response.ok) {
    throw new Error(formatApiError(body, response.status));
  }
  return body;
}

function formatApiError(body, status) {
  if (!body) return `Request failed with HTTP ${status}.`;
  if (typeof body.detail === "string") return body.detail;
  if (Array.isArray(body.detail)) {
    return body.detail.map((item) => `${(item.loc || []).join(".")}: ${item.msg}`).join("; ");
  }
  return `Request failed with HTTP ${status}.`;
}

function formatMoney(value) {
  if (value === null || value === undefined || value === "") return "not provided";
  return `Rs ${Number(value).toLocaleString("en-IN")}`;
}

function formatList(items, type = "ul") {
  const list = Array.isArray(items) ? items.filter(Boolean) : [];
  if (!list.length) return "<p class=\"meta\">Not listed in the local dataset.</p>";
  const tag = type === "ol" ? "ol" : "ul";
  return `<${tag}>${list.map((item) => `<li>${escapeHtml(item)}</li>`).join("")}</${tag}>`;
}

function statusClass(status) {
  if (status === "likely eligible") return "likely";
  if (status === "possibly eligible") return "possible";
  return "unlikely";
}

function confidenceClass(label) {
  if (label === "Strong") return "strong";
  if (label === "Moderate") return "moderate";
  if (label === "Verify official source") return "source";
  return "review";
}

function checkClass(passed) {
  if (passed === true) return "pass";
  if (passed === false) return "fail";
  return "unknown";
}

function profileValues() {
  return {
    age: form.elements.age.value,
    state: form.elements.state.value,
    occupation: form.elements.occupation.value,
    income: form.elements.income.value,
    category: form.elements.category.value,
    gender: form.elements.gender.value,
  };
}

function updateProfileMeter() {
  const values = profileValues();
  const total = Object.keys(values).length;
  const provided = Object.values(values).filter((value) => String(value).trim() !== "").length;
  const percent = Math.round((provided / total) * 100);
  profileScore.textContent = `${percent}%`;
  profileMeter.style.width = `${percent}%`;
  if (percent >= 85) {
    profileHint.textContent = "Profile is ready for a sharper eligibility check.";
  } else if (percent >= 50) {
    profileHint.textContent = "A few missing fields may reduce confidence.";
  } else {
    profileHint.textContent = "Fill more fields for sharper eligibility checks.";
  }
}

function setOptions(select, values) {
  const first = select.querySelector("option");
  select.innerHTML = "";
  if (first) select.append(first);
  values.forEach((value) => {
    const option = document.createElement("option");
    option.value = value;
    option.textContent = value;
    select.append(option);
  });
}

function populateMeta(meta) {
  const options = meta.profile_options || {};
  const stateOptions = document.querySelector("#stateOptions");
  stateOptions.innerHTML = (options.states || []).map((state) => `<option value="${escapeHtml(state)}"></option>`).join("");
  setOptions(document.querySelector("#occupationSelect"), options.occupations || []);
  setOptions(document.querySelector("#categorySelect"), options.categories || []);
  setOptions(document.querySelector("#genderSelect"), options.genders || []);
  dataSourceBadge.textContent = `${meta.scheme_count || 0} schemes - ${meta.data_source || "local"} data`;
  renderExamples(meta.examples || fallbackExamples);
}

function renderExamples(examples) {
  examplesContainer.innerHTML = examples
    .map((example, index) => `<button type="button" data-example="${index}">${escapeHtml(example.label)}</button>`)
    .join("");
  examplesContainer.querySelectorAll("button").forEach((button) => {
    button.addEventListener("click", () => applyExample(examples[Number(button.dataset.example)]));
  });
}

function applyExample(example) {
  form.elements.question.value = example.question || "";
  Object.entries(example.profile || {}).forEach(([field, value]) => {
    if (form.elements[field]) form.elements[field].value = value ?? "";
  });
  updateProfileMeter();
}

async function checkHealth() {
  try {
    const data = await fetchJson("/api/health");
    statusBadge.textContent = "API online";
    statusBadge.classList.remove("offline");
    statusBadge.classList.add("online");
    dataSourceBadge.textContent = `${data.schemes} schemes - ${data.data_source} data`;
  } catch {
    statusBadge.textContent = "API offline";
    statusBadge.classList.remove("online");
    statusBadge.classList.add("offline");
  }
}

async function loadMeta() {
  try {
    const meta = await fetchJson("/api/meta");
    populateMeta(meta);
  } catch {
    renderExamples(fallbackExamples);
  }
}

function buildPayload() {
  return {
    question: form.elements.question.value,
    top_k: Number(form.elements.top_k.value),
    session_id: sessionId,
    profile: {
      age: numberOrNull(form.elements.age.value),
      state: valueOrNull(form.elements.state.value),
      occupation: valueOrNull(form.elements.occupation.value),
      income: numberOrNull(form.elements.income.value),
      category: valueOrNull(form.elements.category.value),
      gender: valueOrNull(form.elements.gender.value),
    },
  };
}

function renderSummary(data) {
  const summary = data.summary || {};
  const profile = data.profile_summary || {};
  summaryStrip.innerHTML = `
    <div>
      <span class="summary-label">Top match</span>
      <strong>${escapeHtml(summary.top_scheme_name || "No local match")}</strong>
      <span class="meta">${escapeHtml(summary.confidence_label || "Low")} confidence</span>
    </div>
    <div>
      <span class="summary-label">Profile</span>
      <strong>${escapeHtml(profile.label || "unknown")} - ${escapeHtml(profile.completeness ?? 0)}% complete</strong>
      <span class="meta">${escapeHtml(summary.eligibility_status || "not checked")}</span>
    </div>
    <div>
      <span class="summary-label">Sources</span>
      <strong>${escapeHtml(summary.local_result_count ?? 0)} local / ${escapeHtml(summary.web_source_count ?? 0)} web</strong>
      <span class="meta">${escapeHtml(summary.confidence_reason || "Ask a question to check sources.")}</span>
    </div>
  `;
}

function renderTags(items, emptyLabel, className = "") {
  const values = Array.isArray(items) ? items : [];
  if (!values.length) return `<span class="tag ${className}">${escapeHtml(emptyLabel)}</span>`;
  return values.map((item) => `<span class="tag ${className}">${escapeHtml(item)}</span>`).join("");
}

function renderInsights(data) {
  const profile = data.profile_summary || {};
  const insights = data.query_insights || {};
  const summary = data.summary || {};
  const missing = profile.missing_fields || [];
  const conflicts = insights.profile_conflicts || [];
  const conflictTags = conflicts.length
    ? conflicts.map((item) => `<span class="tag bad">${escapeHtml(item.message)}</span>`).join("")
    : "<span class=\"tag\">No profile conflicts detected</span>";

  return `
    <div class="insight-grid">
      <section class="insight-panel">
        <strong>Confidence</strong>
        <span class="badge ${confidenceClass(summary.confidence_label)}">${escapeHtml(summary.confidence_label || "Low")}</span>
        <p class="meta">${escapeHtml(summary.confidence_reason || "")}</p>
      </section>
      <section class="insight-panel">
        <strong>Missing Fields</strong>
        <div class="tag-list">${renderTags(missing, "No missing fields", missing.length ? "warn" : "")}</div>
      </section>
      <section class="insight-panel">
        <strong>Question Signals</strong>
        <div class="tag-list">${renderTags([...(insights.topics || []), ...(insights.intents || [])], "General search")}</div>
      </section>
    </div>
    <section class="insight-panel">
      <strong>Profile Consistency</strong>
      <div class="tag-list">${conflictTags}</div>
    </section>
  `;
}

function renderNextActions(actions) {
  if (!Array.isArray(actions) || !actions.length) return "";
  return `
    <section class="insight-panel">
      <strong>Next Actions</strong>
      <ol class="next-actions">
        ${actions.map((action) => `<li>${escapeHtml(action)}</li>`).join("")}
      </ol>
    </section>
  `;
}

function renderAnswer(data) {
  const traceLink = data.trace_url
    ? `<a href="${escapeHtml(data.trace_url)}" target="_blank" rel="noreferrer">View Langfuse trace</a>`
    : "";
  return `
    <article class="answer-panel">
      <div class="scheme-top">
        <div>
          <h2>Answer</h2>
          <p class="meta">Generated from local scheme data${data.web_sources?.length ? " and discovered official web sources" : ""}.</p>
        </div>
        ${traceLink}
      </div>
      <pre class="answer-text">${escapeHtml(data.answer || "No answer returned.")}</pre>
    </article>
  `;
}

function renderWebSources(sources) {
  if (!Array.isArray(sources) || !sources.length) return "";
  return `
    <section class="source-panel">
      <h2>Discovered Official Web Sources</h2>
      ${sources
        .map(
          (source) => `
            <div class="source-item">
              <a href="${escapeHtml(source.url)}" target="_blank" rel="noreferrer">${escapeHtml(source.title || source.url)}</a>
              <p class="source-url">${escapeHtml(source.url)}</p>
              <p>${escapeHtml(source.snippet || "No snippet returned.")}</p>
            </div>
          `
        )
        .join("")}
    </section>
  `;
}

function renderChecks(checks) {
  return `
    <div class="check-grid">
      ${(checks || [])
        .map(
          (check) => `
            <div class="check ${checkClass(check.passed)}">
              <strong>${escapeHtml(check.name)}</strong>
              <span>${escapeHtml(check.detail)}</span>
            </div>
          `
        )
        .join("")}
    </div>
  `;
}

function renderSchemes(resultsData) {
  if (!Array.isArray(resultsData) || !resultsData.length) return "";
  return `
    <div class="scheme-grid">
      ${resultsData
        .map((item, index) => {
          const scheme = item.scheme || {};
          const eligibility = item.eligibility || {};
          const citation = item.citation || {};
          return `
            <article class="scheme-card">
              <div class="scheme-top">
                <div class="scheme-title">
                  <span class="badge ${statusClass(eligibility.status)}">${escapeHtml(eligibility.status || "unknown")} - ${escapeHtml(eligibility.score ?? 0)}% match</span>
                  <h3>${index + 1}. ${escapeHtml(scheme.name)}</h3>
                  <p class="meta">${escapeHtml(scheme.category || "Scheme")} | retrieval ${escapeHtml(item.retrieval_score ?? 0)} | matched terms: ${escapeHtml((item.matched_terms || []).join(", ") || "none")}</p>
                </div>
                <a href="${escapeHtml(citation.url || scheme.source_url || "#")}" target="_blank" rel="noreferrer">Official source</a>
              </div>
              <p>${escapeHtml(scheme.summary || "No summary available.")}</p>
              ${renderChecks(eligibility.checks)}
              <div class="detail-columns">
                <section class="detail-box">
                  <strong>Documents</strong>
                  ${formatList(scheme.documents)}
                </section>
                <section class="detail-box">
                  <strong>Apply Steps</strong>
                  ${formatList(scheme.apply_steps, "ol")}
                </section>
              </div>
              <div class="detail-box">
                <strong>Benefits</strong>
                ${formatList(scheme.benefits)}
              </div>
            </article>
          `;
        })
        .join("")}
    </div>
  `;
}

function renderAgentSteps(steps) {
  if (!Array.isArray(steps) || !steps.length) return "";
  return `
    <details class="agent-log">
      <summary>Agent steps</summary>
      <div class="agent-rows">
        ${steps
          .map(
            (step) => `
              <div class="agent-row">
                <strong>${escapeHtml(step.skill)}</strong>
                <span>${escapeHtml(step.status)}</span>
              </div>
            `
          )
          .join("")}
      </div>
    </details>
  `;
}

function renderResponse(data) {
  renderSummary(data);
  results.innerHTML = `
    ${renderInsights(data)}
    ${renderNextActions(data.next_actions)}
    ${renderAnswer(data)}
    ${renderWebSources(data.web_sources)}
    ${renderSchemes(data.results)}
    ${renderAgentSteps(data.agent_steps)}
  `;
}

function renderError(error) {
  summaryStrip.innerHTML = `
    <div>
      <span class="summary-label">Top match</span>
      <strong>Request failed</strong>
    </div>
    <div>
      <span class="summary-label">Profile</span>
      <strong>Not checked</strong>
    </div>
    <div>
      <span class="summary-label">Sources</span>
      <strong>Not checked</strong>
    </div>
  `;
  results.innerHTML = `
    <div class="error-state">
      <h2>Request failed</h2>
      <p>${escapeHtml(error.message)}</p>
    </div>
  `;
}

form.addEventListener("input", updateProfileMeter);

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  const submit = form.querySelector(".primary");
  submit.disabled = true;
  submitLabel.textContent = "Searching...";

  try {
    const data = await fetchJson("/api/ask", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(buildPayload()),
    });
    renderResponse(data);
  } catch (error) {
    renderError(error);
  } finally {
    submit.disabled = false;
    submitLabel.textContent = "Ask CivicAid";
  }
});

renderExamples(fallbackExamples);
updateProfileMeter();
checkHealth();
loadMeta();
