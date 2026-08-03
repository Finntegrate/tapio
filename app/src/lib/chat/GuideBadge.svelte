<script lang="ts">
	interface Props {
		name: string;
		title?: string;
		color?: string;
	}

	let { name, title, color }: Props = $props();

	const colorClasses: Record<string, string> = {
		forest: 'bg-emerald-600',
		amber: 'bg-amber-500',
		nordic: 'bg-sky-600'
	};
</script>

<span
	class="inline-flex items-center gap-2 rounded-full bg-slate-100 px-3 py-1 text-sm font-medium text-slate-800 dark:bg-slate-800 dark:text-slate-100"
>
	<span class="h-2 w-2 rounded-full {colorClasses[color ?? ''] ?? 'bg-slate-400'}"></span>
	<span>{name}</span>
	{#if title}
		<span class="text-slate-500 dark:text-slate-400">· {title}</span>
	{/if}
</span>
