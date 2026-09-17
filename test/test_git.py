# pycargoebuild
# (c) 2026 Anthony Lannutti <lannuttia@gmail.com>
# SPDX-License-Identifier: GPL-2.0-or-later

import tarfile
import tempfile
from pathlib import Path
from test.fixtures.git_repos import (
    create_git_repo_with_submodule,
    create_simple_git_repo,
)

import pytest

from pycargoebuild.cargo import GitCrate
from pycargoebuild.git import _create_tarball, clone_git_crate


class TestCreateTarball:
    """Tests for tarball creation without git operations."""

    def test_creates_tarball_with_prefix(self, tmp_path):
        """Test that tarball is created with correct prefix structure."""
        # Create a test directory structure
        source = tmp_path / "source"
        source.mkdir()
        (source / "file.txt").write_text("test content")
        (source / "subdir").mkdir()
        (source / "subdir" / "nested.txt").write_text("nested")

        # Create tarball
        output = tmp_path / "test.tar.gz"
        _create_tarball(source, output, "myrepo-abc123")

        # Verify tarball contents
        assert output.exists()
        with tarfile.open(output, "r:gz") as tar:
            names = sorted(tar.getnames())
            assert "myrepo-abc123/file.txt" in names
            assert "myrepo-abc123/subdir" in names
            assert "myrepo-abc123/subdir/nested.txt" in names

    def test_skips_git_directories(self, tmp_path):
        """Test that .git directories are excluded from tarball."""
        source = tmp_path / "source"
        source.mkdir()
        (source / ".git").mkdir()
        (source / ".git" / "config").write_text("git config")
        (source / "file.txt").write_text("keep this")

        output = tmp_path / "test.tar.gz"
        _create_tarball(source, output, "repo-123")

        with tarfile.open(output, "r:gz") as tar:
            names = tar.getnames()
            assert "repo-123/file.txt" in names
            assert not any(".git" in name for name in names)


class TestCloneGitCrate:
    """Tests for git cloning operations using real git repos."""

    def test_clone_simple_repo(self, tmp_path):
        """Test cloning a simple repository without submodules."""
        # Create a real git repository
        with tempfile.TemporaryDirectory() as git_tmpdir:
            fixture = create_simple_git_repo(Path(git_tmpdir))

            # Create a GitCrate pointing to the local repo
            # Use file:// URL for local testing
            crate = GitCrate(
                name="test-crate",
                version="1.0.0",
                repository=f"file://{fixture.path}",
                commit=fixture.commit,
            )

            # Clone it
            distdir = tmp_path / "distdir"
            distdir.mkdir()

            result = clone_git_crate(crate, distdir)

            # Verify tarball was created
            assert result.exists()
            assert result.name == crate.filename

            # Verify tarball contains expected files
            with tarfile.open(result, "r:gz") as tar:
                names = tar.getnames()
                # Should have format: test-crate-{commit}/...
                assert any("Cargo.toml" in name for name in names)
                assert any("src/lib.rs" in name for name in names)

    def test_clone_repo_with_submodule(self, tmp_path):
        """Test cloning a repository with submodules."""
        with tempfile.TemporaryDirectory() as git_tmpdir:
            fixture = create_git_repo_with_submodule(Path(git_tmpdir))

            crate = GitCrate(
                name="main-crate",
                version="1.0.0",
                repository=f"file://{fixture.path}",
                commit=fixture.commit,
            )

            distdir = tmp_path / "distdir"
            distdir.mkdir()

            result = clone_git_crate(crate, distdir)

            # Verify tarball exists
            assert result.exists()

            # Verify submodule contents are included
            with tarfile.open(result, "r:gz") as tar:
                names = tar.getnames()
                # Main repo files
                assert any("Cargo.toml" in name for name in names)
                # Submodule files should be present
                assert any("submodule-repo" in name for name in names)
                assert any("submodule-repo/Cargo.toml" in name for name in names)

    def test_skips_existing_tarball(self, tmp_path):
        """Test that existing tarballs are not re-created."""
        with tempfile.TemporaryDirectory() as git_tmpdir:
            fixture = create_simple_git_repo(Path(git_tmpdir))

            crate = GitCrate(
                name="test-crate",
                version="1.0.0",
                repository=f"file://{fixture.path}",
                commit=fixture.commit,
            )

            distdir = tmp_path / "distdir"
            distdir.mkdir()

            # Create a pre-existing tarball
            existing_tarball = distdir / crate.filename
            existing_content = b"existing content"
            existing_tarball.write_bytes(existing_content)

            # Try to clone
            result = clone_git_crate(crate, distdir)

            # Should return existing tarball without modification
            assert result == existing_tarball
            assert result.read_bytes() == existing_content

    def test_tarball_format_matches_github(self, tmp_path):
        """Test that created tarball matches GitHub's archive format."""
        with tempfile.TemporaryDirectory() as git_tmpdir:
            fixture = create_simple_git_repo(Path(git_tmpdir))

            # For a GitHub repo, the format should be:
            # {repo_name}-{commit}/path/to/file
            crate = GitCrate(
                name="test-crate",
                version="1.0.0",
                repository=f"file://{fixture.path}",
                commit=fixture.commit,
            )

            distdir = tmp_path / "distdir"
            distdir.mkdir()

            result = clone_git_crate(crate, distdir)

            with tarfile.open(result, "r:gz") as tar:
                names = tar.getnames()
                # All paths should start with {repo_name}-{commit}/
                expected_prefix = f"{crate.repo_name}-{fixture.commit}/"
                for name in names:
                    assert name.startswith(
                        expected_prefix
                    ) or name == expected_prefix.rstrip("/")


class TestErrorHandling:
    """Tests for error conditions."""

    def test_nonexistent_commit_raises_error(self, tmp_path):
        """Test that invalid commit SHA raises GitCloneError."""
        with tempfile.TemporaryDirectory() as git_tmpdir:
            fixture = create_simple_git_repo(Path(git_tmpdir))

            # Use a non-existent commit SHA
            crate = GitCrate(
                name="test-crate",
                version="1.0.0",
                repository=f"file://{fixture.path}",
                commit="0000000000000000000000000000000000000000",
            )

            distdir = tmp_path / "distdir"
            distdir.mkdir()

            from pycargoebuild.git import GitCloneError

            with pytest.raises(GitCloneError, match=r"Commit.*not found"):
                clone_git_crate(crate, distdir)
