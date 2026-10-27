import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it } from "vitest";

import { Kbd } from "./kbd";
import { Field, Input, SearchInput } from "./input";

it("links the label and the hint to the field", async () => {
  render(
    <Field label="Имя" hint="Показывается в рейтинге">
      {(control) => <Input {...control} />}
    </Field>,
  );
  const input = screen.getByRole("textbox", { name: "Имя" });
  expect(input).toHaveAccessibleDescription("Показывается в рейтинге");
  expect(input).not.toHaveAttribute("aria-invalid");
  await userEvent.type(input, "ivan");
  expect(input).toHaveValue("ivan");
});

it("shows an error instead of the hint", () => {
  render(
    <Field label="Почта" hint="Для входа" error="Введите адрес полностью">
      {(control) => <Input {...control} defaultValue="ivan@" />}
    </Field>,
  );
  const input = screen.getByRole("textbox", { name: "Почта" });
  expect(input).toBeInvalid();
  expect(input).toHaveAccessibleDescription("Введите адрес полностью");
  expect(screen.queryByText("Для входа")).not.toBeInTheDocument();
  const note = screen.getByText("Введите адрес полностью");
  expect(note).toHaveClass("text-er");
  expect(note.querySelector("svg")).toBeInTheDocument();
});

it("takes no input while disabled", async () => {
  render(
    <Field label="Имя">{(control) => <Input {...control} disabled defaultValue="ivan" />}</Field>,
  );
  const input = screen.getByRole("textbox", { name: "Имя" });
  expect(input).toBeDisabled();
  expect(input).not.toHaveAccessibleDescription();
  await userEvent.type(input, "x");
  expect(input).toHaveValue("ivan");
});

it("is a search field with the hint of its key", async () => {
  render(<SearchInput aria-label="Найти задачу" placeholder="Найти задачу" hint={<Kbd>/</Kbd>} />);
  const input = screen.getByRole("searchbox", { name: "Найти задачу" });
  await userEvent.type(input, "fifo");
  expect(input).toHaveValue("fifo");
  expect(screen.getByText("/").tagName).toBe("KBD");
});
