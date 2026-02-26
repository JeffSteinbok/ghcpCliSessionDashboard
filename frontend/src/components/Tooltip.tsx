/**
 * Custom tooltip — follows the mouse cursor on elements with `data-tip`.
 *
 * Uses event delegation on document to avoid per-element listeners,
 * with a 400ms hover delay before showing.
 */

import { useEffect, useRef, useCallback } from "react";
import { TOOLTIP_DELAY_MS, Z_TOOLTIP } from "../constants";

export default function Tooltip() {
  const tipRef = useRef<HTMLDivElement>(null);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const positionTip = useCallback(
    (e: MouseEvent) => {
      const t = tipRef.current;
      if (!t) return;
      const pad = 12;
      const vw = window.innerWidth;
      const vh = window.innerHeight;
      let x = e.clientX + pad;
      let y = e.clientY + pad;
      if (x + t.offsetWidth > vw - pad) x = e.clientX - t.offsetWidth - pad;
      if (y + t.offsetHeight > vh - pad) y = e.clientY - t.offsetHeight - pad;
      t.style.left = x + "px";
      t.style.top = y + "px";
    },
    [],
  );

  useEffect(() => {
    const handleOver = (e: MouseEvent) => {
      const el = (e.target as HTMLElement).closest("[data-tip]") as HTMLElement | null;
      if (!el) return;
      if (timerRef.current) clearTimeout(timerRef.current);
      timerRef.current = setTimeout(() => {
        const t = tipRef.current;
        if (!t) return;
        t.textContent = el.getAttribute("data-tip") || "";
        t.style.display = "block";
        positionTip(e);
      }, TOOLTIP_DELAY_MS);
    };

    const handleMove = (e: MouseEvent) => {
      const t = tipRef.current;
      if (t && t.style.display !== "none") positionTip(e);
    };

    const handleOut = (e: MouseEvent) => {
      const el = (e.target as HTMLElement).closest("[data-tip]");
      if (!el) return;
      if (el.contains(e.relatedTarget as Node)) return;
      if (timerRef.current) clearTimeout(timerRef.current);
      const t = tipRef.current;
      if (t) t.style.display = "none";
    };

    document.addEventListener("mouseover", handleOver);
    document.addEventListener("mousemove", handleMove);
    document.addEventListener("mouseout", handleOut);

    return () => {
      document.removeEventListener("mouseover", handleOver);
      document.removeEventListener("mousemove", handleMove);
      document.removeEventListener("mouseout", handleOut);
      if (timerRef.current) clearTimeout(timerRef.current);
    };
  }, [positionTip]);

  return (
    <div
      ref={tipRef}
      id="dash-tooltip"
      style={{
        display: "none",
        position: "fixed",
        zIndex: Z_TOOLTIP,
        pointerEvents: "none",
        maxWidth: 320,
        background: "var(--surface2)",
        border: "1px solid var(--border)",
        borderRadius: 7,
        padding: "6px 10px",
        fontSize: 12,
        color: "var(--text1)",
        boxShadow: "0 4px 16px rgba(0,0,0,0.35)",
        lineHeight: 1.5,
        wordBreak: "break-all",
      }}
    />
  );
}
