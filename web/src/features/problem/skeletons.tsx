// Skeletons of the problem page (mock-up Loading): the statement, the editor and the results, in
// the places and sizes of the real panels.
import { useTranslations } from "next-intl";

import { Skeleton } from "@/components/ui/skeleton";

// Line widths of the mock-up, in per cent of the editor.
const CODE_LINES = [46, 38, 52, 30, 64, 58, 44, 70, 36, 55, 48, 28, 62, 40];
const RESULT_LINES = [46, 62, 38];

/** The editor until Monaco is ready: line numbers and lines of code. */
export function EditorSkeleton() {
  const t = useTranslations("problem.editor");
  return (
    <div role="status" className="flex h-full flex-col gap-[9px] bg-ed px-4 pt-4">
      <span className="sr-only">{t("loading")}</span>
      {CODE_LINES.map((width, index) => (
        <div key={index} className="flex items-center gap-2.5">
          <Skeleton className="h-2.5 w-[22px]" />
          <Skeleton className="h-2.5" style={{ width: `${width}%` }} />
        </div>
      ))}
    </div>
  );
}

/** The header, the paragraphs and two blocks of the statement. */
export function StatementSkeleton() {
  return (
    <div aria-hidden="true">
      <div className="flex flex-col gap-3 border-b border-bd px-[22px] pt-[18px] pb-3.5">
        <Skeleton className="h-6 w-[262px] max-w-full" />
        <div className="flex gap-1.5">
          <Skeleton className="h-[22px] w-[74px]" />
          <Skeleton className="h-[22px] w-12" />
          <Skeleton className="h-[22px] w-14" />
          <Skeleton className="h-[22px] w-[72px]" />
        </div>
      </div>
      <div className="flex flex-col gap-3 px-[22px] py-4">
        {[100, 96, 88, 100, 42].map((width, index) => (
          <Skeleton key={index} className="h-3" style={{ width: `${width}%` }} />
        ))}
        <Skeleton className="mt-4 h-[120px]" />
        <Skeleton className="mt-3 h-[150px]" />
      </div>
    </div>
  );
}

/** The pipeline, the tabs and a few lines of the results. */
export function ResultsSkeleton() {
  return (
    <div aria-hidden="true" className="flex flex-col gap-3 px-3.5 pt-3.5">
      <div className="flex justify-between">
        <Skeleton className="h-2.5 w-[120px]" />
        <Skeleton className="h-2.5 w-20" />
      </div>
      <div className="flex gap-[3px]">
        {[3, 4, 3, 3].map((grow, index) => (
          <Skeleton key={index} className="h-11" style={{ flexGrow: grow }} />
        ))}
      </div>
      <div className="flex gap-[18px] border-b border-bd pb-2">
        {[60, 50, 130, 50, 56].map((width, index) => (
          <Skeleton key={index} className="h-2.5" style={{ width }} />
        ))}
      </div>
      <div className="flex flex-col gap-[9px]">
        {RESULT_LINES.map((width, index) => (
          <Skeleton key={index} className="h-2.5" style={{ width: `${width}%` }} />
        ))}
      </div>
    </div>
  );
}
