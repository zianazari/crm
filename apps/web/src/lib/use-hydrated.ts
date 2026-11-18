import { useSyncExternalStore } from "react";

const noopSubscribe = () => () => {};

/**
 * False on the server and during hydration, true afterwards. Parts of a page can hydrate
 * after shared queries (the user, the workload) have already loaded, while the server
 * rendered them without that data; such parts wait for this before using it.
 */
export function useHydrated(): boolean {
  return useSyncExternalStore(noopSubscribe, () => true, () => false);
}
