const fs = require("fs");
const path = require("path");
const axios = require("axios");
const jwt = require("jsonwebtoken");
const crypto = require("crypto");

require("dotenv").config();

const REQUIRED_ENV_VARS = [
  "TELEGRAM_BOT_TOKEN",
  "TELEGRAM_CHAT_ID",
  "TARGET_CURRENCY",
];

const missingVars = REQUIRED_ENV_VARS.filter((name) => !process.env[name]);
if (missingVars.length > 0) {
  console.error(`Missing required env vars: ${missingVars.join(", ")}`);
  process.exit(1);
}

const ACCESS_KEY = process.env.UPBIT_OPEN_API_ACCESS_KEY || "";
const SECRET_KEY = process.env.UPBIT_OPEN_API_SECRET_KEY || "";
const TELEGRAM_BOT_TOKEN = process.env.TELEGRAM_BOT_TOKEN;
const TELEGRAM_CHAT_ID = process.env.TELEGRAM_CHAT_ID;
const TARGET_CURRENCY = process.env.TARGET_CURRENCY.trim().toUpperCase();

const RAW_REGION = (process.env.UPBIT_REGION || "sg").toLowerCase();
const REGION = ["sg", "id", "th"].includes(RAW_REGION) ? RAW_REGION : "sg";
const PRIVATE_BASE_URL = `https://${REGION}-api.upbit.com`;
const PUBLIC_BASE_URL = `https://ccx${REGION}.upbit.com/api`;
const PRIVATE_STATUS_URL = `${PRIVATE_BASE_URL}/v1/status/wallet`;
const PUBLIC_STATUS_URL = `${PUBLIC_BASE_URL}/v1/status/wallet`;
const STATE_FILE =
  process.env.STATE_FILE || path.join(__dirname, "data", "state.json");

const POLL_INTERVAL_MS = Number(process.env.POLL_INTERVAL_MS || "60000");
const NOTIFY_ON_START = parseBoolean(process.env.NOTIFY_ON_START, false);
const NOTIFY_ON_CLOSE = parseBoolean(process.env.NOTIFY_ON_CLOSE, false);

const TARGET_NET_TYPES = parseNetTypes(
  process.env.TARGET_NET_TYPES || process.env.TARGET_NET_TYPE || ""
);

const HAS_UPBIT_KEYS = Boolean(ACCESS_KEY && SECRET_KEY);
const HAS_PARTIAL_KEYS = Boolean(ACCESS_KEY || SECRET_KEY) && !HAS_UPBIT_KEYS;

const OPEN_WALLET_STATES = new Set(["working", "deposit_only"]);

function parseBoolean(value, fallback) {
  if (!value) return fallback;
  return ["1", "true", "yes", "y"].includes(value.trim().toLowerCase());
}

function parseNetTypes(value) {
  if (!value) return null;
  const types = value
    .split(",")
    .map((item) => item.trim().toUpperCase())
    .filter(Boolean);
  return types.length > 0 ? new Set(types) : null;
}

function loadState() {
  try {
    const raw = fs.readFileSync(STATE_FILE, "utf8");
    return JSON.parse(raw);
  } catch (error) {
    return { entries: {}, lastCheckedAt: null };
  }
}

function saveState(state) {
  const dir = path.dirname(STATE_FILE);
  fs.mkdirSync(dir, { recursive: true });
  fs.writeFileSync(STATE_FILE, JSON.stringify(state, null, 2));
}

function buildJwt() {
  const payload = {
    access_key: ACCESS_KEY,
    nonce: crypto.randomUUID(),
  };
  return jwt.sign(payload, SECRET_KEY);
}

async function fetchWalletStatus() {
  if (HAS_UPBIT_KEYS) {
    const token = buildJwt();
    const response = await axios.get(PRIVATE_STATUS_URL, {
      headers: {
        Authorization: `Bearer ${token}`,
        Accept: "application/json",
      },
      timeout: 10000,
    });
    return { data: response.data, source: "private" };
  }

  const response = await axios.get(PUBLIC_STATUS_URL, {
    headers: { Accept: "application/json" },
    timeout: 10000,
  });
  return { data: response.data, source: "public" };
}

function filterEntries(entries, supportsNetType) {
  let filtered = entries.filter(
    (entry) => (entry.currency || "").toUpperCase() === TARGET_CURRENCY
  );
  if (TARGET_NET_TYPES) {
    if (!supportsNetType) {
      console.warn(
        "TARGET_NET_TYPES is set but net_type is unavailable. Ignoring net filter."
      );
    } else {
      filtered = filtered.filter((entry) =>
        TARGET_NET_TYPES.has((entry.net_type || "").toUpperCase())
      );
    }
  }
  return filtered;
}

function entryKey(entry) {
  const netType = entry.net_type || entry.network_name || "UNKNOWN";
  return `${entry.currency}|${netType}`;
}

function describeEntry(entry) {
  const parts = [
    `currency=${entry.currency}`,
    `net_type=${entry.net_type || "unknown"}`,
    `wallet_state=${entry.wallet_state}`,
  ];
  if (entry.network_name) {
    parts.push(`network_name=${entry.network_name}`);
  }
  if (entry.block_state) {
    parts.push(`block_state=${entry.block_state}`);
  }
  if (entry.message) {
    parts.push(`message=${entry.message}`);
  }
  return parts.join(", ");
}

async function sendTelegramMessage(text) {
  const url = `https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/sendMessage`;
  await axios.post(url, {
    chat_id: TELEGRAM_CHAT_ID,
    text,
    disable_web_page_preview: true,
  });
}

async function processEntries(entries, state) {
  let notified = 0;
  for (const entry of entries) {
    const key = entryKey(entry);
    const previous = state.entries[key] || {};
    const depositOpen = OPEN_WALLET_STATES.has(entry.wallet_state);
    const previouslyOpen = Boolean(previous.deposit_open);
    const isFirst = typeof previous.wallet_state === "undefined";

    if (depositOpen && ((isFirst && NOTIFY_ON_START) || (!isFirst && !previouslyOpen))) {
      const message = `Upbit deposit OPEN: ${describeEntry(entry)}`;
      await sendTelegramMessage(message);
      notified += 1;
    }

    if (NOTIFY_ON_CLOSE && previouslyOpen && !depositOpen) {
      const message = `Upbit deposit CLOSED: ${describeEntry(entry)}`;
      await sendTelegramMessage(message);
      notified += 1;
    }

    state.entries[key] = {
      currency: entry.currency,
      net_type: entry.net_type || null,
      network_name: entry.network_name || null,
      wallet_state: entry.wallet_state,
      deposit_open: depositOpen,
      updated_at: new Date().toISOString(),
    };
  }

  state.lastCheckedAt = new Date().toISOString();
  saveState(state);
  return notified;
}

function formatError(error) {
  if (error.response) {
    return `HTTP ${error.response.status}: ${JSON.stringify(error.response.data)}`;
  }
  return error.message || String(error);
}

let isRunning = false;

async function checkOnce() {
  if (isRunning) {
    console.warn("Previous check still running, skipping this tick.");
    return;
  }
  isRunning = true;

  try {
    const { data, source } = await fetchWalletStatus();
    const rawEntries = Array.isArray(data) ? data : [];
    const supportsNetType =
      source === "private" && rawEntries.some((entry) => entry.net_type);
    const entries = filterEntries(rawEntries, supportsNetType);
    if (entries.length === 0) {
      console.warn(
        `No entries found for ${TARGET_CURRENCY} ` +
          (TARGET_NET_TYPES ? `with net types: ${Array.from(TARGET_NET_TYPES).join(", ")}` : "")
      );
      return;
    }

    const state = loadState();
    const notified = await processEntries(entries, state);
    console.log(
      `${new Date().toISOString()} check complete. entries=${entries.length} notified=${notified}`
    );
  } catch (error) {
    console.error(`Check failed: ${formatError(error)}`);
  } finally {
    isRunning = false;
  }
}

async function start() {
  if (HAS_PARTIAL_KEYS) {
    console.warn(
      "Incomplete Upbit API keys provided. Falling back to public endpoint."
    );
  }
  if (REGION !== RAW_REGION) {
    console.warn(`Unknown region '${RAW_REGION}', falling back to 'sg'.`);
  }

  const mode = HAS_UPBIT_KEYS ? "private" : "public";
  const endpoint = HAS_UPBIT_KEYS ? PRIVATE_STATUS_URL : PUBLIC_STATUS_URL;
  console.log(
    `Starting monitor for ${TARGET_CURRENCY} on region ${REGION}. ` +
      `interval=${POLL_INTERVAL_MS}ms mode=${mode}`
  );
  if (!HAS_UPBIT_KEYS) {
    console.warn(
      `Using public wallet status endpoint: ${endpoint}. ` +
        "net_type data is not available."
    );
  }
  await checkOnce();
  setInterval(checkOnce, POLL_INTERVAL_MS);
}

start();
