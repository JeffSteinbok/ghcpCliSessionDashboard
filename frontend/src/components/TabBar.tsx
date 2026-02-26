/**
 * Tab bar with Active/Previous/Timeline/Files tabs, notification button,
 * and tile/list view toggle.
 */

import { TOOLTIP_DELAY_MS } from "../constants";
import { useNotifications } from "../hooks";
import { useAppState, useAppDispatch, type Tab, type View } from "../state";
import { useRef, useState, useCallback } from "react";

interface TabBarProps {
  activeCount: number;
  previousCount: number;
}

export default function TabBar({ activeCount, previousCount }: TabBarProps) {
  const { currentTab, currentView } = useAppState();
  const dispatch = useAppDispatch();
  const { notificationsEnabled, toggle: toggleNotif, popoverContent } =
    useNotifications();

  // Notification popover hover timer (400ms delay)
  const [popVisible, setPopVisible] = useState(false);
  const hintTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const showHint = useCallback(() => {
    if (hintTimer.current) clearTimeout(hintTimer.current);
    hintTimer.current = setTimeout(() => setPopVisible(true), TOOLTIP_DELAY_MS);
  }, []);

  const hideHint = useCallback(() => {
    if (hintTimer.current) clearTimeout(hintTimer.current);
    setPopVisible(false);
  }, []);

  const switchTab = (tab: Tab) => {
    dispatch({ type: "SET_TAB", tab });
    history.replaceState(null, "", "#" + tab);
  };

  const setView = (view: View) => dispatch({ type: "SET_VIEW", view });

  const tabs: { key: Tab; label: string; icon: string; count?: number; title: string }[] = [
    { key: "active", label: "Active", icon: "⚡", count: activeCount, title: "Currently running Copilot CLI sessions" },
    { key: "previous", label: "Previous", icon: "📋", count: previousCount, title: "Completed sessions from the last 5 days" },
    { key: "timeline", label: "Timeline", icon: "📅", title: "Gantt-style view of session activity over the last 5 days" },
    { key: "files", label: "Files", icon: "📁", title: "Files most frequently edited across recent sessions" },
  ];

  return (
    <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 16 }}>
      <div className="tabs" style={{ marginBottom: 0, flex: 1 }}>
        {tabs.map((t) => (
          <div
            key={t.key}
            className={`tab ${currentTab === t.key ? "active" : ""}`}
            data-tab={t.key}
            onClick={() => switchTab(t.key)}
            title={t.title}
          >
            {t.icon} {t.label}
            {t.count !== undefined && (
              <span className="count">{t.count}</span>
            )}
          </div>
        ))}
      </div>

      <div className="view-toggle">
        {/* Notification button with hover popover */}
        <div id="notif-wrap" style={{ position: "relative" }}>
          <button
            className="view-btn"
            onClick={toggleNotif}
            onMouseEnter={showHint}
            onMouseLeave={hideHint}
            style={{ opacity: notificationsEnabled ? 1 : 0.6 }}
          >
            {notificationsEnabled ? "🔔 Notifications On" : "🔕 Notifications Off"}
          </button>
          {popVisible && (
            <div className="notif-popover visible">
              {popoverContent()}
            </div>
          )}
        </div>

        <button
          className={`view-btn ${currentView === "tile" ? "active" : ""}`}
          onClick={() => setView("tile")}
          title="Tile view"
        >
          ▦
        </button>
        <button
          className={`view-btn ${currentView === "list" ? "active" : ""}`}
          onClick={() => setView("list")}
          title="List view"
        >
          ☰
        </button>
      </div>
    </div>
  );
}
