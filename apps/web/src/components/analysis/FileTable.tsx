import type {
  ArchitectureNode,
  FileAnalysis,
} from "@/lib/types";

interface FileTableProps {
  files: FileAnalysis[];
  nodes: ArchitectureNode[];
  selectedPath: string | null;
  onSelect: (path: string) => void;
}

export function FileTable({
  files,
  nodes,
  selectedPath,
  onSelect,
}: FileTableProps) {
  const statsByPath = new Map(
    nodes.map((node) => [node.path, node]),
  );

  return (
    <div className="table-scroll">
      <table className="data-table">
        <thead>
          <tr>
            <th>File</th>
            <th>Language</th>
            <th>Symbols</th>
            <th>Imports</th>
            <th>Dependents</th>
          </tr>
        </thead>

        <tbody>
          {files.map((file) => {
            const stats = statsByPath.get(file.path);
            const selected =
              selectedPath === file.path;

            return (
              <tr
                key={file.path}
                className={
                  selected ? "selected" : ""
                }
                onClick={() =>
                  onSelect(file.path)
                }
              >
                <td>
                  <button
                    className="file-link"
                    type="button"
                  >
                    <span className="file-type-icon">
                      {file.language.slice(0, 1)}
                    </span>

                    <span className="file-name-cell">
                      <code title={file.path}>
                        {file.path}
                      </code>
                    </span>
                  </button>
                </td>

                <td>
                  <span className="language-chip">
                    {file.language}
                  </span>
                </td>

                <td>
                  {file.symbols.length}
                </td>

                <td>
                  {stats?.imports_count ?? 0}
                </td>

                <td>
                  {stats?.imported_by_count ?? 0}
                </td>
              </tr>
            );
          })}

          {files.length === 0 && (
            <tr>
              <td
                className="empty-table"
                colSpan={5}
              >
                No files match this search.
              </td>
            </tr>
          )}
        </tbody>
      </table>
    </div>
  );
}