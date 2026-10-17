import { describe, expect, it } from 'vitest';
import { safeHttpsUrl } from './safe-url';

describe('safeHttpsUrl', () => {
	it('keeps an https URL', () => {
		expect(safeHttpsUrl('https://migri.fi/en/residence-permit')).toBe(
			'https://migri.fi/en/residence-permit'
		);
	});

	it.each([
		'javascript:alert(1)',
		'JavaScript:alert(1)',
		'data:text/html,<script>alert(1)</script>',
		'http://migri.fi',
		'/relative/path',
		'not a url'
	])('rejects %s', (url) => {
		expect(safeHttpsUrl(url)).toBeUndefined();
	});
});
