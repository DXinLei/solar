"""版本与构建信息管理"""

import os
import subprocess
from datetime import datetime, timezone, timedelta
from pathlib import Path

APP_VERSION = "1.1.1"
DEFAULT_COMMIT = "b8170c6"
PROCESS_START_TIME = datetime.now(timezone(timedelta(hours=8))).isoformat()


def get_git_commit() -> str:
    """获取当前代码的 Git Commit Hash（优先环境变量，其次 Git 命令，再次 .git 文件，最后保底）。"""
    env_commit = os.getenv("GIT_COMMIT")
    if env_commit:
        return env_commit.strip()

    try:
        root_dir = Path(__file__).resolve().parent.parent
        res = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=2,
            cwd=str(root_dir),
        )
        if res.returncode == 0 and res.stdout.strip():
            return res.stdout.strip()
    except Exception:
        pass

    try:
        root_dir = Path(__file__).resolve().parent.parent
        git_head = root_dir / ".git" / "HEAD"
        if git_head.exists():
            content = git_head.read_text().strip()
            if content.startswith("ref:"):
                ref_path = root_dir / ".git" / content[5:].strip()
                if ref_path.exists():
                    return ref_path.read_text().strip()[:7]
            else:
                return content[:7]
    except Exception:
        pass

    return DEFAULT_COMMIT
