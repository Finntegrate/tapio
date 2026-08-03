<script lang="ts">
	import * as m from '$lib/paraglide/messages.js';
	import type { Citation } from '$lib/api/types';

	interface Props {
		citations: Citation[];
	}

	let { citations }: Props = $props();
</script>

{#if citations.length > 0}
	<div class="mt-2">
		<p class="text-xs font-medium text-slate-500 dark:text-slate-400">{m.chat_sources_heading()}</p>
		<div class="mt-1 flex flex-wrap gap-2 text-xs">
			<!-- eslint-disable svelte/no-navigation-without-resolve -- external source URLs from the backend, not internal SvelteKit routes -->
			{#each citations as citation, index (index + citation.source_url + citation.title)}
				<a
					href={citation.source_url}
					target="_blank"
					rel="noopener noreferrer"
					title={citation.snippet}
					class="rounded-full border border-slate-300 px-2 py-1 text-slate-600 hover:bg-slate-100 dark:border-slate-700 dark:text-slate-300 dark:hover:bg-slate-800"
				>
					{citation.title}
				</a>
			{/each}
			<!-- eslint-enable svelte/no-navigation-without-resolve -->
		</div>
	</div>
{/if}
