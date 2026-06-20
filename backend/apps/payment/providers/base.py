from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class EntryResult:
    provider_order_id: str
    amount: int
    currency: str
    client_payload: dict = field(default_factory=dict)


@dataclass
class ExecuteResult:
    transaction_id: str
    auth_status: str
    raw: dict = field(default_factory=dict)


@dataclass
class AlterResult:
    auth_status: str
    raw: dict = field(default_factory=dict)


class ProviderError(Exception):
    def __init__(self, message: str, code: str = '', raw: dict = None):
        self.message = message
        self.code = code
        self.raw = raw or {}
        super().__init__(message)


class BasePaymentProvider(ABC):
    name: str = ''

    @abstractmethod
    def entry(self, order_id: str, amount: int, currency: str, **kwargs) -> EntryResult: ...

    @abstractmethod
    def execute(self, provider_order_id: str, **kwargs) -> ExecuteResult: ...

    @abstractmethod
    def capture(self, pg_txn) -> AlterResult: ...

    @abstractmethod
    def cancel(self, pg_txn) -> AlterResult: ...

    @abstractmethod
    def refund(self, pg_txn, amount: Optional[int] = None) -> AlterResult: ...

    @abstractmethod
    def get_status(self, provider_order_id: str) -> dict: ...
