/* =========================================================
   history.js
   Local browser history, pagination, and shared confirm modal.
   ========================================================= */

const SIDE_HISTORY_COLLAPSED_KEY = "scamcheck_side_history_collapsed_v1";


// ===== Save History Section =====
function saveHistory() {
  localStorage.setItem(HISTORY_KEY, JSON.stringify(history));
}


// ===== Permanent History Section =====
async function loadPersistentHistory() {
  try {
    const data = await get("/api/history");
    const remoteHistory = Array.isArray(data.history)
      ? data.history.map(item => normalizeResult(item))
      : [];

    history = mergeHistory(remoteHistory, history);
    saveHistory();
    drawHistory();
  } catch {
    // Local history still works if the backend history file cannot be read.
  }
}


function mergeHistory(...groups) {
  const byId = new Map();

  groups.flat().forEach(item => {
    if (!item) return;
    const normalized = normalizeResult(item);
    const key = normalized.share_id || normalized.id;

    if (key && !byId.has(key)) {
      byId.set(key, normalized);
    }
  });

  return [...byId.values()].sort((a, b) => {
    return new Date(b.time || 0) - new Date(a.time || 0);
  });
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
      .map((item, index) => normalizeResult({
        ...item,
        id: item.id || "saved-" + index
      }));
  } catch {
    return [];
  }
}


// ===== Confirm Modal Section =====
function confirmDialog({
  title = "Xác nhận",
  message = "Bác có chắc muốn tiếp tục không?",
  confirmText = "Đồng ý",
  danger = false
} = {}) {
  // Opens the shared confirmation modal and resolves true/false for delete/submit actions.
  ensureConfirmModal();

  $("confirmTitle").textContent = title;
  $("confirmMessage").textContent = message;
  $("confirmOk").textContent = confirmText;
  $("confirmOk").classList.toggle("danger", danger);
  $("confirmModal").hidden = false;

  return new Promise(resolve => {
    const close = value => {
      $("confirmModal").hidden = true;
      $("confirmCancel").onclick = null;
      $("confirmOk").onclick = null;
      resolve(value);
    };

    $("confirmCancel").onclick = () => close(false);
    $("confirmOk").onclick = () => close(true);
  });
}


function ensureConfirmModal() {
  // Creates the modal markup once so every destructive action can reuse it.
  if ($("confirmModal")) return;

  document.body.insertAdjacentHTML("beforeend", `
    <div id="confirmModal" class="confirm-backdrop" hidden>
      <section class="confirm-card" role="dialog" aria-modal="true" aria-labelledby="confirmTitle">
        <h2 id="confirmTitle">Xác nhận</h2>
        <p id="confirmMessage"></p>
        <div class="confirm-actions">
          <button id="confirmCancel" class="confirm-cancel" type="button">Hủy</button>
          <button id="confirmOk" class="confirm-ok" type="button">Đồng ý</button>
        </div>
      </section>
    </div>
  `);

  $("confirmModal").addEventListener("click", event => {
    if (event.target === $("confirmModal")) {
      $("confirmCancel").click();
    }
  });
}


// ===== Clear History Section =====
async function clearHistory() {
  showPermanentHistoryNotice();
}


async function deleteHistoryItem(id) {
  showPermanentHistoryNotice();
}


function showPermanentHistoryNotice() {
  if (typeof showToast === "function" && $("toolToast")) {
    showToast("Lịch sử đang được lưu vĩnh viễn nên không xóa trong ứng dụng.");
  }
}


// ===== Main History Render Section =====
function drawHistory() {
  const clearButton = $("clearHistory");
  if (clearButton) {
    clearButton.hidden = true;
  }

  const hint = document.querySelector("#history .hint");
  if (hint) {
    hint.textContent = "Lịch sử được lưu vĩnh viễn trên máy chủ của app. Bấm vào một kết quả để mở lại hoặc chia sẻ link riêng.";
  }

  const pages = totalHistoryPages();
  historyPage = Math.max(1, Math.min(historyPage, pages));

  const start = (historyPage - 1) * HISTORY_PAGE_SIZE;
  const pageItems = history.slice(start, start + HISTORY_PAGE_SIZE);

  $("historyList").innerHTML = history.length
    ? pageItems.map(item => historyItemHtml(item)).join("")
    : "<div class='history-item'>Chưa có kết quả kiểm tra nào.</div>";

  drawHistoryPagination(pages);
  drawSideHistory();
  bindHistoryButtons();
}


function historyItemHtml(item) {
  // Builds one paginated history row with an open target and compact delete action.
  return `
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
    </article>
  `;
}


function bindHistoryButtons() {
  // Connects history row open/delete actions and numbered pagination controls.
  document.querySelectorAll("[data-history-open]").forEach(button => {
    button.onclick = () => {
      const item = history.find(savedItem => savedItem.id === button.dataset.historyOpen);

      if (item) {
        showResult(item);
      }
    };
  });

  document.querySelectorAll("[data-history-page]").forEach(button => {
    button.onclick = () => {
      historyPage = Number(button.dataset.historyPage);
      drawHistory();
    };
  });
}


function totalHistoryPages() {
  // Calculates the visible page count from the unlimited local history list.
  return Math.max(1, Math.ceil(history.length / HISTORY_PAGE_SIZE));
}


function drawHistoryPagination(pages = totalHistoryPages()) {
  // Renders Previous, numbered page buttons, and Next for the history screen.
  const target = $("historyPagination");

  if (!target) return;

  if (!history.length || pages <= 1) {
    target.innerHTML = "";
    return;
  }

  const pageButtons = Array.from({ length: pages }, (_, index) => {
    const page = index + 1;
    return `
      <button
        class="page-btn ${page === historyPage ? "active" : ""}"
        data-history-page="${page}"
        type="button"
      >${page}</button>
    `;
  }).join("");

  target.innerHTML = `
    <button class="page-btn" data-history-page="${Math.max(1, historyPage - 1)}" ${historyPage === 1 ? "disabled" : ""} type="button">‹ Trước</button>
    ${pageButtons}
    <button class="page-btn" data-history-page="${Math.min(pages, historyPage + 1)}" ${historyPage === pages ? "disabled" : ""} type="button">Sau ›</button>
  `;
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


function trashIcon() {
  // Returns the shared SVG trash icon used by delete-all and delete-one buttons.
  return `
    <svg aria-hidden="true" viewBox="0 0 24 24">
      <path d="M3 6h18"></path>
      <path d="M8 6V4h8v2"></path>
      <path d="M6 6l1 15h10l1-15"></path>
      <path d="M10 10v7"></path>
      <path d="M14 10v7"></path>
    </svg>
  `;
}

