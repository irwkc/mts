import { writable } from 'svelte/store';

/** Статус нейро-картинки: спиннер и подпись у имени модели (delta.gena из шлюза). */
export const genaImageGeneration = writable<{ active: boolean; label: string }>({
	active: false,
	label: ''
});

export function applyGenaImageDelta(raw: unknown) {
	const d = raw as { type?: string };
	if (!d || typeof d !== 'object' || !d.type) return;
	if (d.type === 'image_generation_start') {
		genaImageGeneration.set({ active: true, label: 'Генерация изображения…' });
	}
	if (d.type === 'image_generation_done') {
		genaImageGeneration.set({ active: false, label: '' });
	}
}

export function clearGenaImageGeneration() {
	genaImageGeneration.set({ active: false, label: '' });
}
