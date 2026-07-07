import { useMemo, useRef, useSyncExternalStore } from 'react';

type Snapshot = unknown;
type Selector<TSelection> = (snapshot: Snapshot) => TSelection;
type Equality<TSelection> = (left: TSelection, right: TSelection) => boolean;

export function useSyncExternalStoreWithSelector<TSelection>(
  subscribe: (onStoreChange: () => void) => () => void,
  getSnapshot: () => Snapshot,
  getServerSnapshot: undefined | null | (() => Snapshot),
  selector: Selector<TSelection>,
  isEqual: Equality<TSelection> = Object.is,
): TSelection {
  const memo = useRef<{
    hasValue: boolean;
    selection: TSelection | undefined;
    snapshot: Snapshot;
  }>({
    hasValue: false,
    selection: undefined,
    snapshot: undefined,
  });

  const getSelection = useMemo(() => {
    return (readSnapshot: () => Snapshot) => {
      return () => {
        const snapshot = readSnapshot();
        const nextSelection = selector(snapshot);
        const previous = memo.current;

        if (previous.hasValue) {
          if (Object.is(previous.snapshot, snapshot)) {
            return previous.selection as TSelection;
          }

          if (isEqual(previous.selection as TSelection, nextSelection)) {
            previous.snapshot = snapshot;
            return previous.selection as TSelection;
          }
        }

        previous.hasValue = true;
        previous.snapshot = snapshot;
        previous.selection = nextSelection;
        return nextSelection;
      };
    };
  }, [isEqual, selector]);

  return useSyncExternalStore(
    subscribe,
    getSelection(getSnapshot),
    getServerSnapshot ? getSelection(getServerSnapshot) : getSelection(getSnapshot),
  );
}
