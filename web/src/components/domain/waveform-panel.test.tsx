import { composeStories } from "@storybook/react";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import * as stories from "./waveform-panel.stories";

const { Normal, Loading, LoadingWithCaption, Empty, EmptyWithAction, Failed, TooBig } =
  composeStories(stories);

const panel = () => screen.getByRole("region", { name: "Волны" });
/** The stand-in of the viewer: always in the page, covered and inert but in the normal state. */
const viewer = () => screen.getByText("Surfer").parentElement;

describe("the states", () => {
  it("normal: the header and the viewer", () => {
    render(<Normal />);
    expect(panel()).toHaveAttribute("data-state", "normal");
    expect(screen.getByRole("heading", { level: 3 })).toHaveTextContent(
      "Такты 0–46 · окно вокруг первого расхождения",
    );
    expect(screen.getByText("47 тактов · FST 2,4 кБ")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "К расхождению" })).toBeInTheDocument();
    expect(viewer()).not.toHaveAttribute("inert");
    expect(viewer()).toHaveAttribute("aria-hidden", "false");
  });

  it("loading: skeleton rows, the viewer kept but covered, no tools", () => {
    render(<Loading tools={<button type="button">tool</button>} />);
    expect(screen.getByRole("status", { name: "Волны загружаются" })).toBeInTheDocument();
    expect(viewer()).toHaveAttribute("inert");
    expect(viewer()).toHaveAttribute("aria-hidden", "true");
    expect(screen.queryByRole("button", { name: "tool" })).not.toBeInTheDocument();
  });

  it("loading with a caption", () => {
    render(<LoadingWithCaption />);
    expect(screen.getByRole("status", { name: /^Волны пересоздаются/ })).toHaveTextContent(
      "Волны пересоздаются",
    );
  });

  it("empty: «Волн пока нет», the header says «Волны»", () => {
    render(<Empty />);
    expect(screen.getByRole("heading", { level: 3 })).toHaveTextContent("Волны");
    expect(screen.getByText("Волн пока нет")).toBeInTheDocument();
    expect(screen.getByText("Они появятся после запуска симуляции.")).toBeInTheDocument();
  });

  it("empty with an action", async () => {
    render(<EmptyWithAction />);
    expect(screen.getByText("Волны удалены по сроку хранения")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Пересоздать волны" }));
  });

  it("error: «Повторить» retries", async () => {
    const onRetry = vi.fn();
    render(<Failed state={{ kind: "error", onRetry }} />);
    expect(screen.getByText("Не удалось загрузить волны")).toBeInTheDocument();
    expect(screen.getByText("Файл не получен от сервера.")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Повторить" }));
    expect(onRetry).toHaveBeenCalledOnce();
  });

  it("too big: the size and the download", () => {
    render(<TooBig />);
    expect(screen.getByText("Файл волн 48 МБ")).toBeInTheDocument();
    expect(screen.getByText("Слишком большой для просмотра в браузере.")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Скачать FST" })).toHaveAttribute(
      "href",
      "/api/v1/submissions/1/artifacts/fst",
    );
  });
});
