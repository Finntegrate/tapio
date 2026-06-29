"""Plain document model used for simple URL/content/metadata grouping."""


class Document:
    """A piece of content fetched from a URL, with associated metadata."""

    def __init__(self, url: str, content: str, metadata: dict) -> None:
        """Initialize the document.

        Args:
            url: Source URL of the document
            content: Document content
            metadata: Arbitrary metadata associated with the document
        """
        self.url = url
        self.content = content
        self.metadata = metadata

    def to_dict(self) -> dict[str, str | dict]:
        """Convert the document to a plain dictionary."""
        return {
            "url": self.url,
            "content": self.content,
            "metadata": self.metadata,
        }
