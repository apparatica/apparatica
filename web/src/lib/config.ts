"use client";

// GET /config in the browser: features, difficulty levels, limits. It changes only with a deploy,
// so one request per tab.
import { useQuery } from "@tanstack/react-query";

import { browserApi } from "./api/browser";

async function fetchConfig() {
  const { data, error } = await browserApi.GET("/api/v1/config");
  if (error !== undefined) throw error;
  return data;
}

export function useConfig() {
  return useQuery({ queryKey: ["config"], queryFn: fetchConfig, staleTime: Infinity });
}
