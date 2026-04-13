/**
 * Логи конвейера чата в DevTools (Console).
 *
 * Общий отладочный канал [WebUI:…]:
 *   Включение в production: localStorage.setItem('WEBUI_DEBUG', '1')
 *   Полный JSON: localStorage.setItem('WEBUI_DEBUG_FULL', '1')
 *   Выключить: WEBUI_DEBUG=0
 *
 * Запросы к LLM / нейросетям [Neural:…] — по умолчанию ВСЕГДА в консоли (запросы JSON, ответы task_id, SSE-чанки).
 *   Выключить: localStorage.setItem('WEBUI_NEURAL_LOG', '0')
 *   Почти без усечения текста в сообщениях: localStorage.setItem('WEBUI_NEURAL_LOG_FULL', '1')
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

/** Логи запросов/ответов к моделям (по умолчанию включены). */
export function webuiNeuralLogEnabled(): boolean {
	if (typeof window === 'undefined') return false;
	try {
		const v = localStorage.getItem('WEBUI_NEURAL_LOG');
		if (v === '0' || v === 'false') return false;
		return true;
	} catch {
		return true;
	}
}

export function webuiNeuralFullStrings(): boolean {
	if (typeof window === 'undefined') return false;
	try {
		return localStorage.getItem('WEBUI_NEURAL_LOG_FULL') === '1';
	} catch {
		return false;
	}
}

function _neuralMaxStr(): number {
	return webuiNeuralFullStrings() ? 500_000 : 8_000;
}

/** Запросы к /api/chat/completions, SSE, список моделей — фильтр в консоли: Neural */
export function neuralLog(scope: string, payload?: unknown): void {
	if (!webuiNeuralLogEnabled()) return;
	const max = _neuralMaxStr();
	if (payload !== undefined) {
		console.info(`[Neural:${scope}]`, summarizeChatPayload(payload, max));
	} else {
		console.info(`[Neural:${scope}]`);
	}
}

export function neuralLogError(scope: string, err: unknown): void {
	if (!webuiNeuralLogEnabled()) return;
	console.error(`[Neural:${scope}]`, err);
}
