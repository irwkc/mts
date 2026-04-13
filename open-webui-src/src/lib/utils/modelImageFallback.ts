/** Локальный аватар, если `/models/model/profile/image` недоступен (404, TLS). */
export const MODEL_AVATAR_FALLBACK =
	'data:image/svg+xml,' +
	encodeURIComponent(
		`<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 40 40" width="40" height="40">
<defs><linearGradient id="g" x1="0" y1="0" x2="1" y2="1">
<stop offset="0%" stop-color="#2dd4bf"/><stop offset="100%" stop-color="#7c3aed"/>
</linearGradient></defs>
<rect width="40" height="40" rx="10" fill="url(#g)"/>
<text x="20" y="26" text-anchor="middle" fill="white" font-family="system-ui,sans-serif" font-size="14" font-weight="600">g</text>
</svg>`
	);

export function useModelProfileImageFallback(ev: Event) {
	const el = ev.currentTarget as HTMLImageElement;
	if (!el || el.src.startsWith('data:image/svg+xml')) return;
	el.src = MODEL_AVATAR_FALLBACK;
}
