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

    await publishCurrentResult();

    history = typeof mergeHistory === "function"
      ? mergeHistory([currentResult], history)
      : [currentResult, ...history];
    historyPage = 1;

    saveHistory();
    drawHistory();
    showResult(currentResult);
    loadAnalysisFollowup(body);
  } catch (error) {
    showError(error.message);
  } finally {
    setBusy(false);
  }
}


// ===== Result Display Section =====
async function showResult(item) {
  currentResult = normalizeResult(item);
  showPage("analysis", false);
  updateAnalysisPath(currentResult);

  if (!currentResult.html) {
    $("resultBox").innerHTML = "<p>Đang mở kết quả đã lưu...</p>";

    try {
      currentResult = normalizeResult(
        await post("/api/history-view", currentResult)
      );

      history = history
        .map(savedItem => savedItem.id === currentResult.id ? currentResult : savedItem);

      saveHistory();
    } catch (error) {
      $("resultBox").innerHTML = `<p>${safe(error.message)}</p>`;
      return;
    }
  }

  $("resultBox").innerHTML = currentResult.html + resultToolsHtml();

  polishResultLayout();
  placeSupportCard();

  document.querySelectorAll("[data-action]").forEach(button => {
    button.onclick = () => askAction(Number(button.dataset.action));
  });

  bindResultTools();
}


// ===== Delayed Follow-up Section =====
async function loadAnalysisFollowup(body) {
  // Loads optional Cô tâm lý content after the main detective result is already visible.
  if (!currentResult || currentResult.danger_score_percent < 40) return;

  showFollowupPlaceholder();

  try {
    const data = await post("/api/analysis-followup", {
      result: currentResult,
      message: body.message,
      image: body.image
    });

    currentResult = normalizeResult({
      ...currentResult,
      ...data
    });

    await publishCurrentResult();

    history = history.map(item => {
      return item.id === currentResult.id ? currentResult : item;
    });

    saveHistory();
    drawHistory();
    showResult(currentResult);
  } catch {
    const placeholder = $("followupPlaceholder");

    if (placeholder) {
      placeholder.className = "support-note";
      placeholder.textContent = "Cô tâm lý đang bận, bác có thể tiếp tục theo các bước bên trên.";
    }
  }
}


// ===== Shared Analysis URL Section =====
function updateAnalysisPath(result) {
  // Keeps each analysis on a separate slash URL when a share id exists.
  const shareId = result?.share_id;
  const nextPath = shareId ? `/analysis/${encodeURIComponent(shareId)}` : "/analysis";

  if (location.pathname !== nextPath) {
    window.history.pushState({ page: "analysis", shareId }, "", nextPath);
  }
}


async function publishCurrentResult() {
  // Stores the current result on the backend so the URL can be shared across users.
  if (!currentResult) return null;

  try {
    const data = await post("/api/share-result", { result: currentResult });
    currentResult = normalizeResult({
      ...currentResult,
      ...data,
      share_url: data.share_url
    });
    return currentResult;
  } catch {
    return null;
  }
}


async function loadSharedAnalysisFromPath() {
  // Loads /analysis/<id> results that were opened from another browser or device.
  const parts = location.pathname.split("/").filter(Boolean);

  if (parts[0] !== "analysis" || !parts[1]) return;

  $("resultBox").innerHTML = "<p>Đang mở kết quả đã chia sẻ...</p>";

  try {
    const data = await get(`/api/shared-result/${encodeURIComponent(parts[1])}`);
      currentResult = normalizeResult({
        ...data,
        share_id: parts[1],
        share_url: `/analysis/${parts[1]}`
      });
      history = typeof mergeHistory === "function"
        ? mergeHistory([currentResult], history)
        : [currentResult, ...history];
      saveHistory();
      drawHistory();
      showResult(currentResult);
  } catch (error) {
    $("resultBox").innerHTML = `<p>${safe(error.message)}</p>`;
  }
}


function showFollowupPlaceholder() {
  // Shows a small local loading note beside next steps while the follow-up API runs.
  const actionBox = document.querySelector("#resultCard .grid .box:nth-child(2)");

  if (!actionBox || $("followupPlaceholder")) return;

  actionBox.classList.add("action-box");
  actionBox.insertAdjacentHTML(
    "beforeend",
    `<div id="followupPlaceholder" class="support-loading">
      <span class="mini-spinner"></span>
      <span>Cô tâm lý đang đọc thêm để nhắc nhẹ cho bác...</span>
    </div>`
  );
}


function placeSupportCard() {
  // Moves Cô tâm lý or its fallback note into the next-step column for cleaner layout.
  const supportCard = document.querySelector(".support-card, .support-note");
  const actionBox = document.querySelector("#resultCard .grid .box:nth-child(2)");

  if (supportCard && actionBox) {
    actionBox.classList.add("action-box");
    actionBox.appendChild(supportCard);
  }
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
