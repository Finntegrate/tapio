/**
 * Return `url` normalized if it is an absolute `https` URL, else `undefined`.
 *
 * Citation URLs come from crawled pages via the backend, which is untrusted input
 * (ADR 0011), so a `javascript:`, `data:`, or plain `http:` URL must never become a link.
 */
export function safeHttpsUrl(url: string): string | undefined {
	try {
		const parsed = new URL(url);
		return parsed.protocol === 'https:' ? parsed.href : undefined;
	} catch {
		return undefined;
	}
}
