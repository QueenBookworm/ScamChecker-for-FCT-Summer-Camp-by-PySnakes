/* =========================================================
   app.js
   Global state and app startup. Load this file last.
   ========================================================= */

// ===== Global State Section =====
const HISTORY_KEY = "scamcheck_history_simple_v1";
const AI_CHARACTER_LIMIT = 7000;

let mode = "image";
let selectedImage = null;
let currentResult = null;
let selectedActionLabel = "";

let chatImage = null;
let chatText = "";
let chatMessages = [];
let chatClock = null;
let chatSeconds = 0;

let history = loadHistory();

let libraryData = [];
let libraryGroup = "Tất cả";

let trainingData = [];
let trainingIndex = 0;
let trainingScore = 0;
let trainingAnswered = false;
let trainingTimer = null;


// ===== App Startup Section =====
function startApp() {
  setupNavigation();
  setupTabs();
  setupSideHistoryToggle();
  setupExclusiveDetails(".faq-grid", ".faq-item");
  setupSamples();
  setupMainButtons();
  setupCharacterCounters();
  setupChat();
  setupPasteImage();
  setupTraining();
  setupVoice();

  drawHistory();
  loadExtraPages();
}


// ===== Accordion Details Section =====
function setupExclusiveDetails(containerSelector, itemSelector) {
  const container = document.querySelector(containerSelector);

  if (!container) return;

  container.addEventListener("toggle", event => {
    const opened = event.target;

    if (!opened.matches(itemSelector) || !opened.open) return;

    container.querySelectorAll(itemSelector).forEach(item => {
      if (item !== opened) {
        item.open = false;
      }
    });
  }, true);
}


// ===== Start After Functions Exist Section =====
startApp();
