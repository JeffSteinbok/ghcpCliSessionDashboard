import { useCallback } from "react";
import { useAppState, useAppDispatch } from "../state";

export function useNotifications() {
  const { notificationsEnabled } = useAppState();
  const dispatch = useAppDispatch();

  const toggle = useCallback(() => {
    if (!("Notification" in window)) {
      alert("Desktop notifications not supported in this browser");
      return;
    }
    if (Notification.permission === "granted") {
      const next = !notificationsEnabled;
      dispatch({ type: "SET_NOTIFICATIONS", enabled: next });
      if (next) {
        new Notification("Copilot Dashboard", {
          body: "Notifications enabled!",
        });
      }
      return;
    }
    if (Notification.permission === "denied") return;
    // Default — request permission
    Notification.requestPermission().then((p) => {
      const granted = p === "granted";
      dispatch({ type: "SET_NOTIFICATIONS", enabled: granted });
      if (granted) {
        new Notification("Copilot Dashboard", {
          body: "Notifications enabled!",
        });
      }
    });
  }, [notificationsEnabled, dispatch]);

  const popoverContent = useCallback((): string => {
    if (!("Notification" in window)) {
      return '<div class="pop-title">🚫 Not supported</div><div class="pop-step">Your browser does not support desktop notifications.</div>';
    }
    const p = Notification.permission;
    if (p === "granted") {
      return notificationsEnabled
        ? '<div class="pop-title">🔔 Notifications On</div><div class="pop-step">Click to <span>turn off</span> notifications.</div>'
        : '<div class="pop-title">🔕 Notifications Off</div><div class="pop-step">Click to <span>turn on</span> notifications.</div>';
    }
    if (p === "denied") {
      return (
        '<div class="pop-title">🚫 Notifications blocked</div>' +
        '<div class="pop-step">1. Click the <span>🔒 lock icon</span> in the address bar</div>' +
        '<div class="pop-step">2. Find <span>Notifications</span> → set to <span>Allow</span></div>' +
        '<div class="pop-step">3. Refresh the page and click here again</div>'
      );
    }
    return (
      '<div class="pop-title">🔔 Enable notifications</div>' +
      '<div class="pop-step">Click this button, then look for the</div>' +
      '<div class="pop-step"><span>🔔 bell icon</span> in your address bar → click <span>Allow</span></div>'
    );
  }, [notificationsEnabled]);

  return { notificationsEnabled, toggle, popoverContent };
}
