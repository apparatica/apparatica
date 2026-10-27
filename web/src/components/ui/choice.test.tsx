import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it } from "vitest";

import { Checkbox } from "./checkbox";
import { RadioGroup, RadioGroupItem } from "./radio-group";
import { Switch } from "./switch";

it("checks and unchecks a checkbox", async () => {
  render(
    <>
      <label>
        <Checkbox /> Только нерешённые
      </label>
      <label>
        <Checkbox disabled /> Недоступно
      </label>
    </>,
  );
  const box = screen.getByRole("checkbox", { name: "Только нерешённые" });
  expect(box).not.toBeChecked();
  await userEvent.click(box);
  expect(box).toBeChecked();
  expect(box).toHaveAttribute("data-state", "checked");
  await userEvent.click(screen.getByText("Только нерешённые"));
  expect(box).not.toBeChecked();

  const off = screen.getByRole("checkbox", { name: "Недоступно" });
  await userEvent.click(off);
  expect(off).toBeDisabled();
  expect(off).not.toBeChecked();
});

it("chooses one option of a radio group", async () => {
  render(
    <RadioGroup defaultValue="week" aria-label="Период">
      <label>
        <RadioGroupItem value="day" /> День
      </label>
      <label>
        <RadioGroupItem value="week" /> Неделя
      </label>
      <label>
        <RadioGroupItem value="all" disabled /> Всё время
      </label>
    </RadioGroup>,
  );
  expect(screen.getByRole("radio", { name: "Неделя" })).toBeChecked();
  await userEvent.click(screen.getByRole("radio", { name: "День" }));
  expect(screen.getByRole("radio", { name: "День" })).toBeChecked();
  expect(screen.getByRole("radio", { name: "Неделя" })).not.toBeChecked();
  await userEvent.click(screen.getByRole("radio", { name: "Всё время" }));
  expect(screen.getByRole("radio", { name: "Всё время" })).not.toBeChecked();
});

it("turns a switch on and off", async () => {
  render(
    <label>
      <Switch /> Прокрутка за выводом
    </label>,
  );
  const toggle = screen.getByRole("switch", { name: "Прокрутка за выводом" });
  expect(toggle).not.toBeChecked();
  await userEvent.click(toggle);
  expect(toggle).toBeChecked();
  await userEvent.keyboard(" ");
  expect(toggle).not.toBeChecked();
});
