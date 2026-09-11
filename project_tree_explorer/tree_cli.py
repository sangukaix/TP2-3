"""TP2-3 전체 폴더·파일 트리를 CLI로 출력합니다."""

from __future__ import annotations

import argparse

from tree_core import PROJECT_ROOT, build_tree_text, scan_project


def main() -> None:
    parser = argparse.ArgumentParser(description='TP2-3 프로젝트 폴더·파일 트리 출력')
    parser.add_argument('--include-generated', action='store_true', help='의존성·캐시·빌드 폴더도 포함')
    args = parser.parse_args()
    entries = scan_project(include_generated=args.include_generated)
    print(build_tree_text(entries))
    print(f'\n총 {len(entries)}개 항목 (폴더·파일, 기본 제외 폴더는 --include-generated로 포함)')


if __name__ == '__main__':
    main()

