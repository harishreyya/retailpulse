import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  listNotifications, getUnreadCount, getNotification, markNotificationRead, markAllNotificationsRead,
} from "../api/notifications";
import type { AppNotification, NotificationFilters, NotificationPriority } from "../types";

// Polling, not WebSocket/SSE: no realtime transport exists in this project
// and Analytics.tsx already uses refetchInterval for "should feel live"
// data. 15s is a fair trade-off for alerts — they aren't sub-second
// events — and it keeps state handling simple (react-query refetches,
// the badge and list re-render).
const POLL_MS = 15_000;

const PRIORITY_STYLES: Record<NotificationPriority, string> = {
  CRITICAL: "bg-red-100 text-red-700",
  HIGH: "bg-orange-100 text-orange-700",
  MEDIUM: "bg-amber-100 text-amber-700",
  LOW: "bg-slate-100 text-slate-600",
};

type ReadFilter = "all" | "unread" | "read";
type Category = "" | "stock" | "sales" | "import" | "system";

function timeAgo(iso: string) {
  const diff = Math.max(0, Date.now() - new Date(iso + (iso.endsWith("Z") ? "" : "Z")).getTime());
  const mins = Math.floor(diff / 60_000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins} min ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs} hr ago`;
  return `${Math.floor(hrs / 24)} day(s) ago`;
}

function resourceAction(n: AppNotification): { label: string; path: string } | null {
  if (n.product) return { label: "View Product", path: "/inventory" };
  if (n.customer) return { label: "View Customer", path: `/customers/${n.customer.id}` };
  if (n.resource_type === "ImportJob") return { label: "View Import", path: "/data-import" };
  return null;
}

export default function NotificationCenter() {
  const [open, setOpen] = useState(false);
  const [readFilter, setReadFilter] = useState<ReadFilter>("all");
  const [category, setCategory] = useState<Category>("");
  const [priority, setPriority] = useState<NotificationPriority | "">("");
  const [page, setPage] = useState(1);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const rootRef = useRef<HTMLDivElement>(null);
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  // Close on outside click.
  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (rootRef.current && !rootRef.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, []);

  // Unread badge — always comes from the API, never a local guess.
  const { data: unreadCount = 0 } = useQuery({
    queryKey: ["notifications-unread-count"],
    queryFn: getUnreadCount,
    refetchInterval: POLL_MS,
  });

  const filters: NotificationFilters = {
    page, page_size: 10,
    ...(readFilter === "unread" ? { is_read: false } : readFilter === "read" ? { is_read: true } : {}),
    ...(category ? { category } : {}),
    ...(priority ? { priority } : {}),
  };

  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: ["notifications", filters],
    queryFn: () => listNotifications(filters),
    enabled: open,
    refetchInterval: open ? POLL_MS : false,
    placeholderData: (prev) => prev,
  });

  const { data: detail, isLoading: detailLoading } = useQuery({
    queryKey: ["notification-detail", selectedId],
    queryFn: () => getNotification(selectedId as string),
    enabled: !!selectedId,
  });

  const invalidate = () => {
    queryClient.invalidateQueries({ queryKey: ["notifications"] });
    queryClient.invalidateQueries({ queryKey: ["notifications-unread-count"] });
  };

  const readOne = useMutation({ mutationFn: markNotificationRead, onSuccess: invalidate });
  const readAll = useMutation({ mutationFn: markAllNotificationsRead, onSuccess: invalidate });

  const openNotification = (n: AppNotification) => {
    setSelectedId(n.id);
    if (!n.is_read) readOne.mutate(n.id);
  };

  const changeFilter = <T,>(setter: (v: T) => void) => (v: T) => { setter(v); setPage(1); };

  const totalPages = Math.max(1, Math.ceil((data?.total ?? 0) / 10));
  const action = detail ? resourceAction(detail) : null;

  return (
    <div className="relative" ref={rootRef}>
      <button
        aria-label="Notifications"
        className="relative rounded-full p-2 text-slate-600 hover:bg-slate-100"
        onClick={() => { setOpen((o) => !o); setSelectedId(null); }}
      >
        <svg className="h-6 w-6" fill="none" stroke="currentColor" strokeWidth="1.8" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" d="M15 17h5l-1.4-1.4A2 2 0 0 1 18 14.2V11a6 6 0 1 0-12 0v3.2a2 2 0 0 1-.6 1.4L4 17h5m6 0a3 3 0 1 1-6 0" />
        </svg>
        {unreadCount > 0 && (
          <span className="absolute -right-0.5 -top-0.5 flex h-5 min-w-[20px] items-center justify-center rounded-full bg-red-600 px-1 text-[11px] font-bold text-white">
            {unreadCount > 99 ? "99+" : unreadCount}
          </span>
        )}
      </button>

      {open && (
        <div className="absolute right-0 z-50 mt-2 w-[min(94vw,26rem)] rounded-xl border border-slate-200 bg-white shadow-xl">
          {/* ---------------- Detail view ---------------- */}
          {selectedId ? (
            <div className="p-4">
              <button className="mb-3 text-sm font-medium text-brand-500 hover:underline" onClick={() => setSelectedId(null)}>
                ← Back
              </button>
              {detailLoading || !detail ? (
                <div className="space-y-2">
                  <div className="h-4 w-1/2 animate-pulse rounded bg-slate-200" />
                  <div className="h-3 w-full animate-pulse rounded bg-slate-200" />
                </div>
              ) : (
                <>
                  <div className="mb-2 flex items-center gap-2">
                    <span className={`rounded-full px-2 py-0.5 text-[11px] font-semibold ${PRIORITY_STYLES[detail.priority]}`}>
                      {detail.priority}
                    </span>
                    <span className="text-xs text-slate-400">{detail.type.replace(/_/g, " ")} · {timeAgo(detail.created_at)}</span>
                  </div>
                  <h3 className="text-base font-semibold text-navy">{detail.title}</h3>
                  <p className="mt-1 text-sm text-slate-600">{detail.message}</p>

                  {(detail.product || detail.details) && (
                    <dl className="mt-4 grid grid-cols-2 gap-x-4 gap-y-2 rounded-lg bg-slate-50 p-3 text-sm">
                      {detail.product && (<><dt className="text-slate-400">Product</dt><dd className="font-medium">{detail.product.name}</dd>
                        <dt className="text-slate-400">SKU</dt><dd className="font-medium">{detail.product.sku}</dd></>)}
                      {detail.details?.current_stock != null && (<><dt className="text-slate-400">Current stock</dt><dd className="font-medium">{detail.details.current_stock}</dd></>)}
                      {(detail.details?.reorder_point ?? detail.details?.reorder_level) != null && (
                        <><dt className="text-slate-400">Reorder point</dt><dd className="font-medium">{detail.details?.reorder_point ?? detail.details?.reorder_level}</dd></>)}
                      {detail.details?.risk && (<><dt className="text-slate-400">Risk</dt><dd className="font-medium">{String(detail.details.risk).replace(/_/g, " ")}</dd></>)}
                      {detail.details?.recommended_quantity != null && (<><dt className="text-slate-400">Recommended qty</dt><dd className="font-medium">{detail.details.recommended_quantity}</dd></>)}
                    </dl>
                  )}
                  {detail.customer && (
                    <p className="mt-3 text-sm text-slate-600">Customer: <span className="font-medium">{detail.customer.full_name}</span> ({detail.customer.customer_code})</p>
                  )}

                  {action && (
                    <button className="btn-primary mt-4" onClick={() => { setOpen(false); navigate(action.path); }}>
                      {action.label}
                    </button>
                  )}
                </>
              )}
            </div>
          ) : (
            <>
              {/* ---------------- List view ---------------- */}
              <div className="flex items-center justify-between border-b border-slate-100 px-4 py-3">
                <h3 className="text-sm font-semibold text-navy">Notifications</h3>
                <button
                  className="text-xs font-medium text-brand-500 hover:underline disabled:cursor-not-allowed disabled:text-slate-300"
                  disabled={unreadCount === 0 || readAll.isPending}
                  onClick={() => readAll.mutate()}
                >
                  Mark all as read
                </button>
              </div>

              <div className="space-y-2 border-b border-slate-100 px-4 py-3">
                <div className="flex gap-1">
                  {(["all", "unread", "read"] as ReadFilter[]).map((f) => (
                    <button
                      key={f}
                      onClick={() => changeFilter(setReadFilter)(f)}
                      className={`rounded-md px-2.5 py-1 text-xs font-semibold capitalize ${readFilter === f ? "bg-brand-500 text-white" : "bg-slate-100 text-slate-600 hover:bg-slate-200"}`}
                    >
                      {f}
                    </button>
                  ))}
                </div>
                <div className="flex gap-2">
                  <select className="form-input py-1 text-xs" value={category} onChange={(e) => changeFilter(setCategory)(e.target.value as Category)}>
                    <option value="">All types</option>
                    <option value="stock">Stock</option>
                    <option value="sales">Sales</option>
                    <option value="import">Import</option>
                    <option value="system">System</option>
                  </select>
                  <select className="form-input py-1 text-xs" value={priority} onChange={(e) => changeFilter(setPriority)(e.target.value as NotificationPriority | "")}>
                    <option value="">Any priority</option>
                    <option value="CRITICAL">Critical</option>
                    <option value="HIGH">High</option>
                    <option value="MEDIUM">Medium</option>
                    <option value="LOW">Low</option>
                  </select>
                </div>
              </div>

              <div className="max-h-[22rem] overflow-y-auto">
                {isLoading && Array.from({ length: 4 }).map((_, i) => (
                  <div key={i} className="border-b border-slate-100 px-4 py-3">
                    <div className="mb-2 h-3.5 w-1/3 animate-pulse rounded bg-slate-200" />
                    <div className="h-3 w-full animate-pulse rounded bg-slate-200" />
                  </div>
                ))}

                {!isLoading && isError && (
                  <div className="px-4 py-8 text-center">
                    <p className="mb-2 text-sm text-red-600">Couldn't load notifications.</p>
                    <button className="text-sm font-medium text-brand-500 hover:underline" onClick={() => refetch()}>Try again</button>
                  </div>
                )}

                {!isLoading && !isError && (data?.items.length ?? 0) === 0 && (
                  <p className="px-4 py-10 text-center text-sm text-slate-400">
                    {readFilter === "all" && !category && !priority
                      ? "You're all caught up. No new notifications."
                      : "No notifications match these filters."}
                  </p>
                )}

                {!isLoading && !isError && data?.items.map((n) => (
                  <button
                    key={n.id}
                    onClick={() => openNotification(n)}
                    className={`block w-full border-b border-slate-100 px-4 py-3 text-left hover:bg-slate-50 ${n.is_read ? "" : "bg-brand-50/60"}`}
                  >
                    <div className="mb-1 flex items-center justify-between gap-2">
                      <span className="flex items-center gap-2">
                        {!n.is_read && <span className="h-2 w-2 rounded-full bg-brand-500" />}
                        <span className={`text-sm ${n.is_read ? "font-medium text-slate-700" : "font-semibold text-navy"}`}>{n.title}</span>
                      </span>
                      <span className={`rounded-full px-2 py-0.5 text-[10px] font-semibold ${PRIORITY_STYLES[n.priority]}`}>{n.priority}</span>
                    </div>
                    <p className="line-clamp-2 text-xs text-slate-500">{n.message}</p>
                    <p className="mt-1 text-[11px] text-slate-400">{n.type.replace(/_/g, " ")} · {timeAgo(n.created_at)}</p>
                  </button>
                ))}
              </div>

              {!isLoading && !isError && (data?.total ?? 0) > 10 && (
                <div className="flex items-center justify-between px-4 py-2 text-xs text-slate-500">
                  <button className="disabled:text-slate-300" disabled={page <= 1} onClick={() => setPage((p) => p - 1)}>Previous</button>
                  <span>Page {page} of {totalPages}</span>
                  <button className="disabled:text-slate-300" disabled={page >= totalPages} onClick={() => setPage((p) => p + 1)}>Next</button>
                </div>
              )}
            </>
          )}
        </div>
      )}
    </div>
  );
}
