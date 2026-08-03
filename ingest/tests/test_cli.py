"""Tests for the ingestion command's operational failures."""

from unittest.mock import Mock, patch

from typer.testing import CliRunner

from tapio_ingest.cli import app


@patch("tapio_ingest.cli.MarkdownVectorizer")
@patch("tapio_ingest.cli.Chroma")
@patch("tapio_ingest.cli.HuggingFaceEmbeddings")
def test_ingest_exits_nonzero_when_source_directory_is_unreadable(
    _embeddings: Mock,
    _chroma: Mock,
    vectorizer_class: Mock,
) -> None:
    """Do not report a successful ingest when discovery is denied."""
    vectorizer_class.return_value.process_directory.side_effect = PermissionError(
        "Permission denied",
    )

    result = CliRunner().invoke(app, ["unreadable"])

    assert result.exit_code != 0
    assert isinstance(result.exception, PermissionError)
