/* =========================================================
   history.js
   Local browser history using localStorage.
   ========================================================= */

const SIDE_HISTORY_COLLAPSED_KEY = "scamcheck_side_history_collapsed_v1";


// ===== Save History Section =====
function saveHistory() {
  history = history.slice(0, 10);
  localStorage.setItem(HISTORY_KEY, JSON.stringify(history));
}


// ===== Sidebar History Collapse Section =====
function setupSideHistoryToggle() {
  const panel = document.querySelector(".side-history");
  const button = $("sideHistoryToggle");

  if (!panel || !button) return;

  setSideHistoryCollapsed(
    localStorage.getItem(SIDE_HISTORY_COLLAPSED_KEY) === "1"
  );

  button.onclick = () => {
    setSideHistoryCollapsed(!panel.classList.contains("collapsed"));
  };
}


function setSideHistoryCollapsed(collapsed) {
  const panel = document.querySelector(".side-history");
  const button = $("sideHistoryToggle");

  if (!panel || !button) return;

  panel.classList.toggle("collapsed", collapsed);
  button.setAttribute("aria-expanded", String(!collapsed));
  localStorage.setItem(SIDE_HISTORY_COLLAPSED_KEY, collapsed ? "1" : "0");
}


// ===== Load History Section =====
function loadHistory() {
  try {
    return JSON.parse(localStorage.getItem(HISTORY_KEY) || "[]")
      .filter(item => item.source === "gemini")
      .slice(0, 10)
      .map((item, index) => normalizeResult({
        ...item,
        id: item.id || "saved-" + index
      }));
  } catch {
    return [];
  }
}


// ===== Clear History Section =====
function clearHistory() {
  if (!history.length) return;

  const confirmed = window.confirm(
    "Bác có chắc muốn xóa hết lịch sử kiểm tra trên thiết bị này không?"
  );

  if (!confirmed) return;

  history = [];
  saveHistory();
  drawHistory();
}

// ===== Delete History Item Section =====
function deleteHistoryItem(id) {
  const item = history.find(savedItem => savedItem.id === id);

  if (!item) return;

  const confirmed = window.confirm("Xóa kết quả này khỏi lịch sử?");

  if (!confirmed) return;

  history = history.filter(savedItem => savedItem.id !== id);
  saveHistory();
  drawHistory();
}


// ===== Main History Render Section =====
function drawHistory() {
  $("historyList").innerHTML = history.length
    ? history.map(item => `
      <article class="history-item">
        <button class="history-open" data-history-open="${safe(item.id)}" type="button">
          <div class="history-top">
            <span class="history-status ${safe(item.risk)}">
              ${safe(item.verdict_label)}
            </span>

            <span class="history-score">
              ${item.danger_score_percent}% rủi ro
            </span>
          </div>

          <strong class="history-title">${safe(item.summary)}</strong>
          <p>${safe(item.inputText || item.explanation)}</p>
        </button>
        <button class="history-delete" data-history-delete="${safe(item.id)}" type="button" aria-label="Xóa kết quả này">🗑</button>
      </article>
    `).join("")
    : "<div class='history-item'>Chưa có kết quả kiểm tra nào.</div>";

  drawSideHistory();

  document.querySelectorAll("[data-history-open]").forEach(button => {
    button.onclick = () => {
      const item = history.find(savedItem => savedItem.id === button.dataset.historyOpen);

      if (item) {
        showResult(item);
      }
    };
  });

  document.querySelectorAll("[data-history-delete]").forEach(button => {
    button.onclick = () => deleteHistoryItem(button.dataset.historyDelete);
  });
}


// ===== Sidebar History Render Section =====
function drawSideHistory() {
  if (!$("sideHistoryList")) return;

  $("sideHistoryList").innerHTML = history.length
    ? history.slice(0, 5).map(item => `
      <button class="side-recent-item" data-history-open="${safe(item.id)}" type="button">
        <span class="side-dot"></span>
        <span class="side-title">${safe(item.summary || item.inputText)}</span>
        <span class="side-badge ${safe(item.risk)}">
          ${safe(item.verdict_label)}
        </span>
      </button>
    `).join("")
    : "<div class='side-empty'>Chưa có lượt kiểm tra.</div>";
}
