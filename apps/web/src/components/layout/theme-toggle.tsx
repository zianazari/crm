"use client";

import { Monitor, Moon, Sun } from "lucide-react";

import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuGroup,
  DropdownMenuLabel,
  DropdownMenuRadioGroup,
  DropdownMenuRadioItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { setTheme, useResolvedTheme, useThemeChoice, type ThemeChoice } from "@/lib/theme";

const OPTIONS: { value: ThemeChoice; label: string; icon: typeof Sun }[] = [
  { value: "light", label: "روشن", icon: Sun },
  { value: "dark", label: "تیره", icon: Moon },
  { value: "system", label: "مطابق دستگاه", icon: Monitor },
];

/** Light, dark or the device's setting; sits next to the notifications. */
export function ThemeMenu() {
  const choice = useThemeChoice();
  const resolved = useResolvedTheme();
  const Icon = resolved === "dark" ? Moon : Sun;
  const current = OPTIONS.find((o) => o.value === choice)?.label ?? "";
  return (
    <DropdownMenu>
      <DropdownMenuTrigger
        render={
          <Button variant="ghost" size="icon" aria-label={`ظاهر: ${current}`} title={`ظاهر: ${current}`}>
            <Icon className="size-5" aria-hidden />
          </Button>
        }
      />
      <DropdownMenuContent align="end" className="w-44">
        <DropdownMenuGroup>
          <DropdownMenuLabel>ظاهر</DropdownMenuLabel>
          <DropdownMenuRadioGroup value={choice} onValueChange={(value) => setTheme(value as ThemeChoice)}>
            {OPTIONS.map(({ value, label, icon: OptionIcon }) => (
              <DropdownMenuRadioItem key={value} value={value}>
                <OptionIcon aria-hidden />
                {label}
              </DropdownMenuRadioItem>
            ))}
          </DropdownMenuRadioGroup>
        </DropdownMenuGroup>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
