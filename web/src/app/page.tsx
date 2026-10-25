import { redirect } from "next/navigation";

// The dashboard arrives in Ф4 (specs/08 §1); until then the home page is the catalogue.
export default function Home(): never {
  redirect("/problems");
}
