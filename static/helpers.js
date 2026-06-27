/* =========================================================
   helpers.js
   Shared helpers: DOM lookup, safe HTML, fetch, files, results.
   ========================================================= */

// ===== DOM Helper Section =====
function $(id) {
  return document.getElementById(id);
}


// ===== HTML Safety Section =====
function safe(text) {
  return String(text || "").replace(/[&<>"']/g, character => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#039;"
  }[character]));
}


function cleanDisplayText(text) {
  const parser = document.createElement("textarea");

  parser.innerHTML = String(text || "");

  return parser.value
    .replace(/`n/g, "\n")
    .replace(/\\n/g, "\n")
    .replace(/^```(?:json|html|javascript|js|python|text)?\s*/i, "")
    .replace(/\s*```$/g, "")
    .replace(/<br\s*\/?>/gi, "\n")
    .replace(/<\/(?:p|div|li|h[1-6])\s*>/gi, "\n")
    .replace(/<\/?[^>]+>/g, "")
    .replace(/[ \t]*\n[ \t]*/g, "\n")
    .replace(/^\s*(?:answer|summary|explanation|uncertainty|why|prompt)\s*:\s*/i, "")
    .replace(/\n{3,}/g, "\n\n")
    .trim();
}


function cleanResultForDisplay(item) {
  const result = { ...(item || {}) };

  ["summary", "explanation", "uncertainty", "psychology", "checked_text", "inputText"].forEach(key => {
    if (result[key]) result[key] = cleanDisplayText(result[key]);
  });

  if (Array.isArray(result.evidence)) {
    result.evidence = result.evidence.map(row => ({
      ...row,
      quote: cleanDisplayText(row?.quote),
      why: cleanDisplayText(row?.why || row?.explanation),
      explanation: cleanDisplayText(row?.explanation)
    }));
  }

  if (Array.isArray(result.next_actions)) {
    result.next_actions = result.next_actions.map(action => ({
      ...action,
      label: cleanDisplayText(action?.label),
      prompt: cleanDisplayText(action?.prompt || action?.detail),
      detail: cleanDisplayText(action?.detail || action?.prompt)
    }));
  }

  return result;
}


// ===== POST Request Section =====
async function post(url, body) {
  let response;

  try {
    response = await fetch(url, {
      method: "POST",
      headers: {
        "Content-Type": "application/json"
      },
      body: JSON.stringify(body)
    });
  } catch {
    throw Error("Không kết nối được mạng hoặc backend. Vui lòng thử lại sau.");
  }

  const text = await response.text();

  let data;

  try {
    data = JSON.parse(text);
  } catch {
    throw Error("Backend trả dữ liệu không hợp lệ. Hãy tải lại trang.");
  }

  if (!response.ok) {
    throw Error(data.error || "Backend chưa trả lời.");
  }

  return data;
}


// ===== GET Request Section =====
async function get(url) {
  try {
    const response = await fetch(url);
    const data = await response.json();

    if (!response.ok) {
      throw Error(data.error || "Không tải được dữ liệu.");
    }

    return data;
  } catch {
    throw Error("Không tải được dữ liệu.");
  }
}


// ===== File Reader Section =====
function dataUrl(file) {
  return new Promise((ok, bad) => {
    const reader = new FileReader();

    reader.onload = () => ok(reader.result);
    reader.onerror = bad;

    reader.readAsDataURL(file);
  });
}


// ===== Result Normalizer Section =====
function normalizeResult(item) {
  item = cleanResultForDisplay(item);
  const rawScore = Number(
    item.danger_score_percent ?? item.score ?? item.riskpercentage
  );

  const score = Number.isFinite(rawScore)
    ? Math.max(0, Math.min(100, Math.round(rawScore)))
    : 0;

  const risk = item.risk || (
    score >= 76
      ? "danger"
      : score >= 26
        ? "suspicious"
        : "safe"
  );

  return {
    ...item,
    danger_score_percent: score,
    risk,
    verdict_label: item.verdict_label || item.verdict || (
      risk === "danger"
        ? "Nguy hiểm"
        : risk === "suspicious"
          ? "Nghi ngờ"
          : "An toàn"
    ),
    summary: item.summary || item.explanation || "Kết quả kiểm tra",
    inputText: item.inputText || item.checked_text || "Nội dung đã kiểm tra",
    next_actions: item.next_actions || item.actions || []
  };
}
