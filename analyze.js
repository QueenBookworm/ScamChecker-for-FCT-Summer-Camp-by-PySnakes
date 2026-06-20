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


// ===== Gemini Analyze Section =====
async function analyze() {
  const body = getInputBody();

  if (!body.message && !body.image) {
    return showError("Vui lòng nhập nội dung hoặc chọn ảnh.");
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

  document.querySelectorAll("[data-action]").forEach(button => {
    button.onclick = () => askAction(Number(button.dataset.action));
  });

  bindResultTools();
}


// ===== Result Action Button Section =====
function askAction(index) {
  const action = currentResult.next_actions[index];

  if (!action) return;

  openChat(true);

  $("chatQuestion").value =
    `Tôi muốn làm bước “${action.label}”. Hãy hướng dẫn tôi.`;
    selectedAction = action.prompt || ""
  $("chatQuestion").focus();
}
