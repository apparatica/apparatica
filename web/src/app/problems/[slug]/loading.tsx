import { EditorSkeleton, ResultsSkeleton, StatementSkeleton } from "@/features/problem/skeletons";

// The problem page while the server reads it (mock-up Loading): the panels in their default sizes.
export default function ProblemLoading() {
  return (
    <div className="flex h-[calc(100dvh-6rem)] gap-px bg-bg sm:h-[calc(100dvh-4rem)]">
      <div className="flex w-[38%] flex-col bg-sf">
        <div className="h-9 flex-none border-b border-bd bg-sf2" />
        <StatementSkeleton />
      </div>
      <div className="flex min-w-0 flex-1 flex-col gap-px">
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
