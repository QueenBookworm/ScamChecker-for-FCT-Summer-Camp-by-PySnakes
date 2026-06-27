/* =========================================================
   navigation.js
   Page switching, input tabs, loading state, and errors.
   ========================================================= */

// ===== Page Switch Section =====
function showPage(name, updatePath = true) {
  document.querySelectorAll(".page").forEach(page => {
    page.classList.toggle("active", page.id === name);
  });

  document.querySelectorAll(".nav").forEach(button => {
    button.classList.toggle("active", button.dataset.page === name);
  });

  if (updatePath) {
    window.history.pushState({ page: name }, "", pagePath(name));
  }

  resetPageScroll();
}


function resetPageScroll() {
  const main = document.querySelector(".main");

  if (window.matchMedia("(min-width: 980px)").matches && main) {
    main.scrollTop = 0;
    return;
  }

  scrollTo(0, 0);
}


// ===== URL Path Section =====
function pagePath(name) {
  return name === "home" ? "/" : `/${name}`;
}


function pageFromPath(pathname = location.pathname) {
  const firstPart = pathname.split("/").filter(Boolean)[0] || "home";
  const allowed = ["home", "analysis", "history", "faq", "library", "training"];

  return allowed.includes(firstPart) ? firstPart : "home";
}


// ===== Input Mode Section =====
function setMode(nextMode) {
  mode = nextMode;

  document.querySelectorAll(".tab").forEach(button => {
    button.classList.toggle("active", button.dataset.mode === mode);
  });

  document.querySelectorAll(".panel").forEach(panel => {
    panel.classList.toggle("active", panel.dataset.panel === mode);
  });

  $("error").classList.remove("show");
}


// ===== Loading State Section =====
function setBusy(on) {
  $("analyzeBtn").disabled = on;
  $("analyzeBtn").textContent = on ? "Đang phân tích..." : "Phân tích với AI";

  if ($("loading")) {
    $("loading").classList.toggle("show", on);
  }
}


// ===== Error Message Section =====
function showError(text) {
  $("error").textContent = text;
  $("error").classList.add("show");
}


// ===== Navigation Setup Section =====
function setupNavigation() {
  setupDesktopScrollShell();

  document.querySelectorAll(".nav").forEach(button => {
    button.onclick = () => showPage(button.dataset.page);
  });

  document.querySelectorAll(".side-all").forEach(button => {
    button.onclick = () => showPage(button.dataset.page);
  });

  showPage(pageFromPath(), false);

  if (typeof loadSharedAnalysisFromPath === "function") {
    loadSharedAnalysisFromPath();
  }

  window.onpopstate = () => {
    showPage(pageFromPath(), false);
    if (typeof loadSharedAnalysisFromPath === "function") {
      loadSharedAnalysisFromPath();
    }
  };
}


function setupDesktopScrollShell() {
  const sidebar = document.querySelector(".sidebar");
  const main = document.querySelector(".main");

  if (!sidebar || !main) return;

  sidebar.addEventListener("wheel", event => {
    if (!window.matchMedia("(min-width: 980px)").matches) return;

    event.preventDefault();
    main.scrollTop += event.deltaY;
  }, { passive: false });
}


// ===== Tab Setup Section =====
function setupTabs() {
  document.querySelectorAll(".tab").forEach(button => {
    button.onclick = () => setMode(button.dataset.mode);
  });
}
