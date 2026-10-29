import { composeStories } from "@storybook/react";
import { render, screen } from "@testing-library/react";
import { expect, it } from "vitest";

import * as stories from "./statement.stories";

const { Full, Sanitized, Errors } = composeStories(stories);

it("renders text, formulas, a table, highlighted code and a timing diagram", () => {
  const { container } = render(<Full />);
  expect(screen.getByText("самое старое").tagName).toBe("STRONG");
  expect(screen.getAllByRole("listitem")).toHaveLength(2);
  // KaTeX: two inline formulas and a display one, with MathML for screen readers.
  expect(container.querySelectorAll(".katex")).toHaveLength(3);
  expect(container.querySelectorAll(".katex-display")).toHaveLength(1);
  expect(container.querySelector(".katex math")).not.toBeNull();
  expect(screen.getByRole("table")).toHaveTextContent("без изменений");
  const keyword = screen.getByText("always_ff");
  expect(keyword).toHaveStyle({ color: "var(--kw)" });
  expect(keyword.closest("pre")).toHaveClass("shiki");
  const diagram = screen.getByRole("img", { name: "Временная диаграмма" });
  expect(diagram.tagName.toLowerCase()).toBe("svg");
  expect(diagram.closest("figure")).toHaveClass("wavedrom");
  expect(diagram.querySelector("style")).toBeNull();
  expect(diagram.querySelector("#wd0-pclk")).not.toBeNull();
  expect(screen.getByRole("heading", { name: "Пример" })).toBeInTheDocument();
  const link = screen.getByRole("link", { name: "документации SystemVerilog" });
  expect(link).toHaveAttribute("target", "_blank");
  expect(link).toHaveAttribute("rel", "noopener noreferrer nofollow");
}, 15_000); // the first render loads KaTeX, WaveDrom and Shiki: slow when the suite loads the machine

it("cleans the HTML of the author", () => {
  const { container } = render(<Sanitized />);
  expect(screen.getByText("жирный").tagName).toBe("B");
  expect(container.querySelector("script")).toBeNull();
  expect(container.querySelector("[onerror], [style]")).toBeNull();
  expect(container.querySelector("img")).toBeNull(); // not from assets/
  expect(screen.getByText("ссылка")).not.toHaveAttribute("href");
});

it("shows broken formulas and diagrams as they are", () => {
  const { container } = render(<Errors />);
  expect(container.querySelector(".katex-error")).toHaveTextContent("\\frac{1}{");
  expect(container.querySelector("code.language-wavedrom")).toHaveTextContent("{signal: [");
});
