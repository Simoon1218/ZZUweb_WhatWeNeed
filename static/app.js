/* ZZU WhatWeNeed SPA */

const TAB_META = {
  dashboard: ["校园概览", "欢迎回来，一站查看课表、空教室、成绩、考试与校园卡"],
  classrooms: ["空教室查询", "按校区、教学楼、日期、楼层与节次筛选空闲自习教室"],
  courses: ["个人课表", "按学期与周次查看课程安排与上课时间"],
  grades: ["成绩查询", "查看历年课程成绩、学分统计与加权绩点参考"],
  exams: ["期末考试", "查看当前学期考试时间、地点、座位号与倒计时"],
  ecard: ["校园卡与电费", "实时查询校园卡余额、宿舍剩余电量并支持卡对卡转账"],
};

const COURSE_COLORS = [
  "#9e1f32",
  "#2563eb",
  "#0f766e",
  "#7c3aed",
  "#c2410c",
  "#0369a1",
  "#4f46e5",
  "#b45309",
];

const state = {
  user: null,
  loginMode: "password",
  activeTab: "dashboard",
  campuses: [],
  semesters: [],
  selectedPeriods: new Set(),
  weekOffset: 0,
  timetable: [],
  grades: [],
  pendingTransfer: null,
};

const $ = (id) => document.getElementById(id);

function showToast(message, type = "info") {
  const container = $("toast-container");
  const el = document.createElement("div");
  el.className = `toast ${type}`;
  el.textContent = message;
  container.appendChild(el);
  setTimeout(() => {
    el.remove();
  }, 3600);
}

async function apiFetch(url, options = {}) {
  const resp = await fetch(url, {
    credentials: "same-origin",
    headers: {
      "Content-Type": "application/json",
      ...(options.headers || {}),
    },
    ...options,
  });

  let data = null;
  try {
    data = await resp.json();
  } catch {
    data = null;
  }

  if (resp.status === 401 && !url.startsWith("/api/auth/")) {
    showLoginView();
    throw new Error((data && data.detail) || "会话已过期，请重新登录");
  }

  if (!resp.ok) {
    throw new Error((data && data.detail) || `请求失败 (${resp.status})`);
  }

  return data;
}

function pick(obj, keys, fallback = "") {
  if (!obj || typeof obj !== "object") return fallback;
  for (const k of keys) {
    if (obj[k] !== undefined && obj[k] !== null && obj[k] !== "") {
      return obj[k];
    }
  }
  return fallback;
}

function asArray(val) {
  if (Array.isArray(val)) return val;
  if (val && typeof val === "object") {
    for (const k of ["list", "rows", "data", "items", "courses", "grades", "tasks", "semester_grades"]) {
      if (Array.isArray(val[k])) return val[k];
    }
  }
  return [];
}

function escapeHtml(str) {
  return String(str ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

// ------------------------------------------------------------------
// Theme
// ------------------------------------------------------------------
function initTheme() {
  const saved = localStorage.getItem("zzu_theme");
  if (saved === "dark") {
    document.documentElement.setAttribute("data-theme", "dark");
  }
  $("theme-toggle-btn").addEventListener("click", () => {
    const isDark = document.documentElement.getAttribute("data-theme") === "dark";
    const next = isDark ? "light" : "dark";
    document.documentElement.setAttribute("data-theme", next);
    localStorage.setItem("zzu_theme", next);
  });
}

// ------------------------------------------------------------------
// Auth & View Switching
// ------------------------------------------------------------------
function showLoginView() {
  state.user = null;
  $("app-shell").classList.add("hidden");
  $("login-view").classList.remove("hidden");
}

function showAppView(user) {
  state.user = user;
  $("login-view").classList.add("hidden");
  $("app-shell").classList.remove("hidden");

  $("sidebar-account").textContent = user.account;
  $("sidebar-mode").textContent = user.demo_mode ? "演示体验账号" : "郑州大学移动校园";
  $("demo-badge").classList.toggle("hidden", !user.demo_mode);
  $("today-badge").textContent = user.today || "";
  $("tx-from").value = user.account || "";
  $("cr-date").value = user.today || new Date().toISOString().slice(0, 10);

  switchTab("dashboard");
  bootstrapData();
}

function switchTab(tab) {
  state.activeTab = tab;
  const [title, desc] = TAB_META[tab] || ["ZZU WhatWeNeed", ""];
  $("page-title").textContent = title;
  $("page-desc").textContent = desc;

  document.querySelectorAll(".tab-panel").forEach((el) => {
    el.classList.toggle("active", el.id === `panel-${tab}`);
  });
  document.querySelectorAll(".nav-item, .mnav-item").forEach((el) => {
    el.classList.toggle("active", el.dataset.tab === tab);
  });

  if (tab === "classrooms" && state.campuses.length === 0) {
    loadCampuses();
  }
  if (tab === "grades" && state.grades.length === 0) {
    loadGrades();
  }
  if (tab === "ecard") {
    loadEcard(false);
  }
}

async function bootstrapData() {
  await Promise.allSettled([
    loadSemesters(),
    loadCampuses(),
    loadEcard(false),
  ]);
  await Promise.allSettled([
    loadCourses(),
    loadExams(),
  ]);
}

// ------------------------------------------------------------------
// 1. Semesters (shared by Courses & Exams)
// ------------------------------------------------------------------
async function loadSemesters() {
  try {
    const res = await apiFetch("/api/jw/semesters");
    const list = asArray(res.data);
    state.semesters = list;

    const courseSel = $("course-semester");
    const examSel = $("exam-semester");
    courseSel.innerHTML = "";
    examSel.innerHTML = "";

    if (list.length === 0) {
      const opt = new Option("未获取到学期", "");
      courseSel.add(opt.cloneNode(true));
      examSel.add(opt);
      return;
    }

    let defaultId = "";
    list.forEach((s, idx) => {
      const id = String(pick(s, ["id", "semester_id", "semesterId"], idx));
      const name = pick(s, ["name", "name_zh", "semester_name", "code"], `学期 ${id}`);
      const isCur = Boolean(pick(s, ["is_current", "current", "isCurrent"], false));
      if (isCur || idx === 0) {
        if (!defaultId || isCur) defaultId = id;
      }
      courseSel.add(new Option(name, id));
      examSel.add(new Option(name, id));
    });

    if (defaultId) {
      courseSel.value = defaultId;
      examSel.value = defaultId;
      const activeSem = list.find((s) => String(pick(s, ["id", "semester_id", "semesterId"])) === defaultId);
      $("dash-semester-name").textContent = pick(activeSem, ["name", "name_zh", "semester_name"], "当前学期");
    }
  } catch (err) {
    showToast(`学期列表加载失败：${err.message}`, "error");
  }
}

// ------------------------------------------------------------------
// 2. Empty Classrooms (空教室查询)
// ------------------------------------------------------------------
function initPeriodPills() {
  const wrap = $("cr-periods");
  wrap.innerHTML = "";
  for (let i = 1; i <= 10; i++) {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "period-pill";
    btn.dataset.period = String(i);
    btn.textContent = `第${i}节`;
    btn.addEventListener("click", () => {
      if (state.selectedPeriods.has(i)) {
        state.selectedPeriods.delete(i);
        btn.classList.remove("selected");
      } else {
        state.selectedPeriods.add(i);
        btn.classList.add("selected");
      }
    });
    wrap.appendChild(btn);
  }

  document.querySelectorAll(".chip-btn[data-periods]").forEach((chip) => {
    chip.addEventListener("click", () => {
      state.selectedPeriods.clear();
      const raw = chip.dataset.periods;
      if (raw) {
        raw.split(",").forEach((n) => state.selectedPeriods.add(Number(n)));
      }
      document.querySelectorAll(".period-pill").forEach((pill) => {
        pill.classList.toggle("selected", state.selectedPeriods.has(Number(pill.dataset.period)));
      });
    });
  });
}

async function loadCampuses() {
  try {
    const res = await apiFetch("/api/jw/campuses");
    const rawList = asArray(res.data);
    state.campuses = rawList;

    const campusSel = $("cr-campus");
    campusSel.innerHTML = "";

    rawList.forEach((c, idx) => {
      const name = pick(c, ["campus_name", "campusName", "name_zh", "name"], `校区 ${idx + 1}`);
      campusSel.add(new Option(name, String(idx)));
    });

    populateBuildings();
  } catch (err) {
    showToast(`教学楼列表加载失败：${err.message}`, "error");
  }
}

function populateBuildings() {
  const idx = Number($("cr-campus").value || 0);
  const campus = state.campuses[idx];
  const bSel = $("cr-building");
  bSel.innerHTML = "";

  const buildings = asArray(pick(campus, ["buildings", "building_list", "buildingList", "children"], []));
  if (buildings.length === 0 && campus) {
    // Fallback if upstream returns flat building objects
    const id = pick(campus, ["building_id", "buildingId", "id"], "5");
    const name = pick(campus, ["building_name", "buildingName", "name_zh", "name"], `教学楼 ${id}`);
    bSel.add(new Option(name, String(id)));
    return;
  }

  buildings.forEach((b) => {
    const id = pick(b, ["building_id", "buildingId", "id"], "");
    const name = pick(b, ["building_name", "buildingName", "name_zh", "name"], `教学楼 ${id}`);
    bSel.add(new Option(name, String(id)));
  });
}

async function searchClassrooms() {
  const buildingId = $("cr-building").value;
  if (!buildingId) {
    showToast("请先选择教学楼", "error");
    return;
  }

  const date = $("cr-date").value;
  const floor = $("cr-floor").value;
  const periods = [...state.selectedPeriods].sort((a, b) => a - b).join(",");

  const params = new URLSearchParams({ building_id: buildingId });
  if (date) params.set("date", date);
  if (floor) params.set("floor", floor);
  if (periods) params.set("periods", periods);

  const btn = $("cr-search-btn");
  btn.disabled = true;
  btn.textContent = "查询中...";

  try {
    const res = await apiFetch(`/api/jw/classrooms?${params.toString()}`);
    $("cr-raw").textContent = JSON.stringify(res, null, 2);

    // Update floor filter options while keeping selection
    const floorSel = $("cr-floor");
    const prevFloor = floorSel.value;
    floorSel.innerHTML = '<option value="">全部楼层</option>';
    (res.floors || []).forEach((f) => {
      floorSel.add(new Option(`${f} 楼`, String(f)));
    });
    if (prevFloor && (res.floors || []).includes(prevFloor)) {
      floorSel.value = prevFloor;
    }

    $("cr-summary").textContent = `共 ${res.total_rooms} 间教室，符合条件 ${res.available_count} 间（${res.date}）`;
    renderRooms(res.available_rooms || []);
  } catch (err) {
    showToast(`查询空教室失败：${err.message}`, "error");
  } finally {
    btn.disabled = false;
    btn.textContent = "查询空教室";
  }
}

function renderRooms(rooms) {
  const wrap = $("cr-results");
  if (!rooms.length) {
    wrap.innerHTML = '<div class="empty-state">当前筛选条件下没有空闲教室，试试调整节次或楼层。</div>';
    return;
  }

  wrap.innerHTML = rooms
    .map((r) => {
      const name = pick(r, ["room_name", "roomName", "name_zh", "name"], "未知教室");
      const floor = pick(r, ["floor"], "-");
      const seats = pick(r, ["seats", "seat_count", "capacity"], "");
      const roomType = pick(r, ["room_type", "roomType", "type_name"], "");
      const units = String(pick(r, ["occupy_units", "occupyUnits"], "0000000000"));

      const cells = Array.from({ length: 10 }, (_, idx) => {
        const busy = units[idx] === "1";
        return `<div class="unit-cell ${busy ? "busy" : "free"}" title="第${idx + 1}节：${busy ? "占用" : "空闲"}">${idx + 1}</div>`;
      }).join("");

      const metaParts = [`${floor}楼`];
      if (seats) metaParts.push(`${seats}座`);
      if (roomType) metaParts.push(roomType);

      return `
        <div class="room-card">
          <div class="room-top">
            <span class="room-name">${escapeHtml(name)}</span>
            <span class="badge badge-success">空闲可用</span>
          </div>
          <div class="room-meta">${escapeHtml(metaParts.join(" · "))}</div>
          <div class="unit-bar">${cells}</div>
        </div>
      `;
    })
    .join("");
}

// ------------------------------------------------------------------
// 3. Course Schedule (个人课表)
// ------------------------------------------------------------------
function getWeekRange(offsetWeeks) {
  const now = new Date();
  const day = now.getDay() || 7; // Mon=1 .. Sun=7
  const monday = new Date(now);
  monday.setDate(now.getDate() - (day - 1) + offsetWeeks * 7);
  const sunday = new Date(monday);
  sunday.setDate(monday.getDate() + 6);

  const fmt = (d) =>
    `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
  return { start: fmt(monday), end: fmt(sunday) };
}

async function loadCourses() {
  const semesterId = $("course-semester").value;
  if (!semesterId) return;

  const { start, end } = getWeekRange(state.weekOffset);
  $("course-date-range").textContent = `${start} ~ ${end}`;

  try {
    const [courseRes, timeRes] = await Promise.all([
      apiFetch(`/api/jw/courses?semester_id=${encodeURIComponent(semesterId)}&start_date=${start}&end_date=${end}`),
      apiFetch(`/api/jw/timetable?semester_id=${encodeURIComponent(semesterId)}`).catch(() => ({ data: [] })),
    ]);

    state.timetable = asArray(timeRes.data);
    const courses = asArray(courseRes.data);
    $("course-raw").textContent = JSON.stringify(courseRes, null, 2);
    $("dash-course-count").textContent = String(courses.length);
    renderTimetable(courses);
  } catch (err) {
    showToast(`课表加载失败：${err.message}`, "error");
    $("course-grid-wrap").innerHTML = `<div class="empty-state">${escapeHtml(err.message)}</div>`;
  }
}

function renderTimetable(courses) {
  const wrap = $("course-grid-wrap");
  const days = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"];

  // Map courses to [weekday][start_unit]
  const colorMap = new Map();
  let colorIdx = 0;
  const slots = Array.from({ length: 11 }, () => Array.from({ length: 8 }, () => []));

  courses.forEach((c) => {
    const name = pick(c, ["course_name", "courseName", "lesson_name", "name_zh", "name"], "未命名课程");
    if (!colorMap.has(name)) {
      colorMap.set(name, COURSE_COLORS[colorIdx++ % COURSE_COLORS.length]);
    }
    let weekday = Number(pick(c, ["weekday", "week_day", "day_of_week", "day"], 0));
    if (!weekday && c.date) {
      const parsed = new Date(c.date);
      if (!Number.isNaN(parsed.getTime())) weekday = parsed.getDay() || 7;
    }
    const startUnit = Number(pick(c, ["start_unit", "startUnit", "unit_start", "start_section"], 1));
    const endUnit = Number(pick(c, ["end_unit", "endUnit", "unit_end", "end_section"], startUnit));

    if (weekday >= 1 && weekday <= 7 && startUnit >= 1 && startUnit <= 10) {
      slots[startUnit][weekday].push({
        name,
        room: pick(c, ["room_name", "roomName", "classroom", "place"], ""),
        teacher: pick(c, ["teacher_name", "teacherName", "teachers"], ""),
        weeks: pick(c, ["weeks", "week_str"], ""),
        span: Math.max(1, endUnit - startUnit + 1),
        color: colorMap.get(name),
      });
    }
  });

  const periodTimes = {};
  state.timetable.forEach((t, idx) => {
    const p = Number(pick(t, ["index", "unit", "section", "index_no"], idx + 1));
    const st = pick(t, ["start_time", "startTime", "start_text"], "");
    const et = pick(t, ["end_time", "endTime", "end_text"], "");
    if (st || et) periodTimes[p] = `${st}${et ? "-" + et : ""}`;
  });

  let html = '<table class="timetable"><thead><tr><th class="period-col">节次</th>';
  days.forEach((d) => {
    html += `<th>${d}</th>`;
  });
  html += "</tr></thead><tbody>";

  for (let p = 1; p <= 10; p++) {
    html += `<tr><td class="period-col"><strong>第${p}节</strong><br/><span>${escapeHtml(periodTimes[p] || "")}</span></td>`;
    for (let d = 1; d <= 7; d++) {
      const items = slots[p][d];
      const cellHtml = items
        .map(
          (item) => `
            <div class="course-block" style="background:${item.color}">
              <div class="c-title">${escapeHtml(item.name)}</div>
              <div class="c-meta">${escapeHtml([item.room, item.teacher].filter(Boolean).join(" · "))}</div>
              ${item.span > 1 ? `<div class="c-meta">第${p}-${p + item.span - 1}节</div>` : ""}
            </div>
          `
        )
        .join("");
      html += `<td>${cellHtml}</td>`;
    }
    html += "</tr>";
  }

  html += "</tbody></table>";
  wrap.innerHTML = html;
}

// ------------------------------------------------------------------
// 4. Grades (成绩查询)
// ------------------------------------------------------------------
function flattenGrades(rawData) {
  if (Array.isArray(rawData)) {
    // Check if nested by semester
    const nested = [];
    for (const item of rawData) {
      const children = asArray(pick(item, ["grades", "course_grades", "lessons", "items"], null));
      if (children.length) {
        const semName = pick(item, ["semester", "semester_name", "name_zh", "name"], "");
        children.forEach((g) => nested.push({ ...g, _semester: semName }));
      } else {
        nested.push(item);
      }
    }
    return nested;
  }
  return asArray(rawData);
}

async function loadGrades() {
  try {
    const res = await apiFetch("/api/jw/grades");
    $("grades-raw").textContent = JSON.stringify(res, null, 2);

    const flat = flattenGrades(res.data);
    state.grades = flat.map((g) => ({
      semester: pick(g, ["semester", "semester_name", "semesterName", "_semester"], "未知学期"),
      course_name: pick(g, ["course_name", "courseName", "lesson_name", "name_zh", "name"], "未知课程"),
      course_code: pick(g, ["course_code", "courseCode", "code"], ""),
      course_type: pick(g, ["course_type", "courseType", "course_property", "type"], "-"),
      credits: Number(pick(g, ["credits", "credit"], 0)) || 0,
      score: pick(g, ["score", "ga_grade", "grade", "final_grade", "score_text"], "-"),
      gp: pick(g, ["gp", "gpa", "grade_point"], "-"),
    }));

    // Populate semester filter
    const semSel = $("grade-semester-filter");
    semSel.innerHTML = '<option value="">全部学期</option>';
    const sems = [...new Set(state.grades.map((g) => g.semester))];
    sems.forEach((s) => semSel.add(new Option(s, s)));

    renderGrades();
  } catch (err) {
    showToast(`成绩加载失败：${err.message}`, "error");
  }
}

function renderGrades() {
  const sem = $("grade-semester-filter").value;
  const kw = $("grade-search").value.trim().toLowerCase();

  const filtered = state.grades.filter((g) => {
    if (sem && g.semester !== sem) return false;
    if (kw && !`${g.course_name} ${g.course_code}`.toLowerCase().includes(kw)) return false;
    return true;
  });

  // Stats
  let totalCredits = 0;
  let weightedGp = 0;
  let gpCredits = 0;
  filtered.forEach((g) => {
    totalCredits += g.credits;
    const gpNum = Number(g.gp);
    if (!Number.isNaN(gpNum) && g.credits > 0) {
      weightedGp += gpNum * g.credits;
      gpCredits += g.credits;
    }
  });

  $("grade-stat-count").textContent = String(filtered.length);
  $("grade-stat-credits").textContent = totalCredits.toFixed(1);
  $("grade-stat-gpa").textContent = gpCredits > 0 ? (weightedGp / gpCredits).toFixed(2) : "--";

  const tbody = $("grades-tbody");
  if (!filtered.length) {
    tbody.innerHTML = '<tr><td colspan="6" class="empty-cell">暂无匹配的成绩记录</td></tr>';
    return;
  }

  tbody.innerHTML = filtered
    .map(
      (g) => `
      <tr>
        <td>${escapeHtml(g.semester)}</td>
        <td><strong>${escapeHtml(g.course_name)}</strong> ${g.course_code ? `<span class="muted">(${escapeHtml(g.course_code)})</span>` : ""}</td>
        <td>${escapeHtml(g.course_type)}</td>
        <td>${g.credits || "-"}</td>
        <td><strong>${escapeHtml(g.score)}</strong></td>
        <td>${escapeHtml(g.gp)}</td>
      </tr>
    `
    )
    .join("");
}

// ------------------------------------------------------------------
// 5. Exams (期末考试)
// ------------------------------------------------------------------
async function loadExams() {
  const semesterId = $("exam-semester").value;
  if (!semesterId) return;

  try {
    const res = await apiFetch(`/api/jw/exams?semester_id=${encodeURIComponent(semesterId)}`);
    $("exams-raw").textContent = JSON.stringify(res, null, 2);

    const list = asArray(res.data);
    $("dash-exam-count").textContent = String(list.length);
    renderExams(list);
  } catch (err) {
    showToast(`考试安排加载失败：${err.message}`, "error");
  }
}

function daysUntil(dateStr) {
  if (!dateStr) return null;
  const target = new Date(dateStr.slice(0, 10) + "T00:00:00");
  if (Number.isNaN(target.getTime())) return null;
  const now = new Date();
  const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  return Math.round((target - today) / 86400000);
}

function renderExams(list) {
  const wrap = $("exams-list");
  const preview = $("dash-exams-preview");

  if (!list.length) {
    wrap.innerHTML = '<div class="empty-state">本学期暂无考试安排</div>';
    preview.innerHTML = '<div class="muted">本学期暂无待考安排</div>';
    return;
  }

  const normalized = list.map((e) => {
    const date = pick(e, ["exam_date", "examDate", "date"], "");
    return {
      name: pick(e, ["course_name", "courseName", "lesson_name", "name"], "未知科目"),
      date,
      time: pick(e, ["exam_time", "examTime", "time_text", "time"], ""),
      room: pick(e, ["room_name", "roomName", "place", "location"], "待定"),
      seat: pick(e, ["seat_no", "seatNo", "seat"], ""),
      type: pick(e, ["exam_type", "examType"], ""),
      days: daysUntil(date),
    };
  });

  const badgeHtml = (d) => {
    if (d === null) return "";
    if (d < 0) return '<span class="badge badge-neutral">已结束</span>';
    if (d === 0) return '<span class="badge badge-accent">今天考试</span>';
    return `<span class="badge badge-warn">还有 ${d} 天</span>`;
  };

  wrap.innerHTML = normalized
    .map(
      (e) => `
      <div class="exam-card">
        <div class="exam-top">
          <span class="exam-title">${escapeHtml(e.name)}</span>
          ${badgeHtml(e.days)}
        </div>
        <div class="exam-meta">
          <div>🕒 ${escapeHtml([e.date, e.time].filter(Boolean).join(" ") || "时间待定")}</div>
          <div>📍 ${escapeHtml(e.room)}${e.seat ? ` · 座位 ${escapeHtml(e.seat)}` : ""}</div>
          ${e.type ? `<div>📌 ${escapeHtml(e.type)}</div>` : ""}
        </div>
      </div>
    `
    )
    .join("");

  preview.innerHTML = normalized
    .slice(0, 3)
    .map(
      (e) => `
      <div class="preview-item">
        <div>
          <strong>${escapeHtml(e.name)}</strong>
          <div class="muted">${escapeHtml([e.date, e.time, e.room].filter(Boolean).join(" · "))}</div>
        </div>
        ${badgeHtml(e.days)}
      </div>
    `
    )
    .join("");
}

// ------------------------------------------------------------------
// 6. E-Card & Transfer (校园卡与电费)
// ------------------------------------------------------------------
async function loadEcard(forceRefresh = false) {
  try {
    const res = await apiFetch(`/api/ecard/summary?refresh=${forceRefresh ? "true" : "false"}`);
    const d = res.data || {};
    $("ecard-raw").textContent = JSON.stringify(res, null, 2);

    const cardBal = d.card_balance !== null && d.card_balance !== undefined ? `¥ ${d.card_balance}` : "--";
    const elecBal =
      d.electric_balance !== null && d.electric_balance !== undefined
        ? `${d.electric_balance} ${d.electric_unit || ""}`.trim()
        : "--";
    const loc = d.location || {};
    const dormText = [loc.area, loc.building, loc.level, loc.room].filter(Boolean).join(" · ") || "未绑定宿舍";
    const ownerText = [d.utilityUsername, d.utilityAccount].filter(Boolean).join(" · ") || "--";

    $("ecard-balance").textContent = cardBal;
    $("ecard-electric").textContent = elecBal;
    $("ecard-dorm").textContent = dormText;
    $("ecard-owner").textContent = ownerText;

    $("dash-card-balance").textContent = cardBal;
    $("dash-card-user").textContent = ownerText;
    $("dash-electric-balance").textContent = elecBal;
    $("dash-dorm-loc").textContent = dormText;

    const templates = Array.isArray(d.templateList) ? d.templateList : [];
    const wrap = $("ecard-templates");
    if (!templates.length) {
      wrap.innerHTML = '<div class="empty-state">暂无详情字段</div>';
    } else {
      wrap.innerHTML = templates
        .map(
          (item) => `
          <div class="kv-row">
            <span class="muted">${escapeHtml(pick(item, ["name", "title", "label"], "项目"))}</span>
            <strong>${escapeHtml(pick(item, ["value"], "-"))} ${escapeHtml(pick(item, ["unit"], ""))}</strong>
          </div>
        `
        )
        .join("");
    }
  } catch (err) {
    showToast(`校园卡信息加载失败：${err.message}`, "error");
  }
}

async function executeTransfer() {
  if (!state.pendingTransfer) return;
  const payload = state.pendingTransfer;
  state.pendingTransfer = null;
  $("confirm-modal").classList.add("hidden");

  try {
    const res = await apiFetch("/api/ecard/transfer", {
      method: "POST",
      body: JSON.stringify(payload),
    });
    showToast(res.message || "转账成功", "success");
    $("transfer-result").textContent = res.message || "转账成功";
    $("tx-password").value = "";
    loadEcard(false);
  } catch (err) {
    showToast(`转账失败：${err.message}`, "error");
    $("transfer-result").textContent = `转账失败：${err.message}`;
  }
}

// ------------------------------------------------------------------
// Event Wiring
// ------------------------------------------------------------------
function initEvents() {
  // Login mode toggle
  document.querySelectorAll(".mode-tab").forEach((tab) => {
    tab.addEventListener("click", () => {
      state.loginMode = tab.dataset.loginMode;
      document.querySelectorAll(".mode-tab").forEach((t) => t.classList.toggle("active", t === tab));
      $("password-field").classList.toggle("hidden", state.loginMode !== "password");
      $("token-field").classList.toggle("hidden", state.loginMode !== "token");
    });
  });

  // Login submit
  $("login-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    const btn = $("login-submit-btn");
    btn.disabled = true;
    btn.textContent = "正在登录...";
    try {
      const payload = {
        account: $("login-account").value.trim(),
        password: state.loginMode === "password" ? $("login-password").value : "",
        user_token: state.loginMode === "token" ? $("login-token").value.trim() : "",
      };
      const user = await apiFetch("/api/auth/login", {
        method: "POST",
        body: JSON.stringify(payload),
      });
      showToast("登录成功", "success");
      if (user.warnings && user.warnings.length) {
        user.warnings.forEach((w) => showToast(w, "error"));
      }
      showAppView(user);
    } catch (err) {
      showToast(err.message, "error");
    } finally {
      btn.disabled = false;
      btn.textContent = "登录进入校园站";
    }
  });

  // Demo login
  $("demo-login-btn").addEventListener("click", async () => {
    try {
      const user = await apiFetch("/api/auth/demo", { method: "POST" });
      showToast("已进入演示模式（使用模拟数据）", "success");
      showAppView(user);
    } catch (err) {
      showToast(err.message, "error");
    }
  });

  // Logout
  $("logout-btn").addEventListener("click", async () => {
    await apiFetch("/api/auth/logout", { method: "POST" }).catch(() => {});
    showToast("已退出登录");
    showLoginView();
  });

  // Navigation
  document.querySelectorAll(".nav-item, .mnav-item").forEach((btn) => {
    btn.addEventListener("click", () => switchTab(btn.dataset.tab));
  });
  document.querySelectorAll("[data-jump]").forEach((btn) => {
    btn.addEventListener("click", () => switchTab(btn.dataset.jump));
  });

  // Dashboard refresh
  $("dash-refresh-btn").addEventListener("click", () => bootstrapData());

  // Classrooms
  $("cr-campus").addEventListener("change", populateBuildings);
  $("reload-campuses-btn").addEventListener("click", loadCampuses);
  $("cr-search-btn").addEventListener("click", searchClassrooms);

  // Courses
  $("week-prev-btn").addEventListener("click", () => {
    state.weekOffset -= 1;
    loadCourses();
  });
  $("week-today-btn").addEventListener("click", () => {
    state.weekOffset = 0;
    loadCourses();
  });
  $("week-next-btn").addEventListener("click", () => {
    state.weekOffset += 1;
    loadCourses();
  });
  $("course-load-btn").addEventListener("click", loadCourses);
  $("course-semester").addEventListener("change", loadCourses);

  // Grades
  $("grade-refresh-btn").addEventListener("click", loadGrades);
  $("grade-semester-filter").addEventListener("change", renderGrades);
  $("grade-search").addEventListener("input", renderGrades);

  // Exams
  $("exam-load-btn").addEventListener("click", loadExams);
  $("exam-semester").addEventListener("change", loadExams);

  // E-Card
  $("ecard-refresh-btn").addEventListener("click", () => loadEcard(false));
  $("ecard-force-refresh-btn").addEventListener("click", () => loadEcard(true));

  // Transfer confirmation modal
  $("transfer-form").addEventListener("submit", (e) => {
    e.preventDefault();
    const from_id = $("tx-from").value.trim();
    const to_id = $("tx-to").value.trim();
    const amount = Number($("tx-amount").value);
    const card_password = $("tx-password").value;

    if (!to_id || !amount || amount <= 0 || !card_password) {
      showToast("请完整填写转账信息", "error");
      return;
    }

    state.pendingTransfer = { from_id, to_id, amount, card_password };
    $("confirm-modal-text").textContent = `确认从学号 ${from_id} 向学号 ${to_id} 转账 ¥${amount.toFixed(2)} 元？此操作不可撤销。`;
    $("confirm-modal").classList.remove("hidden");
  });

  $("confirm-cancel-btn").addEventListener("click", () => {
    state.pendingTransfer = null;
    $("confirm-modal").classList.add("hidden");
  });
  $("confirm-ok-btn").addEventListener("click", executeTransfer);
}

async function init() {
  initTheme();
  initPeriodPills();
  initEvents();

  try {
    const me = await apiFetch("/api/auth/me");
    if (me && me.authenticated) {
      showAppView(me);
      return;
    }
  } catch {
    // ignore and stay on login view
  }
  showLoginView();
}

init();
