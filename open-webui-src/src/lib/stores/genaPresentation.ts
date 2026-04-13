import { writable } from 'svelte/store';

/** Показывается после chat:start до первого chat:completion. */
export const genaThinking = writable(false);

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
