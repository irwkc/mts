/** Скрытие служебных маркеров gena в UI (контент в API/истории без изменений). */

const GENA_STYLE_HEAD = /^\s*\[gena_style:([a-z0-9_-]+)\]\s*/i;

/** Текст пользователя для отображения (без префикса выбора стиля). */
export function stripGenaStylePrefixForDisplay(raw: string): string {
	return (raw ?? '').replace(GENA_STYLE_HEAD, '').trim();
}

/**
 * Второе сообщение после выбора стиля: `[gena_style:x] + тот же промпт`.
 * Скрываем пузырь целиком — стиль уже выбран кнопкой.
 */
export function shouldHideGenaStyleUserBubble(
	message: { role?: string; content?: string; parentId?: string | null },
	history: { messages: Record<string, unknown> }
): boolean {
	if (message.role !== 'user') return false;
	const c = message.content ?? '';
	if (!GENA_STYLE_HEAD.test(c)) return false;
	const rest = stripGenaStylePrefixForDisplay(c);
	const parent = message.parentId ? history.messages[message.parentId] : null;
	const p = parent as { role?: string; parentId?: string | null } | undefined;
	if (!p || p.role !== 'assistant') return false;
	const gpId = p.parentId;
	const prevUser = gpId ? history.messages[gpId] : null;
	const pu = prevUser as { role?: string; content?: string } | undefined;
	if (!pu || pu.role !== 'user') return false;
	const prevText = (pu.content ?? '').trim();
	const r = rest.trim();
	return r === prevText || r === '';
}

/** Убрать служебные заголовки из ответа ассистента (дублируют док). */
export function sanitizeGenaAssistantMarkdown(raw: string): string {
	if (!raw) return raw;
	return raw
		.replace(/\*\*\[gena · презентация\]\*\*\s*/g, '')
		.replace(/\[gena · презентация\]\s*/g, '')
		.replace(/\*\*\[gena · изображение\][^\n]*\n*/g, '')
		.replace(/\[gena · изображение\][^\n]*\n*/g, '')
		.replace(/\*\(Генерация изображения[^)]*\)\*\s*/g, '')
		.replace(/\(Генерация изображения[^)]*\)\s*/g, '')
		.replace(/\u200b/g, '');
}
