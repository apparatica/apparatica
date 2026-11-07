import { Skeleton } from "@/components/ui/skeleton";

// The solution page while the server reads it: the title, the code and the cards beside it.
export default function SolutionLoading() {
  return (
    <div
      aria-busy="true"
      className="mx-auto flex max-w-[1240px] flex-col gap-4 px-4 pt-3 pb-6 sm:px-8 sm:pt-6"
    >
      <div className="flex flex-col gap-2">
        <Skeleton className="h-7 w-56" />
        <Skeleton className="h-4 w-80" />
      </div>
      <div className="grid items-start gap-4 lg:grid-cols-[minmax(0,1fr)_340px]">
        <Skeleton className="h-[480px] rounded-md" />
        <div className="flex flex-col gap-2.5">
          <Skeleton className="h-[76px] rounded-md" />
          <Skeleton className="h-[92px] rounded-md" />
          <Skeleton className="h-[86px] rounded-md" />
          <div className="grid grid-cols-2 gap-2">
            {[0, 1, 2, 3].map((card) => (
              <Skeleton key={card} className="h-[110px] rounded-md" />
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
