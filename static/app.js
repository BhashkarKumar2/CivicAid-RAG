const form = document.querySelector("#askForm");
const results = document.querySelector("#results");
const statusBadge = document.querySelector("#status");

async function checkHealth() {
  try {
    const response = await fetch("/api/health");
    const data = await response.json();
    statusBadge.textContent = `API online - ${data.schemes} schemes indexed (${data.data_source} data)`;
  } catch {
    statusBadge.textContent = "API offline";
  }
}

function numberOrNull(value) {
  return value === "" ? null : Number(value);
}

function valueOrNull(value) {
  return value.trim() === "" ? null : value.trim();
}

function classForStatus(status) {
  if (status === "likely eligible") return "likely";
  if (status === "possibly eligible") return "possible";
  return "unlikely";
}

function classForCheck(passed) {
  if (passed === true) return "pass";
  if (passed === false) return "fail";
  return "unknown";
}

function renderResponse(data) {
  const traceLink = data.trace_url
    ? `<p><a href="${data.trace_url}" target="_blank" rel="noreferrer">View Langfuse trace</a></p>`
    : "";
  const agentSteps = data.agent_steps?.length
    ? `
      <div class="agent-steps">
        <h3>Agent Skills Used</h3>
        ${data.agent_steps
          .map(
            (step) => `
              <div class="agent-step">
                <strong>${step.skill}</strong>
                <span>${step.status}</span>
              </div>
            `
          )
          .join("")}
      </div>
    `
    : "";
  const cards = data.results
    .map((item) => {
      const scheme = item.scheme;
      const eligibility = item.eligibility;
      const checks = eligibility.checks
        .map(
          (check) => `
            <div class="check ${classForCheck(check.passed)}">
              <strong>${check.name}</strong>: ${check.detail}
            </div>
          `
        )
        .join("");

      return `
        <article class="scheme">
          <span class="badge ${classForStatus(eligibility.status)}">${eligibility.status} - ${eligibility.score}% match</span>
          <h3>${scheme.name}</h3>
          <p class="meta">${scheme.category} | matched terms: ${item.matched_terms.join(", ") || "none"}</p>
          <p>${scheme.summary}</p>
          <div class="checks">${checks}</div>
          <p><strong>Documents:</strong> ${scheme.documents.join(", ")}</p>
          <p><strong>Apply:</strong> ${scheme.apply_steps.join(" -> ")}</p>
          <a href="${item.citation.url}" target="_blank" rel="noreferrer">${item.citation.title}</a>
        </article>
      `;
    })
    .join("");
  const webSources = data.web_sources?.length
    ? `
      <article class="scheme">
        <h3>Discovered Official Web Sources</h3>
        ${data.web_sources
          .map(
            (source) => `
              <p>
                <a href="${source.url}" target="_blank" rel="noreferrer">${source.title}</a><br />
                <span class="meta">${source.url}</span>
              </p>
            `
          )
          .join("")}
      </article>
    `
    : "";

  results.innerHTML = `
    <article class="answer">
      <h2>Answer</h2>
      ${traceLink}
      ${agentSteps}
      <pre>${data.answer}</pre>
    </article>
    ${webSources}
    ${cards}
  `;
}

document.querySelectorAll("[data-question]").forEach((button) => {
  button.addEventListener("click", () => {
    form.elements.question.value = button.dataset.question;
  });
});

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  const submit = form.querySelector(".primary");
  submit.disabled = true;
  submit.textContent = "Searching...";

  const payload = {
    question: form.elements.question.value,
    top_k: 3,
    profile: {
      age: numberOrNull(form.elements.age.value),
      state: valueOrNull(form.elements.state.value),
      occupation: valueOrNull(form.elements.occupation.value),
      income: numberOrNull(form.elements.income.value),
      category: valueOrNull(form.elements.category.value),
      gender: valueOrNull(form.elements.gender.value),
    },
  };

  try {
    const response = await fetch("/api/ask", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const data = await response.json();
    renderResponse(data);
  } catch (error) {
    results.innerHTML = `
      <div class="empty">
        <h2>Request failed</h2>
        <p>${error.message}</p>
      </div>
    `;
  } finally {
    submit.disabled = false;
    submit.textContent = "Ask CivicAid";
  }
});

checkHealth();
