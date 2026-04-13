import { writable } from 'svelte/store';

/** Статус нейро-картинки: спиннер и подпись только у того ответа, в чьём стриме пришёл gena. */
export const genaImageGeneration = writable<{
	active: boolean;
	label: string;
	messageId: string | null;
}>({
	active: false,
	label: '',
	messageId: null
});

export function applyGenaImageDelta(raw: unknown, forMessageId: string | null) {
	const d = raw as { type?: string };
	if (!d || typeof d !== 'object' || !d.type) return;
	if (d.type === 'image_generation_start') {
		genaImageGeneration.set({
			active: true,
			label: 'Генерация изображения…',
			messageId: forMessageId
		});
	}
	if (d.type === 'image_generation_done') {
		genaImageGeneration.set({ active: false, label: '', messageId: null });
	}
}

export function clearGenaImageGeneration() {
	genaImageGeneration.set({ active: false, label: '', messageId: null });
}
