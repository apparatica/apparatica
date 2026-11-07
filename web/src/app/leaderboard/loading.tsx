import { Skeleton } from "@/components/ui/skeleton";

// The global leaderboard while the server reads it: the title, the own position and the rows.
export default function GlobalLeaderboardLoading() {
  return (
    <div
      aria-busy="true"
      className="mx-auto flex max-w-[1240px] flex-col gap-4 px-4 pt-3 pb-6 sm:px-8 sm:pt-6"
    >
      <div className="flex flex-col gap-2">
        <Skeleton className="h-7 w-56" />
        <Skeleton className="h-4 w-96 max-w-full" />
      </div>
      <Skeleton className="h-[52px] rounded-md" />
      <div className="flex flex-col gap-px overflow-hidden rounded-md border border-bd">
        {Array.from({ length: 10 }, (_, row) => (
          <Skeleton key={row} className="h-[34px] rounded-none" />
        ))}
      </div>
    </div>
  );
}
