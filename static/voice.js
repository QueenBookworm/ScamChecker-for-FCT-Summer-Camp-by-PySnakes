/* =========================================================
   voice.js
   Live microphone transcription directly into the textarea.
   ========================================================= */

let liveRecognition = null;
let liveVoiceBaseText = "";
let liveVoiceFinalText = "";
let liveVoiceStopping = false;
let liveVoiceTimer = null;

const LIVE_VOICE_LIMIT_MS = 90000;


// ===== Voice Setup Section =====
function setupVoice() {
  const button = $("recordBtn");
  const status = $("voiceStatus");

  if (!button) return;

  button.type = "button";
  button.disabled = false;
  button.dataset.on = "0";
  button.addEventListener("click", toggleVoiceRecording);

  renderMicrophoneTrustMessage();

  if (!speechRecognitionClass()) {
    status.textContent =
      "Trình duyệt này chưa hỗ trợ nhận diện giọng nói trực tiếp. Bác có thể nhập nội dung bằng tay.";
  }
}


// ===== Live Recording Toggle Section =====
async function toggleVoiceRecording(event) {
  event?.preventDefault();

  if ($("recordBtn").dataset.on === "1") {
    stopVoiceRecording();
    return;
  }

  await startVoiceRecording();
}


// ===== Live Speech Start Section =====
async function startVoiceRecording() {
  const SpeechRecognition = speechRecognitionClass();

  const permission = await ensureMicrophonePermission();

  if (!permission.ok) {
    renderMicrophoneTrustMessage(permission.message);
    setRecording(false);
    return;
  }

  if (!SpeechRecognition) {
    $("voiceStatus").textContent =
      "Trình duyệt này chưa hỗ trợ nhận diện giọng nói trực tiếp.";
    return;
  }

  liveVoiceBaseText = $("voiceText").value.trim();
  liveVoiceFinalText = "";
  liveVoiceStopping = false;
  liveRecognition = new SpeechRecognition();
  liveRecognition.lang = "vi-VN";
  liveRecognition.continuous = true;
  liveRecognition.interimResults = true;
  liveRecognition.maxAlternatives = 1;

  liveRecognition.onresult = updateLiveTranscript;
  liveRecognition.onerror = handleVoiceError;
  liveRecognition.onend = restartLiveRecognitionIfNeeded;

  try {
    liveRecognition.start();
    startVoiceTimeout();
    setRecording(true, "Micro đã được cho phép. Đang nghe trực tiếp, chữ sẽ hiện ở ô bên dưới.");
  } catch {
    clearVoiceTimeout();
    $("voiceStatus").textContent =
      "Micro chưa sẵn sàng. Bác thử bấm lại hoặc kiểm tra quyền micro.";
    setRecording(false);
  }
}


// ===== Microphone Permission Section =====
async function ensureMicrophonePermission() {
  if (!window.isSecureContext && !isLocalhost()) {
    return {
      ok: false,
      message: "Chrome chỉ cho dùng micro trên HTTPS hoặc localhost."
    };
  }

  if (!navigator.mediaDevices?.getUserMedia) {
    return {
      ok: false,
      message: "Trình duyệt này không có API cấp quyền micro. Bác thử Chrome/Edge mới hơn hoặc nhập bằng tay."
    };
  }

  try {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    stream.getTracks().forEach(track => track.stop());
    return { ok: true };
  } catch (error) {
    if (error?.name === "NotAllowedError") {
      return {
        ok: false,
        message: "Micro đang bị chặn. Bác bấm biểu tượng ổ khóa trên thanh địa chỉ, cho phép Microphone, rồi tải lại trang."
      };
    }

    if (error?.name === "NotFoundError") {
      return {
        ok: false,
        message: "Không tìm thấy micro trên thiết bị này. Bác kiểm tra tai nghe/micro rồi thử lại."
      };
    }

    return {
      ok: false,
      message: "Chưa mở được micro. Bác kiểm tra quyền micro trong trình duyệt rồi bấm ghi lại."
    };
  }
}


function renderMicrophoneTrustMessage(message = microphoneTrustMessage()) {
  const status = $("voiceStatus");

  if (!status) return;

  if (!window.isSecureContext && !isLocalhost()) {
    const localUrl = localhostUrl();
    status.innerHTML = `
      <strong>${safe(message)}</strong>
      <br>
      Nếu đang chạy app trên máy này, mở bằng
      <a href="${safe(localUrl)}">localhost</a>
      để Chrome cho phép micro. Khi deploy cho người dùng thật, cần dùng link HTTPS.
    `;
    return;
  }

  status.textContent = message;
}


function microphoneTrustMessage() {
  if (!window.isSecureContext && !isLocalhost()) {
    return "Micro đang bị Chrome chặn vì trang này chưa chạy bằng HTTPS hoặc localhost.";
  }

  return "Micro chỉ bật sau khi bác bấm nút ghi và trình duyệt hỏi quyền. ScamCheck không tự ghi âm nền.";
}


function isLocalhost() {
  return ["localhost", "127.0.0.1", "::1"].includes(location.hostname);
}


function localhostUrl() {
  return `${location.protocol}//localhost${location.port ? `:${location.port}` : ""}${location.pathname}${location.search}${location.hash}`;
}


// ===== Live Speech Stop Section =====
function stopVoiceRecording() {
  liveVoiceStopping = true;
  clearVoiceTimeout();

  if (liveRecognition) {
    liveRecognition.stop();
  }

  setRecording(false, "Đã dừng ghi. Bác có thể sửa lại chữ rồi bấm phân tích.");
}


// ===== Voice Timeout Section =====
function startVoiceTimeout() {
  // Stops live transcription after 90 seconds so recording cannot run forever.
  clearVoiceTimeout();

  liveVoiceTimer = setTimeout(() => {
    liveVoiceStopping = true;

    if (liveRecognition) {
      liveRecognition.stop();
    }

    setRecording(false, "Đã tự dừng sau 90 giây. Bác có thể bấm ghi lại nếu muốn nói thêm.");
  }, LIVE_VOICE_LIMIT_MS);
}


function clearVoiceTimeout() {
  // Clears the 90-second microphone timeout whenever recording ends manually.
  if (liveVoiceTimer) {
    clearTimeout(liveVoiceTimer);
    liveVoiceTimer = null;
  }
}


// ===== Live Transcript Update Section =====
function updateLiveTranscript(event) {
  let interimText = "";

  for (let index = event.resultIndex; index < event.results.length; index += 1) {
    const transcript = event.results[index][0].transcript.trim();

    if (event.results[index].isFinal) {
      liveVoiceFinalText = joinVoiceText(liveVoiceFinalText, transcript);
    } else {
      interimText = joinVoiceText(interimText, transcript);
    }
  }

  $("voiceText").value = joinVoiceText(
    liveVoiceBaseText,
    joinVoiceText(liveVoiceFinalText, interimText)
  );

  updateVoiceMeter();
}


// ===== Live Speech Error Section =====
function handleVoiceError(event) {
  if (event.error === "no-speech") {
    $("voiceStatus").textContent = "Cô đang nghe... bác cứ nói tiếp nhé.";
    return;
  }

  if (event.error === "not-allowed" || event.error === "service-not-allowed") {
    liveVoiceStopping = true;
    clearVoiceTimeout();
    setRecording(false, "Micro đang bị chặn. Bác hãy cho phép quyền micro rồi bấm ghi lại.");
    return;
  }

  $("voiceStatus").textContent = "Nhận diện giọng nói bị ngắt, bác bấm ghi lại nếu cần.";
}


// ===== Live Speech Restart Section =====
function restartLiveRecognitionIfNeeded() {
  if (liveVoiceStopping || $("recordBtn").dataset.on !== "1") return;

  try {
    liveRecognition.start();
  } catch {
    clearVoiceTimeout();
    setRecording(false, "Ghi giọng nói đã dừng. Bác bấm lại để tiếp tục.");
  }
}


// ===== Recording Button State Section =====
function setRecording(on, statusText = "") {
  const button = $("recordBtn");

  if (!on) {
    clearVoiceTimeout();
  }

  button.dataset.on = on ? "1" : "0";
  button.classList.toggle("recording", on);
  button.innerHTML =
    `<span class="record-icon"></span>` +
    (on ? "Đang nghe - bấm để dừng" : "Ghi giọng nói");

  if (statusText) {
    $("voiceStatus").textContent = statusText;
  }
}


// ===== Voice Text Utility Section =====
function joinVoiceText(first, second) {
  return [first, second]
    .map(part => String(part || "").trim())
    .filter(Boolean)
    .join(" ");
}


function updateVoiceMeter() {
  if (typeof updateCharacterMeter === "function") {
    updateCharacterMeter("voiceCharacterCount", countCharacters($("voiceText")?.value));
  }
}


function speechRecognitionClass() {
  return window.SpeechRecognition || window.webkitSpeechRecognition;
}
