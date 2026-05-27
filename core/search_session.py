"""搜索会话数据模型"""

from __future__ import annotations


class SearchSession:
    """用户搜索会话"""

    def __init__(
        self,
        query: str,
        results: list[str],
        page_size: int = 20,
        current_page: int = 0,
        api_page: int = 1,
    ):
        self.query = query
        self.results = results
        self.page_size = page_size
        self.current_page = current_page
        self.api_page = api_page

    @property
    def total_pages(self) -> int:
        return (len(self.results) + self.page_size - 1) // self.page_size

    def get_current_page(self) -> list[str]:
        start = self.current_page * self.page_size
        end = start + self.page_size
        return self.results[start:end]

    def advance_page(self) -> None:
        self.current_page += 1

    def has_next_page(self) -> bool:
        return self.current_page < self.total_pages - 1

    def is_last_page(self) -> bool:
        return self.current_page >= self.total_pages - 1

    def needs_fetch_more(self) -> bool:
        remaining = len(self.results) - (self.current_page + 1) * self.page_size
        return remaining <= 0

    def append_results(self, new_results: list[str]) -> None:
        self.results.extend(new_results)

    def reset(self) -> None:
        self.current_page = 0
        self.api_page = 1
        self.results = []