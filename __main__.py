"""`python -m regexplain` 入口。"""

try:
    from .regexplain import main
except ImportError:  # 直接在目录内运行时回退
    from regexplain import main

if __name__ == "__main__":
    raise SystemExit(main())
