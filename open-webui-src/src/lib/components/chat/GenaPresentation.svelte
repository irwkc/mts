<script lang="ts">
	import { onDestroy, onMount } from 'svelte';
	import { genaPresentation, genaThinking, genaThinkingProgress } from '$lib/stores/genaPresentation';

	const MARK = 'data-gena-pptx-embed';

	let dockMinimized = false;

	$: p = $genaPresentation;
	$: progressPct = Math.round($genaThinkingProgress);

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

<!-- «gena думает…» + полоса прогресса -->
{#if $genaThinking}
	<div class="gena-thinking gena-thinking-visible" aria-live="polite">
		<div class="gena-thinking-card">
			<div class="gena-thinking-row">
				<span class="gena-thinking-spinner" aria-hidden="true"></span>
				<div class="gena-thinking-text">
					<span class="gena-thinking-title">gena думает…</span>
					<span class="gena-thinking-sub">ожидайте ответ — идёт обработка запроса</span>
				</div>
				<span class="gena-thinking-pct">{progressPct}%</span>
			</div>
			<div class="gena-progress-track" role="progressbar" aria-valuemin="0" aria-valuemax="100" aria-valuenow={progressPct}>
				<div class="gena-progress-fill" style="width: {$genaThinkingProgress}%"></div>
				<div class="gena-progress-shimmer"></div>
			</div>
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
		min-width: min(420px, calc(100vw - 32px));
	}
	.gena-thinking-visible {
		opacity: 1;
		transform: translateX(-50%) translateY(0);
		pointer-events: auto;
	}
	.gena-thinking-card {
		padding: 14px 16px 12px;
		border-radius: 14px;
		background: linear-gradient(145deg, oklch(0.22 0.06 285) 0%, oklch(0.18 0.055 270) 50%, oklch(0.16 0.05 250) 100%);
		border: 1px solid oklch(0.45 0.12 195 / 0.45);
		box-shadow:
			0 12px 40px oklch(0.05 0.05 280 / 0.55),
			0 0 0 1px oklch(0.55 0.15 295 / 0.15) inset;
		color: oklch(0.92 0.02 230);
		font-size: 13px;
		font-family: ui-sans-serif, system-ui, sans-serif;
	}
	.gena-thinking-row {
		display: flex;
		align-items: flex-start;
		gap: 12px;
		margin-bottom: 10px;
	}
	.gena-thinking-spinner {
		width: 20px;
		height: 20px;
		margin-top: 2px;
		border: 2px solid oklch(0.55 0.1 195 / 0.35);
		border-top-color: oklch(0.75 0.14 195);
		border-radius: 50%;
		animation: gena-spin 0.75s linear infinite;
		flex-shrink: 0;
	}
	@keyframes gena-spin {
		to {
			transform: rotate(360deg);
		}
	}
	.gena-thinking-text {
		display: flex;
		flex-direction: column;
		gap: 2px;
		flex: 1;
		min-width: 0;
	}
	.gena-thinking-title {
		font-weight: 600;
		color: oklch(0.95 0.03 200);
	}
	.gena-thinking-sub {
		font-size: 11px;
		color: oklch(0.72 0.04 235);
		line-height: 1.35;
	}
	.gena-thinking-pct {
		font-variant-numeric: tabular-nums;
		font-size: 12px;
		font-weight: 600;
		color: oklch(0.78 0.12 195);
		flex-shrink: 0;
	}
	.gena-progress-track {
		position: relative;
		height: 6px;
		border-radius: 999px;
		background: oklch(0.25 0.04 270 / 0.9);
		overflow: hidden;
		border: 1px solid oklch(0.4 0.08 295 / 0.35);
	}
	.gena-progress-fill {
		height: 100%;
		border-radius: 999px;
		background: linear-gradient(90deg, oklch(0.55 0.14 195), oklch(0.48 0.18 295));
		transition: width 0.25s ease-out;
		box-shadow: 0 0 12px oklch(0.55 0.14 195 / 0.45);
	}
	.gena-progress-shimmer {
		position: absolute;
		inset: 0;
		background: linear-gradient(
			90deg,
			transparent,
			oklch(0.95 0.05 200 / 0.12),
			transparent
		);
		animation: gena-shimmer 1.4s ease-in-out infinite;
		pointer-events: none;
	}
	@keyframes gena-shimmer {
		0% {
			transform: translateX(-100%);
		}
		100% {
			transform: translateX(100%);
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
		background: linear-gradient(165deg, oklch(0.2 0.055 285) 0%, oklch(0.14 0.05 270) 100%);
		border: 1px solid oklch(0.45 0.1 195 / 0.4);
		border-radius: 12px;
		box-shadow: 0 12px 40px oklch(0.05 0.04 280 / 0.6);
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
		background: oklch(0.28 0.08 295 / 0.35);
		border-bottom: 1px solid oklch(0.42 0.1 195 / 0.3);
	}
	.gena-dock-head strong {
		color: oklch(0.93 0.03 200);
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
		color: oklch(0.72 0.12 195);
		cursor: pointer;
		padding: 2px 6px;
		border-radius: 4px;
		font-size: 16px;
		line-height: 1;
	}
	.gena-dock-actions button:hover {
		background: oklch(0.95 0.02 230 / 0.08);
	}
	.gena-dock-body {
		padding: 10px 12px 14px;
		overflow-y: auto;
		flex: 1;
		color: oklch(0.82 0.03 235);
	}
	:global(.gena-phase) {
		display: flex;
		align-items: center;
		gap: 8px;
		padding: 4px 0;
		font-size: 12px;
		color: oklch(0.65 0.04 235);
	}
	:global(.gena-phase .dot) {
		width: 8px;
		height: 8px;
		border-radius: 50%;
		background: oklch(0.4 0.04 250);
		flex-shrink: 0;
	}
	:global(.gena-phase.gena-on .dot) {
		background: oklch(0.62 0.14 195);
		box-shadow: 0 0 10px oklch(0.55 0.14 195 / 0.65);
	}
	:global(.gena-phase.gena-done .dot) {
		background: oklch(0.55 0.14 195);
		box-shadow: 0 0 6px oklch(0.48 0.16 295 / 0.5);
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
		background: oklch(0.16 0.04 270);
		border: 1px solid oklch(0.35 0.06 280 / 0.8);
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
		background: linear-gradient(transparent, oklch(0.12 0.04 285 / 0.92));
		color: oklch(0.95 0.02 230);
		max-height: 2.6em;
		overflow: hidden;
	}
	.gena-slide-tile.gena-empty .gena-ph {
		display: flex;
		align-items: center;
		justify-content: center;
		height: 100%;
		color: oklch(0.55 0.04 235);
		font-size: 11px;
	}
	.gena-complete {
		margin-top: 12px;
		padding-top: 10px;
		border-top: 1px solid oklch(0.35 0.06 280 / 0.6);
	}
	.gena-dock-complete-label {
		font-size: 11px;
		color: oklch(0.65 0.04 235);
		margin-bottom: 8px;
	}
	.gena-err {
		color: oklch(0.75 0.12 25);
		font-size: 12px;
		margin-top: 8px;
	}

	:global(.gena-pptx-embed-wrap) {
		margin: 0.75rem 0 1rem 0;
		max-width: 100%;
		border-radius: 8px;
		overflow: hidden;
		border: 1px solid oklch(0.45 0.08 195 / 0.35);
		background: oklch(0.14 0.04 285);
	}
	:global(.gena-pptx-embed-iframe) {
		display: block;
		width: 100%;
		min-height: 420px;
		height: min(70vh, 640px);
		border: 0;
	}
</style>
