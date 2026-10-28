import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import Link from "next/link";
import { expect, it, vi } from "vitest";

import { Button } from "./button";
import { Shortcut } from "./kbd";

it("has the four looks of sheet CmpD and the outline of Run", () => {
  render(
    <>
      <Button variant="primary">Submit</Button>
      <Button>Run</Button>
      <Button variant="outline">Run на открытых</Button>
      <Button variant="ghost">Сбросить</Button>
      <Button variant="selected">Режим</Button>
    </>,
  );
  expect(screen.getByRole("button", { name: "Submit" })).toHaveClass("bg-ac", "text-acx");
  expect(screen.getByRole("button", { name: "Run" })).toHaveClass("bg-sf", "border-bc");
  expect(screen.getByRole("button", { name: "Run на открытых" })).toHaveClass(
    "border-ac",
    "text-ac",
  );
  expect(screen.getByRole("button", { name: "Сбросить" })).toHaveClass("border-transparent");
  expect(screen.getByRole("button", { name: "Режим" })).toHaveClass("bg-acs", "border-ac");
});

it("does nothing while disabled or loading", async () => {
  const click = vi.fn();
  render(
    <>
      <Button disabled onClick={click}>
        Недоступно
      </Button>
      <Button loading onClick={click}>
        Проверка…
      </Button>
    </>,
  );
  const loading = screen.getByRole("button", { name: "Проверка…" });
  expect(loading).toBeDisabled();
  expect(loading).toHaveAttribute("aria-busy", "true");
  expect(loading.querySelector("svg")).toHaveClass("animate-spin");
  await userEvent.click(screen.getByRole("button", { name: "Недоступно" }));
  await userEvent.click(loading);
  expect(click).not.toHaveBeenCalled();
});

it("is an icon button with a label, and a link when asked", () => {
  render(
    <>
      <Button size="icon" aria-label="Копировать">
        <svg aria-hidden="true" />
      </Button>
      <Button asChild variant="primary">
        <Link href="/problems">К задачам</Link>
      </Button>
    </>,
  );
  expect(screen.getByRole("button", { name: "Копировать" })).toHaveClass("w-[30px]");
  expect(screen.getByRole("link", { name: "К задачам" })).toHaveClass("bg-ac");
});

it("shows a shortcut hint", () => {
  render(
    <Button variant="primary">
      Run <Shortcut keys={["Mod", "Enter"]} />
    </Button>,
  );
  expect(screen.getByRole("button")).toHaveTextContent("Run Ctrl ↵");
});
