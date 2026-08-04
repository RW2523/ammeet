import Overlay from "./windows/Overlay";
import Settings from "./windows/Settings";
import { isTauri } from "./ipc";

export type WindowKind = "settings" | "overlay";

/** Route by `?window=` query param (tauri.conf.json sets it per window);
 *  fall back to the Tauri window label, then to settings. */
export function whichWindow(): WindowKind {
  const q = new URLSearchParams(window.location.search).get("window");
  if (q === "overlay" || q === "settings") return q;
  if (isTauri) {
    try {
      // Lazy require via the global injected by Tauri — the label is also
      // exposed on the internals object; avoids an async import here.
      const internals = (
        window as unknown as Record<string, { metadata?: { currentWebviewWindow?: { label?: string } } }>
      )["__TAURI_INTERNALS__"];
      const label = internals?.metadata?.currentWebviewWindow?.label;
      if (label === "overlay") return "overlay";
    } catch {
      /* fall through */
    }
  }
  return "settings";
}

export default function App() {
  return whichWindow() === "overlay" ? <Overlay /> : <Settings />;
}
