/**
 * Lightweight toast notification — auto-dismisses after a few seconds.
 *
 * Usage:
 *   import { showToast } from "./Toast";
 *   showToast("Window focused!", "success");
 *   showToast("Could not find tab", "error");
 */

import { useRef, useState, useCallback } from "react";

type ToastType = "success" | "error" | "info";

interface ToastItem {
  id: number;
  message: string;
  type: ToastType;
}

// Global dispatch so callers don't need context
let _dispatch: ((msg: string, type: ToastType) => void) | null = null;

export function showToast(message: string, type: ToastType = "info") {
  _dispatch?.(message, type);
}

const TOAST_DURATION_MS = 4000;
const Z_TOAST = 9997;

export function ToastContainer() {
  const [toasts, setToasts] = useState<ToastItem[]>([]);
  const nextId = useRef(0);

  _dispatch = useCallback((message: string, type: ToastType) => {
    const id = nextId.current++;
    setToasts((prev) => [...prev, { id, message, type }]);
    setTimeout(() => {
      setToasts((prev) => prev.filter((t) => t.id !== id));
    }, TOAST_DURATION_MS);
  }, []);

  if (!toasts.length) return null;

  return (
    <div
      style={{
        position: "fixed",
        bottom: 20,
        right: 20,
        zIndex: Z_TOAST,
        display: "flex",
        flexDirection: "column",
        gap: 8,
        maxWidth: 360,
      }}
    >
      {toasts.map((t) => (
        <div
          key={t.id}
          style={{
            padding: "10px 16px",
            borderRadius: 8,
            fontSize: 13,
            lineHeight: 1.4,
            color: "#fff",
            background:
              t.type === "error"
                ? "var(--red, #e74c3c)"
                : t.type === "success"
                  ? "var(--green, #27ae60)"
                  : "var(--surface2, #444)",
            border: "1px solid var(--border, #555)",
            boxShadow: "0 4px 16px rgba(0,0,0,0.4)",
            animation: "toast-in 0.2s ease-out",
          }}
        >
          {t.type === "error" ? "⚠️ " : t.type === "success" ? "✅ " : ""}
          {t.message}
        </div>
      ))}
      <style>{`@keyframes toast-in { from { opacity:0; transform:translateY(10px); } to { opacity:1; transform:translateY(0); } }`}</style>
    </div>
  );
}
