"use client";

import { useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";

import { ApiError, apiFetch } from "@/lib/api";
import { keys } from "@/lib/queries";
import type { Board, DealFull, Stage } from "@/lib/types";

/** Move a deal to another stage: the board updates at once, then the server decides.
 * On rejection or a conflict the board is reloaded so it shows the server's state
 * (spec 4.3: a failed save must not leave the card in the wrong column). */
export function useMoveDeal() {
  const queryClient = useQueryClient();

  return async function move(deal: DealFull, stage: Stage) {
    if (deal.stage.id === stage.id) return;
    await queryClient.cancelQueries({ queryKey: [...keys.deals, "board"] });
    queryClient.setQueriesData<Board>({ queryKey: [...keys.deals, "board"] }, (board) =>
      board ? moveInBoard(board, deal, stage) : board,
    );
    try {
      await apiFetch(`/deals/${deal.id}/move`, {
        method: "POST",
        body: JSON.stringify({ stage_id: stage.id, version: deal.version }),
      });
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "انتقال انجام نشد.");
    } finally {
      await queryClient.invalidateQueries({ queryKey: keys.deals });
    }
  };
}

function moveInBoard(board: Board, deal: DealFull, stage: Stage): Board {
  const amount = deal.amount ?? 0;
  return {
    ...board,
    columns: board.columns.map((column) => {
      if (column.stage.id === deal.stage.id) {
        return {
          ...column,
          count: column.count - 1,
          total_amount: column.total_amount - amount,
          deals: column.deals.filter((d) => d.id !== deal.id),
        };
      }
      if (column.stage.id === stage.id) {
        const moved: DealFull = { ...deal, stage: { id: stage.id, name: stage.name } };
        return {
          ...column,
          count: column.count + 1,
          total_amount: column.total_amount + amount,
          deals: [moved, ...column.deals],
        };
      }
      return column;
    }),
  };
}
