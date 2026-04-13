<script lang="ts">
	import { createEventDispatcher } from 'svelte';

	/** { id, label, hint } из delta.gena (шлюз gpthub-gateway) */
	export let styles: Array<{ id: string; label: string; hint?: string }> = [];
	export let history: { messages: Record<string, any> };
	export let assistantMessageId: string;
	export let submitMessage: (parentId: string, prompt: string) => void;

	const dispatch = createEventDispatcher();

	let picked: string | null = null;

	function stripStylePrefix(s: string): string {
		return s.replace(/^\s*\[gena_style:[a-z0-9_-]+\]\s*/i, '').trim();
	}

	function baseUserPrompt(): string {
		const msg = history?.messages?.[assistantMessageId];
		const pid = msg?.parentId;
		const u = pid ? history.messages[pid] : null;
		const c = u?.content;
		return typeof c === 'string' ? stripStylePrefix(c) : '';
	}

	function selectStyle(styleId: string) {
		if (picked) return;
		picked = styleId;
		const body = baseUserPrompt();
		const content = `[gena_style:${styleId}]\n\n${body}`;
		submitMessage(assistantMessageId, content);
		dispatch('selected', { styleId });
	}
</script>

<div
	class="gena-style-picker mt-3 mb-1 w-full max-w-2xl rounded-2xl border border-gray-200/80 dark:border-indigo-500/25 bg-gradient-to-br from-gray-50/95 via-white/90 to-teal-50/30 dark:from-gray-900/90 dark:via-indigo-950/40 dark:to-gray-950/95 p-4 sm:p-5 shadow-sm relative z-20"
	role="region"
	aria-label="Выбор стиля презентации"
>
	<div class="grid grid-cols-2 sm:grid-cols-3 gap-2.5">
		{#each styles as s (s.id)}
			<button
				type="button"
				disabled={picked !== null}
				class="gena-style-btn flex flex-col items-stretch text-left rounded-xl px-4 py-3.5 min-h-[4.5rem] text-sm transition-all border gap-1
					{picked === s.id
					? 'border-teal-500/70 bg-teal-500/15 text-gray-900 dark:text-white ring-1 ring-teal-400/40'
					: picked
						? 'border-gray-200/50 dark:border-gray-700/50 opacity-45 cursor-not-allowed'
						: 'border-gray-200/90 dark:border-indigo-500/20 bg-white/80 dark:bg-gray-850/80 hover:border-teal-400/55 hover:bg-teal-500/5 dark:hover:bg-indigo-500/10 text-gray-800 dark:text-gray-100 cursor-pointer'}"
				on:click={() => selectStyle(s.id)}
			>
				<span class="font-semibold block leading-snug text-[0.9375rem]">{s.label}</span>
				{#if s.hint}
					<span
						class="text-[0.8125rem] text-gray-600 dark:text-gray-300/95 mt-0.5 block leading-relaxed font-normal"
						>{s.hint}</span
					>
				{/if}
			</button>
		{/each}
	</div>
</div>

<style>
	.gena-style-btn:focus-visible {
		outline: 2px solid oklch(0.62 0.14 195);
		outline-offset: 2px;
	}
</style>
