import { useState, useMemo } from "react";
import Pagination from "./Pagination";

interface Column {
  key: string;
  label: string;
  align?: "left" | "right";
  render?: (value: unknown, row: Record<string, unknown>) => React.ReactNode;
  sortable?: boolean;
}

interface Props {
  columns: Column[];
  data: Record<string, unknown>[];
  pageSize?: number;
  onRowClick?: (row: Record<string, unknown>) => void;
  defaultSort?: { key: string; dir: "asc" | "desc" };
}

export default function SortableTable({
  columns,
  data,
  pageSize = 20,
  onRowClick,
  defaultSort,
}: Props) {
  const [sort, setSort] = useState<{ key: string; dir: "asc" | "desc" }>(
    defaultSort || { key: columns[0]?.key || "", dir: "desc" }
  );
  const [page, setPage] = useState(1);

  const sorted = useMemo(() => {
    const s = [...data].sort((a, b) => {
      const av = a[sort.key];
      const bv = b[sort.key];
      if (av == null && bv == null) return 0;
      if (av == null) return 1;
      if (bv == null) return -1;
      if (typeof av === "number" && typeof bv === "number") {
        return sort.dir === "asc" ? av - bv : bv - av;
      }
      const sa = String(av);
      const sb = String(bv);
      return sort.dir === "asc" ? sa.localeCompare(sb) : sb.localeCompare(sa);
    });
    return s;
  }, [data, sort]);

  const totalPages = Math.ceil(sorted.length / pageSize);
  const paged = sorted.slice((page - 1) * pageSize, page * pageSize);

  const handleSort = (key: string) => {
    if (sort.key === key) {
      setSort({ key, dir: sort.dir === "asc" ? "desc" : "asc" });
    } else {
      setSort({ key, dir: "desc" });
    }
    setPage(1);
  };

  return (
    <div>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-left text-xs text-gray-500 border-b border-gray-800">
              {columns.map((col) => (
                <th
                  key={col.key}
                  className={`pb-2 pr-4 ${col.align === "right" ? "text-right" : ""} ${
                    col.sortable !== false ? "cursor-pointer hover:text-gray-300 select-none" : ""
                  }`}
                  onClick={() => col.sortable !== false && handleSort(col.key)}
                >
                  <span className="inline-flex items-center gap-1">
                    {col.label}
                    {sort.key === col.key && (
                      <span className="text-indigo-400">
                        {sort.dir === "asc" ? "\u25B2" : "\u25BC"}
                      </span>
                    )}
                  </span>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {paged.map((row, i) => (
              <tr
                key={i}
                onClick={() => onRowClick?.(row)}
                className={`border-b border-gray-800/50 ${
                  onRowClick
                    ? "hover:bg-gray-800/50 cursor-pointer"
                    : "hover:bg-gray-800/30"
                } transition-colors`}
              >
                {columns.map((col) => (
                  <td
                    key={col.key}
                    className={`py-2 pr-4 ${col.align === "right" ? "text-right" : ""} text-gray-300`}
                  >
                    {col.render
                      ? col.render(row[col.key], row)
                      : String(row[col.key] ?? "")}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <Pagination
        page={page}
        totalPages={totalPages}
        onPageChange={setPage}
        totalItems={sorted.length}
        pageSize={pageSize}
      />
    </div>
  );
}
