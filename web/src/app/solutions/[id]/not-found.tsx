import { NotFoundState } from "@/features/errors/states";

// No such public solution: a Run, a Submit that was not accepted, a guest's one, or its problem is
// not published (FR-SOL-01).
export default function SolutionNotFound() {
  return <NotFoundState kind="solution" />;
}
