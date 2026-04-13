<script lang="ts">
	import { onDestroy, onMount } from 'svelte';
	import { genaPresentation, genaThinking } from '$lib/stores/genaPresentation';

	const MARK = 'data-gena-pptx-embed';

	let dockMinimized = false;

	$: p = $genaPresentation;

	function previewUrlFromAnchor(a: HTMLAnchorElement): string | null {
		const href = a.getAttribute('href');
		if (!href) return null;
		try {
			const u = new URL(href, window.location.href);
			if (!/\.pptx$/i.test(u.pathname)) return null;
			if (!/\/static\/presentations\/[^/]+\.pptx$/i.test(u.pathname)) return null;
			const rel = u.pathname.replace(/^\//, '');
			return `${u.origin}/preview/pptx?path=${encodeURIComponent(rel)}`;
		} catch {
			return null;
		}
	}

	function enhancePptxEmbeds(root: ParentNode) {
		const links = root.querySelectorAll('a[href*=".pptx"]');
		for (const node of links) {
			const a = node as HTMLAnchorElement;
			if (a.getAttribute(MARK)) continue;
			const pv = previewUrlFromAnchor(a);
			if (!pv) continue;
			a.setAttribute(MARK, '1');
			const wrap = document.createElement('div');
			wrap.className = 'gena-pptx-embed-wrap';
			const iframe = document.createElement('iframe');
			iframe.className = 'gena-pptx-embed-iframe';
			iframe.src = pv;
			iframe.title = 'Предпросмотр';
			iframe.loading = 'lazy';
			iframe.setAttribute('referrerpolicy', 'no-referrer-when-downgrade');
			wrap.appendChild(iframe);
			a.insertAdjacentElement('afterend', wrap);
		}
	}

	let mo: MutationObserver | undefined;

	onMount(() => {
		enhancePptxEmbeds(document.body);
		mo = new MutationObserver(() => enhancePptxEmbeds(document.body));
		mo.observe(document.body, { childList: true, subtree: true });
	});

	onDestroy(() => mo?.disconnect());

	function phaseClass(id: string, st: string) {
		let c = 'gena-phase';
		if (st === 'on') c += ' gena-on';
		if (st === 'done') c += ' gena-done';
		return c;
	}
</script>

<!-- «gena думает…» -->
{#if $genaThinking}
	<div class="gena-thinking gena-thinking-visible" aria-live="polite">
		<div class="gena-thinking-card">
			<span class="gena-thinking-spinner" aria-hidden="true"></span>
			<span>gena думает…</span>
		</div>
	</div>
{/if}

<!-- Док презентации -->
{#if p.visible}
	<div class="gena-dock" class:gena-dock-hidden={dockMinimized}>
		<div class="gena-dock-head">
			<strong>gena · презентация</strong>
			<div class="gena-dock-actions">
				<button type="button" title="Свернуть" on:click={() => (dockMinimized = !dockMinimized)}
					>−</button
				>
				<button type="button" title="Закрыть" on:click={() => genaPresentation.update((s) => ({ ...s, visible: false }))}
					>×</button
				>
			</div>
		</div>
		<div class="gena-dock-body">
			<div class={phaseClass('research', p.phases.research)}>
				<span class="dot"></span><span>Веб-поиск и контекст</span>
			</div>
			<div class={phaseClass('llm', p.phases.llm)}>
				<span class="dot"></span><span>Структура слайдов (LLM)</span>
			</div>
			<div class={phaseClass('images', p.phases.images)}>
				<span class="dot"></span><span>Картинки по слайдам</span>
			</div>
			<div class={phaseClass('build', p.phases.build)}>
				<span class="dot"></span><span>Сборка PPTX</span>
			</div>

			{#if p.slides.length > 0}
				<div class="gena-slides-grid">
					{#each p.slides as s (s.index)}
						<div class="gena-slide-tile" class:gena-empty={!p.slidePreview[s.index]}>
							{#if p.slidePreview[s.index]}
								<img src={p.slidePreview[s.index]} alt="" loading="lazy" />
								<div class="gena-slide-cap">#{s.index + 1}</div>
							{:else}
								<div class="gena-ph">…</div>
								<div class="gena-slide-cap">{s.title ?? `Слайд ${s.index + 1}`}</div>
							{/if}
						</div>
					{/each}
				</div>
			{/if}

			{#if p.completeNote}
				<div class="gena-complete">
					<div class="gena-dock-complete-label">{p.completeNote}</div>
				</div>
			{/if}
			{#if p.error}
				<div class="gena-err">{p.error}</div>
			{/if}
		</div>
	</div>
{/if}

<style>
	.gena-thinking {
		position: fixed;
		bottom: 100px;
		left: 50%;
		transform: translateX(-50%) translateY(20px);
		z-index: 999991;
		opacity: 0;
		pointer-events: none;
		transition:
			opacity 0.2s ease,
			transform 0.2s ease;
	}
	.gena-thinking-visible {
		opacity: 1;
		transform: translateX(-50%) translateY(0);
		pointer-events: auto;
	}
	.gena-thinking-card {
		display: flex;
		align-items: center;
		gap: 10px;
		padding: 10px 16px;
		border-radius: 999px;
		background: linear-gradient(135deg, rgba(30, 27, 75, 0.95), rgba(15, 23, 42, 0.95));
		border: 1px solid rgba(99, 102, 241, 0.45);
		color: #e0e7ff;
		font-size: 13px;
		font-family: ui-sans-serif, system-ui, sans-serif;
		box-shadow: 0 8px 32px rgba(0, 0, 0, 0.45);
	}
	.gena-thinking-spinner {
		width: 18px;
		height: 18px;
		border: 2px solid rgba(199, 210, 254, 0.35);
		border-top-color: #a5b4fc;
		border-radius: 50%;
		animation: gena-spin 0.7s linear infinite;
		flex-shrink: 0;
	}
	@keyframes gena-spin {
		to {
			transform: rotate(360deg);
		}
	}

	.gena-dock {
		position: fixed;
		right: 12px;
		top: 72px;
		width: min(380px, calc(100vw - 24px));
		max-height: min(82vh, 900px);
		z-index: 999990;
		display: flex;
		flex-direction: column;
		font-family: ui-sans-serif, system-ui, sans-serif;
		font-size: 13px;
		background: linear-gradient(165deg, #16161e 0%, #0c0c10 100%);
		border: 1px solid rgba(99, 102, 241, 0.35);
		border-radius: 12px;
		box-shadow: 0 12px 40px rgba(0, 0, 0, 0.55);
		overflow: hidden;
		transition:
			transform 0.2s ease,
			opacity 0.2s ease;
	}
	.gena-dock-hidden {
		transform: translateX(calc(100% + 24px));
		opacity: 0;
		pointer-events: none;
	}
	.gena-dock-head {
		display: flex;
		align-items: center;
		justify-content: space-between;
		padding: 10px 12px;
		background: rgba(99, 102, 241, 0.15);
		border-bottom: 1px solid rgba(99, 102, 241, 0.25);
	}
	.gena-dock-head strong {
		color: #e0e7ff;
		font-weight: 600;
		font-size: 13px;
	}
	.gena-dock-actions {
		display: flex;
		gap: 6px;
	}
	.gena-dock-actions button {
		background: transparent;
		border: none;
		color: #a5b4fc;
		cursor: pointer;
		padding: 2px 6px;
		border-radius: 4px;
		font-size: 16px;
		line-height: 1;
	}
	.gena-dock-actions button:hover {
		background: rgba(255, 255, 255, 0.08);
	}
	.gena-dock-body {
		padding: 10px 12px 14px;
		overflow-y: auto;
		flex: 1;
		color: #d1d5db;
	}
	:global(.gena-phase) {
		display: flex;
		align-items: center;
		gap: 8px;
		padding: 4px 0;
		font-size: 12px;
		color: #9ca3af;
	}
	:global(.gena-phase .dot) {
		width: 8px;
		height: 8px;
		border-radius: 50%;
		background: #374151;
		flex-shrink: 0;
	}
	:global(.gena-phase.gena-on .dot) {
		background: #6366f1;
		box-shadow: 0 0 8px rgba(99, 102, 241, 0.7);
	}
	:global(.gena-phase.gena-done .dot) {
		background: #22c55e;
	}
	.gena-slides-grid {
		display: grid;
		grid-template-columns: repeat(2, 1fr);
		gap: 8px;
		margin-top: 10px;
	}
	.gena-slide-tile {
		position: relative;
		border-radius: 8px;
		overflow: hidden;
		background: #0f0f14;
		border: 1px solid #2d2d38;
		aspect-ratio: 16 / 10;
	}
	.gena-slide-tile img {
		width: 100%;
		height: 100%;
		object-fit: cover;
		display: block;
	}
	.gena-slide-cap {
		position: absolute;
		bottom: 0;
		left: 0;
		right: 0;
		padding: 4px 6px;
		font-size: 10px;
		line-height: 1.2;
		background: linear-gradient(transparent, rgba(0, 0, 0, 0.85));
		color: #f3f4f6;
		max-height: 2.6em;
		overflow: hidden;
	}
	.gena-slide-tile.gena-empty .gena-ph {
		display: flex;
		align-items: center;
		justify-content: center;
		height: 100%;
		color: #6b7280;
		font-size: 11px;
	}
	.gena-complete {
		margin-top: 12px;
		padding-top: 10px;
		border-top: 1px solid #2d2d38;
	}
	.gena-dock-complete-label {
		font-size: 11px;
		color: #9ca3af;
		margin-bottom: 8px;
	}
	.gena-err {
		color: #fca5a5;
		font-size: 12px;
		margin-top: 8px;
	}

	:global(.gena-pptx-embed-wrap) {
		margin: 0.75rem 0 1rem 0;
		max-width: 100%;
		border-radius: 8px;
		overflow: hidden;
		border: 1px solid rgba(128, 128, 128, 0.35);
		background: #111;
	}
	:global(.gena-pptx-embed-iframe) {
		display: block;
		width: 100%;
		min-height: 420px;
		height: min(70vh, 640px);
		border: 0;
	}
</style>
