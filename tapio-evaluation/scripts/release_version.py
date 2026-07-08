import os
import shutil
import sys


def release_version(version_name):
    """Snapshots active datasets, retrieval, and taxonomy directories into a version folder."""
    root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    target_version_dir = os.path.join(root_dir, "versions", version_name)

    if os.path.exists(target_version_dir):
        print(f"Error: Version {version_name} already exists.")
        sys.exit(1)

    directories_to_copy = ["datasets", "retrieval", "taxonomy"]

    print(f"Creating snapshot for version: {version_name}...")
    os.makedirs(target_version_dir, exist_ok=True)

    for directory in directories_to_copy:
        src = os.path.join(root_dir, directory)
        dst = os.path.join(target_version_dir, directory)

        if os.path.exists(src):
            shutil.copytree(src, dst)
            print(f" -> Archived '{directory}' successfully.")
        else:
            print(f" -> Warning: Source directory '{directory}' does not exist. Skipping.")

    print(f"Version {version_name} successfully archived. Please update versions/changelog.md!")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python release_version.py <version_tag> (e.g., v1.1)")
        sys.exit(1)

    release_version(sys.argv[1])
