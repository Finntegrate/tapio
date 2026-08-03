"""Integration tests for the parser pipeline."""

from pathlib import Path

import pytest

from tapio_crawler.parser.parser import Parser


@pytest.mark.integration
def test_parser_pipeline(tmp_path, test_config_manager):
    """Test complete parsing pipeline from HTML to Markdown.

    This test:
    1. Creates test HTML files
    2. Creates parser with injected config
    3. Parses HTML to Markdown
    4. Verifies output files are created
    """
    # Create test HTML input directory
    input_dir = tmp_path / "content" / "test_site" / "crawled"
    input_dir.mkdir(parents=True)

    # Create output directory
    output_dir = tmp_path / "content" / "test_site" / "parsed"
    output_dir.mkdir(parents=True)

    # Create test HTML file
    test_html = input_dir / "test_page.html"
    test_html.write_text("""
<!DOCTYPE html>
<html>
<head>
    <title>Test Page</title>
</head>
<body>
    <main>
        <h1>Test Document</h1>
        <p>This is a test document about residence permits.</p>
        <h2>Requirements</h2>
        <p>You need a valid passport.</p>
    </main>
</body>
</html>
""")

    # Get site config from test config manager
    site_config = test_config_manager.get_site_config("test_site")

    # Create parser with injected dependencies
    parser = Parser(
        site_name="test_site",
        site_config=site_config,
        input_dir=str(input_dir),
        output_dir=str(output_dir),
    )

    # Parse the file
    results = parser.parse_all()

    # Verify parsing occurred
    assert len(results) == 1
    assert "output_file" in results[0]
    assert "title" in results[0]

    # Verify output file was created
    output_file = Path(results[0]["output_file"])
    assert output_file.exists()

    # Verify output content
    content = output_file.read_text()
    assert "Test Document" in content
    assert "residence permits" in content
    assert "Requirements" in content

    # Verify frontmatter was added (should have --- markers)
    assert content.startswith("---")


@pytest.mark.integration
def test_parser_batch_processing(tmp_path, test_config_manager):
    """Test parser handles multiple HTML files correctly."""
    # Create directories
    input_dir = tmp_path / "content" / "test_site" / "crawled"
    input_dir.mkdir(parents=True)
    output_dir = tmp_path / "content" / "test_site" / "parsed"
    output_dir.mkdir(parents=True)

    # Create multiple HTML files
    for i in range(3):
        test_html = input_dir / f"page_{i}.html"
        test_html.write_text(f"""
<!DOCTYPE html>
<html>
<head><title>Page {i}</title></head>
<body>
    <main>
        <h1>Document {i}</h1>
        <p>Content for document {i}</p>
    </main>
</body>
</html>
""")

    # Get site config
    site_config = test_config_manager.get_site_config("test_site")

    # Create parser
    parser = Parser(
        site_name="test_site",
        site_config=site_config,
        input_dir=str(input_dir),
        output_dir=str(output_dir),
    )

    # Parse all files
    results = parser.parse_all()

    # Verify all files were processed
    assert len(results) == 3

    # Verify all have required fields
    for result in results:
        assert "output_file" in result
        assert "title" in result

    # Verify all output files exist
    for i in range(3):
        # Find the result for this page
        matching_results = [r for r in results if f"page_{i}" in r["output_file"]]
        assert len(matching_results) == 1

        output_file = Path(matching_results[0]["output_file"])
        assert output_file.exists()
        content = output_file.read_text()
        assert f"Document {i}" in content
