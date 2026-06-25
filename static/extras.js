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
      <button id="copyResult" class="tool-btn" type="button">Sao chép</button>
      <button id="shareResult" class="tool-btn" type="button">Chia sẻ</button>
      <button id="downloadCard" class="tool-btn" type="button">Tải PDF</button>
      <button id="reportScam" class="tool-btn" type="button">Báo cáo</button>
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


function rescueOptionsHtml() {
  if (!currentResult || currentResult.danger_score_percent < 40) {
    return "";
  }

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
  window.open("https://chongluadao.vn/", "_blank", "noopener,noreferrer");
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
    $("copyResult").classList.add("copied");
    $("copyResult").textContent = "Đã chép";
    showToast("✓ Đã sao chép kết quả.");
    setTimeout(() => {
      if ($("copyResult")) {
        $("copyResult").classList.remove("copied");
        $("copyResult").textContent = "Sao chép";
      }
    }, 1600);
  } catch {
    showToast("Không copy được trên trình duyệt này.");
  }
}


// ===== Share Result Section =====
async function shareResult() {
  if (!currentResult?.share_id && typeof publishCurrentResult === "function") {
    await publishCurrentResult();
  }

  const shareUrl = currentResult?.share_url || (currentResult?.share_id ? `/analysis/${currentResult.share_id}` : location.href);
  const absoluteUrl = new URL(shareUrl, location.origin).href;

  try {
    if (navigator.share) {
      await navigator.share({
        title: "ScamCheck",
        text: resultText(),
        url: absoluteUrl
      });
    } else {
      await navigator.clipboard.writeText(absoluteUrl);
    }

    showToast("Đã chuẩn bị link chia sẻ.");
  } catch {
    showToast("Không thể chia sẻ lúc này.");
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


// ===== Readable Multi-Page Download Override Section =====
function drawShareCard(pageIndex = 0) {
  const canvas = $("shareCanvas");
  const context = canvas.getContext("2d");

  canvas.width = 1080;
  canvas.height = 1600;

  const pages = buildSharePages(context);
  const safePageIndex = Math.max(0, Math.min(pageIndex, pages.length - 1));
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
    `${currentResult.verdict_label} - ${currentResult.danger_score_percent}% rủi ro`,
    110,
    250
  );
  context.fillStyle = "#64748b";
  context.font = "bold 25px Segoe UI, Arial";
  context.fillText(`Trang ${safePageIndex + 1}/${pages.length}`, 820, 345);

  for (const block of pages[safePageIndex]) {
    if (block.type === "title") {
      context.fillStyle = "#172033";
      context.font = "bold 36px Segoe UI, Arial";
      context.fillText(block.text, 70, block.y);
    } else {
      context.fillStyle = "#475569";
      context.font = "30px Segoe UI, Arial";
      context.fillText(block.text, 82, block.y);
    }
  }

  context.fillStyle = "#64748b";
  context.font = "25px Segoe UI, Arial";
  wrapCanvasText(
    context,
    "ScamCheck là công cụ giáo dục và không thay thế cảnh báo chính thức.",
    70,
    canvas.height - 75,
    940,
    34
  );

  return pages.length;
}


function buildSharePages(context) {
  const evidence = Array.isArray(currentResult.evidence)
    ? currentResult.evidence
    : [];
  const actions = Array.isArray(currentResult.next_actions)
    ? currentResult.next_actions
    : [];
  const sections = [
    ["Kết luận", [
      currentResult.summary,
      currentResult.explanation,
      currentResult.uncertainty
    ]],
    ["Dấu hiệu phát hiện", evidence.flatMap((item, index) => [
      `${index + 1}. ${item.quote || "Dấu hiệu đáng chú ý"}`,
      item.why || item.explanation
    ])],
    ["Nên làm gì tiếp?", actions.map((action, index) => `${index + 1}. ${action.label}`)],
    ["Tin gốc", [
      currentResult.checked_text || currentResult.inputText || "Không có văn bản gốc."
    ]]
  ];

  if (currentResult.psychology) {
    sections.push(["Cô tâm lý nhắc nhẹ", [currentResult.psychology]]);
  }

  const pages = [[]];
  const top = 390;
  const bottom = 1465;
  let y = top;

  function newPage() {
    pages.push([]);
    y = top;
  }

  for (const [title, lines] of sections) {
    if (y > top && y + 86 > bottom) newPage();
    pages[pages.length - 1].push({ type: "title", text: title, y });
    y += 54;
    context.font = "30px Segoe UI, Arial";

    const wrappedLines = lines
      .filter(Boolean)
      .flatMap(line => wrapCanvasLines(context, line, 900));

    for (const line of wrappedLines) {
      if (y + 40 > bottom) newPage();
      pages[pages.length - 1].push({ type: "body", text: line, y });
      y += 40;
    }

    y += 34;
  }

  return pages.filter(page => page.length);
}


function wrapCanvasLines(context, text, maxWidth) {
  const words = String(text).split(/\s+/).filter(Boolean);
  const lines = [];
  let row = "";

  for (const word of words) {
    const testRow = row ? `${row} ${word}` : word;

    if (context.measureText(testRow).width > maxWidth && row) {
      lines.push(row);
      row = word;
    } else {
      row = testRow;
    }
  }

  if (row) lines.push(row);
  return lines;
}


async function downloadResultCard() {
  // Opens a PDF preview first, then lets the user download the exact file.
  const button = $("downloadCard");
  const oldText = button.textContent;

  button.disabled = true;
  button.textContent = "Đang mở PDF";

  try {
    const response = await fetch("/api/result-pdf", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ result: currentResult })
    });

    if (!response.ok) {
      const data = await response.json().catch(() => ({}));
      throw new Error(data.error || "Không tạo được PDF.");
    }

    const blob = await response.blob();
    showPdfPreview(blob);
    showToast("Đã mở bản xem trước PDF.");
  } catch (error) {
    showToast(error.message);
  } finally {
    button.disabled = false;
    button.textContent = oldText;
  }
}


function showPdfPreview(blob) {
  // Displays the generated PDF inside the app before downloading.
  const oldPreview = $("pdfPreviewModal");

  if (oldPreview) {
    oldPreview.remove();
  }

  const url = URL.createObjectURL(blob);

  document.body.insertAdjacentHTML("beforeend", `
    <div id="pdfPreviewModal" class="pdf-preview-backdrop" role="dialog" aria-modal="true" aria-label="Xem trước PDF">
      <section class="pdf-preview-card">
        <div class="pdf-preview-head">
          <strong>Xem trước PDF kết quả</strong>
          <div class="pdf-preview-actions">
            <button id="pdfPreviewClose" class="pdf-close" type="button">Đóng</button>
            <button id="pdfPreviewDownload" class="pdf-download" type="button">Tải xuống</button>
          </div>
        </div>
        <iframe class="pdf-frame" src="${url}" title="Bản xem trước PDF ScamCheck"></iframe>
      </section>
    </div>
  `);

  const closePreview = () => {
    URL.revokeObjectURL(url);
    $("pdfPreviewModal")?.remove();
  };

  $("pdfPreviewClose").onclick = closePreview;
  $("pdfPreviewModal").onclick = event => {
    if (event.target.id === "pdfPreviewModal") {
      closePreview();
    }
  };
  $("pdfPreviewDownload").onclick = () => {
    const link = document.createElement("a");

    link.href = url;
    link.download = "scamcheck-ket-qua.pdf";
    link.click();
    showToast("Đã tải PDF kết quả.");
  };
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

    trainingAllData = await get("/api/training");
    startTrainingBatch(0);
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
  // Wires the SAT-style practice controls to answer, navigate, and submit actions.
  $("trainScam").onclick = () => answerTraining("scam");
  $("trainSafe").onclick = () => answerTraining("safe");
  $("trainNext").onclick = nextTraining;
  $("trainPrev").onclick = previousTraining;
  $("trainSubmit").onclick = submitTraining;
}


// ===== Training Batch Section =====
function startTrainingBatch(startIndex) {
  // Starts the first 15-question batch or the remaining practice batch.
  trainingBatchStart = Math.max(0, startIndex);
  const batchSize = trainingBatchStart === 0
    ? TRAINING_FIRST_BATCH_SIZE
    : Math.max(1, trainingAllData.length - trainingBatchStart);

  trainingData = trainingAllData.slice(trainingBatchStart, trainingBatchStart + batchSize);
  trainingAnswers = Array(trainingData.length).fill(null);
  trainingIndex = 0;
  trainingScore = 0;
  trainingSubmitted = false;
  drawTraining();
}


// ===== Training Render Section =====
function drawTraining() {
  clearTimeout(trainingTimer);

  if (!trainingData.length) return;

  if (trainingAnswers.length !== trainingData.length) {
    trainingAnswers = Array(trainingData.length).fill(null);
    trainingSubmitted = false;
    trainingIndex = 0;
  }

  trainingIndex = Math.max(0, Math.min(trainingIndex, trainingData.length - 1));
  trainingScore = calculateTrainingScore();

  const item = trainingData[trainingIndex];
  const answer = trainingAnswers[trainingIndex];
  const answeredCount = trainingAnswers.filter(Boolean).length;
  const batchName = trainingBatchStart === 0 ? "Phần 1" : "Phần 2";

  $("trainProgress").textContent =
    `${batchName} · Câu ${trainingIndex + 1}/${trainingData.length} · Đã làm ${answeredCount}/${trainingData.length} · Điểm ${trainingSubmitted ? trainingScore : "--"}`;

  $("trainText").textContent = item.text;
  $("trainScam").classList.toggle("selected", answer === "scam");
  $("trainSafe").classList.toggle("selected", answer === "safe");
  $("trainScam").disabled = false;
  $("trainSafe").disabled = false;
  $("trainNext").disabled = false;
  $("trainSubmit").disabled = false;
  $("trainPrev").disabled = trainingIndex === 0;
  $("trainNext").textContent = trainingIndex === trainingData.length - 1 ? "Nộp bài" : "Câu tiếp";

  renderTrainingMap();
  renderTrainingFeedback();
}


function renderTrainingMap() {
  // Draws numbered question chips showing current, answered, correct, and wrong states.
  $("trainMap").innerHTML = trainingData.map((item, index) => {
    const answer = trainingAnswers[index];
    const state = !answer
      ? "unanswered"
      : answer === item.label
        ? "correct"
        : "wrong";

    return `
      <button
        class="train-chip ${state} ${index === trainingIndex ? "current" : ""}"
        data-train-index="${index}"
        type="button"
        aria-label="Câu ${index + 1}: ${answer ? "đã trả lời" : "chưa trả lời"}"
      >
        ${index + 1}
      </button>
    `;
  }).join("");

  document.querySelectorAll("[data-train-index]").forEach(button => {
    button.onclick = () => {
      trainingIndex = Number(button.dataset.trainIndex);
      drawTraining();
    };
  });
}


function renderTrainingFeedback() {
  // Updates the explanation panel for unanswered, correct, and incorrect responses.
  const item = trainingData[trainingIndex];
  const answer = trainingAnswers[trainingIndex];

  $("trainFeedback").className = "hint";

  if (!answer) {
    $("trainFeedback").textContent = "Bác chọn một đáp án, hoặc bấm Câu tiếp để bỏ qua tạm thời.";
    return;
  }

  const correct = answer === item.label;
  $("trainFeedback").className = correct ? "hint train-ok" : "hint train-bad";
  $("trainFeedback").innerHTML = `
    <span class="train-icon">${correct ? "✓" : "×"}</span>
    <span>
      <strong>${correct ? "Chính xác" : "Chưa đúng"}</strong><br>
      ${safe(item.why)}
    </span>
  `;
}


// ===== Training Answer Section =====
function answerTraining(choice) {
  if (!trainingData[trainingIndex]) return;

  trainingAnswers[trainingIndex] = choice;
  trainingSubmitted = false;
  drawTraining();
}


// ===== Training Navigation Section =====
function previousTraining() {
  // Moves back one question while keeping existing answers in place.
  trainingIndex = Math.max(0, trainingIndex - 1);
  drawTraining();
}


function nextTraining() {
  // Moves forward one question, or submits when the user is on the last question.
  if (trainingIndex >= trainingData.length - 1) {
    submitTraining();
    return;
  }

  trainingIndex++;
  drawTraining();
}


async function submitTraining() {
  // Confirms unfinished quizzes before locking in the final score.
  const unanswered = trainingAnswers.filter(answer => !answer).length;

  if (unanswered) {
    const confirmed = await confirmDialog({
      title: "Nộp bài luyện tập?",
      message: `Bác còn ${unanswered} câu chưa trả lời. Bác vẫn muốn nộp bài và xem điểm chứ?`,
      confirmText: "Nộp bài",
      danger: false
    });

    if (!confirmed) return;
  }

  finishTraining();
}


// ===== Training Finish Section =====
function finishTraining() {
  trainingSubmitted = true;
  trainingScore = calculateTrainingScore();
  const answeredCount = trainingAnswers.filter(Boolean).length;
  const unansweredCount = trainingData.length - answeredCount;
  const wrongCount = answeredCount - trainingScore;
  const percent = Math.round((trainingScore / trainingData.length) * 100);
  const nextStart = trainingBatchStart + trainingData.length;
  const hasMoreQuestions = nextStart < trainingAllData.length;

  const tip = trainingScore >= Math.ceil(trainingData.length * 0.8)
    ? "Rất tốt. Bác đã nhận ra hầu hết dấu hiệu nguy hiểm."
    : trainingScore >= Math.ceil(trainingData.length * 0.55)
      ? "Khá ổn. Bác nên luyện thêm phần link lạ, OTP và chuyển tiền gấp."
      : "Bác nên xem lại Thư viện kiểu lừa đảo rồi luyện lại một lần nữa.";

  $("trainProgress").textContent =
    `Hoàn thành · ${trainingScore}/${trainingData.length}`;

  $("trainText").innerHTML = `
    <div class="training-dashboard">
      <span class="dashboard-label">Bảng phân tích luyện tập</span>
      <strong>${percent}%</strong>
      <p>${safe(tip)}</p>
      <div class="dashboard-stats">
        <span><b>${trainingScore}</b><small>Câu đúng</small></span>
        <span><b>${wrongCount}</b><small>Câu sai</small></span>
        <span><b>${unansweredCount}</b><small>Chưa làm</small></span>
      </div>
      <button id="trainContinue" class="training-submit" type="button">
        ${hasMoreQuestions ? `Tiếp tục luyện ${trainingAllData.length - nextStart} câu còn lại` : "Luyện lại từ đầu"}
      </button>
    </div>
  `;

  $("trainFeedback").className = "hint train-ok";
  $("trainFeedback").innerHTML = `
    <span class="train-icon">✓</span>
    <span>
      <strong>Đã nộp bài luyện tập</strong><br>
      ${safe(tip)}
    </span>
  `;

  $("trainScam").disabled = true;
  $("trainSafe").disabled = true;
  $("trainNext").disabled = true;
  $("trainSubmit").disabled = true;
  $("trainPrev").disabled = trainingIndex === 0;

  const continueButton = $("trainContinue");
  if (continueButton) {
    continueButton.onclick = () => startTrainingBatch(hasMoreQuestions ? nextStart : 0);
  }

  renderTrainingMap();
}


function calculateTrainingScore() {
  // Counts answers that match the Python-provided correct label.
  return trainingData.reduce((score, item, index) => {
    return score + (trainingAnswers[index] === item.label ? 1 : 0);
  }, 0);
}
