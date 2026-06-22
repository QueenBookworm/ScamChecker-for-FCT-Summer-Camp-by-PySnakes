/* =========================================================
   extras.js
   Result tools, rescue, library, training, QR/share/download.
   ========================================================= */

// ===== Result Tools HTML Section =====
function resultToolsHtml() {
  const appUrl = location.origin || "http://localhost:5000";
  const rescueOptions = rescueOptionsHtml();

  return `
    <div class="result-action-rail">
      <button id="copyResult" class="tool-btn" type="button">Copy text</button>
      <button id="shareResult" class="tool-btn" type="button">Share</button>
      <button id="downloadCard" class="tool-btn" type="button">Download</button>
      <button id="reportScam" class="tool-btn" type="button">Report scam</button>
    </div>

    <div id="qrBox" class="qr-popover" hidden>
      <img
        class="qr-img"
        alt="QR ScamCheck"
        src="https://api.qrserver.com/v1/create-qr-code/?size=180x180&data=${encodeURIComponent(appUrl)}"
      >
      <span class="hint">Quét để mở ScamCheck</span>
    </div>

    ${rescueOptions}

    <canvas id="shareCanvas" width="1080" height="1600"></canvas>
    <div id="toolToast" class="tool-toast"></div>
  `;
}

// ===== Rescue Options HTML Section =====
function rescueOptionsHtml() {
  const options = Array.isArray(currentResult?.rescue_options)
    ? currentResult.rescue_options
    : [];

  if (!options.length) {
    return "";
  }

  return `
    <details class="rescue-panel" open>
      <summary>
        <strong>Bác đã làm gì rồi?</strong>
        <span class="hint">Gợi ý theo phân tích Gemini</span>
      </summary>

      <div class="rescue-options">
        ${options.map(option => `
          <button class="rescue-btn" data-rescue="${safe(option.id)}" aria-pressed="false" type="button">
            <span class="rescue-check"></span>
            <span>${safe(option.label)}</span>
          </button>
        `).join("")}
      </div>

      <button id="rescueSubmit" class="rescue-submit" disabled type="button">
        Nhận hướng dẫn xử lý
      </button>

      <div id="rescueOutput" class="rescue-output"></div>
    </details>
  `;
}


// ===== Result Tools Binding Section =====
function bindResultTools() {
  document.querySelectorAll("[data-rescue]").forEach(button => {
    button.onclick = () => toggleRescueChoice(button);
  });

  if ($("rescueSubmit")) {
    $("rescueSubmit").onclick = submitRescue;
  }
  $("copyResult").onclick = copyResult;
  $("shareResult").onclick = shareResult;
  $("downloadCard").onclick = downloadResultCard;
  $("reportScam").onclick = reportScam;

  drawShareCard();
}


// ===== Official Scam Report Section =====
function reportScam() {
  window.open("https://canhbao.khonggianmang.vn", "_blank", "noopener,noreferrer");
  showToast("Đã mở trang báo cáo chính thức của NCSC.");
}


// ===== Rescue Choice Section =====
function toggleRescueChoice(clickedButton) {
  const buttons = [...document.querySelectorAll("[data-rescue]")];

  if (clickedButton.dataset.rescue === "none") {
    buttons.forEach(button => {
      button.classList.remove("selected");
    });
  } else {
    const noneButton = buttons.find(button => button.dataset.rescue === "none");

    if (noneButton) {
      noneButton.classList.remove("selected");
    }
  }

  clickedButton.classList.toggle("selected");

  buttons.forEach(button => {
    button.setAttribute(
      "aria-pressed",
      button.classList.contains("selected")
    );
  });

  $("rescueSubmit").disabled = !buttons.some(button => {
    return button.classList.contains("selected");
  });
}


// ===== Rescue Submit Section =====
async function submitRescue() {
  const situations = [...document.querySelectorAll("[data-rescue].selected")]
    .map(button => button.dataset.rescue);

  if (!situations.length) return;

  const submitButton = $("rescueSubmit");

  submitButton.disabled = true;
  submitButton.textContent = "Đang chuẩn bị hướng dẫn...";

  $("rescueOutput").innerHTML =
    "<div>Gemini đang xem các tình huống bác đã chọn.</div>";

  try {
    const data = await post("/api/rescue", {
      situations,
      result: currentResult
    });

    $("rescueOutput").innerHTML = data.steps
      .map(step => `<div>${safe(step)}</div>`)
      .join("");
  } catch (error) {
    $("rescueOutput").innerHTML = `<div>${safe(error.message)}</div>`;
  } finally {
    submitButton.textContent = "Cập nhật hướng dẫn";
    submitButton.disabled = false;
  }
}


// ===== Result Text Section =====
function resultText() {
  return `
ScamCheck
${currentResult.verdict_label} - ${currentResult.danger_score_percent}% rủi ro
${currentResult.summary || ""}
${currentResult.explanation || ""}
  `.trim();
}


// ===== Copy Result Section =====
async function copyResult() {
  try {
    await navigator.clipboard.writeText(resultText());
    showToast("Đã copy kết quả.");
  } catch {
    showToast("Không copy được trên trình duyệt này.");
  }
}


// ===== Share Result Section =====
async function shareResult() {
  drawShareCard();

  try {
    if (navigator.share) {
      await navigator.share({
        title: "ScamCheck",
        text: resultText(),
        url: location.href
      });
    } else {
      await copyResult();
    }

    showToast("Đã mở chia sẻ.");
  } catch {
    showToast("Đã hủy chia sẻ.");
  }
}


// ===== Canvas Drawing Section =====
function drawShareCard() {
  const canvas = $("shareCanvas");
  const context = canvas.getContext("2d");

  const evidence = Array.isArray(currentResult.evidence)
    ? currentResult.evidence
    : [];

  const actions = Array.isArray(currentResult.next_actions)
    ? currentResult.next_actions
    : [];

  const allText = [
    currentResult.summary,
    currentResult.explanation,
    currentResult.uncertainty,
    currentResult.checked_text,
    currentResult.psychology,
    ...evidence.flatMap(item => [item.quote, item.why]),
    ...actions.map(action => action.label)
  ].filter(Boolean).join(" ");

  canvas.width = 1080;
  canvas.height = Math.max(1700, 1050 + 42 * Math.ceil(allText.length / 42));

  const riskColor = currentResult.risk === "danger"
    ? "#ef4444"
    : currentResult.risk === "suspicious"
      ? "#f59e0b"
      : "#22c55e";

  context.fillStyle = "#fffaf7";
  context.fillRect(0, 0, canvas.width, canvas.height);

  context.fillStyle = "#172033";
  context.font = "bold 72px Segoe UI, Arial";
  context.fillText("ScamCheck", 70, 110);

  context.fillStyle = riskColor;
  context.fillRect(70, 155, 940, 150);

  context.fillStyle = "white";
  context.font = "bold 54px Segoe UI, Arial";
  context.fillText(
    `${currentResult.verdict_label} · ${currentResult.danger_score_percent}% rủi ro`,
    110,
    250
  );

  let y = 375;

  function section(title, lines) {
    context.fillStyle = "#172033";
    context.font = "bold 34px Segoe UI, Arial";
    context.fillText(title, 70, y);
    y += 52;

    context.font = "29px Segoe UI, Arial";
    context.fillStyle = "#475569";

    lines.filter(Boolean).forEach(line => {
      y = wrapCanvasText(context, line, 80, y, 920, 42) + 10;
    });

    y += 24;
  }

  section("Kết luận", [
    currentResult.summary,
    currentResult.explanation,
    currentResult.uncertainty
  ]);

  section(
    "Dấu hiệu phát hiện",
    evidence.flatMap((item, index) => [
      `${index + 1}. ${item.quote || "Dấu hiệu đáng chú ý"}`,
      item.why || item.explanation
    ])
  );

  section(
    "Nên làm gì tiếp?",
    actions.map((action, index) => `${index + 1}. ${action.label}`)
  );

  section("Tin gốc", [
    currentResult.checked_text || currentResult.inputText || "Không có văn bản gốc."
  ]);

  if (currentResult.psychology) {
    section("Hiểu vì sao mình suýt tin", [
      currentResult.psychology
    ]);
  }

  context.fillStyle = "#64748b";
  context.font = "25px Segoe UI, Arial";

  wrapCanvasText(
    context,
    "ScamCheck là công cụ giáo dục, không thay thế cảnh báo chính thức.",
    70,
    canvas.height - 75,
    940,
    34
  );
}


// ===== Canvas Text Wrap Section =====
function wrapCanvasText(context, text, x, y, maxWidth, lineHeight) {
  const words = String(text).split(" ");
  let row = "";

  for (const word of words) {
    const testRow = row + word + " ";

    if (context.measureText(testRow).width > maxWidth) {
      context.fillText(row, x, y);
      row = word + " ";
      y += lineHeight;
    } else {
      row = testRow;
    }
  }

  context.fillText(row, x, y);

  return y + lineHeight;
}


// ===== Download Result Card Section =====
function downloadResultCard() {
  drawShareCard();

  const link = document.createElement("a");

  link.href = $("shareCanvas").toDataURL("image/png");
  link.download = "scamcheck-canh-bao.png";
  link.click();

  showToast("Đã tạo ảnh cảnh báo.");
}


// ===== Toast Section =====
function showToast(text) {
  $("toolToast").textContent = text;

  setTimeout(() => {
    if ($("toolToast")) {
      $("toolToast").textContent = "";
    }
  }, 2400);
}


// ===== Extra Pages Load Section =====
async function loadExtraPages() {
  try {
    libraryData = await get("/api/library");
    drawLibrary();

    trainingData = await get("/api/training");
    drawTraining();
  } catch {
    // Extra pages are optional. If they fail, the main checker still works.
  }
}


// ===== Library Render Section =====
function drawLibrary() {
  const groups = [
    "Tất cả",
    ...new Set(libraryData.map(item => item.group))
  ];

  $("libraryFilters").innerHTML = groups.map(group => `
    <button
      class="filter-btn ${group === libraryGroup ? "active" : ""}"
      data-group="${safe(group)}"
      type="button"
    >
      ${safe(group)}
    </button>
  `).join("");

  document.querySelectorAll("#libraryFilters [data-group]").forEach(button => {
    button.onclick = () => {
      libraryGroup = button.dataset.group;
      drawLibrary();
    };
  });

  const rows = libraryGroup === "Tất cả"
    ? libraryData
    : libraryData.filter(item => item.group === libraryGroup);

  $("libraryList").innerHTML = rows.map(item => `
    <details class="library-item">
      <summary>
        <span class="library-title">
          <span class="library-tag">${safe(item.group)}</span>
          <strong>${safe(item.name)}</strong>
        </span>
      </summary>

      <div class="library-body">
        <p>${safe(item.description)}</p>
        <div class="library-example">
          <span>Ví dụ:</span> ${safe(item.example)}
        </div>
      </div>
    </details>
  `).join("");

  setupExclusiveDetails("#libraryList", ".library-item");
}


// ===== Training Setup Section =====
function setupTraining() {
  $("trainScam").onclick = () => answerTraining("scam");
  $("trainSafe").onclick = () => answerTraining("safe");
  $("trainNext").onclick = handleTrainingNext;
}


// ===== Training Render Section =====
function drawTraining() {
  clearTimeout(trainingTimer);

  if (!trainingData.length) return;

  if (trainingIndex >= trainingData.length) {
    finishTraining();
    return;
  }

  const item = trainingData[trainingIndex];

  trainingAnswered = false;

  $("trainProgress").textContent =
    `Câu ${trainingIndex + 1}/${trainingData.length} · Điểm ${trainingScore}`;

  $("trainText").textContent = item.text;

  $("trainFeedback").className = "hint";
  $("trainFeedback").textContent = "Bác chọn một đáp án bên dưới.";

  $("trainScam").disabled = false;
  $("trainSafe").disabled = false;

  $("trainNext").textContent = "Bỏ qua";
}


// ===== Training Answer Section =====
function answerTraining(choice) {
  const item = trainingData[trainingIndex];

  if (!item || trainingAnswered) return;

  trainingAnswered = true;

  const correct = choice === item.label;

  if (correct) {
    trainingScore++;
  }

  $("trainScam").disabled = true;
  $("trainSafe").disabled = true;

  $("trainFeedback").className = correct
    ? "hint train-ok"
    : "hint train-bad";

  $("trainFeedback").innerHTML = `
    <span class="train-icon">${correct ? "✓" : "×"}</span>

    <span>
      <strong>${correct ? "Chính xác" : "Chưa đúng"}</strong><br>
      ${safe(item.why)}<br>
      <small>Tự chuyển sang câu tiếp theo...</small>
    </span>
  `;

  $("trainProgress").textContent =
    `Câu ${trainingIndex + 1}/${trainingData.length} · Điểm ${trainingScore}`;

  trainingTimer = setTimeout(
    nextTraining,
    correct ? 1300 : 2200
  );
}


// ===== Training Next Section =====
function handleTrainingNext() {
  if (trainingIndex < 0 || trainingAnswered) {
    nextTraining();
    return;
  }

  skipTraining();
}


function skipTraining() {
  clearTimeout(trainingTimer);
  trainingIndex++;
  drawTraining();
}


function nextTraining() {
  clearTimeout(trainingTimer);

  if (!trainingAnswered && trainingIndex < trainingData.length) {
    $("trainFeedback").textContent =
      "Bác hãy chọn Lừa đảo hoặc An toàn trước.";
    return;
  }

  trainingIndex++;
  drawTraining();
}


// ===== Training Finish Section =====
function finishTraining() {
  clearTimeout(trainingTimer);

  const tip = trainingScore >= 20
    ? "Rất tốt. Bác đã nhận ra hầu hết dấu hiệu nguy hiểm."
    : trainingScore >= 14
      ? "Khá ổn. Bác nên luyện thêm phần link lạ, OTP và chuyển tiền gấp."
      : "Bác nên xem lại Thư viện kiểu lừa đảo rồi luyện lại một lần nữa.";

  $("trainProgress").textContent =
    `Hoàn thành · ${trainingScore}/${trainingData.length}`;

  $("trainText").textContent = tip;

  $("trainFeedback").className = "hint train-ok";
  $("trainFeedback").innerHTML = `
    <span class="train-icon">✓</span>

    <span>
      <strong>Đã xong bài luyện tập</strong><br>
      Bấm Luyện lại để bắt đầu lại từ câu 1.
    </span>
  `;

  $("trainScam").disabled = true;
  $("trainSafe").disabled = true;

  $("trainNext").textContent = "Luyện lại";

  trainingIndex = -1;
  trainingScore = 0;
  trainingAnswered = true;
}
