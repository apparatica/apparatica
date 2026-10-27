import { act, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { expect, it, vi } from "vitest";

import { renderWithProviders } from "@/test/render";

import { Button } from "./button";
import {
  Dialog,
  DialogBody,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "./dialog";
import {
  DropdownMenu,
  DropdownMenuCheckboxItem,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuRadioGroup,
  DropdownMenuRadioItem,
  DropdownMenuShortcut,
  DropdownMenuTrigger,
} from "./dropdown-menu";
import { notify, Toaster } from "./toast";
import { Tooltip, TooltipProvider } from "./tooltip";

it("opens a menu, highlights items and runs the chosen one", async () => {
  const copy = vi.fn();
  renderWithProviders(
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button>Ещё</Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent>
        <DropdownMenuItem onSelect={copy}>
          Скопировать ссылку
          <DropdownMenuShortcut>Ctrl L</DropdownMenuShortcut>
        </DropdownMenuItem>
        <DropdownMenuItem disabled>Скачать VCD</DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>,
  );
  await userEvent.click(screen.getByRole("button", { name: "Ещё" }));
  const item = screen.getByRole("menuitem", { name: /Скопировать ссылку/ });
  await userEvent.keyboard("{ArrowDown}");
  expect(item).toHaveAttribute("data-highlighted");
  expect(screen.getByRole("menuitem", { name: "Скачать VCD" })).toHaveAttribute(
    "aria-disabled",
    "true",
  );
  await userEvent.keyboard("{Enter}");
  expect(copy).toHaveBeenCalledOnce();
  expect(screen.queryByRole("menu")).not.toBeInTheDocument();
});

it("marks the chosen option of a radio menu", async () => {
  function Menu() {
    const [value, setValue] = useState("light");
    return (
      <DropdownMenu>
        <DropdownMenuTrigger>Тема</DropdownMenuTrigger>
        <DropdownMenuContent>
          <DropdownMenuLabel>Тема</DropdownMenuLabel>
          <DropdownMenuRadioGroup value={value} onValueChange={setValue}>
            <DropdownMenuRadioItem value="light">Светлая</DropdownMenuRadioItem>
            <DropdownMenuRadioItem value="dark">Тёмная</DropdownMenuRadioItem>
          </DropdownMenuRadioGroup>
        </DropdownMenuContent>
      </DropdownMenu>
    );
  }
  renderWithProviders(<Menu />);
  await userEvent.click(screen.getByRole("button", { name: "Тема" }));
  expect(screen.getByRole("menuitemradio", { name: "Светлая" })).toBeChecked();
  await userEvent.click(screen.getByRole("menuitemradio", { name: "Тёмная" }));
  await userEvent.click(screen.getByRole("button", { name: "Тема" }));
  expect(screen.getByRole("menuitemradio", { name: "Тёмная" })).toBeChecked();
});

it("checks several options of a menu and stays open between them", async () => {
  function Menu() {
    const [levels, setLevels] = useState(["easy"]);
    const toggle = (level: string) => (on: boolean) =>
      setLevels(on ? [...levels, level] : levels.filter((item) => item !== level));
    return (
      <DropdownMenu>
        <DropdownMenuTrigger>Сложность</DropdownMenuTrigger>
        <DropdownMenuContent>
          {["easy", "hard"].map((level) => (
            <DropdownMenuCheckboxItem
              key={level}
              checked={levels.includes(level)}
              onCheckedChange={toggle(level)}
              onSelect={(event) => event.preventDefault()}
            >
              {level}
            </DropdownMenuCheckboxItem>
          ))}
        </DropdownMenuContent>
      </DropdownMenu>
    );
  }
  renderWithProviders(<Menu />);
  await userEvent.click(screen.getByRole("button", { name: "Сложность" }));
  expect(screen.getByRole("menuitemcheckbox", { name: "easy" })).toBeChecked();
  await userEvent.click(screen.getByRole("menuitemcheckbox", { name: "hard" }));
  expect(screen.getByRole("menuitemcheckbox", { name: "hard" })).toBeChecked();
  await userEvent.click(screen.getByRole("menuitemcheckbox", { name: "easy" }));
  expect(screen.getByRole("menuitemcheckbox", { name: "easy" })).not.toBeChecked();
});

it("shows a tooltip on focus", async () => {
  renderWithProviders(
    <TooltipProvider delayDuration={0}>
      <Tooltip content="Сравнение появится после Submit">
        <Button>Задержка</Button>
      </Tooltip>
    </TooltipProvider>,
  );
  await userEvent.tab();
  expect(await screen.findByRole("tooltip")).toHaveTextContent("Сравнение появится после Submit");
  await userEvent.keyboard("{Escape}");
  await waitFor(() => expect(screen.queryByRole("tooltip")).not.toBeInTheDocument());
});

it("opens a dialog with a title, a footer and a close button", async () => {
  renderWithProviders(
    <Dialog>
      <DialogTrigger asChild>
        <Button>Пожаловаться</Button>
      </DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Пожаловаться на задачу</DialogTitle>
          <DialogDescription>Синхронный FIFO · версия 3</DialogDescription>
        </DialogHeader>
        <DialogBody>Что не так</DialogBody>
        <DialogFooter>
          <Button variant="primary">Отправить жалобу</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>,
  );
  await userEvent.click(screen.getByRole("button", { name: "Пожаловаться" }));
  const dialog = screen.getByRole("dialog", { name: "Пожаловаться на задачу" });
  expect(dialog).toHaveAccessibleDescription("Синхронный FIFO · версия 3");
  await userEvent.click(screen.getByRole("button", { name: "Закрыть" }));
  expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
});

it("notifies with the tone of the message and closes on request", async () => {
  renderWithProviders(<Toaster />);
  act(() => {
    notify({ tone: "ok", title: "Решение принято", description: "Вы заняли 12 место" });
    notify({ tone: "er", title: "Не удалось отправить" });
  });
  const accepted = (await screen.findByText("Решение принято")).closest("div.shadow-pop");
  expect(accepted).toHaveClass("border-l-ok");
  expect(accepted).toHaveTextContent("Вы заняли 12 место");
  const failed = screen.getByText("Не удалось отправить").closest("div.shadow-pop");
  expect(failed).toHaveClass("border-l-er");

  const [close] = screen.getAllByRole("button", { name: "Закрыть" });
  await userEvent.click(close as HTMLElement);
  await waitFor(() => expect(screen.getAllByRole("button", { name: "Закрыть" })).toHaveLength(1));
});
