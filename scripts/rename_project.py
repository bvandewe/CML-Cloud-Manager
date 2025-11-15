#!/usr/bin/env python3
"""
Project Renamer Utility
=======================

Purpose:
    Turn this repo into a reusable starter by safely replacing occurrences of the
    original project name ("starter-app" and its variants) with a new name.

Features:
    - Derives multiple naming styles (slug, snake, Pascal, title, UPPER_SNAKE) from one input.
    - Replaces common variants: starter-app, starter_app, Starter App, StarterApp, STARTER_APP.
    - Updates service identifiers (e.g., service_name, KEYCLOAK_REALM, KEYCLOAK_CLIENT_ID) optionally.
    - Dry-run mode shows planned changes without modifying files.
    - Skips binary/large/unrelated paths (venv, .git, node_modules, __pycache__, *.pyc, *.png/.jpg, package lock files, dist assets).
    - Optional path-based include/exclude filters.
    - Prints a concise summary of changed files.

Usage Examples:
    Dry run (recommended first):
        python scripts/rename_project.py --new-name "Acme Tasks" --dry-run

    Execute replacements:
        python scripts/rename_project.py --new-name "Acme Tasks"

    Override derived styles explicitly:
        python scripts/rename_project.py --new-name "Acme Tasks" \
            --slug acme-tasks --snake acme_tasks --pascal AcmeTasks --upper ACME_TASKS

    Restrict to src + docs only:
        python scripts/rename_project.py --new-name "Acme Tasks" --include src docs

Caution:
    - Commit or stash your work before running.
    - Review dry-run output carefully.
    - Renaming Keycloak realm/client requires external Keycloak adjustments.

Exit Codes:
    0 success, 1 usage error, 2 runtime error.
"""
from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Mapping

# Original name variants to search for
ORIGINAL_VARIANTS = {
    "starter-app",     # slug
    "starter_app",     # snake
    "Starter App",     # title/spaced
    "StarterApp",      # Pascal
    "STARTER_APP",     # upper snake
    "Starter App API",  # special case
}

# Files/directories to ignore when traversing
DEFAULT_EXCLUDES = {
    ".git",
    ".venv",
    "node_modules",
    "__pycache__",
    "dist",
    "build",
    "static",
    "logs",
    ".pytest_cache",
    ".parcel-cache",
}

# Extensions to skip (binary / generated)
SKIP_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg", ".ico", ".lock", ".woff", ".woff2", ".map"}
SKIP_FILE_PATTERNS = {".pyc"}


@dataclass
class NameStyles:
    title: str
    slug: str
    snake: str
    pascal: str
    upper: str

    @staticmethod
    def derive(base: str) -> "NameStyles":
        # Normalize whitespace
        words = re.split(r"[\s_-]+", base.strip())
        clean_words = [w for w in words if w]
        if not clean_words:
            raise ValueError("Cannot derive name styles from empty input")
        title = " ".join(w.capitalize() for w in clean_words)
        slug = "-".join(w.lower() for w in clean_words)
        snake = "_".join(w.lower() for w in clean_words)
        pascal = "".join(w.capitalize() for w in clean_words)
        upper = "_".join(w.upper() for w in clean_words)
        return NameStyles(title=title, slug=slug, snake=snake, pascal=pascal, upper=upper)

    def replacement_map(self) -> Mapping[str, str]:
        return {
            "starter-app": self.slug,
            "starter_app": self.snake,
            "Starter App": self.title,
            "StarterApp": self.pascal,
            "STARTER_APP": self.upper,
            "Starter App API": f"{self.title} API",
        }


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Rename project occurrences of 'starter-app' variants.")
    p.add_argument("--new-name", required=True, help="Base name for project (e.g. 'Acme Tasks')")
    p.add_argument("--slug", help="Override slug variant")
    p.add_argument("--snake", help="Override snake_case variant")
    p.add_argument("--pascal", help="Override PascalCase variant")
    p.add_argument("--upper", help="Override UPPER_SNAKE variant")
    p.add_argument("--dry-run", action="store_true", help="Show changes without writing")
    p.add_argument("--include", nargs="*", help="Limit replacements to these top-level paths")
    p.add_argument("--exclude", nargs="*", help="Additional paths to exclude")
    p.add_argument("--update-keycloak", action="store_true", help="Also replace KEYCLOAK_REALM and client ids if present")
    return p.parse_args()


def should_skip(path: Path) -> bool:
    if any(part in DEFAULT_EXCLUDES for part in path.parts):
        return True
    if path.is_dir():
        return False
    if path.suffix.lower() in SKIP_EXTS:
        return True
    if any(str(path).endswith(pattern) for pattern in SKIP_FILE_PATTERNS):
        return True
    # skip large files > 2MB
    try:
        if path.stat().st_size > 2 * 1024 * 1024:
            return True
    except OSError:
        return True
    return False


def iter_candidate_files(root: Path, includes: list[str] | None) -> Iterable[Path]:
    if includes:
        for inc in includes:
            base = root / inc
            if not base.exists():
                continue
            if base.is_file():
                yield base
            else:
                for p in base.rglob("*"):
                    if p.is_file() and not should_skip(p):
                        yield p
        return
    for p in root.rglob("*"):
        if p.is_file() and not should_skip(p):
            yield p


def replace_in_file(path: Path, replacements: Mapping[str, str]) -> tuple[bool, int]:
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return False, 0
    original = text
    total_subs = 0
    for old, new in replacements.items():
        if old in text:
            count = text.count(old)
            text = text.replace(old, new)
            total_subs += count
    if text != original:
        path.write_text(text, encoding="utf-8")
        return True, total_subs
    return False, 0


def main() -> int:
    args = parse_args()
    try:
        styles = NameStyles.derive(args.new_name)
    except ValueError as e:
        print(f"[error] {e}")
        return 1

    # Override if provided
    if args.slug:
        styles.slug = args.slug
    if args.snake:
        styles.snake = args.snake
    if args.pascal:
        styles.pascal = args.pascal
    if args.upper:
        styles.upper = args.upper

    replacements = dict(styles.replacement_map())

    # Optional Keycloak realm/client updates (best-effort basic patterns)
    if args.update_keycloak:
        # NOTE: user must adjust Keycloak server config externally.
        replacements["starter-app-backend"] = f"{styles.slug}-backend"
        replacements["starter-app"] = styles.slug  # realm name occurrences
        replacements["starter-app-backend-secret-change-in-production"] = f"{styles.slug}-backend-secret-change-in-production"

    excludes = set(DEFAULT_EXCLUDES)
    if args.exclude:
        excludes.update(args.exclude)

    root = Path.cwd()
    print("=== Project Rename Plan ===")
    print(f"Root: {root}")
    print(f"New Name Styles: title='{styles.title}', slug='{styles.slug}', snake='{styles.snake}', pascal='{styles.pascal}', upper='{styles.upper}'")
    if args.dry_run:
        print("Mode: DRY-RUN (no files will be modified)")
    print("Replacements:")
    for k, v in replacements.items():
        print(f"  {k} -> {v}")

    changed_files = []
    total_subs = 0
    for file_path in iter_candidate_files(root, args.include):
        if any(part in excludes for part in file_path.parts):
            continue
        try:
            with file_path.open("r", encoding="utf-8") as fh:
                content = fh.read()
        except UnicodeDecodeError:
            continue
        new_content = content
        file_subs = 0
        for old, new in replacements.items():
            if old in new_content:
                count = new_content.count(old)
                new_content = new_content.replace(old, new)
                file_subs += count
        if file_subs > 0:
            if not args.dry_run:
                file_path.write_text(new_content, encoding="utf-8")
            changed_files.append((file_path, file_subs))
            total_subs += file_subs

    print("\nSummary:")
    print(f"  Files changed: {len(changed_files)}")
    print(f"  Total substitutions: {total_subs}")
    for fp, count in changed_files[:25]:  # limit output
        print(f"   - {fp} ({count} substitutions)")
    if len(changed_files) > 25:
        print(f"   ... (+{len(changed_files)-25} more)")

    if args.dry_run:
        print("\nDry run complete. Re-run without --dry-run to apply changes.")
    else:
        print("\nRename applied. Review changes and adjust remaining identifiers (e.g., Docker image names) if needed.")

    print("\nNext steps (manual):")
    print("  1. Rename repository folder and remote origin if desired.")
    print("  2. Update Keycloak realm/client to match new identifiers (if --update-keycloak used).")
    print("  3. Search for any lingering custom branding.")
    print("  4. Run tests to confirm functionality: 'poetry run pytest -q'.")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\n[abort] Interrupted by user.")
        sys.exit(2)
