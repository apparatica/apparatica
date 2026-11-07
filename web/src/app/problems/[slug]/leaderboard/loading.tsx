import { Skeleton } from "@/components/ui/skeleton";

// The leaderboard page while the server reads it: the title, the three cards and the rows.
export default function ProblemLeaderboardLoading() {
  return (
    <div
      aria-busy="true"
      className="mx-auto flex max-w-[1240px] flex-col gap-4 px-4 pt-3 pb-6 sm:px-8 sm:pt-6"
    >
      <div className="flex flex-col gap-2">
        <Skeleton className="h-7 w-56" />
        <Skeleton className="h-4 w-40" />
      </div>
      <div className="grid gap-2 lg:grid-cols-3">
        {[0, 1, 2].map((card) => (
          <Skeleton key={card} className="h-[82px] rounded-md" />
        ))}
      </div>
      <Skeleton className="h-4 w-2/3" />
      <div className="flex flex-col gap-px overflow-hidden rounded-md border border-bd">
        {Array.from({ length: 10 }, (_, row) => (
          <Skeleton key={row} className="h-[34px] rounded-none" />
        ))}
      </div>
    </div>
  );
}
