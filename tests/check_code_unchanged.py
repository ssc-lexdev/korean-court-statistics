"""Check that edits to a script changed only comments and docstrings.

Compares the abstract syntax tree of each file with its original copy after
removing docstrings. Comments are not part of the tree, so any difference means
that executable code (including string literals such as prompts) changed.

Usage: python check_code_unchanged.py <original_dir> <edited_dir> [file ...]
"""
import ast
import sys
from pathlib import Path


def tree_without_docstrings(src):
    t = ast.parse(src)
    for node in ast.walk(t):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            b = node.body
            if b and isinstance(b[0], ast.Expr) and isinstance(getattr(b[0], "value", None), ast.Constant) \
                    and isinstance(b[0].value.value, str):
                node.body = b[1:] or [ast.Pass()]
    return ast.dump(t, include_attributes=False)


def main():
    orig, edit = Path(sys.argv[1]), Path(sys.argv[2])
    files = sys.argv[3:] or [p.relative_to(orig).as_posix() for p in orig.rglob("*.py")]
    bad = 0
    for f in sorted(files):
        a = tree_without_docstrings((orig / f).read_text(encoding="utf-8-sig"))
        b = tree_without_docstrings((edit / f).read_text(encoding="utf-8-sig"))
        same = a == b
        bad += not same
        print(("SAME     " if same else "CHANGED  ") + f)
    print(f"{len(files) - bad}/{len(files)} files: code unchanged (comments/docstrings only)")
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
