import type { Metadata } from "next";
import { getTranslations } from "next-intl/server";

import { LoginPage } from "@/features/account/login-page";
import { serverApi } from "@/lib/api/server";
import { sitePath } from "@/lib/session";

export async function generateMetadata(): Promise<Metadata> {
  const t = await getTranslations("login");
  return { title: t("pageTitle") };
}

const one = (value: string | string[] | undefined) => (Array.isArray(value) ? value[0] : value);

export default async function Login({ searchParams }: PageProps<"/login">) {
  const { next, error } = await searchParams;
  // The enabled providers, in the order of their buttons (docs/api.md, «Провайдеры входа»).
  const config = await serverApi.GET("/api/v1/config");
  if (config.data === undefined) {
    throw new Error(`GET /config: ${config.error?.code ?? "no response"}`);
  }
  return (
    <LoginPage
      providers={config.data.auth_providers}
      next={sitePath(one(next))}
      error={one(error) ?? null}
    />
  );
}
