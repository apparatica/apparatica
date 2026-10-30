// The open tab of the left panel of the problem page, or of its phone view, kept in the address.
import { useState } from "react";

import { type LeftTab, parseLeftTab, setPageQuery } from "./page-query";

export function useLeftTab(initial: LeftTab): [LeftTab, (value: string) => void] {
  const [tab, setTab] = useState(initial);
  const select = (value: string) => {
    const next = parseLeftTab(value);
    setTab(next);
    setPageQuery({ tab: next === "statement" ? null : next });
  };
  return [tab, select];
}
