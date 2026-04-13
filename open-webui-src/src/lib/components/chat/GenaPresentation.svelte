<script lang="ts">
	import { genaPresentation } from '$lib/stores/genaPresentation';

	let dockMinimized = false;

	$: p = $genaPresentation;

	function phaseClass(st: string) {
		let c = 'gena-phase';
		if (st === 'on') c += ' gena-on';
		if (st === 'done') c += ' gena-done';
		return c;
	}
</script>

{#if p.visible}
	<div class="gena-dock" class:gena-dock-hidden={dockMinimized}>
		<div class="gena-dock-head">
			<strong>Презентация</strong>
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
			<div class={phaseClass(p.phases.research)}>
				<span class="dot"></span><span>Веб-поиск и контекст</span>
			</div>
			<div class={phaseClass(p.phases.llm)}>
				<span class="dot"></span><span>Структура слайдов (LLM)</span>
			</div>
			<div class={phaseClass(p.phases.images)}>
				<span class="dot"></span><span>Картинки по слайдам</span>
			</div>
			<div class={phaseClass(p.phases.build)}>
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
	.gena-dock {
		position: fixed;
		right: 0;
		top: 0;
		width: min(380px, 42vw);
		height: 100vh;
		max-height: 100vh;
		z-index: 999990;
		display: flex;
		flex-direction: column;
		font-family: ui-sans-serif, system-ui, sans-serif;
		font-size: 13px;
		background: linear-gradient(165deg, oklch(0.2 0.055 285) 0%, oklch(0.14 0.05 270) 100%);
		border: none;
		border-left: 1px solid oklch(0.45 0.1 195 / 0.45);
		border-radius: 0;
		box-shadow: -8px 0 32px oklch(0.05 0.04 280 / 0.45);
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
</style>
