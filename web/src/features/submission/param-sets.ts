// Parameter sets of a check (ADR-0014, specs/06 §2): a stage checked at several sets runs as one
// instance per set, keyed `<stage key>@<set id>`; the primary set, the defaults of the interface,
// keeps the bare key.
import type { Schemas } from "@/lib/api/client";

export type ParamSet = Schemas["ParamSet"];

/** The id of the primary parameter set. */
export const PRIMARY_SET = "default";

/** The stage key of an instance key: `sim_full@narrow` → `sim_full`. */
export function stageKeyOf(key: string): string {
  const at = key.indexOf("@");
  return at === -1 ? key : key.slice(0, at);
}

/** The set of an instance at an extra parameter set; null at the primary one. */
export function extraSetOf(stage: { param_set?: ParamSet | null | undefined }): ParamSet | null {
  const set = stage.param_set ?? null;
  return set !== null && set.id !== PRIMARY_SET ? set : null;
}

/** The values of a set as the pages write them: `WIDTH=1, DEPTH=2`. */
export function setValues(set: ParamSet): string {
  return Object.entries(set.values)
    .map(([name, value]) => `${name}=${value}`)
    .join(", ");
}
