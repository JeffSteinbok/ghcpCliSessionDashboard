import { useEffect, useState, useCallback } from "react";
import { fetchVersion, triggerUpdate } from "../api";
import {
  UPDATE_POLL_INTERVAL_MS,
  UPDATE_POLL_TIMEOUT_MS,
  VERSION_CHECK_MS,
} from "../constants";
import type { VersionInfo } from "../types";

/**
 * Periodic version check — every 30 minutes.
 */
export function useVersion(initialVersion: string) {
  const [versionInfo, setVersionInfo] = useState<VersionInfo>({
    current: initialVersion,
    latest: null,
    update_available: false,
  });
  const [updating, setUpdating] = useState(false);

  useEffect(() => {
    // Initial check + periodic re-check every 30 minutes
    let mounted = true;
    const doCheck = () => {
      fetchVersion()
        .then((info) => { if (mounted) setVersionInfo(info); })
        .catch(() => {});
    };
    doCheck();
    const timer = setInterval(doCheck, VERSION_CHECK_MS);
    return () => { mounted = false; clearInterval(timer); };
  }, []);

  const doUpdate = useCallback(async () => {
    setUpdating(true);
    await triggerUpdate();
    // Poll until the (new) server responds, then reload
    const start = Date.now();
    const pollRef = { id: 0 as ReturnType<typeof setInterval> };
    pollRef.id = setInterval(async () => {
      if (Date.now() - start > UPDATE_POLL_TIMEOUT_MS) {
        clearInterval(pollRef.id);
        setUpdating(false);
        return;
      }
      try {
        const r = await fetch("/api/server-info");
        if (r.ok) {
          clearInterval(pollRef.id);
          location.reload();
        }
      } catch {
        // Not up yet
      }
    }, UPDATE_POLL_INTERVAL_MS);
    // Store for cleanup — though this is a one-shot user action
    return () => clearInterval(pollRef.id);
  }, []);

  return { versionInfo, updating, doUpdate };
}
