/**
 * Hook to fetch and update dashboard settings (sync toggle) from the backend.
 */

import { useCallback, useEffect, useState } from "react";
import { fetchSettings, updateSettings } from "../api";
import type { DashboardSettings } from "../types";

const DEFAULT_SETTINGS: DashboardSettings = {
  sync_enabled: true,
};

export interface UseSettingsResult {
  settings: DashboardSettings;
  loading: boolean;
  setSyncEnabled: (enabled: boolean) => void;
}

export function useSettings(): UseSettingsResult {
  const [settings, setSettings] = useState<DashboardSettings>(DEFAULT_SETTINGS);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetchSettings()
      .then(setSettings)
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  const setSyncEnabled = useCallback((enabled: boolean) => {
    setSettings((prev) => ({ ...prev, sync_enabled: enabled }));
    updateSettings({ sync_enabled: enabled })
      .then(setSettings)
      .catch(() => {});
  }, []);

  return { settings, loading, setSyncEnabled };
}
