import { ReactNode } from "react";

/** Line icons for the menu (24x24, stroke only), so the menu needs no icon library. */
const PATHS: Record<string, ReactNode> = {
  register: <><path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z" /><path d="M14 3v5h5" /><path d="M12 12v6M9 15h6" /></>,
  history: <><circle cx="12" cy="12" r="9" /><path d="M12 7v5l3 2" /></>,
  audit: <><path d="M12 3l7 3v5c0 5-3 8-7 10-4-2-7-5-7-10V6z" /><path d="M9 12l2 2 4-4" /></>,
  customers: <><circle cx="9" cy="8" r="3" /><path d="M3 20c0-3 3-5 6-5s6 2 6 5" /><circle cx="17" cy="9" r="2.5" /><path d="M17 14c2.5 0 4 1.7 4 4" /></>,
  sites: <><path d="M12 21s-7-6-7-11a7 7 0 0 1 14 0c0 5-7 11-7 11z" /><circle cx="12" cy="10" r="2.5" /></>,
  contracts: <><path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z" /><path d="M14 3v5h5M9 13h6M9 17h6" /></>,
  orders: <><path d="M3 8l9-5 9 5v8l-9 5-9-5z" /><path d="M3 8l9 5 9-5M12 13v8" /></>,
  containers: <><rect x="4" y="9" width="16" height="11" rx="1.5" /><path d="M3 9l2-5h14l2 5M10 13h4" /></>,
  dashboard: <><path d="M4 20V11M10 20V4M16 20v-6M22 20H2" /></>,
  readout: <><path d="M5 21V4M5 4h12l-2.5 4L17 12H5" /></>,
  rootcauses: <><circle cx="6" cy="6" r="2" /><circle cx="6" cy="18" r="2" /><circle cx="18" cy="12" r="2" /><path d="M6 8v8M8 6h3a5 5 0 0 1 5 5M8 18h3a5 5 0 0 0 5-5" /></>,
  rca: <><circle cx="11" cy="11" r="6" /><path d="M20 20l-4.5-4.5M9 11h4M11 9v4" /></>,
  evaluation: <><rect x="6" y="4" width="12" height="17" rx="2" /><path d="M9 4h6v3H9zM9 14l2 2 4-4" /></>,
  config: <><path d="M4 7h9M17 7h3M4 17h3M11 17h9" /><circle cx="15" cy="7" r="2" /><circle cx="9" cy="17" r="2" /></>,
  users: <><circle cx="10" cy="8" r="3.5" /><path d="M3 20c0-3.5 3-6 7-6" /><circle cx="17.5" cy="17.5" r="2" /><path d="M17.5 13.5v1M17.5 20.5v1M14 17.5h1M20 17.5h1" /></>,
  about: <><circle cx="12" cy="12" r="9" /><path d="M12 11v6M12 7.5v.5" /></>,
  chevron: <path d="M15 6l-6 6 6 6" />,
};

export function Icon({ name, size = 20 }: { name: string; size?: number }) {
  return (
    <svg className="icon" width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor"
      strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" focusable="false">
      {PATHS[name] || PATHS.about}
    </svg>
  );
}

/** Placeholder shapes shown while a screen loads: the layout appears at once instead of the word "Loading". */
export function Skeleton({ lines = 3, block = false }: { lines?: number; block?: boolean }) {
  return (
    <div className="skeleton" aria-hidden="true">
      {block && <span className="sk sk-block" />}
      {Array.from({ length: lines }, (_, i) => <span key={i} className="sk sk-line" style={{ width: `${92 - ((i * 17) % 40)}%` }} />)}
    </div>
  );
}

/** A loading area for a card or a screen; the text is for screen readers only. */
export function Loading({ label, lines = 4, block = true }: { label: string; lines?: number; block?: boolean }) {
  return (
    <div className="loading-area" role="status">
      <span className="sr-only">{label}</span>
      <Skeleton lines={lines} block={block} />
    </div>
  );
}

/** First letters of a name, for the avatar. */
export function initials(name: string) {
  return (name || "?").split(/\s+/).filter(Boolean).slice(0, 2).map((w) => w[0].toUpperCase()).join("");
}
