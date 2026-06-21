# ScamCheck Code Walkthrough

This file explains the app flow with current line references. These references are intentionally kept here instead of repeated every three lines in the source files, because source comments with exact line numbers become wrong as soon as code is edited.

## Main Page And Script Order

- `templates/index.html:412` contains the main text input with id `message`.
- `templates/index.html:437` contains `resultBox`, where analysis HTML is inserted by `static/analyze.js:118`.
- `templates/index.html:491` contains the practice button `trainNext`, wired by `static/extras.js:415`.
- `templates/index.html:506` contains the floating `chatToggle`, wired by `static/chat.js:10`.
- `templates/index.html:547-554` loads JavaScript in dependency order. `static/app.js:33` starts the app last, after helper functions are available.

## Frontend Startup

- `static/app.js:7-29` stores shared state: mode, selected image, current result, chat state, history, library data, and training progress.
- `static/app.js:33` runs `startApp()`. It calls setup functions from the other JS files: navigation, tabs, history collapse, sample buttons, main buttons, chat, paste upload, practice, and voice.
- `static/app.js:51` defines `setupExclusiveDetails()`. It listens for opened `<details>` items and closes the previous one, used for FAQ and library accordions.

## Analyze Flow

- `static/analyze.js:18` defines `setupMainButtons()`. It connects the analyze button to `static/analyze.js:85`.
- `static/analyze.js:63` defines `getInputBody()`. It returns `{ message, image }` to `static/analyze.js:85`, which then sends that body to the backend.
- `static/analyze.js:85` defines `analyze()`. It calls `post("/api/analyze", body)` from `static/helpers.js:25`.
- `app.py:782` registers `/api/analyze`, and `app.py:783` handles the request in `analyze()`.
- `app.py:783` calls `read_body()` at `app.py:371`, checks length with `prompt_is_too_long()` at `app.py:384`, builds the AI prompt with `analysis_prompt()` at `app.py:536`, and sends it through `ask_gemini()` at `app.py:493`.
- `app.py:783` passes Gemini output into `clean_result()` at `app.py:631`, optionally adds the psychology card with `add_psychology_if_needed()` at `app.py:664`, then renders final HTML with `result_html()` at `app.py:303`.
- The backend response returns to `static/analyze.js:85`, where it is normalized by `normalizeResult()` at `static/helpers.js:89`, saved to history by `saveHistory()` at `static/history.js:10`, and displayed by `showResult()` at `static/analyze.js:118`.
- `static/analyze.js:118` inserts `currentResult.html` into `resultBox`, appends the copy/share/download tools from `static/extras.js:7`, and calls `polishResultLayout()` at `static/analyze.js:163`.

## Backend AI Helpers

- `app.py:94` loads `.env` values so Gemini keys can come from the environment.
- `app.py:109` returns available Gemini API keys. `ask_gemini()` at `app.py:493` rotates through these keys when calling Gemini.
- `app.py:120` returns model names to try.
- `app.py:493` calls the Gemini REST API with text and optional image content. It returns parsed AI data to callers such as `analyze()` at `app.py:783`, `chat()` at `app.py:805`, and `rescue()` at `app.py:844`.
- `app.py:480` parses AI JSON from a plain response string. `ask_gemini()` uses it before returning data to route handlers.
- `app.py:631` cleans the analysis result. It returns a normalized result object back to `analyze()` at `app.py:783`.
- `app.py:303` converts a result object into the HTML string consumed by `static/analyze.js:118`.

## Evidence And Highlight Flow

- `app.py:218` highlights only risky pieces of the original text, such as payment pressure, suspicious links, OTP requests, identity documents, and urgency.
- `app.py:269` expands each evidence explanation so detected signs are more detailed.
- `app.py:631` applies `detailed_evidence_why()` from `app.py:269` to each detected sign, then returns those signs to `result_html()` at `app.py:303`.
- `static/analyze.js:163` moves the original prompt into a smaller quote under the score/result heading.

## Psychology Card Flow

- `app.py:664` decides whether the "Co tam ly" support card should appear. It only runs for risky or suspicious results and avoids breaking the page if Gemini fails.
- `app.py:607` builds the short warm psychology prompt.
- `app.py:303` places the support card in the result HTML.
- `static/analyze.js:118` moves that card into the next-step box so it appears beside the checklist on wide screens and below it on small screens.

## Chat Flow

- `templates/index.html:506` creates the `chatToggle` button.
- `static/chat.js:10` wires chat setup. It calls `setupChatToggleDrag()` at `static/chat.js:31`, connects close/send/file controls, and handles Enter-to-send.
- `static/chat.js:31` makes the AI button movable. It calls `placeChatToggle()` at `static/chat.js:94`, `saveChatTogglePosition()` at `static/chat.js:110`, and `keepChatToggleOnScreen()` at `static/chat.js:132`.
- `static/chat.js:143` opens or closes the drawer and updates the button label.
- `static/chat.js:172` sends the user question, current result, history, and optional file/image to `post("/api/chat", ...)` from `static/helpers.js:25`.
- `app.py:804` registers `/api/chat`, and `app.py:805` handles chat requests.
- `app.py:805` builds a prompt with `chat_prompt()` at `app.py:705`, calls `ask_gemini()` at `app.py:493`, and returns an answer plus next steps to `static/chat.js:172`.
- `static/chat.js:222` renders user and AI messages into the chat log.

## History Flow

- `static/history.js:46` loads recent results from localStorage into the global `history` value used by `static/app.js:20`.
- `static/history.js:10` saves the latest history after `static/analyze.js:85` receives a new result.
- `static/history.js:70` draws the full history page.
- `static/history.js:105` draws the compact sidebar history.
- `static/history.js:17` wires the sidebar history header in `templates/index.html:370` so the user can hide or show prior history.
- `app.py:891` registers `/api/history-view`, and `app.py:892` rebuilds saved result HTML when an old compact result is opened.

## Library And Practice Flow

- `static/extras.js:351` loads library, training, and hotline data from `/api/library`, `/api/training`, and `/api/hotlines`.
- `app.py:828` returns `SCAM_LIBRARY` to the library UI.
- `static/extras.js:365` renders library items and calls `setupExclusiveDetails()` at `static/app.js:51` so opening one question closes the previous question.
- `app.py:833` returns `TRAINING_MESSAGES` to the practice UI.
- `static/extras.js:415` connects the practice next button from `templates/index.html:491` to `handleTrainingNext()` at `static/extras.js:494`.
- `static/extras.js:494` skips forward when the user has not answered yet, and advances normally after an answer.
- `static/extras.js:504` performs the skip by incrementing `trainingIndex` and calling `drawTraining()` at `static/extras.js:423`.
- `static/extras.js:453` grades a selected practice answer and returns control to the next/finish button state.

## Share And Download Tools

- `static/extras.js:7` returns the result action toolbar HTML.
- `static/extras.js:68` connects toolbar buttons to copy, share, and download handlers.
- `static/extras.js:147` builds plain text from the current result.
- `static/extras.js:158` copies result text to the clipboard.
- `static/extras.js:169` uses native share when available, otherwise falls back to copy.
- `static/extras.js:325` downloads the visual result card generated by `drawShareCard()` at `static/extras.js:191`.

## Navigation, Helpers, And Voice

- `static/navigation.js:7` switches visible screens.
- `static/navigation.js:21` switches input mode between image, link, text, and voice.
- `static/navigation.js:37` toggles busy state while analysis is running.
- `static/navigation.js:48` displays user-facing errors.
- `static/helpers.js:7` is the short DOM lookup helper used across JS files.
- `static/helpers.js:13` escapes user-facing text before inserting it into HTML.
- `static/helpers.js:25` posts JSON to Flask and returns parsed JSON to the caller.
- `static/helpers.js:76` converts uploaded files into data URLs for Gemini.
- `static/helpers.js:89` normalizes backend results so old saved results and new AI results share the same shape.
- `static/voice.js:7` wires browser speech recognition into the voice text input.

## Notes For Future Comments

- Add inline comments when code makes a non-obvious decision, such as rotating Gemini keys, moving DOM elements after render, or preserving draggable button position.
- Avoid comments that repeat the exact JavaScript or Python statement, such as "set variable" or "return value"; those become clutter quickly.
- If a function starts calling a new file, update this walkthrough with the caller line and callee line.
