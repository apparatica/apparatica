// Server-Sent Events over fetch (https://html.spec.whatwg.org/multipage/server-sent-events.html):
// unlike EventSource, the caller decides when to reconnect and which Last-Event-ID to send.

export interface SseMessage {
  /** The `id:` of this message; null without one (a `queue` event has none). */
  id: string | null;
  event: string;
  data: string;
}

/** The messages of an event stream body; comments (`: keepalive`) are skipped. */
export async function* readSse(body: ReadableStream<Uint8Array>): AsyncGenerator<SseMessage> {
  const reader = body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let id: string | null = null;
  let event = "";
  let data: string[] = [];
  try {
    for (;;) {
      const { done, value } = await reader.read();
      if (done) return; // an unfinished message is dropped, as the standard says
      buffer += decoder.decode(value, { stream: true });
      let end: number;
      while ((end = buffer.search(/\r\n|\r(?!$)|\n/)) !== -1) {
        const line = buffer.slice(0, end);
        buffer = buffer.slice(end + (buffer.startsWith("\r\n", end) ? 2 : 1));
        if (line === "") {
          if (data.length > 0) yield { id, event: event || "message", data: data.join("\n") };
          id = null;
          event = "";
          data = [];
          continue;
        }
        if (line.startsWith(":")) continue;
        const colon = line.indexOf(":");
        const field = colon === -1 ? line : line.slice(0, colon);
        let value = colon === -1 ? "" : line.slice(colon + 1);
        if (value.startsWith(" ")) value = value.slice(1);
        if (field === "data") data.push(value);
        else if (field === "event") event = value;
        else if (field === "id" && !value.includes("\0")) id = value;
      }
    }
  } finally {
    await reader.cancel().catch(() => {});
  }
}
