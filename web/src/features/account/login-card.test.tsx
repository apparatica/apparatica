import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http } from "msw";
import { expect, it, vi } from "vitest";

import { Toaster } from "@/components/ui/toast";
import type { AltchaWidgetProps } from "@/features/captcha/altcha-widget";
import type { Schemas } from "@/lib/api/client";
import { api, problem } from "@/mocks/http";
import { server } from "@/mocks/server";
import { renderWithProviders } from "@/test/render";

import { LoginCard } from "./login-card";
import { LoginPage, type LoginPageProps } from "./login-page";

// The widget runs workers; this one is solved by a click.
vi.mock("@/features/captcha/altcha-widget", () => ({
  AltchaWidget: ({ onChange }: AltchaWidgetProps) => (
    <button type="button" onClick={() => onChange("solved")}>
      Я не робот
    </button>
  ),
}));

const GITHUB: Schemas["AuthProvider"] = { key: "github", title: "GitHub", kind: "oauth" };
const EMAIL: Schemas["AuthProvider"] = { key: "email", title: "Email", kind: "email" };

function renderCard(props: Partial<LoginPageProps> = {}) {
  return renderWithProviders(
    <>
      <LoginCard providers={[GITHUB, EMAIL]} next={null} error={null} {...props} />
      <Toaster />
    </>,
  );
}

/** Captures the bodies of the requested login links; the mocks answer. */
function captureRequests(): Schemas["EmailLoginRequest"][] {
  const bodies: Schemas["EmailLoginRequest"][] = [];
  server.use(
    http.post(api("/api/v1/auth/email/request"), async ({ request }) => {
      bodies.push((await request.clone().json()) as Schemas["EmailLoginRequest"]);
      return undefined;
    }),
  );
  return bodies;
}

it("shows the enabled providers, the guest way and the consent", () => {
  renderCard({ next: "/problems/mux4" });
  expect(screen.getByRole("heading", { level: 1, name: "Войти в Apparatica" })).toBeInTheDocument();
  expect(screen.getByRole("link", { name: "Войти через GitHub" })).toHaveAttribute(
    "href",
    "/api/v1/auth/github/login?next=%2Fproblems%2Fmux4",
  );
  expect(screen.getByText("или по email")).toBeInTheDocument();
  expect(screen.getByRole("textbox", { name: "Почта" })).toBeInTheDocument();
  expect(screen.getByRole("link", { name: "Продолжить как гость →" })).toHaveAttribute(
    "href",
    "/problems/mux4",
  );
  expect(screen.getByRole("link", { name: "пользовательское соглашение" })).toHaveAttribute(
    "href",
    "/legal/terms",
  );
  expect(
    screen.getByRole("link", { name: "политику обработки персональных данных" }),
  ).toHaveAttribute("href", "/legal/privacy");
  expect(screen.queryByRole("alert")).not.toBeInTheDocument();
});

it("hides what is not enabled", () => {
  const { unmount } = renderCard({ providers: [EMAIL] });
  expect(screen.queryByRole("link", { name: /Войти через/ })).not.toBeInTheDocument();
  expect(screen.queryByText("или по email")).not.toBeInTheDocument();
  expect(screen.getByRole("link", { name: "Продолжить как гость →" })).toHaveAttribute(
    "href",
    "/problems",
  );
  unmount();

  renderCard({ providers: [GITHUB] });
  expect(screen.getByRole("link", { name: "Войти через GitHub" })).toHaveAttribute(
    "href",
    "/api/v1/auth/github/login",
  );
  expect(screen.queryByRole("textbox", { name: "Почта" })).not.toBeInTheDocument();
});

it("says when no login is enabled", () => {
  renderCard({ providers: [] });
  expect(screen.getByText("Вход сейчас недоступен.")).toBeInTheDocument();
});

it("explains why a login through a provider failed", () => {
  const { unmount } = renderCard({ error: "invalid_state" });
  expect(screen.getByRole("alert")).toHaveTextContent(
    "Вход устарел или начат в другом браузере. Начните его заново.",
  );
  unmount();

  renderCard({ error: "something" });
  expect(screen.getByRole("alert")).toHaveTextContent("Не удалось войти. Попробуйте ещё раз.");
});

it("sends a login link, then sends it again or to another address", async () => {
  const user = userEvent.setup();
  const bodies = captureRequests();
  renderCard({ next: "/settings" });
  const field = screen.getByRole("textbox", { name: "Почта" });

  await user.type(field, "ada@example");
  await user.click(screen.getByRole("button", { name: "Получить ссылку для входа" }));
  expect(field).toHaveAttribute("aria-invalid", "true");
  expect(field).toHaveAccessibleDescription("Проверьте адрес почты: например, name@example.com.");
  expect(bodies).toEqual([]);

  await user.type(field, ".com ");
  expect(field).not.toHaveAttribute("aria-invalid");
  await user.keyboard("{Enter}");
  const sent = await screen.findByRole("status");
  expect(within(sent).getByRole("heading", { name: "Проверьте почту" })).toBeInTheDocument();
  expect(sent).toHaveTextContent("Ссылка для входа отправлена на ada@example.com.");
  expect(bodies).toEqual([{ email: "ada@example.com", next: "/settings" }]);

  await user.click(within(sent).getByRole("button", { name: "Отправить ещё раз" }));
  expect(await screen.findByText("Ссылка отправлена ещё раз")).toBeInTheDocument();
  expect(bodies).toHaveLength(2);

  await user.click(within(sent).getByRole("button", { name: "Другой адрес" }));
  expect(screen.getByRole("textbox", { name: "Почта" })).toHaveValue("ada@example.com");
});

it("says how long to wait when links are asked too often", async () => {
  const user = userEvent.setup();
  server.use(
    http.post(api("/api/v1/auth/email/request"), () =>
      problem(429, "RATE_LIMITED", "Too many logins", {
        quota: "logins",
        limit: 5,
        window_s: 3600,
        retry_after_s: 290,
      }),
    ),
  );
  renderCard();
  const field = screen.getByRole("textbox", { name: "Почта" });
  await user.type(field, "ada@example.com{Enter}");
  expect(
    await screen.findByText("Слишком много ссылок для входа. Попробуйте через 5 минут."),
  ).toBeInTheDocument();
  expect(field).not.toHaveAttribute("aria-invalid");
});

it("asks for a captcha when the API wants one and sends the link with it", async () => {
  const user = userEvent.setup();
  const bodies = captureRequests();
  let asked = false;
  server.use(
    http.post(api("/api/v1/auth/email/request"), () => {
      if (asked) return undefined;
      asked = true;
      return problem(428, "CAPTCHA_REQUIRED", "Captcha required", {
        reason: "always",
        challenge_url: "/api/v1/captcha/challenge",
      });
    }),
  );
  renderCard();
  await user.type(screen.getByRole("textbox", { name: "Почта" }), "ada@example.com{Enter}");
  const dialog = await screen.findByRole("dialog", { name: "Подтвердите, что вы человек" });
  expect(dialog).toHaveAccessibleDescription(
    "Пройдите короткую проверку, чтобы получить ссылку для входа.",
  );

  await user.click(within(dialog).getByRole("button", { name: "Я не робот" }));
  await user.click(within(dialog).getByRole("button", { name: "Продолжить" }));
  expect(await screen.findByRole("heading", { name: "Проверьте почту" })).toBeInTheDocument();
  expect(bodies.at(-1)).toEqual({ email: "ada@example.com", next: null, captcha: "solved" });
});

it("tells what the platform checks now, without the stages of later phases", () => {
  renderWithProviders(<LoginPage providers={[EMAIL]} next={null} error={null} />);
  const about = screen.getByRole("region", { name: "О платформе" });
  const example = within(about).getByRole("figure", { name: "Пример результата проверки" });
  expect(
    within(example)
      .getAllByRole("listitem")
      .map((item) => item.textContent),
  ).toEqual(["Линт0,4 с", "Симуляция3,1 с"]);
  expect(about).not.toHaveTextContent(/синтез|формал|рейтинг/i);
});

it("says when the login by email is disabled", async () => {
  const user = userEvent.setup();
  server.use(
    http.post(api("/api/v1/auth/email/request"), () =>
      problem(404, "NOT_FOUND", "Login by email is disabled"),
    ),
  );
  renderCard();
  await user.type(screen.getByRole("textbox", { name: "Почта" }), "ada@example.com{Enter}");
  expect(await screen.findByText("Вход по почте сейчас недоступен.")).toBeInTheDocument();
});
