# DB 어댑터 — 담당자 입력 조회 / 근로자 서류 신분 저장 (현재 인메모리)

from .memory import InMemoryDb
from .protocols import IdentityStore, WorkerCompanyLookup

__all__ = [
    "InMemoryDb",
    "IdentityStore",
    "WorkerCompanyLookup",
]
