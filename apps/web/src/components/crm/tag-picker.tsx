"use client";

import { useState } from "react";
import { Plus } from "lucide-react";
import { useQueryClient } from "@tanstack/react-query";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { apiFetch } from "@/lib/api";
import { useTags } from "@/lib/queries";
import type { Ref } from "@/lib/types";
import { cn } from "@/lib/utils";

export function TagPicker({ value, onChange }: { value: string[]; onChange: (ids: string[]) => void }) {
  const { data: tags = [] } = useTags();
  const queryClient = useQueryClient();
  const [draft, setDraft] = useState("");

  function toggle(id: string) {
    onChange(value.includes(id) ? value.filter((v) => v !== id) : [...value, id]);
  }

  async function add() {
    const name = draft.trim();
    if (!name) return;
    const tag = await apiFetch<Ref>("/tags", { method: "POST", body: JSON.stringify({ name }) });
    await queryClient.invalidateQueries({ queryKey: ["tags"] });
    if (!value.includes(tag.id)) onChange([...value, tag.id]);
    setDraft("");
  }

  return (
    <div className="space-y-2">
      <div className="flex flex-wrap gap-1.5" role="group" aria-label="برچسب‌ها">
        {tags.map((tag) => {
          const selected = value.includes(tag.id);
          return (
            <button
              key={tag.id}
              type="button"
              aria-pressed={selected}
              onClick={() => toggle(tag.id)}
              className={cn(
                "rounded-full border px-2.5 py-0.5 text-xs transition-colors",
                selected ? "border-primary bg-accent text-accent-foreground" : "text-muted-foreground hover:bg-muted",
              )}
            >
              {tag.name}
            </button>
          );
        })}
      </div>
      <div className="flex gap-2">
        <Input
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") {
              e.preventDefault();
              void add();
            }
          }}
          placeholder="برچسب تازه"
          aria-label="برچسب تازه"
          className="h-8"
        />
        <Button type="button" variant="outline" size="sm" onClick={() => void add()} disabled={!draft.trim()}>
          <Plus aria-hidden />
          افزودن
        </Button>
      </div>
    </div>
  );
}
