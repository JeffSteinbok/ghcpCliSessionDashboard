/**
 * Files tab — table of most frequently edited files across recent sessions.
 */

import { useEffect, useState } from "react";
import { fetchFiles } from "../api";
import type { FileFrequency } from "../types";

export default function FilesTab() {
  const [files, setFiles] = useState<FileFrequency[] | null>(null);
  const [error, setError] = useState(false);

  useEffect(() => {
    let cancelled = false;

    fetchFiles()
      .then((data) => { if (!cancelled) setFiles(data); })
      .catch(() => { if (!cancelled) setError(true); });

    return () => { cancelled = true; };
  }, []);

  if (error) return <div className="empty">Error loading files.</div>;
  if (!files) return <div className="loading">Loading files...</div>;
  if (files.length === 0) return <div className="empty">No file data available.</div>;

  const maxCount = files[0].session_count;

  return (
    <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
      <thead>
        <tr>
          <th style={thStyle}>File path</th>
          <th style={thStyle}>Sessions</th>
          <th style={{ ...thStyle, width: 200 }}>Frequency</th>
        </tr>
      </thead>
      <tbody>
        {files.map((f) => {
          const pct = Math.round((f.session_count / maxCount) * 100);
          const shortPath =
            f.file_path.length > 80
              ? "..." + f.file_path.slice(-77)
              : f.file_path;

          return (
            <tr key={f.file_path} style={{ borderBottom: "1px solid var(--border)" }}>
              <td style={{ padding: "6px 8px", fontFamily: "monospace", color: "var(--text2)" }}>
                {shortPath}
              </td>
              <td style={{ padding: "6px 8px", color: "var(--text)" }}>
                {f.session_count}
              </td>
              <td style={{ padding: "6px 8px" }}>
                <div style={{ height: 8, background: "var(--surface2)", borderRadius: 4 }}>
                  <div
                    style={{
                      width: `${pct}%`,
                      height: "100%",
                      background: "var(--accent)",
                      borderRadius: 4,
                    }}
                  />
                </div>
              </td>
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}

const thStyle: React.CSSProperties = {
  textAlign: "left",
  padding: "6px 8px",
  color: "var(--text2)",
  borderBottom: "1px solid var(--border)",
};
