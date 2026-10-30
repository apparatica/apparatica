import { NotFoundState } from "@/features/errors/states";

// The problem is not published (specs/08 §1). The page streams after its loading skeleton, so the
// answer is 200 with `noindex` rather than 404.
export default function ProblemNotFound() {
  return <NotFoundState kind="problem" />;
}
