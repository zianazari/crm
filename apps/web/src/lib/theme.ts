"use client";

/** Light, dark or follow the system (spec section 12, stage 4). The choice is kept in
 * this browser only; a script in the root layout applies it before the first paint so
 * the page never flashes the wrong theme. */

import { useSyncExternalStore } from "react";

export type ThemeChoice = "light" | "dark" | "system";

export const THEME_KEY = "crm-theme";
const EVENT = "crm-theme-change";

/** Runs in <head> before the page paints. Keep it tiny and dependency free. */
export const THEME_SCRIPT = `(function(){try{var c=localStorage.getItem("${THEME_KEY}");var d=c==="dark"||(c!=="light"&&matchMedia("(prefers-color-scheme: dark)").matches);var e=document.documentElement;e.classList.toggle("dark",d);e.style.colorScheme=d?"dark":"light"}catch(_){}})()`;

function stored(): ThemeChoice {
  try {
    const value = localStorage.getItem(THEME_KEY);
    return value === "light" || value === "dark" ? value : "system";
  } catch {
    return "system";
  }
}

function systemDark(): boolean {
  return window.matchMedia("(prefers-color-scheme: dark)").matches;
}

export function applyTheme(choice: ThemeChoice = stored()) {
  const dark = choice === "dark" || (choice === "system" && systemDark());
  const root = document.documentElement;
  root.classList.toggle("dark", dark);
  root.style.colorScheme = dark ? "dark" : "light";
}

function subscribe(onChange: () => void): () => void {
  const media = window.matchMedia("(prefers-color-scheme: dark)");
  const update = () => {
    applyTheme();
    onChange();
  };
  media.addEventListener("change", update);
  window.addEventListener("storage", update);
  window.addEventListener(EVENT, onChange);
  return () => {
    media.removeEventListener("change", update);
    window.removeEventListener("storage", update);
    window.removeEventListener(EVENT, onChange);
  };
}

export function setTheme(choice: ThemeChoice) {
  try {
    if (choice === "system") localStorage.removeItem(THEME_KEY);
    else localStorage.setItem(THEME_KEY, choice);
  } catch {
    // private mode: still switch for this page
  }
  applyTheme(choice);
  window.dispatchEvent(new Event(EVENT));
}

/** The saved choice ("system" while rendering on the server). */
export function useThemeChoice(): ThemeChoice {
  return useSyncExternalStore(subscribe, stored, () => "system");
}

function resolved(): "light" | "dark" {
  return document.documentElement.classList.contains("dark") ? "dark" : "light";
}

/** What is on screen now, for components that draw their own colors. */
export function useResolvedTheme(): "light" | "dark" {
  return useSyncExternalStore(subscribe, resolved, () => "light");
}
