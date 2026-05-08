"""
Git repository sync — clone or pull a repo to a local directory.
"""
import logging
import os
import shutil
import tempfile

from git import Repo, GitCommandError

logger = logging.getLogger(__name__)


class GitSyncService:
    """Clone or pull a Git repo and return the local working directory path."""

    @staticmethod
    def sync_repo(
        git_url: str,
        branch: str = "main",
        auth_token: str | None = None,
        work_dir: str | None = None,
    ) -> str:
        """
        Clone or pull repo. Returns the path to the local working directory.
        If work_dir is provided and contains a valid repo, it will be pulled.
        Otherwise a fresh clone is performed into work_dir or a temp directory.
        """
        url = GitSyncService._inject_token(git_url, auth_token)

        if work_dir and os.path.isdir(os.path.join(work_dir, ".git")):
            return GitSyncService._pull(work_dir, branch, url)

        target = work_dir or tempfile.mkdtemp(prefix="kb_repo_")
        return GitSyncService._clone(url, branch, target)

    @staticmethod
    def _inject_token(git_url: str, token: str | None) -> str:
        if not token:
            return git_url
        if git_url.startswith("https://"):
            parts = git_url.split("://", 1)
            return f"{parts[0]}://oauth2:{token}@{parts[1]}"
        return git_url

    @staticmethod
    def _clone(url: str, branch: str, target: str) -> str:
        if os.path.exists(target):
            shutil.rmtree(target)
        logger.info("Cloning %s (branch=%s) -> %s", url[:60], branch, target)
        try:
            Repo.clone_from(
                url,
                target,
                branch=branch,
                depth=1,
                env={"GIT_HTTP_VERSION": "HTTP/1.1"},
            )
        except GitCommandError as exc:
            raise RuntimeError(f"Git clone failed: {exc}") from exc
        return target

    @staticmethod
    def _pull(work_dir: str, branch: str, url: str) -> str:
        logger.info("Pulling %s in %s", branch, work_dir)
        try:
            repo = Repo(work_dir)
            origin = repo.remotes.origin
            origin.set_url(url)
            with repo.git.custom_environment(GIT_HTTP_VERSION="HTTP/1.1"):
                origin.fetch()
                repo.git.checkout(branch)
                origin.pull()
        except GitCommandError as exc:
            raise RuntimeError(f"Git pull failed: {exc}") from exc
        return work_dir

    @staticmethod
    def cleanup(work_dir: str) -> None:
        if work_dir and os.path.exists(work_dir):
            shutil.rmtree(work_dir, ignore_errors=True)
