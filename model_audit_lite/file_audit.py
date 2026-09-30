"""配布物としての安全性監査: pickle形式の検出、カスタムコードの検出、チェックサム計算。

モデルの重み自体の内容（バックドアの有無など）は検証しない。あくまで
「配布形式として安全か」「任意コード実行のリスクがないか」を確認するもの。
"""
import hashlib

from huggingface_hub import HfApi, hf_hub_download

RISKY_EXTENSIONS = {".bin", ".pt", ".pth", ".pkl", ".pickle", ".ckpt"}
CODE_EXTENSIONS = {".py"}
HASH_EXTENSIONS = {".safetensors", ".json"}


def _sha256_of(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def audit_repo(repo_id: str, repo_type: str = "model", api: HfApi | None = None) -> dict:
    """指定したHugging Faceリポジトリのファイル一覧を取得し、機械的に安全性チェックを行う。

    Returns:
        dict with keys: repo_id, total_files, risky_pickle_files, custom_code_files, checksums
    """
    api = api or HfApi()
    info = api.model_info(repo_id, files_metadata=True) if repo_type == "model" else api.dataset_info(repo_id, files_metadata=True)
    files = [s.rfilename for s in info.siblings]

    risky = [f for f in files if any(f.endswith(ext) for ext in RISKY_EXTENSIONS)]
    code_files = [f for f in files if any(f.endswith(ext) for ext in CODE_EXTENSIONS)]

    checksums = {}
    for f in files:
        if any(f.endswith(ext) for ext in HASH_EXTENSIONS) or f in code_files:
            local = hf_hub_download(repo_id, f, repo_type=repo_type)
            checksums[f] = _sha256_of(local)

    return {
        "repo_id": repo_id,
        "total_files": len(files),
        "risky_pickle_files": risky,
        "custom_code_files": code_files,
        "checksums": checksums,
    }
