/**
 * Логи конвейера чата в DevTools (Console).
 *
 * Включение в production: localStorage.setItem('WEBUI_DEBUG', '1')
 * Полный JSON без усечения строк: localStorage.setItem('WEBUI_DEBUG_FULL', '1')
 * Выключить: localStorage.removeItem('WEBUI_DEBUG') или '0' (см. webuiDebugEnabled)
 */

export function webuiDebugEnabled(): boolean {
	if (typeof window === 'undefined') return false;
	try {
		const v = localStorage.getItem('WEBUI_DEBUG');
		if (v === '0' || v === 'false') return false;
		if (v === '1' || v === 'true') return true;
		return import.meta.env.DEV;
	} catch {
		return import.meta.env.DEV;
	}
}

export function webuiDebugFullEnabled(): boolean {
	if (typeof window === 'undefined') return false;
	try {
		return localStorage.getItem('WEBUI_DEBUG_FULL') === '1';
	} catch {
		return false;
	}
}

/** Усечь длинные строки в JSON-подобных данных (для console без мегабайт текста). */
export function summarizeChatPayload(data: unknown, maxStr = 900): unknown {
	if (data === undefined || data === null) return data;
	try {
		return JSON.parse(
			JSON.stringify(data, (_key, val) => {
				if (typeof val === 'string' && val.length > maxStr) {
					return val.slice(0, maxStr) + `… (+${val.length - maxStr} chars)`;
				}
				return val;
			})
		);
	} catch {
		const s = String(data);
		return s.length > maxStr ? s.slice(0, maxStr) + `… (+${s.length - maxStr} chars)` : s;
	}
}

export function webuiLog(scope: string, payload?: unknown): void {
	if (!webuiDebugEnabled()) return;
	if (payload !== undefined) {
		console.info(`[WebUI:${scope}]`, payload);
	} else {
		console.info(`[WebUI:${scope}]`);
	}
}

export function webuiLogFull(scope: string, data: unknown): void {
	if (!webuiDebugEnabled() || !webuiDebugFullEnabled()) return;
	console.info(`[WebUI:${scope}:FULL]`, data);
}
