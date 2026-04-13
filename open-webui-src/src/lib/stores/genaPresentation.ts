import { writable } from 'svelte/store';

/** Показывается после chat:start до первого chat:completion. */
export const genaThinking = writable(false);

/** Псевдо-прогресс 0–100 пока gena «думает» (нет реального % от API). */
export const genaThinkingProgress = writable(0);

let progressTimer: ReturnType<typeof setInterval> | null = null;

function startThinkingProgress() {
	genaThinkingProgress.set(6);
	if (progressTimer) clearInterval(progressTimer);
	progressTimer = setInterval(() => {
		genaThinkingProgress.update((p) => {
			const headroom = 96 - p;
			const step = headroom * 0.06 + Math.random() * 4;
			return Math.min(p + step, 94);
		});
	}, 320);
}

function stopThinkingProgress() {
	if (progressTimer) {
		clearInterval(progressTimer);
		progressTimer = null;
	}
	genaThinkingProgress.set(100);
	setTimeout(() => genaThinkingProgress.set(0), 450);
}

/** Включить/выключить индикатор «gena думает» и анимацию прогресса. */
export function setGenaThinking(on: boolean) {
	genaThinking.set(on);
	if (on) startThinkingProgress();
	else stopThinkingProgress();
}

export type GenaPhaseId = 'research' | 'llm' | 'images' | 'build';

export type GenaPhaseState = 'off' | 'on' | 'done';

export type GenaPresentationState = {
	visible: boolean;
	minimized: boolean;
	phases: Record<GenaPhaseId, GenaPhaseState>;
	slides: Array<{ index: number; title?: string }>;
	slidePreview: Record<number, string | undefined>;
	completeNote: string;
	error: string;
};

function emptyPhases(): Record<GenaPhaseId, GenaPhaseState> {
	return {
		research: 'off',
		llm: 'off',
		images: 'off',
		build: 'off'
	};
}

function initialState(): GenaPresentationState {
	return {
		visible: false,
		minimized: false,
		phases: emptyPhases(),
		slides: [],
		slidePreview: {},
		completeNote: '',
		error: ''
	};
}

export const genaPresentation = writable<GenaPresentationState>(initialState());

/** События из choices[0].delta.gena (SSE), проброшенные через WebUI как chat:completion. */
export function applyGenaDelta(raw: unknown) {
	const d = raw as { type?: string; phase?: string; slides?: unknown[]; [key: string]: unknown };
	if (!d || typeof d !== 'object' || !d.type) {
		return;
	}

	genaPresentation.update((s) => {
		switch (d.type) {
			case 'presentation_start':
				return {
					...initialState(),
					visible: true,
					phases: { ...emptyPhases(), research: 'on' }
				};
			case 'phase': {
				const phases = { ...s.phases };
				const ph = String(d.phase ?? '');
				if (ph === 'research') phases.research = 'on';
				if (ph === 'research_done') phases.research = 'done';
				if (ph === 'llm') phases.llm = 'on';
				if (ph === 'images') {
					phases.llm = 'done';
					phases.images = 'on';
				}
				if (ph === 'build') {
					phases.images = 'done';
					phases.build = 'on';
				}
				if (ph === 'done') phases.build = 'done';
				return { ...s, phases };
			}
			case 'deck_structure': {
				const slidesIn = Array.isArray(d.slides) ? d.slides : [];
				const slides = slidesIn.map((x: { index?: number; title?: string }, i: number) => ({
					index: typeof x?.index === 'number' ? x.index : i,
					title: x?.title
				}));
				return { ...s, slides };
			}
			case 'slide_image': {
				const idx = d.slide_index as number;
				const raw = d.preview_url as string | undefined;
				const url = raw && String(raw).trim() ? raw : undefined;
				return {
					...s,
					slidePreview: { ...s.slidePreview, [idx]: url }
				};
			}
			case 'presentation_complete':
				return {
					...s,
					phases: { ...s.phases, build: 'done' },
					completeNote: 'Готово — ссылки на PPTX/PDF в сообщении чата'
				};
			case 'error':
				return { ...s, error: String(d.message ?? 'Ошибка') };
			default:
				return s;
		}
	});
}
