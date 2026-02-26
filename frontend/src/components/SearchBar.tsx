/**
 * Search bar — filters sessions by name, repo, branch, MCP server, or directory.
 */

import { useAppState, useAppDispatch } from "../state";

export default function SearchBar() {
  const { searchFilter } = useAppState();
  const dispatch = useAppDispatch();

  return (
    <input
      className="search-bar"
      type="text"
      placeholder="🔍  Filter sessions by name, repo, branch, MCP server, or directory..."
      value={searchFilter}
      onChange={(e) => dispatch({ type: "SET_SEARCH", filter: e.target.value })}
    />
  );
}
