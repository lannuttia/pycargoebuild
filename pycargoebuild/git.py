# pycargoebuild
# (c) 2026 Anthony Lannutti <lannuttia@gmail.com>
# SPDX-License-Identifier: GPL-2.0-or-later

"""Git operations for fetching git-based crates with submodule support."""

import logging
import tarfile
import tempfile
import typing
from pathlib import Path

if typing.TYPE_CHECKING:
    from pycargoebuild.cargo import GitCrate

try:
    import dulwich.porcelain
except ImportError as e:
    raise ImportError(
        "dulwich is required for git dependency support.\n"
        "This should have been installed automatically."
    ) from e


logger = logging.getLogger(__name__)


class GitCloneError(RuntimeError):
    """Raised when git clone operation fails."""


def clone_git_crate(
    crate: "GitCrate",
    distdir: Path,
) -> Path:
    """
    Clone a git repository with submodules and create a tarball.

    This function clones a git repository at a specific commit,
    recursively initializes all submodules, and creates a gzipped
    tarball that matches the format of GitHub's archive downloads.

    Args:
        crate: GitCrate object containing repository URL and commit
        distdir: Directory where the resulting tarball will be saved

    Returns:
        Path to the created tarball

    Raises:
        GitCloneError: If cloning or tarball creation fails
    """
    tarball_path = distdir / crate.filename

    if tarball_path.exists():
        logger.debug(f"Tarball already exists: {tarball_path}")
        return tarball_path

    logger.info(f"Cloning {crate.repository} @ {crate.commit}")

    try:
        with tempfile.TemporaryDirectory(prefix="pycargoebuild-git-") as tmpdir:
            clone_path = Path(tmpdir) / "repo"

            repo = dulwich.porcelain.clone(
                source=crate.repository,
                target=str(clone_path),
                depth=1,
                recurse_submodules=True,
                checkout=True,
            )

            commit_sha = crate.commit.encode("ascii")
            try:
                repo[commit_sha]
                repo.refs[b"HEAD"] = commit_sha  # type: ignore[index,assignment]
            except KeyError as e:
                raise GitCloneError(
                    f"Commit {crate.commit} not found in repository "
                    f"{crate.repository}. It may not be in the default branch."
                ) from e

            _create_tarball(
                source_dir=clone_path,
                output_path=tarball_path,
                archive_prefix=f"{crate.repo_name}-{crate.commit}",
            )

            logger.info(f"Created tarball: {tarball_path}")

    except Exception as e:
        if isinstance(e, GitCloneError):
            raise
        if tarball_path.exists():
            tarball_path.unlink()
        raise GitCloneError(f"Failed to create tarball for {crate.name}: {e}") from e

    return tarball_path


def _create_tarball(source_dir: Path, output_path: Path, archive_prefix: str) -> None:
    """
    Create a gzipped tarball from a directory.

    Mimics GitHub's archive format where all files are under
    a {repo_name}-{commit}/ prefix directory.

    Args:
        source_dir: Directory to archive
        output_path: Path where tarball should be created
        archive_prefix: Prefix directory for all files in archive
                       (e.g., "libcosmic-abc123")
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with tarfile.open(output_path, "w:gz") as tar:
        for item in sorted(source_dir.rglob("*")):
            if ".git" in item.parts:
                continue

            rel_path = item.relative_to(source_dir)
            arcname = Path(archive_prefix) / rel_path
            tar.add(str(item), arcname=str(arcname), recursive=False)
