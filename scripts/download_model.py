"""One-time public download; inference itself has no network dependency."""
import hashlib
from pathlib import Path
import subprocess

root = Path(__file__).resolve().parent.parent
name = 'gemma-4-E4B-it.litertlm'
revision = 'e6a3892a8c22cf87ff99583996149cf3cb32452b'
sha256 = '0b2a8980ce155fd97673d8e820b4d29d9c7d99b8fa6806f425d969b145bd52e0'
target = root / 'models' / name
target.parent.mkdir(exist_ok=True)

def verify(path):
    with path.open('rb') as f:
        digest = hashlib.file_digest(f, 'sha256').hexdigest()
    if digest != sha256:
        raise RuntimeError(f'Model checksum mismatch: {path}. Remove the incomplete file and retry.')

if target.exists():
    verify(target)
    print(f'Model verified: {target}')
else:
    partial = target.with_suffix('.litertlm.part')
    subprocess.run(['curl', '-fL', '--retry', '3', '-C', '-', '-o', str(partial),
        f'https://huggingface.co/litert-community/gemma-4-E4B-it-litert-lm/resolve/{revision}/{name}'], check=True)
    verify(partial)
    partial.rename(target)
    print(f'Ready: {target}')
