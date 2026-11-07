import { Skeleton } from "@/components/ui/skeleton";

// The public solutions of a user while the server reads them: the title and the rows.
export default function UserSolutionsLoading() {
  return (
    <div
      aria-busy="true"
      className="mx-auto flex max-w-[960px] flex-col gap-4 px-4 pt-3 pb-6 sm:px-8 sm:pt-6"
    >
      <div className="flex flex-col gap-2">
        <Skeleton className="h-7 w-56" />
        <Skeleton className="h-4 w-96 max-w-full" />
      </div>
      <div className="flex flex-col gap-px overflow-hidden rounded-md border border-bd">
        {Array.from({ length: 8 }, (_, row) => (
          <Skeleton key={row} className="h-[52px] rounded-none" />
        ))}
      </div>
    </div>
  );
}
