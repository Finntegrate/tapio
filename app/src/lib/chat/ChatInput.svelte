<script lang="ts">
	import * as m from '$lib/paraglide/messages.js';

	interface Props {
		disabled?: boolean;
		onsend: (text: string) => void;
	}

	let { disabled = false, onsend }: Props = $props();
	let value = $state('');

	function submit() {
		if (!value.trim() || disabled) return;
		onsend(value);
		value = '';
	}

	function handleKeydown(event: KeyboardEvent) {
		if (event.key === 'Enter' && !event.shiftKey) {
			event.preventDefault();
			submit();
		}
	}
</script>

<form
	class="flex gap-2 border-t border-slate-200 p-4 dark:border-slate-800"
	onsubmit={(event) => {
		event.preventDefault();
		submit();
	}}
>
	<textarea
		bind:value
		{disabled}
		onkeydown={handleKeydown}
		rows="2"
		placeholder={m.chat_placeholder()}
		class="flex-1 resize-none rounded-lg border border-slate-300 px-3 py-2 focus:border-emerald-600 focus:outline-none disabled:opacity-50 dark:border-slate-700 dark:bg-slate-900"
	></textarea>
	<button
		type="submit"
		{disabled}
		class="rounded-lg bg-emerald-700 px-4 py-2 font-medium text-white disabled:opacity-50"
	>
		{m.chat_send()}
	</button>
</form>
