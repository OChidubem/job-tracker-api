const STATUSES = [
  "Wishlist",
  "Applied",
  "Phone Screen",
  "Technical",
  "Onsite",
  "Offer",
  "Rejected",
  "Ghosted",
];

const state = {
  jobs: [],
  filters: {
    status: "",
    company: "",
    role: "",
  },
  activeLoadRequest: 0,
  filterTimer: null,
  token: localStorage.getItem("jobTrackerToken") || "",
  user: null,
};

const elements = {
  loginForm: document.getElementById("login-form"),
  registerForm: document.getElementById("register-form"),
  createForm: document.getElementById("create-job-form"),
  filterForm: document.getElementById("filter-form"),
  createStatus: document.getElementById("create-status"),
  filterStatus: document.getElementById("filter-status"),
  metrics: document.getElementById("metrics"),
  feedback: document.getElementById("feedback"),
  jobsGrid: document.getElementById("jobs-grid"),
  refreshButton: document.getElementById("refresh-button"),
  resetFiltersButton: document.getElementById("reset-filters-button"),
  jobCount: document.getElementById("job-count"),
  lastRefresh: document.getElementById("last-refresh"),
  authGuest: document.getElementById("auth-guest"),
  authUser: document.getElementById("auth-user"),
  authUsername: document.getElementById("auth-username"),
  logoutButton: document.getElementById("logout-button"),
  template: document.getElementById("job-card-template"),
  navButtons: Array.from(document.querySelectorAll("[data-scroll-target]")),
};

function populateStatusOptions() {
  for (const status of STATUSES) {
    elements.createStatus.add(new Option(status, status));
    elements.filterStatus.add(new Option(status, status));
  }
}

function setFeedback(message, tone = "") {
  elements.feedback.textContent = message;
  elements.feedback.className = `feedback ${tone}`.trim();
}

function formatDate(value) {
  if (!value) return "Unknown";

  return new Intl.DateTimeFormat(undefined, {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(value));
}

function renderMetrics() {
  const totals = STATUSES.map((status) => ({
    status,
    count: state.jobs.filter((job) => job.status === status).length,
  })).filter((entry) => entry.count > 0);

  const metrics = totals.length ? totals : [{ status: "No jobs yet", count: 0 }];

  elements.metrics.innerHTML = metrics
    .map(
      (entry) => `
        <div class="metric-tile">
          <div class="metric-label">${entry.status}</div>
          <div class="metric-value">${entry.count}</div>
        </div>
      `,
    )
    .join("");
}

function renderJobs() {
  elements.jobCount.textContent = `${state.jobs.length} ${state.jobs.length === 1 ? "job" : "jobs"}`;

  if (!state.jobs.length) {
    elements.jobsGrid.innerHTML = '<div class="empty-state">No jobs match the current filters.</div>';
    renderMetrics();
    return;
  }

  const fragment = document.createDocumentFragment();

  for (const job of state.jobs) {
    const node = elements.template.content.firstElementChild.cloneNode(true);
    node.dataset.jobId = job.id;
    node.querySelector(".job-company").textContent = job.company;
    node.querySelector(".job-role").textContent = job.role;
    node.querySelector(".job-notes").textContent = job.notes?.trim() || "No notes yet.";
    node.querySelector(".job-date").textContent = `Applied ${formatDate(job.applied_date)}`;
    node.querySelector(".job-updated").textContent = `Updated ${formatDate(job.last_updated)}`;

    const statusSelect = node.querySelector(".status-select");
    for (const status of STATUSES) {
      statusSelect.add(new Option(status, status));
    }
    statusSelect.value = job.status;
    statusSelect.addEventListener("change", () => updateStatus(job.id, statusSelect.value));

    const deleteButton = node.querySelector(".delete-button");
    deleteButton.addEventListener("click", () => deleteJob(job.id));

    fragment.appendChild(node);
  }

  elements.jobsGrid.replaceChildren(fragment);
  renderMetrics();
}

async function request(path, options = {}) {
  const headers = {
    ...(options.headers || {}),
  };

  if (!headers["Content-Type"] && options.body) {
    headers["Content-Type"] = "application/json";
  }

  if (state.token) {
    headers.Authorization = `Bearer ${state.token}`;
  }

  const response = await fetch(path, {
    headers,
    ...options,
  });

  if (!response.ok) {
    let message = `Request failed with status ${response.status}`;
    try {
      const payload = await response.json();
      message = Array.isArray(payload.detail)
        ? payload.detail.map((entry) => entry.msg).join(", ")
        : payload.detail || message;
    } catch {
      // Keep the default message when the body is not JSON.
    }
    if (response.status === 401) {
      clearSession();
      renderAuthState();
    }
    throw new Error(message);
  }

  if (response.status === 204) {
    return null;
  }

  return response.json();
}

function buildQuery() {
  const params = new URLSearchParams();
  const { status, company, role } = state.filters;

  if (status) params.set("status", status);
  if (company) params.set("company", company);
  if (role) params.set("role", role);

  return params.toString() ? `/jobs?${params.toString()}` : "/jobs";
}

function persistSession(token, user) {
  state.token = token;
  state.user = user;
  localStorage.setItem("jobTrackerToken", token);
}

function clearSession() {
  state.token = "";
  state.user = null;
  state.jobs = [];
  localStorage.removeItem("jobTrackerToken");
}

function renderAuthState() {
  const authenticated = Boolean(state.token && state.user);
  elements.authGuest.classList.toggle("hidden", authenticated);
  elements.authUser.classList.toggle("hidden", !authenticated);
  elements.createForm.closest(".card").classList.toggle("hidden", !authenticated);
  elements.metrics.closest(".card").classList.toggle("hidden", !authenticated);
  elements.jobsGrid.closest(".card").classList.toggle("hidden", !authenticated);

  if (authenticated) {
    elements.authUsername.textContent = state.user.username;
  } else {
    elements.authUsername.textContent = "";
    elements.jobCount.textContent = "0 jobs";
    elements.lastRefresh.textContent = "Sign in to load your workspace";
    elements.metrics.innerHTML = '<div class="empty-state">Your pipeline appears here after you sign in.</div>';
    elements.jobsGrid.innerHTML = '<div class="empty-state">Create an account or log in to view your jobs.</div>';
  }
}

async function loadJobs() {
  if (!state.token) {
    renderAuthState();
    return;
  }

  const requestId = ++state.activeLoadRequest;
  setFeedback("Syncing jobs...");

  try {
    const jobs = await request(buildQuery());
    if (requestId !== state.activeLoadRequest) {
      return;
    }
    state.jobs = jobs;
    elements.lastRefresh.textContent = `Last sync ${new Intl.DateTimeFormat(undefined, {
      timeStyle: "short",
      dateStyle: "medium",
    }).format(new Date())}`;
    renderJobs();
    setFeedback(`Loaded ${state.jobs.length} ${state.jobs.length === 1 ? "job" : "jobs"}.`, "success");
  } catch (error) {
    if (requestId !== state.activeLoadRequest) {
      return;
    }
    setFeedback(error.message, "error");
  }
}

async function authenticate(path, form) {
  const formData = new FormData(form);
  const payload = {
    username: String(formData.get("username")).trim(),
    password: String(formData.get("password")),
  };

  const result = await request(path, {
    method: "POST",
    body: JSON.stringify(payload),
  });
  persistSession(result.token, result.user);
  renderAuthState();
  await loadJobs();
}

async function createJob(event) {
  event.preventDefault();
  const formData = new FormData(elements.createForm);
  const payload = {
    company: String(formData.get("company")).trim(),
    role: String(formData.get("role")).trim(),
    status: String(formData.get("status")),
    notes: String(formData.get("notes")).trim() || null,
  };

  try {
    await request("/jobs", {
      method: "POST",
      body: JSON.stringify(payload),
    });
    elements.createForm.reset();
    elements.createStatus.value = "Applied";
    setFeedback("Job created.", "success");
    await loadJobs();
  } catch (error) {
    setFeedback(error.message, "error");
  }
}

async function updateStatus(jobId, status) {
  try {
    await request(`/jobs/${jobId}`, {
      method: "PATCH",
      body: JSON.stringify({ status }),
    });
    setFeedback("Status updated.", "success");
    await loadJobs();
  } catch (error) {
    setFeedback(error.message, "error");
  }
}

async function deleteJob(jobId) {
  try {
    await request(`/jobs/${jobId}`, {
      method: "DELETE",
    });
    setFeedback("Job deleted.", "success");
    await loadJobs();
  } catch (error) {
    setFeedback(error.message, "error");
  }
}

async function hydrateSession() {
  if (!state.token) {
    renderAuthState();
    return;
  }

  try {
    state.user = await request("/auth/me");
  } catch {
    clearSession();
  }
  renderAuthState();
}

async function handleLogin(event) {
  event.preventDefault();
  try {
    await authenticate("/auth/login", elements.loginForm);
    elements.loginForm.reset();
    setFeedback("Logged in.", "success");
  } catch (error) {
    setFeedback(error.message, "error");
  }
}

async function handleRegister(event) {
  event.preventDefault();
  try {
    await authenticate("/auth/register", elements.registerForm);
    elements.registerForm.reset();
    setFeedback("Account created.", "success");
  } catch (error) {
    setFeedback(error.message, "error");
  }
}

async function handleLogout() {
  try {
    await request("/auth/logout", { method: "POST" });
  } catch {
    // Clear local session even if the server token is already invalid.
  }
  clearSession();
  renderAuthState();
  setFeedback("Logged out.", "success");
}

function updateFilters() {
  const formData = new FormData(elements.filterForm);
  state.filters = {
    status: String(formData.get("status") || ""),
    company: String(formData.get("company") || "").trim(),
    role: String(formData.get("role") || "").trim(),
  };
  clearTimeout(state.filterTimer);
  state.filterTimer = window.setTimeout(loadJobs, 180);
}

function resetFilters() {
  elements.filterForm.reset();
  state.filters = {
    status: "",
    company: "",
    role: "",
  };
  loadJobs();
}

function scrollToSection(event) {
  const targetId = event.currentTarget.dataset.scrollTarget;
  const target = document.getElementById(targetId);
  if (!target) {
    return;
  }
  target.scrollIntoView({ behavior: "smooth", block: "start" });
}

function init() {
  populateStatusOptions();
  elements.createStatus.value = "Applied";
  elements.loginForm.addEventListener("submit", handleLogin);
  elements.registerForm.addEventListener("submit", handleRegister);
  elements.createForm.addEventListener("submit", createJob);
  elements.filterForm.addEventListener("input", updateFilters);
  elements.refreshButton.addEventListener("click", loadJobs);
  elements.resetFiltersButton.addEventListener("click", resetFilters);
  elements.logoutButton.addEventListener("click", handleLogout);
  elements.navButtons.forEach((button) => button.addEventListener("click", scrollToSection));
  hydrateSession().then(loadJobs);
}

init();
