"use client";

import { Moon, Sun } from "lucide-react";

import { Button } from "@/components/ui/button";
import { setTheme, useResolvedTheme } from "@/lib/theme";

/** One button between light and dark, for pages without the staff user menu. */
export function ThemeToggle() {
  const theme = useResolvedTheme();
  const dark = theme === "dark";
  return (
    <Button
      variant="ghost"
      size="icon-sm"
      aria-label={dark ? "ظاهر روشن" : "ظاهر تیره"}
      title={dark ? "ظاهر روشن" : "ظاهر تیره"}
      onClick={() => setTheme(dark ? "light" : "dark")}
    >
      {dark ? <Sun aria-hidden /> : <Moon aria-hidden />}
    </Button>
  );
}
