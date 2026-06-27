/* =========================================================
   chat.js
   AI chat drawer only.
   ========================================================= */

const CHAT_TOGGLE_POSITION_KEY = "scamcheck_chat_toggle_position_v1";
const CHAT_HISTORY_KEY = "scamcheck_chat_messages_v1";


// ===== Chat Setup Section =====
function setupChat() {
  setupChatToggleDrag();
  loadChatHistory();
  renderChatHistory();

  $("chatClose").onclick = () => openChat(false);

  $("chatFile").onchange = event => {
    setChatFile(event.target.files[0]);
  };

  $("chatSend").onclick = sendChat;

  $("chatQuestion").addEventListener("input", updateChatCharacterCount);

  $("chatQuestion").onkeydown = event => {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      sendChat();
    }
  };

  updateChatCharacterCount();
}


// ===== Movable AI Button Section =====
function setupChatToggleDrag() {
  const button = $("chatToggle");
  let startX = 0;
  let startY = 0;
  let startLeft = 0;
  let startTop = 0;
  let moved = false;

  resetChatTogglePosition();

  window.addEventListener("resize", keepChatToggleOnScreen);

  button.addEventListener("pointerdown", event => {
    if ($("chatDrawer").classList.contains("open")) return;

    const rect = button.getBoundingClientRect();

    startX = event.clientX;
    startY = event.clientY;
    startLeft = rect.left;
    startTop = rect.top;
    moved = false;

    button.classList.add("dragging");
    button.setPointerCapture(event.pointerId);
  });

  button.addEventListener("pointermove", event => {
    if (!button.classList.contains("dragging")) return;

    const dx = event.clientX - startX;
    const dy = event.clientY - startY;

    if (Math.abs(dx) + Math.abs(dy) > 5) {
      moved = true;
    }

    if (moved) {
      placeChatToggle(startLeft + dx, startTop + dy);
    }
  });

  button.addEventListener("pointerup", event => {
    if (!button.classList.contains("dragging")) return;

    button.classList.remove("dragging");
    button.releasePointerCapture(event.pointerId);

    if (moved) {
      saveChatTogglePosition();
      return;
    }

    openChat(!$("chatDrawer").classList.contains("open"));
  });

  button.addEventListener("pointercancel", () => {
    button.classList.remove("dragging");
    keepChatToggleOnScreen();
  });
}


function placeChatToggle(left, top) {
  const button = $("chatToggle");
  const rect = button.getBoundingClientRect();
  const margin = 12;
  const maxLeft = window.innerWidth - rect.width - margin;
  const maxTop = window.innerHeight - rect.height - margin;
  const nextLeft = Math.max(margin, Math.min(maxLeft, left));
  const nextTop = Math.max(margin, Math.min(maxTop, top));

  button.style.left = `${nextLeft}px`;
  button.style.top = `${nextTop}px`;
  button.style.right = "auto";
  button.style.bottom = "auto";
}


function saveChatTogglePosition() {
  const rect = $("chatToggle").getBoundingClientRect();
  localStorage.setItem(
    CHAT_TOGGLE_POSITION_KEY,
    JSON.stringify({ left: rect.left, top: rect.top })
  );
}


function restoreChatTogglePosition() {
  try {
    const saved = JSON.parse(localStorage.getItem(CHAT_TOGGLE_POSITION_KEY) || "null");

    if (saved && Number.isFinite(saved.left) && Number.isFinite(saved.top)) {
      placeChatToggle(saved.left, saved.top);
    }
  } catch {
    localStorage.removeItem(CHAT_TOGGLE_POSITION_KEY);
  }
}


function resetChatTogglePosition() {
  const button = $("chatToggle");

  localStorage.removeItem(CHAT_TOGGLE_POSITION_KEY);
  button.style.left = "";
  button.style.top = "";
  button.style.right = "";
  button.style.bottom = "";
}


function keepChatToggleOnScreen() {
  const rect = $("chatToggle").getBoundingClientRect();

  if ($("chatToggle").style.left && $("chatToggle").style.top) {
    placeChatToggle(rect.left, rect.top);
    saveChatTogglePosition();
  }
}


// ===== Chat Drawer Toggle Section =====
function openChat(on) {
  $("chatDrawer").classList.toggle("open", on);
  document.querySelector(".app").classList.toggle("chat-open", on);
  $("chatToggle").textContent = on ? "AI đang mở" : "Hỏi AI";
}


// ===== Chat File Section =====
async function setChatFile(file) {
  chatImage = null;
  chatText = "";

  $("chatFileName").textContent = file ? `Đã chọn: ${file.name}` : "";

  document.querySelector(".chat-file")?.classList.toggle("has-file", Boolean(file));

  if (!file) {
    updateChatCharacterCount();
    return;
  }

  if (file.type.startsWith("image/")) {
    chatImage = {
      name: file.name,
      mimeType: file.type,
      dataUrl: await dataUrl(file)
    };
  } else {
    chatText = (await file.text()).slice(0, 3000);
  }

  updateChatCharacterCount();
}


// ===== Chat Send Section =====
async function sendChat() {
  const question = $("chatQuestion").value.trim();
  const characters = countCharacters([question, chatText].filter(Boolean).join(" "));

  if (!question && !chatImage && !chatText) return;

  if (characters > AI_CHARACTER_LIMIT) {
    addChatMessage(
      "ai",
      `Nội dung có ${characters.toLocaleString("vi-VN")} ký tự, vượt quá giới hạn ${AI_CHARACTER_LIMIT.toLocaleString("vi-VN")} ký tự. Bác rút gọn câu hỏi hoặc tệp rồi gửi lại nhé.`
    );
    return;
  }

  addChatMessage("user", question || "Đã gửi thêm tệp/ảnh để AI xem.");

  const fallbackAnswer = "AI chưa trả lời được rõ ràng. Bác mô tả thêm điều bác đang cần, ScamCheck sẽ bám theo nội dung đó để hướng dẫn tiếp.";

  $("chatSend").disabled = true;
  $("chatSend").textContent = "...";

  setChatTimer(true);

  try {
    const data = await post("/api/chat", {
      question,
      image: chatImage,
      fileText: chatText,
      result: currentResult || history[0] || {},
      history,
      messages: chatMessages
    });

    const finalAnswer = data.answer || fallbackAnswer;

    addChatMessage("ai", finalAnswer, data.next_steps);

    selectedActionLabel = "";

    $("chatQuestion").value = "";
    $("chatFile").value = "";

    await setChatFile();
    updateChatCharacterCount();
  } catch (error) {
    addChatMessage("ai", error.message);
  } finally {
    setChatTimer(false);

    $("chatSend").disabled = false;
    $("chatSend").textContent = "Gửi";
  }
}


function updateChatCharacterCount() {
  const question = $("chatQuestion")?.value || "";
  const characters = countCharacters([question, chatText].filter(Boolean).join(" "));
  const meter = $("chatCharacterCount");

  if (!meter) return;

  meter.textContent = formatCharacterCount(characters);
  meter.classList.toggle("danger", characters > AI_CHARACTER_LIMIT);
}


// ===== Chat Message Render Section =====
function addChatMessage(role, text, steps = []) {
  const cleanText = cleanDisplayText(text);
  const cleanSteps = Array.isArray(steps) ? steps.map(cleanDisplayText).filter(Boolean) : [];

  chatMessages.push({ role, text: cleanText, steps: cleanSteps });
  chatMessages = chatMessages.slice(-30);
  saveChatHistory();

  appendChatMessage({ role, text: cleanText, steps: cleanSteps });
}


// ===== Chat History Persistence Section =====
function loadChatHistory() {
  try {
    chatMessages = JSON.parse(localStorage.getItem(CHAT_HISTORY_KEY) || "[]")
      .filter(message => message && message.role && message.text)
      .slice(-30);
  } catch {
    chatMessages = [];
  }
}


function saveChatHistory() {
  localStorage.setItem(CHAT_HISTORY_KEY, JSON.stringify(chatMessages));
}


function renderChatHistory() {
  if (!chatMessages.length) return;

  $("chatLog").innerHTML = "";
  chatMessages.forEach(appendChatMessage);
}


function appendChatMessage(message) {
  const steps = Array.isArray(message.steps) ? message.steps.map(cleanDisplayText).filter(Boolean) : [];
  const stepList = steps.length
    ? `<ul>${steps.map(step => `<li>${formatChatRichText(step)}</li>`).join("")}</ul>`
    : "";

  $("chatLog").insertAdjacentHTML(
    "beforeend",
    `<div class="chat-msg ${message.role}">${formatChatRichText(message.text)}${stepList}</div>`
  );

  $("chatLog").scrollTop = $("chatLog").scrollHeight;
}


function formatChatRichText(text) {
  const raw = cleanDisplayText(text);
  const tokenRegex = /\bhttps?:\/\/[^\s<>"')]+|\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b|\b(?:1900\d{6}|1800\d{6}|113|156|5656)\b/gi;
  let html = "";
  let cursor = 0;
  let match;

  while ((match = tokenRegex.exec(raw)) !== null) {
    html += highlightChatPhrases(raw.slice(cursor, match.index));
    html += formatChatToken(match[0]);
    cursor = match.index + match[0].length;
  }

  html += highlightChatPhrases(raw.slice(cursor));
  return html;
}


function formatChatToken(token) {
  if (/^https?:\/\//i.test(token)) {
    const cleanUrl = token.replace(/[.,;:!?]+$/, "");
    const trailing = token.slice(cleanUrl.length);
    return `<a class="chat-link bank-link" href="${safeAttribute(cleanUrl)}" target="_blank" rel="noopener noreferrer"><strong><em>${safe(cleanUrl)}</em></strong></a>${safe(trailing)}`;
  }

  if (/^[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}$/i.test(token)) {
    return `<a class="chat-link report-link" href="mailto:${safeAttribute(token)}"><strong>${safe(token)}</strong></a>`;
  }

  return `<a class="chat-phone" href="tel:${safeAttribute(token)}"><strong>${safe(token)}</strong></a>`;
}


function highlightChatPhrases(text) {
  return safe(text)
    .replace(
      /\b(Vietcombank|VPBank|BIDV|VietinBank|Agribank|Techcombank|MB Bank|MBBank|ACB|Sacombank|TPBank)\b/g,
      `<mark class="chat-bank-name"><strong>$1</strong></mark>`
    )
    .replace(
      /(kênh chính thức|website chính thức|ứng dụng chính thức|Hotline|Báo cáo\/hỗ trợ|Báo cáo|hỗ trợ|email)/gi,
      `<mark class="chat-support-phrase"><strong><em>$1</em></strong></mark>`
    );
}


function safeAttribute(value) {
  return safe(value).replace(/"/g, "&quot;");
}


// ===== Chat Timer Section =====
function setChatTimer(on) {
  clearInterval(chatClock);

  if (on) {
    chatSeconds = 0;
    $("chatTimer").textContent = "AI đang suy nghĩ · 0 giây";

    chatClock = setInterval(() => {
      chatSeconds++;
      $("chatTimer").textContent = `AI đang suy nghĩ · ${chatSeconds} giây`;
    }, 1000);
  } else {
    $("chatTimer").textContent = `Đã trả lời trong ${chatSeconds} giây`;
  }
}
