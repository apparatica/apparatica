// The waveform viewer in an isolated frame (ADR-0004, docs/waveview.md#адаптер): the client of the
// adapter protocol, version 1, and the state of the frame for React (an external store, as the
// submission: the frame lives outside the render). The frame has the opaque origin "null", so
// messages go with targetOrigin "*" and only replies whose source is the frame are taken.

export const PROTOCOL = 1;
/** The first start downloads the WASM of Surfer (3 MB compressed). */
export const READY_TIMEOUT_MS = 30_000;
/** Surfer parses about 5 MB in 2 s (S3); the adapter gives up on its own after this. */
export const LOAD_TIMEOUT_MS = 5000;
const COMMAND_TIMEOUT_MS = 10_000;

export type ThemeName = "apparatica-light" | "apparatica-dark";

/** A colour name of the themes (waveview/themes). */
export type SignalColor = "Clock" | "Bus" | "Expected" | "Error";

export interface SignalItem {
  path: string;
  color?: SignalColor | undefined;
  label?: string | undefined;
}

/** What to show: the bytes of an FST, its signals in order, the cursor and its marker. */
export interface TraceView {
  /** Changes when the file does: the same key is not loaded twice. */
  key: string;
  bytes: ArrayBuffer;
  signals: readonly SignalItem[];
  cursor: { time: number; marker: string } | null;
}

export type ViewerState =
  /** No frame: nobody asked for the waves yet. */
  | { phase: "idle" }
  /** The frame boots. */
  | { phase: "starting" }
  /** Up, waiting for a trace. */
  | { phase: "ready" }
  | { phase: "loading" }
  | { phase: "shown"; key: string }
  /** The frame is dead or the file did not open: retry() makes a new frame. */
  | { phase: "failed"; message: string };

export interface ViewerSnapshot {
  state: ViewerState;
  /** The key of the frame element: a new key, a new frame. */
  frame: number;
}

type Reply = { apx: number; id?: number; type: string; message?: string } & Record<string, unknown>;

export class ViewerError extends Error {}

/** The protocol over one frame: commands and their replies, and what comes unprompted. */
export class Channel {
  private next = 0;
  private readonly waiting = new Map<number, (reply: Reply) => void>();

  constructor(
    private readonly frame: HTMLIFrameElement,
    private readonly unprompted: (message: Reply) => void,
    private readonly host: Window,
  ) {
    host.addEventListener("message", this.receive);
  }

  close(): void {
    this.host.removeEventListener("message", this.receive);
    const waiting = [...this.waiting.values()];
    this.waiting.clear();
    for (const reply of waiting) reply({ apx: PROTOCOL, type: "error", message: "closed" });
  }

  owns(frame: HTMLIFrameElement): boolean {
    return frame === this.frame;
  }

  /** One command; rejects with the error of the adapter or after the timeout. */
  call(
    type: string,
    fields: Record<string, unknown> = {},
    {
      transfer = [],
      timeoutMs = COMMAND_TIMEOUT_MS,
    }: { transfer?: Transferable[]; timeoutMs?: number } = {},
  ): Promise<Reply> {
    const target = this.frame.contentWindow;
    if (target === null) return Promise.reject(new ViewerError("the frame is gone"));
    const id = ++this.next;
    return new Promise((resolve, reject) => {
      const timer = setTimeout(() => {
        this.waiting.delete(id);
        reject(new ViewerError(`${type}: no reply in ${timeoutMs} ms`));
      }, timeoutMs);
      this.waiting.set(id, (reply) => {
        clearTimeout(timer);
        if (reply.type === "error")
          reject(new ViewerError(`${type}: ${reply.message ?? "failed"}`));
        else resolve(reply);
      });
      target.postMessage({ apx: PROTOCOL, id, type, ...fields }, "*", transfer);
    });
  }

  private readonly receive = (event: MessageEvent) => {
    if (event.source === null || event.source !== this.frame.contentWindow) return;
    const message = event.data as Reply | null;
    if (message?.apx !== PROTOCOL || typeof message.type !== "string") return;
    const reply = message.id === undefined ? undefined : this.waiting.get(message.id);
    if (reply === undefined) {
      this.unprompted(message);
      return;
    }
    this.waiting.delete(message.id as number);
    reply(message);
  };
}

/** The viewer of a problem page: one frame at a time, the trace and the theme it should show. */
export class Viewer {
  private snapshot: ViewerSnapshot = { state: { phase: "idle" }, frame: 0 };
  private readonly listeners = new Set<() => void>();
  private channel: Channel | null = null;
  private timer: ReturnType<typeof setTimeout> | undefined;
  /** Commands run one after another; a new frame starts a new chain. */
  private chain: Promise<unknown> = Promise.resolve();
  private trace: TraceView | null = null;
  private theme: ThemeName | null = null;

  /** `host`: the window the replies come to; the page's by default (not known on the server). */
  constructor(private readonly host: Window | null = null) {}

  subscribe = (listener: () => void) => {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  };

  getSnapshot = () => this.snapshot;

  /** The frame element is in the page: wait for its "ready". */
  attach(frame: HTMLIFrameElement): void {
    if (this.channel?.owns(frame)) return;
    this.channel?.close();
    const host = this.host ?? window;
    const channel = new Channel(frame, (message) => this.unprompted(channel, message), host);
    this.channel = channel;
    this.chain = Promise.resolve();
    this.set({ phase: "starting" });
    clearTimeout(this.timer);
    this.timer = setTimeout(
      () => this.fail(channel, `the viewer did not start in ${READY_TIMEOUT_MS} ms`),
      READY_TIMEOUT_MS,
    );
  }

  /** The frame element left the page. */
  detach(frame: HTMLIFrameElement): void {
    if (this.channel === null || !this.channel.owns(frame)) return;
    this.channel.close();
    this.channel = null;
    clearTimeout(this.timer);
    this.set({ phase: "idle" });
  }

  /** A new frame: after a failure, or to load a file again. */
  retry(): void {
    this.channel?.close();
    this.channel = null;
    clearTimeout(this.timer);
    this.snapshot = { state: { phase: "starting" }, frame: this.snapshot.frame + 1 };
    this.emit();
  }

  /** The trace to show; shown as soon as the viewer is up. */
  show(trace: TraceView | null): void {
    this.trace = trace;
    const { state } = this.snapshot;
    if (trace === null || (state.phase === "shown" && state.key === trace.key)) return;
    if (state.phase === "ready" || state.phase === "shown") this.load();
  }

  setTheme(theme: ThemeName): void {
    if (theme === this.theme) return;
    this.theme = theme;
    const { phase } = this.snapshot.state;
    if (phase === "ready" || phase === "loading" || phase === "shown") {
      this.run((channel) => channel.call("theme", { name: theme }));
    }
  }

  /** "Show on the diagram": the cursor back to the mismatch, in the middle of the view. */
  focus(): void {
    const { state } = this.snapshot;
    const cursor = this.trace?.cursor;
    if (state.phase !== "shown" || cursor == null) return;
    this.run(async (channel) => {
      await channel.call("cursor", { time: cursor.time });
      await channel.call("center", { time: cursor.time });
    });
  }

  /** The whole window of the trace. */
  fit(): void {
    if (this.snapshot.state.phase !== "shown") return;
    this.run((channel) => channel.call("fit"));
  }

  private unprompted(channel: Channel, message: Reply): void {
    if (channel !== this.channel) return;
    if (message.type === "ready" && this.snapshot.state.phase === "starting") {
      clearTimeout(this.timer);
      this.run(async (ready) => {
        await ready.call("chrome", {}); // the menus and panels of Surfer stay hidden
        if (this.theme !== null) await ready.call("theme", { name: this.theme });
      });
      this.set({ phase: "ready" });
      if (this.trace !== null) this.load();
    } else if (message.type === "crashed") {
      this.fail(channel, `the viewer crashed: ${message.message ?? ""}`);
    }
  }

  private load(): void {
    const trace = this.trace;
    if (trace === null) return;
    this.set({ phase: "loading" });
    this.run(async (channel) => {
      // A copy: the transfer empties the buffer, and a retry needs the bytes again.
      const bytes = trace.bytes.slice(0);
      await channel.call(
        "load",
        { bytes, timeoutMs: LOAD_TIMEOUT_MS },
        { transfer: [bytes], timeoutMs: LOAD_TIMEOUT_MS + COMMAND_TIMEOUT_MS },
      );
      await channel.call("signals", { items: trace.signals });
      await channel.call("fit");
      if (trace.cursor !== null) {
        await channel.call("cursor", { time: trace.cursor.time });
        await channel.call("marker", { time: trace.cursor.time, name: trace.cursor.marker });
      }
      if (this.trace?.key === trace.key) this.set({ phase: "shown", key: trace.key });
      else if (this.trace !== null) this.load(); // another trace came meanwhile
    });
  }

  /** Runs a step after the previous ones on the current frame; a failed step fails the frame. */
  private run(step: (channel: Channel) => Promise<unknown>): void {
    const channel = this.channel;
    if (channel === null) return;
    this.chain = this.chain.then(async () => {
      if (channel !== this.channel) return;
      try {
        await step(channel);
      } catch (error) {
        this.fail(channel, error instanceof Error ? error.message : String(error));
      }
    });
  }

  private fail(channel: Channel, message: string): void {
    if (channel !== this.channel) return;
    clearTimeout(this.timer);
    channel.close();
    this.channel = null;
    this.set({ phase: "failed", message });
  }

  private set(state: ViewerState): void {
    this.snapshot = { ...this.snapshot, state };
    this.emit();
  }

  private emit(): void {
    for (const listener of this.listeners) listener();
  }
}
