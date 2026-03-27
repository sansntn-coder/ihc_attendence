const state = {
  isAdmin: false,
  currentAdminUsername: "",
  selectedDate: formatDateKey(new Date()),
  employees: [],
  filteredEmployees: [],
  records: [],
  admins: [],
  summary: {
    checkedInCount: 0,
    checkedOutCount: 0,
    overtimeCount: 0,
    leaveCount: 0,
    todayPresenceRate: 0,
    activeEmployeesCount: 0,
  },
  monthlySummary: {
    workedDays: 0,
    presentDays: 0,
    leaveDays: 0,
    overtimeHours: 0,
  },
};

const employeeForm = document.getElementById("employeeForm");
const employeeList = document.getElementById("employeeList");
const attendanceTableBody = document.getElementById("attendanceTableBody");
const statusFilter = document.getElementById("statusFilter");
const reportDateInput = document.getElementById("reportDate");
const exportCsvBtn = document.getElementById("exportCsvBtn");
const exportExcelBtn = document.getElementById("exportExcelBtn");
const adminLoginForm = document.getElementById("adminLoginForm");
const adminLogoutBtn = document.getElementById("adminLogoutBtn");
const adminStatusBadge = document.getElementById("adminStatusBadge");
const adminIdentity = document.getElementById("adminIdentity");
const adminHelpText = document.getElementById("adminHelpText");
const adminUsernameInput = document.getElementById("adminUsername");
const adminPasswordInput = document.getElementById("adminPassword");
const employeeSubmitBtn = document.getElementById("employeeSubmitBtn");
const employeeFormHint = document.getElementById("employeeFormHint");
const adminTools = document.getElementById("adminTools");
const passwordChangeForm = document.getElementById("passwordChangeForm");
const currentPasswordInput = document.getElementById("currentPassword");
const newPasswordInput = document.getElementById("newPassword");
const adminCreateForm = document.getElementById("adminCreateForm");
const newAdminUsernameInput = document.getElementById("newAdminUsername");
const newAdminPasswordInput = document.getElementById("newAdminPassword");
const adminUsersList = document.getElementById("adminUsersList");
const employeeSearch = document.getElementById("employeeSearch");
const teamFilter = document.getElementById("teamFilter");
const rosterStatusFilter = document.getElementById("rosterStatusFilter");

const checkedInCount = document.getElementById("checkedInCount");
const checkedOutCount = document.getElementById("checkedOutCount");
const overtimeCount = document.getElementById("overtimeCount");
const leaveCount = document.getElementById("leaveCount");
const todayPresenceRate = document.getElementById("todayPresenceRate");
const activeEmployeesCount = document.getElementById("activeEmployeesCount");
const monthWorkedDays = document.getElementById("monthWorkedDays");
const monthPresentDays = document.getElementById("monthPresentDays");
const monthLeaveDays = document.getElementById("monthLeaveDays");
const monthOvertimeHours = document.getElementById("monthOvertimeHours");

const employeeCardTemplate = document.getElementById("employeeCardTemplate");

reportDateInput.value = state.selectedDate;

adminLoginForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  try {
    await api("/api/login", {
      method: "POST",
      body: {
        username: adminUsernameInput.value.trim(),
        password: adminPasswordInput.value,
      },
    });
    adminPasswordInput.value = "";
    await loadDashboard();
  } catch (error) {
    window.alert(error.message);
  }
});

adminLogoutBtn.addEventListener("click", async () => {
  await api("/api/logout", { method: "POST" });
  await loadDashboard();
});

passwordChangeForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  if (!requireAdmin()) {
    return;
  }

  try {
    await api("/api/change-password", {
      method: "POST",
      body: {
        currentPassword: currentPasswordInput.value,
        newPassword: newPasswordInput.value,
      },
    });
    passwordChangeForm.reset();
    window.alert("Password updated successfully.");
  } catch (error) {
    window.alert(error.message);
  }
});

adminCreateForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  if (!requireAdmin()) {
    return;
  }

  try {
    await api("/api/admins", {
      method: "POST",
      body: {
        username: newAdminUsernameInput.value.trim(),
        password: newAdminPasswordInput.value,
      },
    });
    adminCreateForm.reset();
    await loadDashboard();
  } catch (error) {
    window.alert(error.message);
  }
});

employeeForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  if (!requireAdmin()) {
    return;
  }

  const formData = new FormData(employeeForm);
  try {
    await api("/api/employees", {
      method: "POST",
      body: {
        name: formData.get("employeeName").toString().trim(),
        department: formData.get("employeeDepartment").toString().trim(),
        code: formData.get("employeeCode").toString().trim().toUpperCase(),
      },
    });
    employeeForm.reset();
    await loadDashboard();
  } catch (error) {
    window.alert(error.message);
  }
});

reportDateInput.addEventListener("change", async () => {
  state.selectedDate = reportDateInput.value || formatDateKey(new Date());
  await loadDashboard();
});

statusFilter.addEventListener("change", renderHistory);
employeeSearch.addEventListener("input", applyRosterFilters);
teamFilter.addEventListener("change", applyRosterFilters);
rosterStatusFilter.addEventListener("change", applyRosterFilters);

exportCsvBtn.addEventListener("click", () => {
  if (!requireAdmin()) {
    return;
  }
  window.location.href = `/api/export?date=${encodeURIComponent(state.selectedDate)}&format=csv`;
});

exportExcelBtn.addEventListener("click", () => {
  if (!requireAdmin()) {
    return;
  }
  window.location.href = `/api/export?date=${encodeURIComponent(state.selectedDate)}&format=xls`;
});

loadDashboard();

async function loadDashboard() {
  const data = await api(`/api/bootstrap?date=${encodeURIComponent(state.selectedDate)}`);
  state.isAdmin = data.isAdmin;
  state.currentAdminUsername = data.currentAdminUsername || "";
  state.selectedDate = data.selectedDate;
  state.employees = data.employees;
  state.records = data.records;
  state.admins = data.admins || [];
  state.summary = data.summary;
  state.monthlySummary = data.monthlySummary;
  populateTeamFilter();
  applyRosterFilters();
  render();
}

function render() {
  reportDateInput.value = state.selectedDate;
  renderAdminState();
  renderEmployees();
  renderHistory();
  renderSummary();
  renderMonthlySummary();
  renderAdminUsers();
}

function renderAdminState() {
  adminStatusBadge.textContent = state.isAdmin ? "Admin mode" : "Viewer mode";
  adminStatusBadge.classList.toggle("is-admin", state.isAdmin);
  adminIdentity.textContent = state.currentAdminUsername ? `Logged in: ${state.currentAdminUsername}` : "";
  adminIdentity.classList.toggle("hidden", !state.isAdmin);
  adminLogoutBtn.classList.toggle("hidden", !state.isAdmin);
  adminLoginForm.classList.toggle("hidden", state.isAdmin);
  adminHelpText.classList.toggle("hidden", state.isAdmin);
  adminTools.classList.toggle("hidden", !state.isAdmin);
  employeeSubmitBtn.disabled = !state.isAdmin;
  employeeForm.classList.toggle("is-disabled", !state.isAdmin);
  employeeFormHint.classList.toggle("hidden", state.isAdmin);
}

function renderEmployees() {
  employeeList.innerHTML = "";

  if (state.filteredEmployees.length === 0) {
    const empty = document.createElement("p");
    empty.className = "empty-state";
    empty.textContent = "No employees match the current search or filters.";
    employeeList.append(empty);
    return;
  }

  state.filteredEmployees.forEach((employee) => {
    const attendance = employee.attendance;
    const fragment = employeeCardTemplate.content.cloneNode(true);
    const name = fragment.querySelector(".employee-name");
    const subtitle = fragment.querySelector(".employee-subtitle");
    const status = fragment.querySelector(".employee-status");
    const inTime = fragment.querySelector(".employee-in-time");
    const outTime = fragment.querySelector(".employee-out-time");
    const overtime = fragment.querySelector(".employee-overtime");
    const leave = fragment.querySelector(".employee-leave");
    const leaveType = fragment.querySelector(".employee-leave-type");
    const leaveTypeSelect = fragment.querySelector(".leave-type-select");
    const editBtn = fragment.querySelector(".edit-btn");
    const removeBtn = fragment.querySelector(".remove-btn");

    name.textContent = employee.name;
    subtitle.textContent = `${employee.department} • ${employee.code}`;
    status.textContent = attendance.status;
    status.classList.add(`status-${attendance.status.toLowerCase().replace(/\s+/g, "-")}`);
    inTime.textContent = formatTime(attendance.inTime);
    outTime.textContent = formatTime(attendance.outTime);
    overtime.textContent = `${attendance.overtimeHours}h`;
    leave.textContent = attendance.onLeave ? "Yes" : "No";
    leaveType.textContent = attendance.leaveType || "--";
    leaveTypeSelect.value = attendance.leaveType || "Sick";

    fragment.querySelector(".check-in-btn").addEventListener("click", async () => {
      await updateAttendance(employee.id, "check_in");
    });
    fragment.querySelector(".check-out-btn").addEventListener("click", async () => {
      await updateAttendance(employee.id, "check_out");
    });
    fragment.querySelector(".leave-btn").addEventListener("click", async () => {
      await updateAttendance(employee.id, "leave", leaveTypeSelect.value);
    });

    editBtn.classList.toggle("hidden", !state.isAdmin);
    removeBtn.classList.toggle("hidden", !state.isAdmin);
    editBtn.addEventListener("click", async () => {
      await editEmployee(employee);
    });
    removeBtn.addEventListener("click", async () => {
      await removeEmployee(employee);
    });

    employeeList.append(fragment);
  });
}

function renderHistory() {
  attendanceTableBody.innerHTML = "";
  const selectedStatus = statusFilter.value;
  const visibleRecords = state.records.filter((record) => selectedStatus === "all" || record.status === selectedStatus);

  if (visibleRecords.length === 0) {
    const row = document.createElement("tr");
    row.innerHTML = '<td colspan="6"><p class="empty-state">No attendance records match the current date and filter.</p></td>';
    attendanceTableBody.append(row);
    return;
  }

  visibleRecords.forEach((record) => {
    const row = document.createElement("tr");
    row.innerHTML = `
      <td>${escapeHtml(record.employeeName)}</td>
      <td>${escapeHtml(record.department)}</td>
      <td><span class="status-pill status-${record.status.toLowerCase().replace(/\s+/g, "-")}">${escapeHtml(record.status)}</span></td>
      <td>${escapeHtml(record.leaveType || "--")}</td>
      <td>${escapeHtml(record.details)}</td>
      <td>${escapeHtml(record.timestampLabel)}</td>
    `;
    attendanceTableBody.append(row);
  });
}

function renderSummary() {
  checkedInCount.textContent = state.summary.checkedInCount;
  checkedOutCount.textContent = state.summary.checkedOutCount;
  overtimeCount.textContent = `${state.summary.overtimeCount}h`;
  leaveCount.textContent = state.summary.leaveCount;
  todayPresenceRate.textContent = `${state.summary.todayPresenceRate}%`;
  activeEmployeesCount.textContent = state.summary.activeEmployeesCount;
}

function renderMonthlySummary() {
  monthWorkedDays.textContent = state.monthlySummary.workedDays;
  monthPresentDays.textContent = state.monthlySummary.presentDays;
  monthLeaveDays.textContent = state.monthlySummary.leaveDays;
  monthOvertimeHours.textContent = `${state.monthlySummary.overtimeHours}h`;
}

function renderAdminUsers() {
  adminUsersList.innerHTML = "";
  if (!state.isAdmin) {
    return;
  }
  if (state.admins.length === 0) {
    const empty = document.createElement("p");
    empty.className = "empty-state";
    empty.textContent = "No admin users found.";
    adminUsersList.append(empty);
    return;
  }

  state.admins.forEach((admin) => {
    const row = document.createElement("div");
    row.className = "admin-user-row";
    row.innerHTML = `
      <strong>${escapeHtml(admin.username)}</strong>
      <span>${escapeHtml(admin.createdAtLabel)}</span>
    `;
    adminUsersList.append(row);
  });
}

function populateTeamFilter() {
  const previousValue = teamFilter.value || "all";
  const teams = [...new Set(state.employees.map((employee) => employee.department))].sort((a, b) => a.localeCompare(b));
  teamFilter.innerHTML = '<option value="all">All teams</option>';
  teams.forEach((team) => {
    const option = document.createElement("option");
    option.value = team;
    option.textContent = team;
    teamFilter.append(option);
  });
  if ([...teamFilter.options].some((option) => option.value === previousValue)) {
    teamFilter.value = previousValue;
  }
}

function applyRosterFilters() {
  const query = employeeSearch.value.trim().toLowerCase();
  const selectedTeam = teamFilter.value;
  const selectedStatus = rosterStatusFilter.value;

  state.filteredEmployees = state.employees.filter((employee) => {
    const matchesQuery =
      !query ||
      employee.name.toLowerCase().includes(query) ||
      employee.department.toLowerCase().includes(query) ||
      employee.code.toLowerCase().includes(query);
    const matchesTeam = selectedTeam === "all" || employee.department === selectedTeam;
    const matchesStatus = selectedStatus === "all" || employee.attendance.status === selectedStatus;
    return matchesQuery && matchesTeam && matchesStatus;
  });

  renderEmployees();
}

async function updateAttendance(employeeId, action, leaveType = "") {
  if (!requireAdmin()) {
    return;
  }
  try {
    await api("/api/attendance", {
      method: "POST",
      body: { employeeId, action, leaveType, date: state.selectedDate },
    });
    await loadDashboard();
  } catch (error) {
    window.alert(error.message);
  }
}

async function editEmployee(employee) {
  if (!requireAdmin()) {
    return;
  }
  const name = window.prompt("Edit employee name:", employee.name);
  if (name === null) {
    return;
  }
  const department = window.prompt("Edit team / unit:", employee.department);
  if (department === null) {
    return;
  }
  const code = window.prompt("Edit employee ID:", employee.code);
  if (code === null) {
    return;
  }

  try {
    await api(`/api/employees/${employee.id}`, {
      method: "PUT",
      body: {
        name: name.trim() || employee.name,
        department: department.trim() || employee.department,
        code: code.trim().toUpperCase() || employee.code,
      },
    });
    await loadDashboard();
  } catch (error) {
    window.alert(error.message);
  }
}

async function removeEmployee(employee) {
  if (!requireAdmin()) {
    return;
  }
  if (!window.confirm(`Remove ${employee.name} from the database?`)) {
    return;
  }
  try {
    await api(`/api/employees/${employee.id}`, { method: "DELETE" });
    await loadDashboard();
  } catch (error) {
    window.alert(error.message);
  }
}

function requireAdmin() {
  if (state.isAdmin) {
    return true;
  }
  window.alert("Admin login is required for this action.");
  return false;
}

async function api(url, options = {}) {
  const response = await fetch(url, {
    method: options.method || "GET",
    headers: {
      "Content-Type": "application/json",
      ...(options.headers || {}),
    },
    credentials: "same-origin",
    body: options.body ? JSON.stringify(options.body) : undefined,
  });

  if (!response.ok) {
    let message = "Request failed";
    try {
      const data = await response.json();
      message = data.error || message;
    } catch (_error) {
      message = response.statusText || message;
    }
    throw new Error(message);
  }

  if (response.status === 204) {
    return null;
  }

  return response.json();
}

function formatDateKey(date) {
  return new Date(date).toLocaleDateString("en-CA");
}

function formatTime(value) {
  if (!value) {
    return "--";
  }
  return new Date(value).toLocaleTimeString([], {
    hour: "numeric",
    minute: "2-digit",
  });
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}
