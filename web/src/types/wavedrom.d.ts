// WaveDrom has no types. The part the statement renderer uses: a diagram as an onml tree
// (`[tag, attributes?, ...children]`) and its serialisation.
declare module "wavedrom" {
  export type Onml = [string, ...(Record<string, string | number> | Onml | string)[]];

  export function renderAny(index: number, source: unknown, skin: unknown): Onml;
  export const waveSkin: unknown;
  export const onml: { stringify: (tree: Onml) => string };
}
