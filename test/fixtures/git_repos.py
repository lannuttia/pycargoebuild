# pycargoebuild
# (c) 2026 Anthony Lannutti <lannuttia@gmail.com>
# SPDX-License-Identifier: GPL-2.0-or-later

"""Utilities for creating real git repositories for testing."""

from pathlib import Path
from typing import NamedTuple

import dulwich.index
import dulwich.porcelain
import dulwich.repo


class GitRepoFixture(NamedTuple):
    """A test git repository with metadata."""

    path: Path
    commit: str
    has_submodules: bool


def create_simple_git_repo(base_dir: Path, name: str = "test-repo") -> GitRepoFixture:
    """
    Create a simple git repository without submodules using dulwich.

    Returns:
        GitRepoFixture with path and commit SHA
    """
    repo_path = base_dir / name
    repo_path.mkdir()

    # Initialize git repo using dulwich
    repo = dulwich.porcelain.init(str(repo_path))

    # Create a Cargo.toml
    (repo_path / "Cargo.toml").write_text("""
[package]
name = "test-crate"
version = "1.0.0"
edition = "2021"
""")

    # Create some source files
    src_dir = repo_path / "src"
    src_dir.mkdir()
    (src_dir / "lib.rs").write_text("pub fn hello() {}")

    # Stage and commit using dulwich
    dulwich.porcelain.add(repo, paths=["Cargo.toml", "src/lib.rs"])
    commit_sha = dulwich.porcelain.commit(
        repo,
        message=b"Initial commit",
        author=b"Test User <test@example.com>",
        committer=b"Test User <test@example.com>",
    )

    return GitRepoFixture(
        path=repo_path,
        commit=commit_sha.decode("ascii"),
        has_submodules=False,
    )


def create_git_repo_with_submodule(base_dir: Path) -> GitRepoFixture:
    """
    Create a git repository with a submodule using dulwich.

    Returns:
        GitRepoFixture with path and commit SHA
    """
    # First create the submodule repo
    submodule = create_simple_git_repo(base_dir, name="submodule-repo")

    # Create the main repo
    main_path = base_dir / "main-repo"
    main_path.mkdir()

    # Initialize main repo using dulwich
    repo = dulwich.porcelain.init(str(main_path))

    # Create Cargo.toml in main repo
    (main_path / "Cargo.toml").write_text("""
[package]
name = "main-crate"
version = "1.0.0"
edition = "2021"

[dependencies]
test-crate = { path = "submodule-repo" }
""")

    # Create .gitmodules file manually
    gitmodules_content = f"""[submodule "submodule-repo"]
\tpath = submodule-repo
\turl = {submodule.path}
"""
    (main_path / ".gitmodules").write_text(gitmodules_content)

    # Clone the submodule into the main repo
    submodule_dest = main_path / "submodule-repo"
    dulwich.porcelain.clone(
        source=str(submodule.path),
        target=str(submodule_dest),
        checkout=True,
    )

    # Stage everything and commit
    # Note: We need to add the submodule directory to the git index
    dulwich.porcelain.add(repo, paths=["Cargo.toml", ".gitmodules"])

    # For submodules, we need to add them to the index properly
    # Get the submodule repo and its HEAD commit
    submodule_repo = dulwich.repo.Repo(str(submodule_dest))
    submodule_commit = submodule_repo.head()

    # Add the submodule entry to the index (as a gitlink, mode 160000)
    # This is how git stores submodule commits in the parent repo
    index = repo.open_index()
    index[b"submodule-repo"] = dulwich.index.IndexEntry(
        ctime=(0, 0),
        mtime=(0, 0),
        dev=0,
        ino=0,
        mode=0o160000,  # gitlink mode for submodules
        uid=0,
        gid=0,
        size=0,
        sha=submodule_commit,
        flags=0,
    )
    index.write()
    submodule_repo.close()
    commit_sha = dulwich.porcelain.commit(
        repo,
        message=b"Add submodule",
        author=b"Test User <test@example.com>",
        committer=b"Test User <test@example.com>",
    )

    return GitRepoFixture(
        path=main_path,
        commit=commit_sha.decode("ascii"),
        has_submodules=True,
    )
