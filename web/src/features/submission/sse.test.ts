import { expect, it } from "vitest";

import { readSse, type SseMessage } from "./sse";

function body(...chunks: string[]): ReadableStream<Uint8Array> {
  const encoder = new TextEncoder();
  return new ReadableStream({
    start(controller) {
      for (const chunk of chunks) controller.enqueue(encoder.encode(chunk));
      controller.close();
    },
  });
}

async function read(...chunks: string[]): Promise<SseMessage[]> {
  const messages: SseMessage[] = [];
  for await (const message of readSse(body(...chunks))) messages.push(message);
  return messages;
}

it("reads messages split anywhere between chunks", async () => {
  const text = 'id: 1-0\nevent: log\ndata: {"a":1}\n\nevent: queue\ndata: {"b":2}\n\n';
  const whole = await read(text);
  expect(whole).toEqual([
    { id: "1-0", event: "log", data: '{"a":1}' },
    { id: null, event: "queue", data: '{"b":2}' },
  ]);
  for (let at = 1; at < text.length; at++) {
    expect(await read(text.slice(0, at), text.slice(at))).toEqual(whole);
  }
});

it("skips comments and joins data lines", async () => {
  expect(await read(": keepalive\n\ndata: one\ndata:two\n\n")).toEqual([
    { id: null, event: "message", data: "one\ntwo" },
  ]);
});

it("accepts CRLF and CR line ends, also split between chunks", async () => {
  expect(await read("id: 2-1\r", "\nevent: done\rdata: {}\r\n\r\n")).toEqual([
    { id: "2-1", event: "done", data: "{}" },
  ]);
});

it("drops a message the stream cut off", async () => {
  expect(await read("data: whole\n\n", "id: 3-0\ndata: cut")).toEqual([
    { id: null, event: "message", data: "whole" },
  ]);
});
