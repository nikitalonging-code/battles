const tg = window.Telegram?.WebApp;
tg?.ready();
tg?.expand();

const API_BASE = ""; // мини-апп и API отдаются с одного домена

let state = {
  tab: "active",
  battles: [],
  gifts: [],
  selectedGift: null,
  sheetMode: null, // "create" | battleId для join
  resultsChannel: "",
};

function authHeaders() {
  return {
    "Content-Type": "application/json",
    Authorization: "tma " + (tg?.initData || ""),
  };
}

async function api(path, options = {}) {
  const res = await fetch(API_BASE + path, {
    ...options,
    headers: { ...authHeaders(), ...(options.headers || {}) },
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: "Ошибка сервера" }));
    throw new Error(err.detail || "Ошибка сервера");
  }
  return res.json();
}

function showToast(text) {
  const el = document.getElementById("toast");
  el.textContent = text;
  el.hidden = false;
  setTimeout(() => (el.hidden = true), 2800);
}

// ---------- Рендер списка битв ----------

function fmtTon(v) {
  return (v || 0).toFixed(2);
}

function renderBattles() {
  const list = document.getElementById("battleList");
  const empty = document.getElementById("emptyState");
  list.innerHTML = "";

  if (state.battles.length === 0) {
    empty.hidden = false;
    return;
  }
  empty.hidden = true;

  for (const b of state.battles) {
    list.appendChild(renderBattleCard(b));
  }
}

function renderBattleCard(battle) {
  const card = document.createElement("div");
  card.className = "battle-card";

  const creator = battle.participants[0];
  const slots = battle.max_participants;

  // avatars row
  const avatarsHtml = Array.from({ length: slots })
    .map((_, i) => {
      const p = battle.participants[i];
      if (p) {
        return `<div class="avatar">${p.avatar_url ? `<img src="${p.avatar_url}">` : "🧑"}</div>`;
      }
      return `<div class="avatar-slot">+</div>`;
    })
    .join("");

  // gift slots row
  const giftsHtml = Array.from({ length: slots })
    .map((_, i) => {
      const p = battle.participants[i];
      if (p) {
        const winnerClass = p.is_winner ? "winner" : "";
        const dice = p.dice_value ? `<div class="dice-result">🎲 ${p.dice_value}</div>` : "";
        return `<div class="gift-slot ${winnerClass}">
          ${p.gift_thumb_url ? `<img src="${p.gift_thumb_url}">` : ""}
          <div class="gift-owner">${p.avatar_url ? `<img src="${p.avatar_url}">` : ""}</div>
          ${dice}
        </div>`;
      }
      return `<div class="gift-slot empty"></div>`;
    })
    .join("");

  const statusBadge =
    battle.status === "finished"
      ? `<span class="status-badge finished">Завершена</span>`
      : battle.status === "resolving"
      ? `<span class="status-badge resolving">Розыгрыш...</span>`
      : "";

  const canJoin = battle.status === "open" && battle.participants.length < battle.max_participants;

  card.innerHTML = `
    <div class="battle-card-top">
      <div class="battle-price">
        <span class="amount">◆ ${fmtTon(battle.total_value_ton)}</span>
        <span class="creator">${creator?.username ? "@" + creator.username : "игрок"}</span>
      </div>
      ${statusBadge || `<div class="avatars">${avatarsHtml}</div>`}
    </div>
    <div class="gift-row">${giftsHtml}</div>
    <div class="battle-card-bottom">
      <button class="btn-join" ${canJoin ? "" : "disabled"} data-action="join" data-id="${battle.id}">
        ${canJoin ? "Вступить" : battle.status === "finished" ? "Битва завершена" : "Мест нет"}
      </button>
      <div class="price-pill">◆ ${fmtTon(battle.total_value_ton)}</div>
      <button class="btn-check" data-action="check" data-id="${battle.id}" data-msg="${battle.channel_message_id || ""}">›</button>
    </div>
  `;
  return card;
}

// ---------- Табы ----------

document.getElementById("tabs").addEventListener("click", (e) => {
  const btn = e.target.closest(".tab");
  if (!btn) return;
  document.querySelectorAll(".tab").forEach((t) => t.classList.remove("active"));
  btn.classList.add("active");
  state.tab = btn.dataset.tab;
  loadBattles();
});

document.getElementById("battleList").addEventListener("click", (e) => {
  const btn = e.target.closest("button[data-action]");
  if (!btn) return;
  const id = Number(btn.dataset.id);

  if (btn.dataset.action === "join") {
    openGiftSheet(id);
  }
  if (btn.dataset.action === "check") {
    const msgId = btn.dataset.msg;
    if (!msgId) {
      showToast("Битва ещё не разыграна");
      return;
    }
    const url = `https://t.me/${state.resultsChannel}/${msgId}`;
    tg?.openTelegramLink ? tg.openTelegramLink(url) : window.open(url, "_blank");
  }
});

// ---------- Загрузка данных ----------

async function loadBattles() {
  try {
    state.battles = await api(`/api/battles?tab=${state.tab}`);
    renderBattles();
  } catch (e) {
    showToast(e.message);
  }
}

async function loadConfig() {
  try {
    const cfg = await api("/api/config");
    state.resultsChannel = cfg.results_channel;
  } catch (e) {
    /* не критично для рендера */
  }
}

// ---------- Sheet выбора подарка ----------

const overlay = document.getElementById("giftSheetOverlay");
const giftGrid = document.getElementById("giftGrid");
const sheetEmpty = document.getElementById("sheetEmpty");
const confirmBtn = document.getElementById("confirmGiftBtn");

async function openGiftSheet(mode) {
  state.sheetMode = mode; // "create" или id битвы
  state.selectedGift = null;
  confirmBtn.disabled = true;
  document.getElementById("sheetTitle").textContent =
    mode === "create" ? "Выберите подарок для ставки" : "Выберите подарок, чтобы вступить";

  overlay.hidden = false;
  giftGrid.innerHTML = "";
  sheetEmpty.hidden = true;

  try {
    state.gifts = await api("/api/gifts");
  } catch (e) {
    overlay.hidden = true;
    showToast(e.message);
    return;
  }

  if (state.gifts.length === 0) {
    sheetEmpty.hidden = false;
    return;
  }

  for (const g of state.gifts) {
    const card = document.createElement("div");
    card.className = "gift-card";
    card.dataset.id = g.owned_gift_id;
    card.innerHTML = `
      ${g.thumb_url ? `<img src="${g.thumb_url}">` : ""}
      <div class="gift-card-label">${g.name}</div>
    `;
    card.addEventListener("click", () => {
      document.querySelectorAll(".gift-card").forEach((c) => c.classList.remove("selected"));
      card.classList.add("selected");
      state.selectedGift = g;
      confirmBtn.disabled = false;
    });
    giftGrid.appendChild(card);
  }
}

document.getElementById("sheetClose").addEventListener("click", () => (overlay.hidden = true));
document.getElementById("createBattleBtn").addEventListener("click", () => openGiftSheet("create"));

confirmBtn.addEventListener("click", async () => {
  if (!state.selectedGift) return;
  confirmBtn.disabled = true;
  confirmBtn.textContent = "Подождите...";
  try {
    if (state.sheetMode === "create") {
      await api("/api/battles", {
        method: "POST",
        body: JSON.stringify({ gift: state.selectedGift, max_participants: 3 }),
      });
      showToast("Битва создана!");
    } else {
      await api(`/api/battles/${state.sheetMode}/join`, {
        method: "POST",
        body: JSON.stringify({ gift: state.selectedGift }),
      });
      showToast("Вы вступили в битву!");
    }
    overlay.hidden = true;
    loadBattles();
  } catch (e) {
    showToast(e.message);
  } finally {
    confirmBtn.disabled = false;
    confirmBtn.textContent = "Выбрать";
  }
});

// ---------- Init ----------

(async function init() {
  await loadConfig();
  await loadBattles();
})();
