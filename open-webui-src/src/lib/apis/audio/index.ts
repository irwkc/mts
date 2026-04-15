import { AUDIO_API_BASE_URL } from '$lib/constants';

/** Пустой/битый токен в Authorization ломает сессию по cookie (JWT decode «undefined» → 401). */
function authBearerHeaders(token: string | undefined | null): Record<string, string> {
	const t = (token ?? '').trim();
	if (!t || t === 'undefined' || t === 'null') {
		return {};
	}
	return { Authorization: `Bearer ${t}` };
}

export const getAudioConfig = async (token: string) => {
	let error = null;

	const res = await fetch(`${AUDIO_API_BASE_URL}/config`, {
		method: 'GET',
		credentials: 'include',
		headers: {
			'Content-Type': 'application/json',
			...authBearerHeaders(token)
		}
	})
		.then(async (res) => {
			if (!res.ok) throw await res.json();
			return res.json();
		})
		.catch((err) => {
			console.error(err);
			error = err.detail;
			return null;
		});

	if (error) {
		throw error;
	}

	return res;
};

type OpenAIConfigForm = {
	url: string;
	key: string;
	model: string;
	speaker: string;
};

export const updateAudioConfig = async (token: string, payload: OpenAIConfigForm) => {
	let error = null;

	const res = await fetch(`${AUDIO_API_BASE_URL}/config/update`, {
		method: 'POST',
		credentials: 'include',
		headers: {
			'Content-Type': 'application/json',
			...authBearerHeaders(token)
		},
		body: JSON.stringify({
			...payload
		})
	})
		.then(async (res) => {
			if (!res.ok) throw await res.json();
			return res.json();
		})
		.catch((err) => {
			console.error(err);
			error = err.detail;
			return null;
		});

	if (error) {
		throw error;
	}

	return res;
};

export const transcribeAudio = async (token: string, file: File, language?: string) => {
	const data = new FormData();
	data.append('file', file);
	if (language) {
		data.append('language', language);
	}

	let error = null;
	const res = await fetch(`${AUDIO_API_BASE_URL}/transcriptions`, {
		method: 'POST',
		credentials: 'include',
		headers: {
			Accept: 'application/json',
			...authBearerHeaders(token)
		},
		body: data
	})
		.then(async (res) => {
			if (!res.ok) throw await res.json();
			return res.json();
		})
		.catch((err) => {
			error = err.detail;
			console.error(err);
			return null;
		});

	if (error) {
		throw error;
	}

	return res;
};

function ttsErrorMessage(res: Response, body: unknown): string {
	if (body && typeof body === 'object') {
		const o = body as Record<string, unknown>;
		const d = o.detail;
		if (typeof d === 'string' && d.trim()) return d;
		if (Array.isArray(d)) {
			try {
				return JSON.stringify(d);
			} catch {
				return String(d);
			}
		}
		const err = o.error;
		if (err && typeof err === 'object') {
			const m = (err as Record<string, unknown>).message;
			if (typeof m === 'string' && m.trim()) return m;
		}
		if (typeof err === 'string' && err.trim()) return err;
		try {
			return JSON.stringify(body);
		} catch {
			return String(body);
		}
	}
	return `${res.status} ${res.statusText || 'TTS error'}`;
}

export const synthesizeOpenAISpeech = async (
	token: string = '',
	speaker: string = 'alloy',
	text: string = '',
	model?: string
) => {
	const res = await fetch(`${AUDIO_API_BASE_URL}/speech`, {
		method: 'POST',
		credentials: 'include',
		headers: {
			'Content-Type': 'application/json',
			...authBearerHeaders(token)
		},
		body: JSON.stringify({
			input: text,
			voice: speaker,
			...(model && { model })
		})
	});

	if (!res.ok) {
		const raw = await res.text();
		let parsed: unknown = null;
		if (raw) {
			try {
				parsed = JSON.parse(raw);
			} catch {
				parsed = null;
			}
		}
		const msg = parsed
			? ttsErrorMessage(res, parsed)
			: raw?.trim()
				? raw.slice(0, 2000)
				: ttsErrorMessage(res, null);
		throw new Error(msg);
	}

	return res;
};

interface AvailableModelsResponse {
	models: { name: string; id: string }[] | { id: string }[];
}

export const getModels = async (token: string = ''): Promise<AvailableModelsResponse> => {
	let error = null;

	const res = await fetch(`${AUDIO_API_BASE_URL}/models`, {
		method: 'GET',
		credentials: 'include',
		headers: {
			'Content-Type': 'application/json',
			...authBearerHeaders(token)
		}
	})
		.then(async (res) => {
			if (!res.ok) throw await res.json();
			return res.json();
		})
		.catch((err) => {
			error = err.detail;
			console.error(err);

			return null;
		});

	if (error) {
		throw error;
	}

	return res;
};

export const getVoices = async (token: string = '') => {
	let error = null;

	const res = await fetch(`${AUDIO_API_BASE_URL}/voices`, {
		method: 'GET',
		credentials: 'include',
		headers: {
			'Content-Type': 'application/json',
			...authBearerHeaders(token)
		}
	})
		.then(async (res) => {
			if (!res.ok) throw await res.json();
			return res.json();
		})
		.catch((err) => {
			error = err.detail;
			console.error(err);

			return null;
		});

	if (error) {
		throw error;
	}

	return res;
};
