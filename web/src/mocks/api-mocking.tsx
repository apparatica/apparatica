"use client";

// Development without the backend (NEXT_PUBLIC_API_MOCKING=enabled, docs/frontend.md): the MSW
// service worker answers the API requests of the browser. The children hydrate after it starts,
// so that their first requests are mocked too; until then the server HTML stays.
import dynamic from "next/dynamic";
import { type ReactNode, Suspense, use } from "react";

// msw/browser has no Node.js entry: the worker is loaded in the browser only.
const StartWorker = dynamic(() => import("./start-worker"), { ssr: false });

let started: () => void = () => {};
const ready = new Promise<void>((resolve) => {
  started = resolve;
});

function AfterWorker({ children }: { children: ReactNode }) {
  if (typeof window !== "undefined") use(ready);
  return children;
}

export function ApiMocking({ children }: { children: ReactNode }) {
  return (
    <>
      <StartWorker onStarted={started} />
      <Suspense fallback={null}>
        <AfterWorker>{children}</AfterWorker>
      </Suspense>
    </>
  );
}
