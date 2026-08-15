"use client";

import { useState } from "react";

/**
 * Two-phase fade+slide transition between discrete UI states — swap the
 * underlying value only while it's invisible, so the change never "pops."
 * Used both for the landing/chat swap and, internally, for the homepage's
 * own hero/address-input swap, so it's shared rather than duplicated.
 */
export function useCrossfade<T>(initial: T, durationMs = 200) {
  const [stage, setStage] = useState<T>(initial);
  const [visible, setVisible] = useState(true);

  function transitionTo(next: T) {
    setVisible(false);
    window.setTimeout(() => {
      setStage(next);
      requestAnimationFrame(() => {
        requestAnimationFrame(() => setVisible(true));
      });
    }, durationMs);
  }

  return { stage, visible, transitionTo } as const;
}
