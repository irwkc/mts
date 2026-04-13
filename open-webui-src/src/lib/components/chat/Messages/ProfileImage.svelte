<script lang="ts">
	import { WEBUI_BASE_URL } from '$lib/constants';
	import { useModelProfileImageFallback } from '$lib/utils/modelImageFallback';

	export let className = 'size-8';
	export let src = `${WEBUI_BASE_URL}/static/favicon.png`;

	$: resolvedSrc =
		src === ''
			? `${WEBUI_BASE_URL}/static/favicon.png`
			: src.startsWith(WEBUI_BASE_URL) ||
				  src.startsWith('https://www.gravatar.com/avatar/') ||
				  src.startsWith('data:') ||
				  src.startsWith('/')
				? src
				: `${WEBUI_BASE_URL}/user.png`;

	function onError(ev: Event) {
		const el = ev.currentTarget as HTMLImageElement;
		const attempt = el.getAttribute('src') || '';
		if (attempt.includes('/models/model/profile')) {
			useModelProfileImageFallback(ev);
		} else if (!el.src.includes('/static/favicon.png')) {
			el.src = `${WEBUI_BASE_URL}/static/favicon.png`;
		}
	}
</script>

<img
	aria-hidden="true"
	src={resolvedSrc}
	class=" {className} object-cover rounded-full"
	alt="profile"
	draggable="false"
	on:error={onError}
/>
