import { t } from "./i18n/index.js";

// The schedule's clock, as plain functions: the time zone starts as the browser's, and a time of day is picked in 24 hours (a native time box shows AM/PM on some computers).
const pad = (n) => String(n).padStart(2, "0");

/** The browser's time zone name, "UTC" when it will not say. `intl` is a stand-in for Intl.DateTimeFormat in tests. */
export function browserZone(intl = () => Intl.DateTimeFormat()) {
  try {
    return intl().resolvedOptions().timeZone || "UTC";
  } catch {
    return "UTC";
  }
}

export const hourOptions = Array.from({ length: 24 }, (_, i) => pad(i));
export const minuteOptions = Array.from({ length: 12 }, (_, i) => pad(i * 5));

/** "08:30" as {h: "08", m: "30"}; anything else starts at 08:00. */
export function timeParts(time) {
  const found = /^([01]\d|2[0-3]):([0-5]\d)$/.exec(String(time ?? ""));
  return found ? { h: found[1], m: found[2] } : { h: "08", m: "00" };
}

export const timeFromParts = (h, m) => `${h}:${m}`;

const COMMON_ZONES = ["Asia/Shanghai", "Asia/Hong_Kong", "Asia/Singapore", "Asia/Tokyo", "UTC", "Europe/London", "America/New_York", "America/Los_Angeles"];
const ZONE_KEY = {
  "Asia/Shanghai": "shanghai", "Asia/Hong_Kong": "hongKong", "Asia/Singapore": "singapore", "Asia/Tokyo": "tokyo", UTC: "utc",
  "Europe/London": "london", "America/New_York": "newYork", "America/Los_Angeles": "losAngeles",
};

/** The zones to pick from: the common ones, with the browser's in front when it is not among them. */
export const zoneChoices = (browser) => (COMMON_ZONES.includes(browser) || !browser ? [...COMMON_ZONES] : [browser, ...COMMON_ZONES]);

/** A zone as the person reads it: "Beijing time (Asia/Shanghai)"; a zone with no name of its own keeps its zone name. */
export const zoneLabel = (zone) => (ZONE_KEY[zone] ? t("sources.zone.label", { word: t(`sources.zone.${ZONE_KEY[zone]}`), zone }) : zone);
