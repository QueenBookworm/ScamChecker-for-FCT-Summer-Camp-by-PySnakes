/* =========================================================
   app.js
   Global state and app startup. Load this file last.
   ========================================================= */

// ===== Global State Section =====
const HISTORY_KEY = "scamcheck_history_simple_v1";

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
  setupSamples();
  setupMainButtons();
  setupChat();
  setupPasteImage();
  setupTraining();
  setupVoice();

  drawHistory();
  loadExtraPages();
}


// ===== Start After Functions Exist Section =====
startApp();
