"use client";

// A value in localStorage that the components of every tab follow: the history of a guest, the list
// of their submissions. Parsed once per change of the raw string, so the same object comes back
// while it does not change (useSyncExternalStore needs that).
//
// The values belong to the guest of this browser. While a user is signed in, the stores keep their
// values in memory for this page only: the server has the user's statuses and submissions, and the
// guest's stay in localStorage untouched until the user logs out (their transfer is phase 4).
import { useSyncExternalStore } from "react";

export interface LocalStore<T> {
  /** The stored value; `empty` without one, with a broken one or without storage. */
  read(): T;
  /** Stores `value` as JSON; false when the storage is full or disabled. */
  write(value: unknown): boolean;
  /** The value; null on the server and while the page hydrates, where it is unknown. */
  useValue(): T | null;
}

export type StoreOwner = "guest" | "user";

let owner: StoreOwner = "guest";
/** Every store, told when the owner changes. */
const stores = new Set<() => void>();

export const storeOwner = (): StoreOwner => owner;

/** Who the stores hold the values of. The session sets it before the stores are first read. */
export function setStoreOwner(next: StoreOwner): void {
  if (next === owner) return;
  owner = next;
  for (const changed of stores) changed();
}

export function localStore<T>(key: string, parse: (raw: string) => T, empty: T): LocalStore<T> {
  const listeners = new Set<() => void>();
  let cached: { raw: string | null; value: T } = { raw: null, value: empty };
  let memory = empty;

  const notify = () => {
    for (const listener of listeners) listener();
  };
  stores.add(() => {
    memory = empty; // a new owner starts empty
    notify();
  });

  function readRaw(): string | null {
    try {
      return localStorage.getItem(key);
    } catch {
      return null; // storage disabled: nothing stored
    }
  }

  function read(): T {
    if (owner === "user") return memory;
    const raw = readRaw();
    if (raw !== cached.raw) cached = { raw, value: raw === null ? empty : parse(raw) };
    return cached.value;
  }

  function write(value: unknown): boolean {
    if (owner === "user") {
      // As it would be read back from storage.
      memory = parse(JSON.stringify(value));
    } else {
      try {
        localStorage.setItem(key, JSON.stringify(value));
      } catch {
        return false;
      }
    }
    notify();
    return true;
  }

  function subscribe(listener: () => void): () => void {
    listeners.add(listener);
    // Another tab changed the value of the guest.
    const onStorage = (event: StorageEvent) => {
      if (owner === "guest" && (event.key === key || event.key === null)) listener();
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
