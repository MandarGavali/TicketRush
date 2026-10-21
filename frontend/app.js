/* TicketRush UI: a small single-page app on top of the REST API.
 *
 * - Hash routing: #/  #/event/2  #/checkout/7  #/trips  #/host
 * - All text from the API is inserted with textContent (via h()), never innerHTML: safe against XSS.
 * - The API decides availability; the UI only shows it (a 409 simply refreshes the seat map).
 */
"use strict";

const API = "/api/v1";
const TOKEN_KEY = "ticketrush_token";
const MAX_SEATS = 6;
const SEAT_POLL_MS = 5000;

const state = {
  token: localStorage.getItem(TOKEN_KEY),
  user: null,
  filters: { city: "", q: "", from_date: "", sort: "starts_at" },
  timers: [], // intervals of the current page, cleared on navigation
  afterLogin: null, // action to resume after the login modal
  authMode: "login",
};

// ---------------------------------------------------------------- helpers

/** Tiny DOM builder. Strings become text nodes, so API data can never inject HTML. */
function h(tag, attrs = {}, ...children) {
  const el = document.createElement(tag);
  for (const [key, value] of Object.entries(attrs || {})) {
    if (value === false || value === null || value === undefined) continue;
    if (key === "class") el.className = value;
    else if (key.startsWith("on")) el.addEventListener(key.slice(2), value);
    else if (key === "style") el.style.cssText = value;
    else el.setAttribute(key, value === true ? "" : value);
  }
  for (const child of children.flat()) {
    if (child === null || child === undefined || child === false) continue;
    el.append(child instanceof Node ? child : document.createTextNode(String(child)));
  }
  return el;
}

const $ = (selector) => document.querySelector(selector);

const rupees = (paise) =>
  new Intl.NumberFormat("en-IN", {
    style: "currency",
    currency: "INR",
    maximumFractionDigits: paise % 100 ? 2 : 0,
  }).format(paise / 100);

const formatDate = (iso) =>
  new Date(iso).toLocaleString("en-IN", {
    weekday: "short",
    day: "numeric",
    month: "short",
    year: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });

const shortDate = (iso) =>
  new Date(iso).toLocaleDateString("en-IN", { day: "numeric", month: "short", year: "numeric" });

const newKey = () =>
  crypto.randomUUID ? crypto.randomUUID() : `${Date.now()}-${Math.random().toString(16).slice(2)}`;

function toast(message, kind = "") {
  const el = h("div", { class: `toast ${kind}` }, message);
  const box = $("#toasts");
  box.append(el);
  while (box.children.length > 3) box.firstElementChild.remove();
  setTimeout(() => el.remove(), 4200);
}

function clearTimers() {
  state.timers.forEach(clearInterval);
  state.timers = [];
}

/** Picture for an event: a gradient + emoji chosen from the title (no external images needed). */
const GRADIENTS = [
  ["#ff7e5f", "#feb47b"],
  ["#ff385c", "#bd1e59"],
  ["#6a11cb", "#2575fc"],
  ["#11998e", "#38ef7d"],
  ["#fc5c7d", "#6a82fb"],
  ["#f7971e", "#ffd200"],
  ["#00c6ff", "#0072ff"],
  ["#834d9b", "#d04ed6"],
];
const EMOJIS = [
  [/comedy|stand.?up|laugh/i, "🎤"],
  [/theatre|theater|play\b|drama|shakespeare/i, "🎭"],
  [/cricket|match|ipl|football|sport/i, "🏏"],
  [/dance|garba|ballet/i, "💃"],
  [/music|live|concert|band|rock|jazz|folk|electronic|edm|dj|tour/i, "🎸"],
  [/food|festival|fest|fair/i, "🎪"],
];

function art(eventId, text, cls = "card-image") {
  const [from, to] = GRADIENTS[eventId % GRADIENTS.length];
  const emoji = (EMOJIS.find(([re]) => re.test(text)) || [null, "🎟️"])[1];
  return h(
    "div",
    { class: cls, style: `background: linear-gradient(135deg, ${from}, ${to})` },
    h("span", { class: "card-emoji", "aria-hidden": "true" }, emoji),
  );
}

// ---------------------------------------------------------------- API client

class ApiError extends Error {
  constructor(status, code, message) {
    super(message);
    this.status = status;
    this.code = code;
  }
}

async function api(path, { method = "GET", body, headers = {} } = {}) {
  const options = { method, headers: { ...headers } };
  if (body !== undefined) {
    options.headers["Content-Type"] = "application/json";
    options.body = JSON.stringify(body);
  }
  if (state.token) options.headers.Authorization = `Bearer ${state.token}`;

  let response;
  try {
    response = await fetch(API + path, options);
  } catch {
    throw new ApiError(0, "NETWORK", "Cannot reach the server. Is the API running?");
  }
  const data = await response.json().catch(() => null);
  if (response.ok) return data;

  const error = data?.error || {};
  if (response.status === 401 && state.token && !path.startsWith("/auth/")) {
    setSession(null, null); // token expired or invalid
  }
  throw new ApiError(response.status, error.code || "ERROR", error.message || response.statusText);
}

// ---------------------------------------------------------------- session + header

function setSession(token, user) {
  state.token = token;
  state.user = user;
  if (token) localStorage.setItem(TOKEN_KEY, token);
  else localStorage.removeItem(TOKEN_KEY);
  renderHeader();
}

async function loadUser() {
  if (!state.token) return renderHeader();
  try {
    state.user = await api("/users/me");
  } catch {
    setSession(null, null);
  }
  renderHeader();
}

const isAdmin = () => state.user?.role === "ADMIN";

function renderHeader() {
  const avatar = $("#avatar");
  avatar.textContent = state.user ? state.user.full_name.trim().charAt(0).toUpperCase() : "";
  avatar.classList.toggle("signed-in", Boolean(state.user));
  if (!state.user) avatar.append(personIcon());
  $("#host-link").classList.toggle("hidden", !isAdmin());

  const panel = $("#menu-panel");
  panel.replaceChildren();
  const go = (hash) => () => {
    closeMenu();
    location.hash = hash;
  };
  if (state.user) {
    panel.append(
      h("div", { class: "menu-who" }, `Signed in as ${state.user.email}`),
      h("button", { class: "strong", onclick: go("#/trips") }, "Trips"),
      isAdmin() && h("button", { class: "strong", onclick: go("#/host") }, "Host an event"),
      h("hr"),
      h("a", { href: "/docs", target: "_blank", rel: "noopener" }, "API docs"),
      h("button", { onclick: logout }, "Log out"),
    );
  } else {
    panel.append(
      h("button", { class: "strong", onclick: () => openAuth("signup") }, "Sign up"),
      h("button", { onclick: () => openAuth("login") }, "Log in"),
      h("hr"),
      h("a", { href: "/docs", target: "_blank", rel: "noopener" }, "API docs"),
    );
  }
}

function personIcon() {
  const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  svg.setAttribute("viewBox", "0 0 32 32");
  svg.setAttribute("width", "30");
  svg.setAttribute("height", "30");
  svg.innerHTML =
    '<path fill="#fff" d="M16 .7C7.56.7.7 7.56.7 16S7.56 31.3 16 31.3 31.3 24.44 31.3 16 24.44.7 16 .7zm0 28c-4.02 0-7.6-1.88-9.93-4.81a12.43 12.43 0 0 1 6.45-4.4A6.5 6.5 0 0 1 9.5 14a6.5 6.5 0 0 1 13 0 6.51 6.51 0 0 1-3.02 5.5 12.42 12.42 0 0 1 6.45 4.4A12.67 12.67 0 0 1 16 28.7z"/>';
  return svg;
}

function logout() {
  closeMenu();
  setSession(null, null);
  toast("You are logged out");
  location.hash = "#/";
}

function openMenu() {
  $("#menu-panel").classList.remove("hidden");
  $("#menu-button").setAttribute("aria-expanded", "true");
}
function closeMenu() {
  $("#menu-panel").classList.add("hidden");
  $("#menu-button").setAttribute("aria-expanded", "false");
}

// ---------------------------------------------------------------- auth modal

function requireLogin(action) {
  if (state.token) return action();
  state.afterLogin = action;
  openAuth("login");
}

function openAuth(mode) {
  closeMenu();
  state.authMode = mode;
  const signup = mode === "signup";
  $("#modal-title").textContent = signup ? "Sign up" : "Log in";
  $("#auth-heading").textContent = signup ? "Create your TicketRush account" : "Welcome back";
  $("#name-field").classList.toggle("hidden", !signup);
  $("#auth-form").full_name.required = signup;
  $("#auth-hint").textContent = signup
    ? "Passwords need at least 8 characters."
    : "Demo admin: admin@ticketrush.dev / admin12345";
  $("#switch-text").textContent = signup ? "Already have an account?" : "New here?";
  $("#auth-switch").textContent = signup ? "Log in" : "Create an account";
  $("#modal").classList.remove("hidden");
  $("#auth-form").email.focus();
}

function closeAuth() {
  $("#modal").classList.add("hidden");
  $("#auth-form").reset();
}

async function submitAuth(event) {
  event.preventDefault();
  const form = event.target;
  const email = form.email.value.trim();
  const password = form.password.value;
  const button = $("#auth-submit");
  button.disabled = true;
  try {
    if (state.authMode === "signup") {
      await api("/auth/register", {
        method: "POST",
        body: { email, password, full_name: form.full_name.value.trim() },
      });
    }
    const { access_token } = await api("/auth/login", { method: "POST", body: { email, password } });
    state.token = access_token;
    setSession(access_token, await api("/users/me"));
    closeAuth();
    toast(`Welcome, ${state.user.full_name}!`, "success");
    const next = state.afterLogin;
    state.afterLogin = null;
    if (next) next();
    else render();
  } catch (error) {
    toast(error.message, "error");
  } finally {
    button.disabled = false;
  }
}

// ---------------------------------------------------------------- router

const routes = [
  [/^#?\/?$/, renderHome],
  [/^#\/event\/(\d+)$/, renderEvent],
  [/^#\/checkout\/(\d+)$/, renderCheckout],
  [/^#\/trips$/, renderTrips],
  [/^#\/host$/, renderHost],
];

async function render() {
  clearTimers();
  closeMenu();
  const view = $("#view");
  const hash = location.hash || "#/";
  for (const [pattern, page] of routes) {
    const match = hash.match(pattern);
    if (match) {
      try {
        await page(view, ...match.slice(1).map(Number));
      } catch (error) {
        view.replaceChildren(emptyState("Something went wrong", error.message));
      }
      window.scrollTo(0, 0);
      return;
    }
  }
  view.replaceChildren(emptyState("Page not found", "That page does not exist."));
}

function emptyState(title, text, action) {
  return h("div", { class: "empty" }, h("h2", {}, title), h("p", {}, text), action || null);
}

// ---------------------------------------------------------------- home

const SORTS = [
  ["starts_at", "Soonest"],
  ["-starts_at", "Latest"],
  ["price", "Price: low to high"],
  ["-price", "Price: high to low"],
];

async function renderHome(view) {
  const grid = h("div", { class: "grid" });
  const count = h("span", { class: "result-count" });
  const more = h("div", { class: "show-more" });
  const chips = h(
    "div",
    { class: "chips" },
    SORTS.map(([value, label]) =>
      h(
        "button",
        {
          class: `chip ${state.filters.sort === value ? "active" : ""}`,
          onclick: () => {
            state.filters.sort = value;
            render();
          },
        },
        label,
      ),
    ),
    h("span", { class: "spacer" }),
    count,
  );
  grid.append(...Array.from({ length: 8 }, () => h("div", { class: "skeleton", style: "aspect-ratio: 20/19" })));
  view.replaceChildren(chips, grid, more);

  let page = 1;
  const load = async () => {
    const params = new URLSearchParams({ page, size: 12, sort: state.filters.sort });
    for (const key of ["city", "q", "from_date"]) {
      if (state.filters[key]) params.set(key, state.filters[key]);
    }
    const data = await api(`/events?${params}`);
    if (page === 1) grid.replaceChildren();
    grid.append(...data.items.map(eventCard));
    count.textContent = `${data.total} event${data.total === 1 ? "" : "s"}`;
    more.replaceChildren();
    if (page * data.size < data.total) {
      more.append(
        h("button", { class: "btn btn-dark", onclick: () => { page += 1; load(); } }, "Show more"),
      );
    }
    if (data.total === 0) {
      grid.replaceChildren();
      more.append(
        emptyState(
          "No exact matches",
          "Try changing or removing some of your filters.",
          h("button", { class: "btn", onclick: resetFilters }, "Clear filters"),
        ),
      );
    }
  };
  await load();
}

function resetFilters() {
  state.filters = { city: "", q: "", from_date: "", sort: "starts_at" };
  $("#search-form").reset();
  location.hash = "#/";
  render();
}

function eventCard(event) {
  const left = event.available_seats;
  let badge = null;
  if (left === 0) badge = "Sold out";
  else if (left / event.total_seats < 0.2) badge = "Selling fast";
  else if (new Date(event.starts_at) - Date.now() < 7 * 86400000) badge = "This week";

  const image = art(event.id, `${event.title} ${event.description}`);
  if (badge) image.append(h("span", { class: "badge" }, badge));
  image.append(heartIcon());

  return h(
    "a",
    { class: "card", href: `#/event/${event.id}` },
    image,
    h(
      "div",
      { class: "card-row" },
      h("p", { class: "card-title" }, event.title),
      h("span", { class: "card-left" }, left === 0 ? "Sold out" : `${left} left`),
    ),
    h("p", { class: "card-sub" }, `${event.city} · ${event.venue}`),
    h("p", { class: "card-sub" }, shortDate(event.starts_at)),
    h("p", { class: "card-price" }, h("strong", {}, rupees(event.price_paise)), " per seat"),
  );
}

function heartIcon() {
  const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  svg.setAttribute("viewBox", "0 0 32 32");
  svg.setAttribute("class", "heart");
  svg.setAttribute("aria-hidden", "true");
  svg.innerHTML =
    '<path d="M16 28c7-4.73 14-10 14-17a6.98 6.98 0 0 0-7-7c-1.8 0-3.58.68-4.95 2.05L16 8.1l-2.05-2.05a6.98 6.98 0 0 0-9.9 0A6.98 6.98 0 0 0 2 11c0 7 7 12.27 14 17z"/>';
  return svg;
}

// ---------------------------------------------------------------- event page

async function renderEvent(view, eventId) {
  const [event, seats] = await Promise.all([
    api(`/events/${eventId}`),
    api(`/events/${eventId}/seats`),
  ]);
  const selected = new Map(); // seat id -> seat
  let reservation = { signature: "", key: newKey() }; // same selection => same Idempotency-Key

  const seatmap = h("div", { class: "seat-rows" });
  const card = h("aside", { class: "reserve-card" });

  function drawSeats(list) {
    const rows = new Map();
    for (const seat of list) {
      if (!rows.has(seat.row_label)) rows.set(seat.row_label, []);
      rows.get(seat.row_label).push(seat);
    }
    seatmap.replaceChildren(
      ...[...rows].map(([label, rowSeats]) =>
        h(
          "div",
          { class: "seat-row" },
          h("span", { class: "row-label" }, label),
          rowSeats.map((seat) => {
            const isSelected = selected.has(seat.id);
            const available = seat.status === "AVAILABLE";
            return h(
              "button",
              {
                class: `seat ${available ? "" : seat.status.toLowerCase()} ${isSelected ? "selected" : ""}`,
                title: `${seat.label} · ${available ? rupees(seat.price_paise) : seat.status.toLowerCase()}`,
                disabled: !available,
                "aria-pressed": isSelected ? "true" : "false",
                onclick: () => toggleSeat(seat),
              },
              seat.seat_number,
            );
          }),
          h("span", { class: "row-label" }, label),
        ),
      ),
    );
  }

  function toggleSeat(seat) {
    if (selected.has(seat.id)) selected.delete(seat.id);
    else if (selected.size >= MAX_SEATS) return toast(`You can pick up to ${MAX_SEATS} seats`);
    else selected.set(seat.id, seat);
    drawSeats(currentSeats);
    drawCard();
  }

  function drawCard() {
    const chosen = [...selected.values()].sort((a, b) => a.id - b.id);
    const total = chosen.reduce((sum, seat) => sum + seat.price_paise, 0);
    card.replaceChildren(
      h("div", { class: "reserve-price" }, rupees(event.price_paise), h("span", {}, " per seat")),
      h(
        "div",
        { class: "reserve-box" },
        h("div", {}, h("small", {}, "Date"), formatDate(event.starts_at)),
        h(
          "div",
          {},
          h("small", {}, `Seats (${chosen.length}/${MAX_SEATS})`),
          h(
            "div",
            { class: "seat-tags" },
            chosen.length
              ? chosen.map((seat) => h("span", { class: "seat-tag" }, seat.label))
              : h("span", { class: "muted" }, "Pick seats on the map"),
          ),
        ),
      ),
      h(
        "button",
        { class: "btn btn-primary btn-block", disabled: !chosen.length, onclick: () => requireLogin(reserve) },
        "Reserve",
      ),
      h("p", { class: "reserve-note" }, "Seats are held for 5 minutes. You won't be charged yet."),
      chosen.length
        ? h(
            "div",
            { class: "line-items" },
            h(
              "div",
              { class: "line-item" },
              h("u", {}, `${rupees(event.price_paise)} x ${chosen.length} seat${chosen.length > 1 ? "s" : ""}`),
              h("span", {}, rupees(total)),
            ),
            h("div", { class: "line-item total" }, h("span", {}, "Total"), h("span", {}, rupees(total))),
          )
        : null,
    );
  }

  async function reserve() {
    const ids = [...selected.keys()].sort((a, b) => a - b);
    const signature = ids.join(",");
    // Retrying the same selection reuses the key, so a double click cannot create two bookings.
    if (signature !== reservation.signature) reservation = { signature, key: newKey() };
    try {
      const booking = await api("/bookings", {
        method: "POST",
        body: { event_id: event.id, seat_ids: ids },
        headers: { "Idempotency-Key": reservation.key },
      });
      location.hash = `#/checkout/${booking.id}`;
    } catch (error) {
      toast(error.message, "error");
      if (error.code === "SEAT_UNAVAILABLE") await refreshSeats();
    }
  }

  let currentSeats = seats;
  async function refreshSeats() {
    currentSeats = await api(`/events/${event.id}/seats`);
    const lost = [...selected.values()].filter(
      (seat) => currentSeats.find((s) => s.id === seat.id)?.status !== "AVAILABLE",
    );
    if (lost.length) {
      lost.forEach((seat) => selected.delete(seat.id));
      toast(`${lost.map((s) => s.label).join(", ")} just got taken by someone else`);
      drawCard();
    }
    drawSeats(currentSeats);
  }

  drawSeats(seats);
  drawCard();
  // Other buyers' holds show up within a few seconds.
  state.timers.push(setInterval(() => refreshSeats().catch(() => {}), SEAT_POLL_MS));

  const legendSeat = (cls) => h("i", { class: `seat ${cls}` });
  view.replaceChildren(
    h("a", { class: "back-link", href: "#/" }, "‹ All events"),
    h("h1", { class: "event-title" }, event.title),
    h(
      "div",
      { class: "event-meta" },
      h("u", {}, event.city),
      h("span", { class: "dot" }, "·"),
      h("span", {}, event.venue),
      h("span", { class: "dot" }, "·"),
      h("span", {}, formatDate(event.starts_at)),
    ),
    art(event.id, `${event.title} ${event.description}`, "hero"),
    h(
      "div",
      { class: "event-layout" },
      h(
        "div",
        {},
        h(
          "div",
          { class: "section host-line" },
          h("span", { class: "avatar" }, "T"),
          h(
            "div",
            {},
            h("h2", { style: "margin:0" }, `Live event in ${event.city}`),
            h("p", { class: "muted" }, `${event.total_seats} seats · ${event.available_seats} available`),
          ),
        ),
        h(
          "div",
          { class: "section facts" },
          fact("📅", formatDate(event.starts_at), "Doors open 30 minutes before the show."),
          fact("📍", event.venue, event.city),
          fact("⏱️", "5-minute seat hold", `Pick up to ${MAX_SEATS} seats, then pay before the hold expires.`),
        ),
        event.description
          ? h("div", { class: "section" }, h("h2", {}, "About this event"), h("p", {}, event.description))
          : null,
        h(
          "div",
          { class: "section" },
          h("h2", {}, "Choose your seats"),
          h("p", { class: "muted" }, h("span", { class: "live-dot" }), "Live: refreshes every 5 seconds"),
          h(
            "div",
            { class: "seatmap" },
            h("div", { class: "stage" }, "STAGE"),
            seatmap,
            h(
              "div",
              { class: "legend" },
              h("span", {}, legendSeat(""), "Available"),
              h("span", {}, legendSeat("selected"), "Your pick"),
              h("span", {}, legendSeat("held"), "On hold"),
              h("span", {}, legendSeat("booked"), "Booked"),
            ),
          ),
        ),
      ),
      card,
    ),
  );
}

function fact(icon, title, text) {
  return h(
    "div",
    { class: "fact" },
    h("span", { class: "fact-icon" }, icon),
    h("div", {}, h("strong", {}, title), h("span", { class: "muted" }, text)),
  );
}

// ---------------------------------------------------------------- checkout

async function renderCheckout(view, bookingId) {
  if (!state.token) {
    view.replaceChildren(
      emptyState("Log in to continue", "Your booking is linked to your account.",
        h("button", { class: "btn btn-dark", onclick: () => requireLogin(render) }, "Log in")),
    );
    return;
  }
  const booking = await api(`/bookings/${bookingId}`);
  if (booking.status !== "PENDING") {
    view.replaceChildren(
      emptyState(
        `This booking is ${booking.status.toLowerCase()}`,
        "There is nothing to pay here.",
        h("a", { class: "btn btn-dark", href: "#/trips" }, "Go to trips"),
      ),
    );
    return;
  }

  const timerValue = h("span", { class: "timer-value" });
  const timer = h(
    "div",
    { class: "timer-banner" },
    h("span", { class: "clock" }, "⏳"),
    h("div", {}, h("strong", {}, "Your seats are on hold"), h("div", { class: "muted" }, "Complete payment within ", timerValue)),
  );
  const payButton = h("button", { class: "btn btn-primary btn-block", onclick: pay }, "Confirm and pay");
  const tokenInput = h("input", { name: "token", value: "tok_visa", autocomplete: "off" });

  const tick = () => {
    const ms = new Date(booking.expires_at) - Date.now();
    if (ms <= 0) {
      timerValue.textContent = "0:00, hold expired";
      timer.classList.add("urgent");
      payButton.disabled = true;
      return;
    }
    const minutes = Math.floor(ms / 60000);
    const seconds = String(Math.floor((ms % 60000) / 1000)).padStart(2, "0");
    timerValue.textContent = `${minutes}:${seconds}`;
    timer.classList.toggle("urgent", ms < 60000);
  };
  tick();
  state.timers.push(setInterval(tick, 1000));

  async function pay() {
    payButton.disabled = true;
    try {
      await api(`/bookings/${booking.id}/pay`, { method: "POST", body: { payment_token: tokenInput.value.trim() } });
      toast("Payment successful. You're going!", "success");
      location.hash = "#/trips";
    } catch (error) {
      toast(error.message, "error");
      if (error.code === "BOOKING_EXPIRED" || error.code === "INVALID_STATE") render();
      else payButton.disabled = false;
    }
  }

  async function release() {
    try {
      await api(`/bookings/${booking.id}/cancel`, { method: "POST" });
      toast("Seats released");
      location.hash = `#/event/${booking.event_id}`;
    } catch (error) {
      toast(error.message, "error");
    }
  }

  const n = booking.seats.length;
  view.replaceChildren(
    h("a", { class: "back-link", href: `#/event/${booking.event_id}` }, "‹ Back to seats"),
    h("h1", { class: "page-title" }, "Confirm and pay"),
    h(
      "div",
      { class: "checkout-layout" },
      h(
        "div",
        {},
        timer,
        h(
          "div",
          { class: "section" },
          h("h2", {}, "Your booking"),
          h(
            "div",
            { class: "trip-row" },
            h("div", {}, h("strong", {}, "Seats"), h("span", { class: "muted" }, booking.seats.join(", "))),
          ),
        ),
        h(
          "div",
          { class: "section" },
          h("h2", {}, "Pay with"),
          h("div", { class: "field-group" }, h("label", { class: "field" }, h("span", {}, "Card token (demo)"), tokenInput)),
          h("p", { class: "hint" }, 'This is a mock payment gateway. Type "fail" to simulate a declined card.'),
        ),
        h(
          "div",
          { class: "section" },
          h("h2", {}, "Cancellation policy"),
          h("p", { class: "muted" }, "Cancel any time. Unpaid holds are released automatically; paid bookings are refunded in full."),
        ),
        h("div", { class: "section" }, payButton,
          h("p", { class: "switch" }, h("button", { class: "link-button", onclick: release }, "Release these seats"))),
      ),
      h(
        "aside",
        { class: "summary-card" },
        h(
          "div",
          { class: "summary-head" },
          art(booking.event_id, booking.event_title, "summary-thumb"),
          h("div", {}, h("h3", {}, booking.event_title), h("span", { class: "muted" }, `Booking #${booking.id}`)),
        ),
        h("h2", {}, "Price details"),
        h(
          "div",
          { class: "line-items" },
          h(
            "div",
            { class: "line-item" },
            h("span", {}, `${rupees(booking.total_paise / n)} x ${n} seat${n > 1 ? "s" : ""}`),
            h("span", {}, rupees(booking.total_paise)),
          ),
          h("div", { class: "line-item total" }, h("span", {}, "Total (INR)"), h("span", {}, rupees(booking.total_paise))),
        ),
      ),
    ),
  );
}

// ---------------------------------------------------------------- trips

async function renderTrips(view) {
  if (!state.token) {
    view.replaceChildren(
      h("h1", { class: "page-title" }, "Trips"),
      emptyState("Log in to see your trips", "Your bookings will show up here.",
        h("button", { class: "btn btn-dark", onclick: () => requireLogin(render) }, "Log in")),
    );
    return;
  }
  const { items } = await api("/bookings?size=50");
  if (!items.length) {
    view.replaceChildren(
      h("h1", { class: "page-title" }, "Trips"),
      emptyState("No trips booked... yet!", "Time to find your next live show.",
        h("a", { class: "btn btn-dark", href: "#/" }, "Start searching")),
    );
    return;
  }

  async function cancel(booking) {
    const refund = booking.status === "CONFIRMED";
    if (refund && !confirm(`Cancel booking #${booking.id}? You will be refunded ${rupees(booking.total_paise)}.`)) return;
    try {
      await api(`/bookings/${booking.id}/cancel`, { method: "POST" });
      toast(refund ? "Booking cancelled and refunded" : "Booking cancelled");
      render();
    } catch (error) {
      toast(error.message, "error");
    }
  }

  view.replaceChildren(
    h("h1", { class: "page-title" }, "Trips"),
    h(
      "div",
      { class: "trips" },
      items.map((booking) =>
        h(
          "div",
          { class: "trip" },
          art(booking.event_id, booking.event_title, "summary-thumb"),
          h(
            "div",
            {},
            h("span", { class: `status status-${booking.status}` }, booking.status),
            h("h3", {}, h("a", { href: `#/event/${booking.event_id}` }, booking.event_title)),
            h("div", { class: "muted" }, `Seats ${booking.seats.join(", ")} · ${rupees(booking.total_paise)}`),
            h("div", { class: "muted" }, `Booked ${shortDate(booking.created_at)} · #${booking.id}`),
          ),
          h(
            "div",
            { class: "trip-actions" },
            booking.status === "PENDING" &&
              h("a", { class: "btn btn-primary btn-small", href: `#/checkout/${booking.id}` }, "Pay now"),
            ["PENDING", "CONFIRMED"].includes(booking.status) &&
              h("button", { class: "btn btn-small", onclick: () => cancel(booking) }, "Cancel"),
          ),
        ),
      ),
    ),
  );
}

// ---------------------------------------------------------------- host (admin)

async function renderHost(view) {
  if (!isAdmin()) {
    view.replaceChildren(
      emptyState("Hosts only", "Log in with an admin account to create events.",
        !state.token && h("button", { class: "btn btn-dark", onclick: () => requireLogin(render) }, "Log in")),
    );
    return;
  }
  const field = (label, input) => h("label", { class: "field" }, h("span", {}, label), input);
  const tomorrow = new Date(Date.now() + 86400000);
  tomorrow.setHours(19, 30, 0, 0);
  const localValue = new Date(tomorrow - tomorrow.getTimezoneOffset() * 60000).toISOString().slice(0, 16);

  const form = h(
    "form",
    { class: "host-form", onsubmit: submit },
    h(
      "div",
      { class: "field-group" },
      field("Title", h("input", { name: "title", required: true, maxlength: 200, placeholder: "e.g. Sunburn Arena" })),
      field("Description", h("textarea", { name: "description", maxlength: 2000 })),
    ),
    h(
      "div",
      { class: "field-group form-grid" },
      field("Venue", h("input", { name: "venue", required: true, maxlength: 200 })),
      field("City", h("input", { name: "city", required: true, maxlength: 100 })),
      field("Starts at", h("input", { name: "starts_at", type: "datetime-local", required: true, value: localValue })),
      field("Price per seat (₹)", h("input", { name: "price", type: "number", min: 1, step: "0.01", required: true, value: 499 })),
      field("Rows (A to Z)", h("input", { name: "rows", type: "number", min: 1, max: 26, required: true, value: 8 })),
      field("Seats per row", h("input", { name: "seats_per_row", type: "number", min: 1, max: 50, required: true, value: 16 })),
    ),
    h("button", { class: "btn btn-primary", type: "submit" }, "Publish event"),
  );

  async function submit(event) {
    event.preventDefault();
    const data = new FormData(form);
    try {
      const created = await api("/events", {
        method: "POST",
        body: {
          title: data.get("title").trim(),
          description: data.get("description").trim(),
          venue: data.get("venue").trim(),
          city: data.get("city").trim(),
          starts_at: new Date(data.get("starts_at")).toISOString(),
          price_paise: Math.round(Number(data.get("price")) * 100), // money travels as integer paise
          rows: Number(data.get("rows")),
          seats_per_row: Number(data.get("seats_per_row")),
        },
      });
      toast(`Published with ${created.total_seats} seats`, "success");
      location.hash = `#/event/${created.id}`;
    } catch (error) {
      toast(error.message, "error");
    }
  }

  view.replaceChildren(
    h("h1", { class: "page-title" }, "Host an event"),
    h("p", { class: "muted", style: "margin-top:-20px; margin-bottom:24px" }, "Seats are generated automatically: rows A, B, C... with numbered seats."),
    form,
  );
}

// ---------------------------------------------------------------- wiring

function init() {
  $("#search-form").addEventListener("submit", (event) => {
    event.preventDefault();
    const form = event.target;
    state.filters.city = form.city.value.trim();
    state.filters.q = form.q.value.trim();
    state.filters.from_date = form.from_date.value;
    if (location.hash === "#/" || location.hash === "") render();
    else location.hash = "#/";
  });

  $("#menu-button").addEventListener("click", (event) => {
    event.stopPropagation();
    $("#menu-panel").classList.contains("hidden") ? openMenu() : closeMenu();
  });
  document.addEventListener("click", (event) => {
    if (!event.target.closest(".menu")) closeMenu();
  });

  $("#auth-form").addEventListener("submit", submitAuth);
  $("#auth-switch").addEventListener("click", () => openAuth(state.authMode === "login" ? "signup" : "login"));
  $("#modal-close").addEventListener("click", closeAuth);
  $("#modal").addEventListener("click", (event) => {
    if (event.target.id === "modal") closeAuth();
  });
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") {
      closeAuth();
      closeMenu();
    }
  });

  window.addEventListener("hashchange", render);
  loadUser().then(render);
}

init();
