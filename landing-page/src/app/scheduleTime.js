// The schedule's clock, as plain functions: the time zone starts as the browser's, and a time of day is picked in 24 hours (a native time box shows 上午/下午 on some computers).
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
const ZONE_WORD = {
  "Asia/Shanghai": "北京时间", "Asia/Hong_Kong": "香港时间", "Asia/Singapore": "新加坡时间", "Asia/Tokyo": "东京时间", UTC: "世界协调时间",
  "Europe/London": "伦敦时间", "America/New_York": "纽约时间", "America/Los_Angeles": "洛杉矶时间",
};

/** The zones to pick from: the common ones, with the browser's in front when it is not among them. */
export const zoneChoices = (browser) => (COMMON_ZONES.includes(browser) || !browser ? [...COMMON_ZONES] : [browser, ...COMMON_ZONES]);

/** A zone as the person reads it: 北京时间（Asia/Shanghai）; a zone with no Chinese word keeps its own name. */
export const zoneLabel = (zone) => (ZONE_WORD[zone] ? `${ZONE_WORD[zone]}（${zone}）` : zone);
