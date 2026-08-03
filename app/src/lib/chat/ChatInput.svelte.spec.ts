import { page, userEvent } from 'vitest/browser';
import { describe, expect, it, vi } from 'vitest';
import { render } from 'vitest-browser-svelte';
import ChatInput from './ChatInput.svelte';

describe('ChatInput.svelte', () => {
	it('sends the message on Enter and clears the input', async () => {
		const onsend = vi.fn();
		render(ChatInput, { onsend });

		const textbox = page.getByRole('textbox');
		await userEvent.fill(textbox, 'Hello there');
		await userEvent.keyboard('{Enter}');

		expect(onsend).toHaveBeenCalledWith('Hello there');
		await expect.element(textbox).toHaveValue('');
	});

	it('does not send on Shift+Enter', async () => {
		const onsend = vi.fn();
		render(ChatInput, { onsend });

		const textbox = page.getByRole('textbox');
		await userEvent.fill(textbox, 'Hello');
		await userEvent.keyboard('{Shift>}{Enter}{/Shift}');

		expect(onsend).not.toHaveBeenCalled();
	});

	it('disables the send button while disabled', async () => {
		render(ChatInput, { disabled: true, onsend: vi.fn() });

		await expect.element(page.getByRole('button', { name: 'Send' })).toBeDisabled();
	});
});
