/* =========================================================
   voice.js
   Browser Web Speech API voice recording.
   ========================================================= */

// ===== Voice Setup Section =====
function setupVoice() {
  const Speech = window.SpeechRecognition || window.webkitSpeechRecognition;

  if (!Speech) {
    $("voiceStatus").textContent = "Trình duyệt chưa hỗ trợ Web Speech.";
    return;
  }

  const speech = new Speech();

  speech.lang = "vi-VN";
  speech.continuous = true;
  speech.interimResults = true;

  let finalText = "";

  speech.onresult = event => {
    let temporaryText = "";

    for (let index = event.resultIndex; index < event.results.length; index++) {
      if (event.results[index].isFinal) {
        finalText += event.results[index][0].transcript + " ";
      } else {
        temporaryText += event.results[index][0].transcript;
      }
    }

    $("voiceText").value = (finalText + temporaryText).trim();
  };

  speech.onstart = () => setRecording(true);
  speech.onend = () => setRecording(false);

  $("recordBtn").onclick = () => {
    if ($("recordBtn").dataset.on === "1") {
      speech.stop();
      return;
    }

    finalText = $("voiceText").value + " ";
    speech.start();
  };
}


// ===== Recording State Section =====
function setRecording(on) {
  $("recordBtn").dataset.on = on ? "1" : "0";
  $("recordBtn").classList.toggle("recording", on);

  $("recordBtn").innerHTML =
    `<span class="record-icon"></span>` +
    (on ? "ĐANG GHI ÂM - BẤM ĐỂ DỪNG" : "Bắt đầu ghi giọng nói");

  $("voiceStatus").textContent = on ? "Đang ghi âm..." : "Đã dừng ghi.";
}
