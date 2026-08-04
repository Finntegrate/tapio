<script lang="ts">
	import { AGENT_DOT_CLASSES } from './agent-colors';

	interface Props {
		name: string;
		title?: string;
		color?: string;
	}

	let { name, title, color }: Props = $props();
</script>

<span
	class="inline-flex items-center gap-2 rounded-full bg-pine-800 px-3 py-1 text-sm font-medium text-pine-100"
>
	<span class="h-2 w-2 rounded-full {AGENT_DOT_CLASSES[color ?? ''] ?? 'bg-pine-400'}"></span>
	<span>{name}</span>
	{#if title}
		<span class="text-pine-400">· {title}</span>
	{/if}
</span>
