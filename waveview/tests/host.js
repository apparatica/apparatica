// The test parent: creates the frame (?viewer=<url>) and exposes the protocol as window.apx.
const viewer = new URLSearchParams(location.search).get("viewer");
let frame;
let next = 0;
const replies = new Map();
const unprompted = [];

window.addEventListener("message", (event) => {
  if (event.source !== frame?.contentWindow || event.data?.apx !== 1) return;
  const reply = replies.get(event.data.id);
  if (reply === undefined) unprompted.push(event.data);
  else reply(event.data);
});

window.apx = {
  /** A new frame; resolves with its "ready". */
  open() {
    frame?.remove();
    unprompted.length = 0;
    frame = document.createElement("iframe");
    frame.sandbox = "allow-scripts"; // no allow-same-origin: the origin of the frame is opaque
    frame.src = viewer;
    document.body.append(frame);
    return this.unprompted("ready");
  },

  /** The next unprompted message of this type (ready, crashed, error). */
  async unprompted(type, timeoutMs = 60000) {
    const deadline = Date.now() + timeoutMs;
    while (Date.now() < deadline) {
      const found = unprompted.find((message) => message.type === type);
      if (found !== undefined) return found;
      await new Promise((resolve) => setTimeout(resolve, 50));
    }
    throw new Error(`no ${type} in ${timeoutMs} ms`);
  },

  /** One command; resolves with its reply. `bytes` (base64) becomes a transferred ArrayBuffer. */
  call(type, fields = {}) {
    const id = ++next;
    const message = { apx: 1, id, type, ...fields };
    const transfer = [];
    if (typeof fields.bytes === "string") {
      message.bytes = Uint8Array.from(atob(fields.bytes), (c) => c.charCodeAt(0)).buffer;
      transfer.push(message.bytes);
    }
    return new Promise((resolve) => {
      replies.set(id, resolve);
      frame.contentWindow.postMessage(message, "*", transfer);
    });
  },
};
