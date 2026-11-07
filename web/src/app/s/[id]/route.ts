// A short link of a solution (specs/08 §1): `301` to `/solutions/<uuid>`. The location is a path,
// so the redirect does not depend on the host the request came through. Whether the solution
// exists is the business of the solution page.
import { notFound } from "next/navigation";

import { solutionHref } from "@/features/solution/href";
import { fromShortId } from "@/lib/short-id";

export async function GET(_request: Request, { params }: RouteContext<"/s/[id]">) {
  const id = fromShortId((await params).id);
  if (id === null) notFound();
  return new Response(null, {
    status: 301,
    headers: { Location: solutionHref(id), "Cache-Control": "public, max-age=86400" },
  });
}
