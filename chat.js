/* =========================================================
   chat.js
   AI chat drawer only.
   ========================================================= */

// ===== Chat Setup Section =====
function setupChat() {
  $("chatToggle").onclick = () => {
    openChat(!$("chatDrawer").classList.contains("open"));
  };

  $("chatClose").onclick = () => openChat(false);

  $("chatFile").onchange = event => {
    setChatFile(event.target.files[0]);
  };

  $("chatSend").onclick = sendChat;

  $("chatQuestion").onkeydown = event => {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      sendChat();
    }
  };
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

  if (!file) return;

  if (file.type.startsWith("image/")) {
    chatImage = {
      name: file.name,
      mimeType: file.type,
      dataUrl: await dataUrl(file)
    };
  } else {
    chatText = (await file.text()).slice(0, 3000);
  }
}


// ===== Chat Send Section =====
async function sendChat() {
  const question = $("chatQuestion").value.trim();

  if (!question && !chatImage && !chatText) return;

  const fallbackAnswer = selectedActionLabel
    ? `Bước: ${selectedActionLabel}`
    : "AI chưa trả lời được, nhưng bác có thể xem lại bước đã chọn.";

  const finalAnswer = data.answer
    ? `${fallbackAnswer}\n\n${data.answer}`
    : fallbackAnswer;

  addChatMessage("ai", finalAnswer, data.next_steps);

  selectedActionLabel = "";
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

    addChatMessage("ai", data.answer, data.next_steps);

    $("chatQuestion").value = "";
    $("chatFile").value = "";

    await setChatFile();
  } catch (error) {
    addChatMessage("ai", error.message);
  } finally {
    setChatTimer(false);

    $("chatSend").disabled = false;
    $("chatSend").textContent = "Gửi";
  }
}


// ===== Chat Message Render Section =====
function addChatMessage(role, text, steps = []) {
  chatMessages.push({ role, text });
  chatMessages = chatMessages.slice(-8);

  const stepList = steps.length
    ? `<ul>${steps.map(step => `<li>${safe(step)}</li>`).join("")}</ul>`
    : "";

  $("chatLog").insertAdjacentHTML(
    "beforeend",
    `<div class="chat-msg ${role}">${safe(text)}${stepList}</div>`
  );

  $("chatLog").scrollTop = $("chatLog").scrollHeight;
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
