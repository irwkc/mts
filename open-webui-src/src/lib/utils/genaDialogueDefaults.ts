/**
 * Режим диалога с gena: по умолчанию голос вместо «молчаливого» чата —
 * авто‑озвучка ответа, затем снова микрофон, авто‑отправка после диктовки.
 * Явно выставленные пользователем false сохраняются (проверка через === undefined).
 */

export function normalizeUiFromStored(raw: unknown): Record<string, unknown> {
	if (raw == null) return {};
	if (typeof raw !== 'object' || Array.isArray(raw)) return {};
	const o = raw as Record<string, unknown>;
	if (
		'ui' in o &&
		o.ui &&
		typeof o.ui === 'object' &&
		!Array.isArray(o.ui)
	) {
		return { ...(o.ui as Record<string, unknown>) };
	}
	return { ...o };
}

export function mergeGenaDialogueDefaults(ui: Record<string, unknown>): Record<string, unknown> {
	const s = { ...ui };
	if (s.responseAutoPlayback === undefined) s.responseAutoPlayback = true;
	if (s.conversationMode === undefined) s.conversationMode = true;
	if (s.speechAutoSend === undefined) s.speechAutoSend = true;
	return s;
}
