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
		if (event.key === 'Enter' && !event.shiftKey && !event.isComposing) {
			event.preventDefault();
			submit();
		}
	}
</script>

<form
	class="flex gap-2 border-t border-pine-700 p-4"
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
		class="flex-1 resize-none rounded-lg border border-pine-700 bg-pine-900 px-3 py-2 text-pine-100 placeholder-pine-400 focus:border-lichen-500 focus:outline-none disabled:opacity-50"
	></textarea>
	<button
		type="submit"
		{disabled}
		class="rounded-lg bg-emerald-700 px-4 py-2 font-medium text-white hover:bg-emerald-600 disabled:opacity-50"
	>
		{m.chat_send()}
	</button>
</form>
