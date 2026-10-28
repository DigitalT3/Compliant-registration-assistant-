import { createContext, useContext, useState, ReactNode } from "react";
import { nl } from "./nl";
import { en } from "./en";

export type Lang = "nl" | "en";
const dict: Record<Lang, Record<string, string>> = { nl, en };

const Ctx = createContext<{ lang: Lang; setLang: (l: Lang) => void; t: (k: string, v?: Record<string, string | number>) => string }>(null as any);

export function I18nProvider({ children }: { children: ReactNode }) {
  const [lang, setL] = useState<Lang>((localStorage.getItem("cra.lang") as Lang) || "nl");
  const setLang = (l: Lang) => {
    localStorage.setItem("cra.lang", l);
    setL(l);
  };
  const t = (k: string, v?: Record<string, string | number>) => {
    let s = dict[lang][k] ?? dict.en[k] ?? k;
    if (v) for (const [a, b] of Object.entries(v)) s = s.replace(`{${a}}`, String(b));
    return s;
  };
  return <Ctx.Provider value={{ lang, setLang, t }}>{children}</Ctx.Provider>;
}

export const useI18n = () => useContext(Ctx);
