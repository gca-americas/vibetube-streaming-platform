import { useEffect, useState } from "react";

/**
 * Minimal history-based routing.
 *
 * The app has exactly two routes, so this avoids pulling in a router
 * dependency. nginx already rewrites unknown paths to index.html, so deep
 * links into /e/CODE load correctly on a cold hit.
 */

export type Route =
  | { name: "gate" }
  | { name: "room"; code: string };

export const parseRoute = (pathname: string): Route => {
  const match = pathname.match(/^\/e\/([^/]+)\/?$/);
  if (match) {
    return { name: "room", code: decodeURIComponent(match[1]) };
  }
  return { name: "gate" };
};

export const roomPath = (code: string) => `/e/${encodeURIComponent(code)}`;

/** Query key carrying the open video, so a shared link lands on that video. */
const VIDEO_PARAM = "v";

/** Absolute URL for a single video, for share targets and copy-to-clipboard. */
export const videoShareUrl = (code: string, videoId: string) =>
  `${window.location.origin}${roomPath(code)}?${VIDEO_PARAM}=${encodeURIComponent(videoId)}`;

/** The video id in the current URL, if any. */
export const readVideoParam = (): string | null =>
  new URLSearchParams(window.location.search).get(VIDEO_PARAM);

/**
 * Reflects the open video in the address bar.
 *
 * Uses replaceState rather than pushState: opening and closing videos would
 * otherwise stack history entries, so Back would step through modal state
 * instead of leaving the showroom. It also avoids the popstate dispatch in
 * navigate(), which would re-render the route for a purely visual change.
 */
export const syncVideoParam = (videoId: string | null) => {
  const url = new URL(window.location.href);
  if (videoId) {
    url.searchParams.set(VIDEO_PARAM, videoId);
  } else {
    url.searchParams.delete(VIDEO_PARAM);
  }
  window.history.replaceState({}, "", `${url.pathname}${url.search}`);
};

export const navigate = (path: string) => {
  if (path === window.location.pathname) return;
  window.history.pushState({}, "", path);
  window.dispatchEvent(new PopStateEvent("popstate"));
};

export const useRoute = (): Route => {
  const [route, setRoute] = useState<Route>(() => parseRoute(window.location.pathname));

  useEffect(() => {
    const onPopState = () => setRoute(parseRoute(window.location.pathname));
    window.addEventListener("popstate", onPopState);
    return () => window.removeEventListener("popstate", onPopState);
  }, []);

  return route;
};
