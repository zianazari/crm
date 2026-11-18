"use client";

import { useState, type DragEvent } from "react";
import { useRouter } from "next/navigation";
import { Building2, CalendarPlus, CircleCheck, CircleX, EllipsisVertical, Lock, Plus } from "lucide-react";

import { NextActionPill } from "@/components/crm/activity-bits";
import { ActivityFormDialog } from "@/components/crm/activity-form-dialog";

import { Owner } from "@/components/crm/bits";
import { CloseDealDialog, type CloseMode } from "@/components/crm/close-deal-dialog";
import { DealFormDialog } from "@/components/crm/deal-form-dialog";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuGroup,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Skeleton } from "@/components/ui/skeleton";
import { useMoveDeal } from "@/lib/deal-actions";
import { formatNumber, formatToman } from "@/lib/format";
import { formatIsoDate } from "@/lib/jalali";
import type { Board, Deal, DealFull, Stage } from "@/lib/types";
import { cn } from "@/lib/utils";

const STAGE_DOTS = ["bg-slate-400", "bg-sky-500", "bg-amber-500", "bg-violet-500", "bg-teal-500", "bg-rose-400"];

type Closing = { deal: DealFull; mode: CloseMode } | null;

export function DealBoard({ board, stages }: { board: Board; stages: Stage[] }) {
  const move = useMoveDeal();
  const [dragging, setDragging] = useState<DealFull | null>(null);
  const [over, setOver] = useState<string | null>(null);
  const [closing, setClosing] = useState<Closing>(null);

  function dropProps(target: string, onDrop: (deal: DealFull) => void) {
    return {
      onDragOver: (e: DragEvent) => {
        if (!dragging) return;
        e.preventDefault();
        e.dataTransfer.dropEffect = "move";
        setOver(target);
      },
      onDragLeave: () => setOver((current) => (current === target ? null : current)),
      onDrop: (e: DragEvent) => {
        e.preventDefault();
        setOver(null);
        if (dragging) onDrop(dragging);
        setDragging(null);
      },
    };
  }

  const cardProps = {
    stages,
    onDragStart: setDragging,
    onDragEnd: () => {
      setDragging(null);
      setOver(null);
    },
    onMove: (deal: DealFull, stage: Stage) => void move(deal, stage),
    onClose: (deal: DealFull, mode: CloseMode) => setClosing({ deal, mode }),
  };

  return (
    <>
      <div className="-mx-4 flex gap-3 overflow-x-auto px-4 pb-3 md:-mx-6 md:px-6" aria-label="تابلوی فروش">
        {board.columns.map((column, index) => (
          <section
            key={column.stage.id}
            aria-label={column.stage.name}
            className={cn(
              "flex w-64 shrink-0 flex-col rounded-xl border bg-muted/40 transition-colors",
              over === column.stage.id && "border-primary bg-accent/60",
            )}
            {...dropProps(column.stage.id, (deal) => void move(deal, column.stage))}
          >
            <header className="space-y-1 border-b px-3 py-2.5">
              <div className="flex items-center justify-between gap-2">
                <h2 className="flex items-center gap-2 font-semibold">
                  <span className={cn("size-2 rounded-full", STAGE_DOTS[index % STAGE_DOTS.length])} aria-hidden />
                  {column.stage.name}
                </h2>
                <DealFormDialog
                  stageId={column.stage.id}
                  trigger={
                    <Button variant="ghost" size="icon-sm" aria-label={`فروش جدید در ${column.stage.name}`}>
                      <Plus />
                    </Button>
                  }
                />
              </div>
              <p className="text-xs text-muted-foreground">
                {formatNumber(column.count)} فروش · {formatToman(column.total_amount)}
              </p>
            </header>
            <div className="flex min-h-32 flex-1 flex-col gap-2 p-2">
              {column.deals.map((deal) => (
                <DealCard key={deal.id} deal={deal} {...cardProps} />
              ))}
              {column.truncated ? (
                <p className="py-2 text-center text-xs text-muted-foreground">موارد بیشتر در نمای فهرست</p>
              ) : null}
            </div>
          </section>
        ))}

        <section
          aria-label="نتیجه نهایی"
          className={cn(
            "flex w-64 shrink-0 flex-col rounded-xl border border-dashed bg-muted/20 transition-colors",
            over === "outcome" && "border-primary bg-accent/60",
          )}
          {...dropProps("outcome", (deal) => setClosing({ deal, mode: "won" }))}
        >
          <header className="space-y-1 border-b px-3 py-2.5">
            <h2 className="font-semibold">نتیجه نهایی</h2>
            <p className="flex flex-wrap gap-x-3 text-xs text-muted-foreground">
              <span className="flex items-center gap-1">
                <CircleCheck className="size-3.5 text-primary" aria-hidden />
                {formatNumber(board.outcome.won_count)} موفق · {formatToman(board.outcome.won_total)}
              </span>
              <span className="flex items-center gap-1">
                <CircleX className="size-3.5 text-destructive" aria-hidden />
                {formatNumber(board.outcome.lost_count)} ناموفق
              </span>
            </p>
            <p className="text-xs text-muted-foreground">بسته‌شده از {formatIsoDate(board.outcome.closed_from)}</p>
          </header>
          <div className="flex min-h-32 flex-1 flex-col gap-2 p-2">
            {dragging ? (
              <p className="rounded-lg border border-dashed border-primary/50 p-3 text-center text-xs text-primary">
                برای ثبت نتیجه اینجا رها کنید
              </p>
            ) : null}
            {board.outcome.deals.map((deal) => (
              <DealCard key={deal.id} deal={deal} {...cardProps} />
            ))}
          </div>
        </section>
      </div>

      {closing ? (
        <CloseDealDialog
          key={`${closing.deal.id}-${closing.mode}`}
          deal={closing.deal}
          mode={closing.mode}
          onOpenChange={(open) => !open && setClosing(null)}
        />
      ) : null}
    </>
  );
}

function DealCard({
  deal,
  stages,
  onDragStart,
  onDragEnd,
  onMove,
  onClose,
}: {
  deal: Deal;
  stages: Stage[];
  onDragStart: (deal: DealFull) => void;
  onDragEnd: () => void;
  onMove: (deal: DealFull, stage: Stage) => void;
  onClose: (deal: DealFull, mode: CloseMode) => void;
}) {
  const router = useRouter();
  const full = deal.access === "full" ? deal : null;
  const movable = full !== null && full.status === "open";

  return (
    <article
      draggable={movable}
      onDragStart={(e) => {
        if (!full) return;
        e.dataTransfer.effectAllowed = "move";
        e.dataTransfer.setData("text/plain", full.id);
        onDragStart(full);
      }}
      onDragEnd={onDragEnd}
      onClick={() => router.push(`/deals/${deal.id}`)}
      className={cn(
        "group cursor-pointer space-y-2 rounded-lg border bg-card p-3 text-sm shadow-xs transition-shadow hover:shadow-sm",
        movable && "active:cursor-grabbing",
      )}
    >
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0 space-y-0.5">
          <p className="flex items-center gap-1.5 font-semibold">
            <Building2 className="size-4 shrink-0 text-muted-foreground" aria-hidden />
            <span className="truncate">{deal.customer.full_name}</span>
            {full ? null : <Lock className="size-3.5 shrink-0 text-muted-foreground" aria-label="فقط وضعیت فعلی" />}
          </p>
          <p className="truncate text-muted-foreground">{deal.title}</p>
        </div>
        {movable ? (
          <DropdownMenu>
            <DropdownMenuTrigger
              onClick={(e) => e.stopPropagation()}
              aria-label={`عملیات ${deal.title}`}
              className="rounded-md p-1 text-muted-foreground opacity-70 hover:bg-muted group-hover:opacity-100 focus-visible:opacity-100"
            >
              <EllipsisVertical className="size-4" />
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end" className="w-52" onClick={(e) => e.stopPropagation()}>
              <DropdownMenuGroup>
                <DropdownMenuLabel>انتقال به</DropdownMenuLabel>
                {stages
                  .filter((s) => s.id !== deal.stage.id)
                  .map((stage) => (
                    <DropdownMenuItem key={stage.id} onClick={() => onMove(full, stage)}>
                      {stage.name}
                    </DropdownMenuItem>
                  ))}
              </DropdownMenuGroup>
              <DropdownMenuSeparator />
              <DropdownMenuItem onClick={() => onClose(full, "won")}>
                <CircleCheck aria-hidden />
                فروش انجام شد
              </DropdownMenuItem>
              <DropdownMenuItem onClick={() => onClose(full, "lost")}>
                <CircleX aria-hidden />
                به نتیجه نرسید
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        ) : null}
      </div>

      {full ? (
        <p className="font-semibold">
          {full.status === "won" && full.contract_amount !== null
            ? formatToman(full.contract_amount)
            : full.amount !== null
              ? formatToman(full.amount)
              : "بدون مبلغ"}
        </p>
      ) : null}

      {full && full.status === "open" ? (
        <div className="flex items-center justify-between gap-2" onClick={(e) => e.stopPropagation()}>
          <NextActionPill next={full.next_activity} />
          {!full.next_activity ? (
            <ActivityFormDialog
              compact
              subject={{ deal: { id: full.id, name: full.title } }}
              trigger={
                <Button variant="ghost" size="icon-sm" aria-label="ساخت فعالیت برای این فروش">
                  <CalendarPlus />
                </Button>
              }
            />
          ) : null}
        </div>
      ) : null}

      <div className="flex items-center justify-between gap-2 text-xs">
        <Owner user={deal.owner} className="min-w-0 text-muted-foreground" />
        {deal.status === "won" ? (
          <span className="flex shrink-0 items-center gap-1 whitespace-nowrap rounded-full bg-success px-2 py-0.5 font-medium text-success-foreground">
            <CircleCheck className="size-3.5" aria-hidden />
            فروش انجام شد
          </span>
        ) : deal.status === "lost" ? (
          <span className="flex shrink-0 items-center gap-1 whitespace-nowrap rounded-full bg-destructive/10 px-2 py-0.5 font-medium text-destructive">
            <CircleX className="size-3.5" aria-hidden />
            به نتیجه نرسید
          </span>
        ) : null}
      </div>
    </article>
  );
}

export function BoardSkeleton() {
  return (
    <div className="flex gap-3 overflow-hidden">
      {Array.from({ length: 5 }, (_, i) => (
        <div key={i} className="w-64 shrink-0 space-y-2 rounded-xl border bg-muted/40 p-3">
          <Skeleton className="h-5 w-24" />
          <Skeleton className="h-24" />
          <Skeleton className="h-24" />
        </div>
      ))}
    </div>
  );
}
