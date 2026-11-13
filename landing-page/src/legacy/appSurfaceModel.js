export function resolveAppSurface(pathname) {
  const normalizedPath = pathname.length > 1 ? pathname.replace(/\/+$/, "") : pathname;
  return normalizedPath === "/landing" ? "landing" : "demo";
}
