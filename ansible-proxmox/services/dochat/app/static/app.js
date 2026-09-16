document.addEventListener("DOMContentLoaded", () => {
  const chatMessages = document.getElementById("chatMessages");
  const chatForm = document.getElementById("chatForm");
  const queryInput = document.getElementById("queryInput");
  const sendBtn = document.getElementById("sendBtn");
  const syncBtn = document.getElementById("syncBtn");
  const syncBtnText = document.getElementById("syncBtnText");
  const statsText = document.getElementById("statsText");
  const chips = document.querySelectorAll(".chip");

  // Auto-resize textarea
  queryInput.addEventListener("input", () => {
    queryInput.style.height = "auto";
    queryInput.style.height = Math.min(queryInput.scrollHeight, 140) + "px";
  });

  // Enter to send (Shift+Enter for newline)
  queryInput.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      if (queryInput.value.trim()) {
        chatForm.dispatchEvent(new Event("submit"));
      }
    }
  });

  // Suggestion chips
  chips.forEach((chip) => {
    chip.addEventListener("click", () => {
      const query = chip.getAttribute("data-query");
      if (query) {
        queryInput.value = query;
        chatForm.dispatchEvent(new Event("submit"));
      }
    });
  });

  // Simple Markdown-like formatter for responses
  function formatContent(text) {
    if (!text) return "";
    let formatted = text
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;");

    // Bold **text**
    formatted = formatted.replace(/\*\*(.*?)\*\*/g, "<strong>$1</strong>");
    // Dividers ---
    formatted = formatted.replace(/^---$/gm, '<hr class="divider">');
    // Bullet lists
    formatted = formatted.replace(/^[•\-\*]\s+(.*)$/gm, "<li>• $1</li>");
    formatted = formatted.replace(/(<li>.*<\/li>)/s, '<ul class="clean-list">$1</ul>');
    // Linebreaks
    formatted = formatted.replace(/\n\n/g, "</p><p>");
    formatted = formatted.replace(/\n/g, "<br>");

    return `<p>${formatted}</p>`;
  }

  function appendMessage(role, content, extra = {}) {
    const msgDiv = document.createElement("div");
    msgDiv.className = `message ${role}`;

    const avatar = document.createElement("div");
    avatar.className = "avatar";
    avatar.textContent = role === "user" ? "👤" : "🤖";

    const contentDiv = document.createElement("div");
    contentDiv.className = "message-content";

    if (role === "user") {
      const p = document.createElement("p");
      p.textContent = content;
      contentDiv.appendChild(p);
    } else {
      contentDiv.innerHTML = formatContent(content);

      if (extra.tokens_saved) {
        const badge = document.createElement("div");
        badge.className = "token-savings-badge";
        badge.innerHTML = `⚡ ${extra.tokens_saved}`;
        contentDiv.appendChild(badge);
      }
    }

    msgDiv.appendChild(avatar);
    msgDiv.appendChild(contentDiv);
    chatMessages.appendChild(msgDiv);
    chatMessages.scrollTop = chatMessages.scrollHeight;

    return msgDiv;
  }

  function showTypingIndicator() {
    const msgDiv = document.createElement("div");
    msgDiv.className = "message assistant typing-msg";
    msgDiv.id = "typingIndicator";

    const avatar = document.createElement("div");
    avatar.className = "avatar";
    avatar.textContent = "🤖";

    const contentDiv = document.createElement("div");
    contentDiv.className = "message-content";
    contentDiv.innerHTML = '<div class="typing-dots"><span></span><span></span><span></span></div>';

    msgDiv.appendChild(avatar);
    msgDiv.appendChild(contentDiv);
    chatMessages.appendChild(msgDiv);
    chatMessages.scrollTop = chatMessages.scrollHeight;
  }

  function removeTypingIndicator() {
    const indicator = document.getElementById("typingIndicator");
    if (indicator) indicator.remove();
  }

  // Load stats
  async function loadStats() {
    try {
      const res = await fetch("/api/stats");
      if (res.ok) {
        const data = await res.json();
        const total = data.total_indexed || 0;
        const banks = (data.correspondents || []).join(", ") || "Estados de cuenta";
        statsText.textContent = `${total} docs indexados (${banks})`;
      }
    } catch (e) {
      console.warn("Could not load stats", e);
    }
  }

  // Handle Form Submit
  chatForm.addEventListener("submit", async (e) => {
    e.preventDefault();
    const query = queryInput.value.trim();
    if (!query) return;

    appendMessage("user", query);
    queryInput.value = "";
    queryInput.style.height = "auto";
    sendBtn.disabled = true;

    showTypingIndicator();

    try {
      const response = await fetch("/api/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ query }),
      });

      removeTypingIndicator();

      if (!response.ok) {
        const err = await response.json().catch(() => ({}));
        appendMessage("assistant", `⚠️ Ocurrió un error al procesar la consulta: ${err.detail || response.statusText}`);
      } else {
        const data = await response.json();
        appendMessage("assistant", data.response, data);
        loadStats();
      }
    } catch (err) {
      removeTypingIndicator();
      appendMessage("assistant", `⚠️ Error de red o conexión: ${err.message}`);
    } finally {
      sendBtn.disabled = false;
      queryInput.focus();
    }
  });

  // Handle Sync
  syncBtn.addEventListener("click", async () => {
    syncBtn.classList.add("spinning");
    syncBtn.disabled = true;
    syncBtnText.textContent = "Sincronizando...";

    try {
      const res = await fetch("/api/sync", { method: "POST" });
      if (res.ok) {
        const data = await res.json();
        syncBtnText.textContent = `¡Listo! (+${data.newly_indexed})`;
        setTimeout(() => {
          syncBtnText.textContent = "Sincronizar";
        }, 3000);
        await loadStats();
      } else {
        syncBtnText.textContent = "Error";
      }
    } catch (err) {
      syncBtnText.textContent = "Error";
    } finally {
      syncBtn.classList.remove("spinning");
      syncBtn.disabled = false;
    }
  });

  // Initial load
  loadStats();
});
