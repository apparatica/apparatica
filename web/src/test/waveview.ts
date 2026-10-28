// A fake adapter of the waveview frame (docs/waveview.md#адаптер) for jsdom, where the frame runs
// nothing: it answers the commands posted to the frame the way the real adapter does.
import { vi } from "vitest";

export interface Command {
  apx: number;
  id: number;
  type: string;
  [field: string]: unknown;
}

export interface FakeAdapter {
  /** The commands the page sent, in order. */
  received: Command[];
  /** An unprompted message of the frame, or a reply. */
  say: (data: Record<string, unknown>) => void;
  /** Surfer is up. */
  ready: () => void;
}

/** `fail`: a command type that answers with an error. */
export function fakeAdapter(
  frame: HTMLIFrameElement,
  { fail }: { fail?: string } = {},
): FakeAdapter {
  const target = frame.contentWindow;
  if (target === null) throw new Error("the frame is not in the document");
  const received: Command[] = [];
  const say = (data: Record<string, unknown>) =>
    window.dispatchEvent(
      new MessageEvent("message", { data: { apx: 1, ...data }, source: target }),
    );
  vi.spyOn(target, "postMessage").mockImplementation((message: unknown) => {
    const command = message as Command;
    received.push(command);
    const { id, type } = command;
    setTimeout(() => {
      if (type === fail) say({ type: "error", id, message: `${type} broke` });
      else if (type === "load") say({ type: "loaded", id, ms: 12 });
      else if (type === "signals") {
        const items = command["items"] as { path: string }[];
        say({ type: "ack", id, added: items.map((item) => item.path) });
      } else say({ type: "ack", id });
    }, 0);
  });
  return { received, say, ready: () => say({ type: "ready", protocol: 1, commands: [] }) };
}
