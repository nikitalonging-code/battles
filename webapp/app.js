const tg = window.Telegram?.WebApp;
tg?.ready();
tg?.expand();

const API_BASE = "";

let state = {
  nav: "battles",
  tab: "active",
  battles: [],
  inventory: [],
  selectedItem: null,
  sheetMode: null,
  resultsChannel: "",
  bankUsername: "",
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

function escapeHtml(s) {
  return String(s)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function fmtTon(v) {
  return (v || 0).toFixed(2);
}

// ---------- Навигация ----------

const SCREEN_TITLES = {
  battles: "Битвы",
  slots: "Слоты",
  jackpot: "Джекпот",
  inventory: "Инвентарь",
  profile: "Профиль",
};

function switchNav(nav) {
  state.nav = nav;
  document.querySelectorAll(".nav-item").forEach((el) => {
    el.classList.toggle("active", el.dataset.nav === nav);
  });
  document.querySelectorAll(".screen").forEach((el) => {
    el.hidden = true;
  });
  const screenId = {
    battles: "screenBattles",
    slots: "screenSlots",
    jackpot: "screenJackpot",
    inventory: "screenInventory",
    profile: "screenProfile",
  }[nav];
  const screen = document.getElementById(screenId);
  if (screen) screen.hidden = false;
  document.getElementById("pageTitle").textContent = SCREEN_TITLES[nav] || "Битвы";
  if (nav === "inventory") loadInventory();
  if (nav === "battles") loadBattles();
}

document.querySelector(".bottom-nav").addEventListener("click", (e) => {
  const btn = e.target.closest(".nav-item");
  if (!btn) return;
  switchNav(btn.dataset.nav);
});

// ---------- Битвы ----------

function renderBattles() {
  const list = document.getElementById("battleList");
  const empty = document.getElementById("emptyState");
  list.innerHTML = "";
  if (state.battles.length === 0) {
    empty.hidden = false;
    return;
  }
  empty.hidden = true;
  for (const b of state.battles) list.appendChild(renderBattleCard(b));
}

function renderBattleCard(battle) {
  const card = document.createElement("div");
  card.className = "battle-card";
  const creator = battle.participants[0];
  const slots = battle.max_participants;

  const avatarsHtml = Array.from({ length: slots })
    .map((_, i) => {
      const p = battle.participants[i];
      if (p) {
        return `<div class="avatar">${p.avatar_url ? `<img src="${p.avatar_url}">` : "🧑"}</div>`;
      }
      return `<div class="avatar-slot">+</div>`;
    })
    .join("");

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
  if (btn.dataset.action === "join") openGiftSheet(id);
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
    state.resultsChannel = cfg.results_channel || "";
    state.bankUsername = (cfg.bank_username || "").replace(/^@/, "");
    updateDepositHint();
  } catch (e) {}
}

function updateDepositHint() {
  const hint = document.getElementById("depositHint");
  const btn = document.getElementById("bankLinkBtn");
  if (state.bankUsername) {
    hint.hidden = false;
    btn.textContent = "@" + state.bankUsername;
  } else {
    hint.hidden = true;
  }
}

document.getElementById("bankLinkBtn")?.addEventListener("click", () => {
  if (!state.bankUsername) return;
  const url = `https://t.me/${state.bankUsername}`;
  tg?.openTelegramLink ? tg.openTelegramLink(url) : window.open(url, "_blank");
});

// ---------- Инвентарь ----------

async function loadInventory() {
  try {
    state.inventory = await api("/api/inventory");
    renderInventory();
  } catch (e) {
    showToast(e.message);
  }
}

function renderInventory() {
  const list = document.getElementById("inventoryList");
  const empty = document.getElementById("inventoryEmpty");
  list.innerHTML = "";
  if (state.inventory.length === 0) {
    empty.hidden = false;
    return;
  }
  empty.hidden = true;
  for (const item of state.inventory) list.appendChild(renderInventoryCard(item));
}

function renderInventoryCard(item) {
  const card = document.createElement("div");
  card.className = "inventory-card";
  const valueText = item.value_ton != null ? `◆ ${fmtTon(item.value_ton)}` : "NFT";
  card.innerHTML = `
    <div class="inventory-thumb">
      ${item.thumb_url ? `<img src="${item.thumb_url}" alt="">` : "🎁"}
    </div>
    <div class="inventory-info">
      <div class="name">${escapeHtml(item.name || "Подарок")}</div>
      <div class="meta">${valueText}</div>
    </div>
    <button class="btn-withdraw" data-id="${item.id}">Вывести</button>
  `;
  card.querySelector(".btn-withdraw").addEventListener("click", (e) => {
    e.stopPropagation();
    withdrawItem(item.id, e.currentTarget);
  });
  return card;
}

async function withdrawItem(itemId, btn) {
  if (btn.disabled) return;
  btn.disabled = true;
  btn.textContent = "…";
  try {
    await api(`/api/inventory/${itemId}/withdraw`, { method: "POST" });
    showToast("Подарок отправлен на ваш аккаунт");
    await loadInventory();
  } catch (e) {
    showToast(e.message);
    btn.disabled = false;
    btn.textContent = "Вывести";
  }
}

// ---------- Sheet: выбор из ИНВЕНТАРЯ для стейка ----------

const overlay = document.getElementById("giftSheetOverlay");
const giftGrid = document.getElementById("giftGrid");
const sheetEmpty = document.getElementById("sheetEmpty");
const confirmBtn = document.getElementById("confirmGiftBtn");

async function openGiftSheet(mode) {
  state.sheetMode = mode;
  state.selectedItem = null;
  confirmBtn.disabled = true;
  document.getElementById("sheetTitle").textContent =
    mode === "create" ? "Выберите подарок из инвентаря" : "Выберите подарок, чтобы вступить";

  overlay.hidden = false;
  giftGrid.innerHTML = "";
  sheetEmpty.hidden = true;

  try {
    state.inventory = await api("/api/inventory");
  } catch (e) {
    overlay.hidden = true;
    showToast(e.message);
    return;
  }

  if (state.inventory.length === 0) {
    sheetEmpty.hidden = false;
    const bank = state.bankUsername ? `@${state.bankUsername}` : "аккаунт-банк";
    sheetEmpty.innerHTML = `
      <p>Инвентарь пуст</p>
      <span>Отправьте NFT-подарок на ${bank}</span>
    `;
    return;
  }

  for (const item of state.inventory) {
    const card = document.createElement("div");
    card.className = "gift-card";
    card.dataset.id = item.id;
    card.innerHTML = `
      ${item.thumb_url ? `<img src="${item.thumb_url}">` : ""}
      <div class="gift-card-label">${escapeHtml(item.name || "Подарок")}</div>
    `;
    card.addEventListener("click", () => {
      document.querySelectorAll(".gift-card").forEach((c) => c.classList.remove("selected"));
      card.classList.add("selected");
      state.selectedItem = item;
      confirmBtn.disabled = false;
    });
    giftGrid.appendChild(card);
  }
}

document.getElementById("sheetClose").addEventListener("click", () => (overlay.hidden = true));
document.getElementById("createBattleBtn").addEventListener("click", () => openGiftSheet("create"));

confirmBtn.addEventListener("click", async () => {
  if (!state.selectedItem) return;
  confirmBtn.disabled = true;
  confirmBtn.textContent = "Подождите...";
  try {
    if (state.sheetMode === "create") {
      await api("/api/battles", {
        method: "POST",
        body: JSON.stringify({
          inventory_item_id: state.selectedItem.id,
          max_participants: 3,
        }),
      });
      showToast("Битва создана!");
    } else {
      await api(`/api/battles/${state.sheetMode}/join`, {
        method: "POST",
        body: JSON.stringify({ inventory_item_id: state.selectedItem.id }),
      });
      showToast("Вы вступили в битву!");
    }
    overlay.hidden = true;
    loadBattles();
    if (state.nav === "inventory") loadInventory();
  } catch (e) {
    showToast(e.message);
  } finally {
    confirmBtn.disabled = false;
    confirmBtn.textContent = "Выбрать";
  }
});

(async function init() {
  await loadConfig();
  await loadBattles();
})();
