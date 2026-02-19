interface Props {
  page: number;
  totalPages: number;
  onPageChange: (page: number) => void;
  totalItems?: number;
  pageSize?: number;
}

export default function Pagination({
  page,
  totalPages,
  onPageChange,
  totalItems,
  pageSize,
}: Props) {
  if (totalPages <= 1) return null;

  const start = (page - 1) * (pageSize || 0) + 1;
  const end = Math.min(page * (pageSize || 0), totalItems || 0);

  return (
    <div className="flex items-center justify-between pt-3 border-t border-gray-800">
      <div className="text-xs text-gray-500">
        {totalItems != null && pageSize
          ? `Showing ${start}-${end} of ${totalItems.toLocaleString()}`
          : `Page ${page} of ${totalPages}`}
      </div>
      <div className="flex gap-1">
        <button
          onClick={() => onPageChange(1)}
          disabled={page === 1}
          className="px-2 py-1 text-xs rounded bg-gray-800 text-gray-400 hover:text-white disabled:opacity-30 disabled:cursor-not-allowed"
        >
          First
        </button>
        <button
          onClick={() => onPageChange(page - 1)}
          disabled={page === 1}
          className="px-2.5 py-1 text-xs rounded bg-gray-800 text-gray-400 hover:text-white disabled:opacity-30 disabled:cursor-not-allowed"
        >
          Prev
        </button>
        {/* Page numbers */}
        {Array.from({ length: Math.min(5, totalPages) }, (_, i) => {
          let p: number;
          if (totalPages <= 5) {
            p = i + 1;
          } else if (page <= 3) {
            p = i + 1;
          } else if (page >= totalPages - 2) {
            p = totalPages - 4 + i;
          } else {
            p = page - 2 + i;
          }
          return (
            <button
              key={p}
              onClick={() => onPageChange(p)}
              className={`px-2.5 py-1 text-xs rounded transition-colors ${
                p === page
                  ? "bg-indigo-500/20 text-indigo-300 font-semibold"
                  : "bg-gray-800 text-gray-400 hover:text-white"
              }`}
            >
              {p}
            </button>
          );
        })}
        <button
          onClick={() => onPageChange(page + 1)}
          disabled={page === totalPages}
          className="px-2.5 py-1 text-xs rounded bg-gray-800 text-gray-400 hover:text-white disabled:opacity-30 disabled:cursor-not-allowed"
        >
          Next
        </button>
        <button
          onClick={() => onPageChange(totalPages)}
          disabled={page === totalPages}
          className="px-2 py-1 text-xs rounded bg-gray-800 text-gray-400 hover:text-white disabled:opacity-30 disabled:cursor-not-allowed"
        >
          Last
        </button>
      </div>
    </div>
  );
}
