// The guest banner (FR-GST-02) stays closed once closed: a cookie, so that the server does not
// render it again and the page does not jump.

export const GUEST_BANNER_COOKIE = "ap_guest_banner";
const CLOSED = "closed";
const ONE_YEAR_S = 60 * 60 * 24 * 365;

export function isGuestBannerClosed(value: string | undefined): boolean {
  return value === CLOSED;
}

export function closeGuestBanner(): void {
  document.cookie = `${GUEST_BANNER_COOKIE}=${CLOSED}; Path=/; Max-Age=${ONE_YEAR_S}; SameSite=Lax`;
}
