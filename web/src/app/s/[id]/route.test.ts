import { expect, it } from "vitest";

import { toShortId } from "@/lib/short-id";

import { GET } from "./route";

const ID = "0193a000-0000-7000-8005-000000000003";
const call = (id: string) =>
  GET(new Request(`http://localhost/s/${id}`), { params: Promise.resolve({ id }) });

it("sends a short link to the solution for good, by a path", async () => {
  const response = await call(toShortId(ID));
  expect(response.status).toBe(301);
  expect(response.headers.get("Location")).toBe(`/solutions/${ID}`);
});

it("is a 404 for what is no short id", async () => {
  await expect(call("0abc")).rejects.toMatchObject({ digest: "NEXT_HTTP_ERROR_FALLBACK;404" });
  await expect(call("not-an-id")).rejects.toMatchObject({
    digest: "NEXT_HTTP_ERROR_FALLBACK;404",
  });
});
