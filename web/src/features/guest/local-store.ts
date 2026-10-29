"use client";

// A value in localStorage that the components of every tab follow: the history of a guest, the list
// of their submissions. Parsed once per change of the raw string, so the same object comes back
// while it does not change (useSyncExternalStore needs that).
import { useSyncExternalStore } from "react";

export interface LocalStore<T> {
  /** The stored value; `empty` without one, with a broken one or without storage. */
  read(): T;
  /** Stores `value` as JSON; false when the storage is full or disabled. */
  write(value: unknown): boolean;
  /** The value; null on the server and while the page hydrates, where it is unknown. */
  useValue(): T | null;
}

export function localStore<T>(key: string, parse: (raw: string) => T, empty: T): LocalStore<T> {
  const listeners = new Set<() => void>();
  let cached: { raw: string | null; value: T } = { raw: null, value: empty };

  function readRaw(): string | null {
    try {
      return localStorage.getItem(key);
    } catch {
      return null; // storage disabled: nothing stored
    }
  }

  function read(): T {
    const raw = readRaw();
    if (raw !== cached.raw) cached = { raw, value: raw === null ? empty : parse(raw) };
    return cached.value;
  }

  function write(value: unknown): boolean {
    try {
      localStorage.setItem(key, JSON.stringify(value));
    } catch {
      return false;
    }
    for (const listener of listeners) listener();
    return true;
  }

  function subscribe(listener: () => void): () => void {
    listeners.add(listener);
    // Another tab changed the value.
    const onStorage = (event: StorageEvent) => {
      if (event.key === key || event.key === null) listener();
    };
    window.addEventListener("storage", onStorage);
    return () => {
      listeners.delete(listener);
      window.removeEventListener("storage", onStorage);
    };
  }

  function useValue(): T | null {
    return useSyncExternalStore<T | null>(subscribe, read, () => null);
  }

  return { read, write, useValue };
}
