// The adapter between the problem page and Surfer (ADR-0004, docs/waveview.md): our own protocol on
// postMessage, version 1, on top of WCP (versioned, answers every command). Where WCP has no command
// — loading from bytes, the theme, the panels, display names — it injects Surfer's unstable
// `Message` JSON; the regression test of the build covers these five messages.
//
// Parent -> waveview, every message {apx: 1, id, type, ...}:
//   load    {bytes: ArrayBuffer, timeoutMs?}                 -> "loaded" {ms}
//   signals {items: [{path, color?, label?}]}                -> "ack" {added: [path]}
//   cursor  {time}    marker {time, name}    center {time}   -> "ack"
//   range   {from, to}    fit {}    theme {name}             -> "ack"
//   chrome  {menu?, toolbar?, side?, overview?, status?}     -> "ack"
// A failed command answers "error" {id, message}. Unprompted: "ready" {protocol, commands} once
// Surfer is up, "crashed" {message} after a panic (the viewer is dead: recreate the iframe),
// "error" {message} for an uncaught error.
import init, {
  handle_wcp_cs_message,
  index_of_name,
  inject_message,
  next_wcp_sc_message,
  start_wcp,
  waves_loaded,
} from "./surfer.js";

const PROTOCOL = 1;
// A file Surfer cannot parse ends in its log, not in a WCP reply: the load gives up after this.
const LOAD_TIMEOUT_MS = 5000;
const THEMES = new Set(["apparatica-light", "apparatica-dark"]);

const parent = window.parent;
// The frame has the opaque origin "null" and does not know its parent's; frame-ancestors of the
// CSP decides who may embed it, and the replies hold nothing but the user's own trace.
const send = (message) => parent.postMessage({ apx: PROTOCOL, ...message }, "*");

// Surfer pops its external message queue from the end: messages injected within one frame would run
// in reverse order. A batch keeps the order.
const inject = (...messages) =>
  inject_message(JSON.stringify(messages.length === 1 ? messages[0] : { Batch: messages }));

// WCP answers commands strictly in order; events come in between.
const waiting = [];
let onLoaded = null;
let greeted;
const greeting = new Promise((resolve) => (greeted = resolve));

function wcp(command) {
  return new Promise((resolve, reject) => {
    waiting.push({ resolve, reject });
    handle_wcp_cs_message(JSON.stringify({ type: "command", ...command }));
  });
}

async function pump() {
  for (;;) {
    const raw = await next_wcp_sc_message();
    if (raw == null) return; // the channel is closed
    const message = JSON.parse(raw);
    if (message.type === "event") {
      if (message.event === "waveforms_loaded" && onLoaded) onLoaded();
    } else if (message.type === "greeting") {
      greeted(message); // our greeting is answered by Surfer's, with its commands
    } else {
      const next = waiting.shift();
      if (next === undefined) continue;
      if (message.type === "error") next.reject(new Error(`${message.error}: ${message.message}`));
      else next.resolve(message);
    }
  }
}

function time(value, name = "time") {
  if (!Number.isSafeInteger(value) || value < 0) throw new Error(`${name} must be a time in FST units`);
  return value;
}

async function load({ bytes, timeoutMs = LOAD_TIMEOUT_MS }) {
  if (!(bytes instanceof ArrayBuffer)) throw new Error("bytes must be an ArrayBuffer");
  const started = performance.now();
  const loaded = new Promise((resolve) => (onLoaded = resolve));
  // Vec<u8> in serde JSON is an array of numbers; "Clear" replaces the shown file.
  inject({ LoadFromData: [Array.from(new Uint8Array(bytes)), "Clear"] });
  const timeout = new Promise((resolve) => setTimeout(() => resolve("timeout"), timeoutMs));
  const outcome = await Promise.race([loaded, timeout]);
  onLoaded = null;
  if (outcome === "timeout") {
    // Surfer keeps the previous file on a parse error: the caller recreates the frame.
    throw new Error(`not loaded in ${timeoutMs} ms (waves loaded: ${await waves_loaded()})`);
  }
  return { ms: Math.round(performance.now() - started) };
}

const handlers = {
  load,

  // One at a time: Surfer skips an unknown name silently, and the reply then has fewer ids.
  async signals({ items }) {
    if (!Array.isArray(items)) throw new Error("items must be a list");
    const added = [];
    const labels = {};
    for (const { path, color, label } of items) {
      if (typeof path !== "string") throw new Error("a signal path must be a string");
      const { ids } = await wcp({ command: "add_variables", variables: [path] });
      if (ids.length === 0) continue;
      added.push(path);
      if (typeof color === "string") await wcp({ command: "set_item_color", id: ids[0], color });
      if (typeof label === "string") labels[path] = label;
    }
    // Display names, e.g. "rdata ожидалось": no WCP command; the unstable message takes the index.
    for (const [path, label] of Object.entries(labels)) {
      const index = await index_of_name(path);
      if (index != null) inject({ ItemNameChange: [index, label] });
    }
    return { added };
  },

  async cursor(message) {
    await wcp({ command: "set_cursor", timestamp: time(message.time) });
  },

  async marker(message) {
    if (typeof message.name !== "string") throw new Error("name must be a string");
    const marker = { time: time(message.time), name: message.name, move_focus: false };
    await wcp({ command: "add_markers", markers: [marker] });
  },

  async center(message) {
    await wcp({ command: "set_viewport_to", timestamp: time(message.time) });
  },

  async range(message) {
    const start = time(message.from, "from");
    const end = time(message.to, "to");
    await wcp({ command: "set_viewport_range", start, end });
  },

  async fit() {
    await wcp({ command: "zoom_to_fit", viewport_idx: 0 });
  },

  async theme({ name }) {
    if (!THEMES.has(name)) throw new Error(`unknown theme ${name}`);
    inject({ SelectTheme: name });
  },

  async chrome({ menu = false, toolbar = false, side = false, overview = false, status = false }) {
    inject(
      { SetMenuVisible: Boolean(menu) },
      { SetToolbarVisible: Boolean(toolbar) },
      { SetSidePanelVisible: Boolean(side) },
      { SetOverviewVisible: Boolean(overview) },
      { SetStatusbarVisible: Boolean(status) },
    );
  },
};

window.addEventListener("message", async (event) => {
  if (event.source !== parent) return; // only the embedding page drives the viewer
  const message = event.data;
  if (message?.apx !== PROTOCOL || !Object.hasOwn(handlers, message.type)) return;
  try {
    const result = await handlers[message.type](message);
    send({ type: message.type === "load" ? "loaded" : "ack", id: message.id, ...result });
  } catch (error) {
    send({ type: "error", id: message.id, message: String(error?.message ?? error) });
  }
});

window.addEventListener("error", (event) => send({ type: "error", message: String(event.message) }));
// Surfer's panic hook calls this global; after a panic the viewer is dead.
window.on_surfer_error = (message) =>
  send({ type: "crashed", message: String(message).slice(0, 2000) });

await init({ module_or_path: "./surfer_bg.wasm" });
await start_wcp();
pump();
await handle_wcp_cs_message(
  JSON.stringify({ type: "greeting", version: "0", commands: ["waveforms_loaded"] }),
);
const hello = await greeting;
send({ type: "ready", protocol: PROTOCOL, commands: hello.commands });
