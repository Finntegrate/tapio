"""Tests for the ingestion command's operational failures."""

from unittest.mock import Mock, patch

from typer.testing import CliRunner

from tapio_ingest.cli import DEFAULT_CONTENT_DIR, app


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


@patch("tapio_ingest.cli.MarkdownVectorizer")
@patch("tapio_ingest.cli.Chroma")
@patch("tapio_ingest.cli.HuggingFaceEmbeddings")
def test_ingest_uses_the_shared_content_directory_by_default(
    _embeddings: Mock,
    _chroma: Mock,
    vectorizer_class: Mock,
) -> None:
    """Verify the CLI consumes the shared-folder contract without a crawler import.

    :return: None.
    """
    vectorizer_class.return_value.process_directory.return_value = 2

    result = CliRunner().invoke(app, ["--site", "migri"])

    assert result.exit_code == 0
    assert result.stdout == "Ingested 2 documents.\n"
    vectorizer_class.return_value.process_directory.assert_called_once_with(
        DEFAULT_CONTENT_DIR,
        site_filter="migri",
    )
