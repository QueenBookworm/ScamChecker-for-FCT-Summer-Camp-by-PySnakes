/* =========================================================
   analyze.js
   Main analyze flow: input, /api/analyze, and result display.
   ========================================================= */

// ===== Sample Button Setup Section =====
function setupSamples() {
  document.querySelectorAll(".sample").forEach(button => {
    button.onclick = () => {
      setMode("text");
      $("message").value = button.dataset.sample || button.textContent;
      updateInputCharacterCounts();
    };
  });
}


// ===== Main Button Setup Section =====
function setupMainButtons() {
  $("backHome").onclick = () => showPage("home");
  $("clearHistory").onclick = clearHistory;

  $("imageInput").onchange = event => {
    setImage(event.target.files[0]);
  };

  $("analyzeBtn").onclick = analyze;
}


// ===== Image Selection Section =====
async function setImage(file) {
  selectedImage = file && {
    name: file.name,
    mimeType: file.type,
    dataUrl: await dataUrl(file)
  };

  $("uploadBox").classList.toggle("has-file", !!file);
  $("uploadTitle").textContent = file ? "Đã chọn ảnh" : "Bấm vào đây để tải ảnh";

  $("uploadHint").textContent = file
    ? file.name + " · bấm lại để đổi ảnh"
    : "Ảnh chụp tin nhắn, email, link hoặc màn hình đáng ngờ";
}


// ===== Paste Image Section =====
function setupPasteImage() {
  document.addEventListener("paste", event => {
    const imageItem = [...event.clipboardData.items].find(item => {
      return item.type.startsWith("image/");
    });

    if (imageItem) {
      setMode("image");
      setImage(imageItem.getAsFile());
    }
  });
}


// ===== Input Builder Section =====
function getInputBody() {
  const fields = {
    link: "linkInput",
    text: "message",
    voice: "voiceText"
  };

  if (mode === "image") {
    return {
      message: "",
      image: selectedImage
    };
  }

  return {
    message: $(fields[mode]).value.trim(),
    image: null
  };
}


// ===== Character Count Section =====
function countCharacters(text) {
  return String(text || "").length;
}


function formatCharacterCount(count) {
  return `${count.toLocaleString("vi-VN")} / ${AI_CHARACTER_LIMIT.toLocaleString("vi-VN")} ký tự`;
}


function updateCharacterMeter(meterId, count) {
  const meter = $(meterId);

  if (!meter) return;

  meter.textContent = formatCharacterCount(count);
  meter.classList.toggle("danger", count > AI_CHARACTER_LIMIT);
}


function setupCharacterCounters() {
  ["linkInput", "message", "voiceText"].forEach(id => {
    const field = $(id);

    if (field) {
      field.addEventListener("input", updateInputCharacterCounts);
    }
  });

  updateInputCharacterCounts();
}


function updateInputCharacterCounts() {
  updateCharacterMeter("linkCharacterCount", countCharacters($("linkInput")?.value));
  updateCharacterMeter("messageCharacterCount", countCharacters($("message")?.value));
  updateCharacterMeter("voiceCharacterCount", countCharacters($("voiceText")?.value));
}


function inputCharacterLimitError(body) {
  const count = countCharacters(body.message);

  if (count <= AI_CHARACTER_LIMIT) return "";

  return `Nội dung có ${count.toLocaleString("vi-VN")} ký tự, vượt quá giới hạn ${AI_CHARACTER_LIMIT.toLocaleString("vi-VN")} ký tự. Bác rút gọn rồi gửi lại nhé.`;
}


// ===== Gemini Analyze Section =====
async function analyze() {
  const body = getInputBody();

  if (!body.message && !body.image) {
    return showError("Vui lòng nhập nội dung hoặc chọn ảnh.");
  }

  const limitError = inputCharacterLimitError(body);

  if (limitError) {
    return showError(limitError);
  }

  setBusy(true);

  try {
    const data = await post("/api/analyze", body);

    currentResult = normalizeResult({
      ...data,
      id: "check-" + Date.now(),
      time: new Date().toISOString(),
      inputText: body.message || body.image.name
    });

    history = [currentResult, ...history].slice(0, 10);

    saveHistory();
    drawHistory();
    showResult(currentResult);
  } catch (error) {
    showError(error.message);
  } finally {
    setBusy(false);
  }
}


// ===== Result Display Section =====
async function showResult(item) {
  currentResult = normalizeResult(item);
  showPage("analysis");

  if (!currentResult.html) {
    $("resultBox").innerHTML = "<p>Đang mở kết quả đã lưu...</p>";

    try {
      currentResult = normalizeResult(
        await post("/api/history-view", currentResult)
      );

      history = history
        .map(savedItem => savedItem.id === currentResult.id ? currentResult : savedItem)
        .slice(0, 10);

      saveHistory();
    } catch (error) {
      $("resultBox").innerHTML = `<p>${safe(error.message)}</p>`;
      return;
    }
  }

  $("resultBox").innerHTML = currentResult.html + resultToolsHtml();

  polishResultLayout();

  // Risky results get a small human support card; tuck it beside the checklist.
  const supportCard = document.querySelector(".support-card, .support-note");
  const actionBox = document.querySelector("#resultCard .grid .box:nth-child(2)");

  if (supportCard && actionBox) {
    actionBox.classList.add("action-box");
    actionBox.appendChild(supportCard);
  }

  document.querySelectorAll("[data-action]").forEach(button => {
    button.onclick = () => askAction(Number(button.dataset.action));
  });

  bindResultTools();
}


// ===== Result Layout Polish Section =====
function polishResultLayout() {
  const resultCard = $("resultCard");
  const resultHead = resultCard?.querySelector(".result-head");
  const resultMain = resultCard?.querySelector(".result-main");
  const originalBox = resultCard?.querySelector(".original-text");
  const originalText = originalBox?.querySelector("p");

  if (resultCard && resultHead && resultMain) {
    resultMain.classList.add("score-first");
    resultCard.insertBefore(resultMain, resultHead);
  }

  if (resultHead && originalText) {
    const quote = document.createElement("blockquote");

    quote.className = "prompt-quote";
    quote.innerHTML = `
      <span>Tin bác nhập:</span>
      <p>“${originalText.innerHTML}”</p>
    `;

    resultHead.appendChild(quote);
    originalBox.remove();
  }
}


// ===== Result Action Button Section =====
function askAction(index) {
  const action = currentResult.next_actions[index];

  if (!action) return;

  // Keep the chosen step available for the chat drawer response.
  selectedActionLabel = action.label || "";

  openChat(true);

  $("chatQuestion").value =
    `Tôi muốn làm bước “${action.label}”. Hãy hướng dẫn tôi.`;
  $("chatQuestion").focus();
}
