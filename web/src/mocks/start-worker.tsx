"use client";

import { useEffect } from "react";

import { worker } from "./browser";

let starting: Promise<unknown> | undefined;

export default function StartWorker({ onStarted }: { onStarted: () => void }) {
  useEffect(() => {
    starting ??= worker.start({ onUnhandledFrame: "bypass", quiet: true });
    void starting.then(onStarted);
  }, [onStarted]);
  return null;
}
