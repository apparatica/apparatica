import { EditorSkeleton, ResultsSkeleton, StatementSkeleton } from "@/features/problem/skeletons";

// The problem page while the server reads it (mock-up Loading): the panels in their default sizes;
// on phones the statement alone.
export default function ProblemLoading() {
  return (
    <div className="flex gap-px bg-bg sm:h-[calc(100dvh-4rem)]">
      <div className="flex flex-col bg-sf max-sm:flex-1 sm:w-[38%]">
        <div className="h-11 flex-none border-b border-bd sm:h-9 sm:bg-sf2" />
        <StatementSkeleton />
      </div>
      <div className="flex min-w-0 flex-1 flex-col gap-px max-sm:hidden">
        <div className="flex flex-1 flex-col bg-sf">
          <div className="h-9 flex-none border-b border-bd bg-sf2" />
          <div className="min-h-0 flex-1">
            <EditorSkeleton />
          </div>
        </div>
        <div className="flex-1 bg-sf">
          <ResultsSkeleton />
        </div>
      </div>
    </div>
  );
}
