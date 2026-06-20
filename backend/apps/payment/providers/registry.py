from .base import BasePaymentProvider
from .gmo import GmoProvider
from .paypay import PayPayProvider

_REGISTRY: dict[str, BasePaymentProvider] = {
    'gmo':       GmoProvider(),
    'gmo_paypay': PayPayProvider(),
}

PROVIDER_CHOICES = [(k, k) for k in _REGISTRY]


def get_provider(name: str) -> BasePaymentProvider:
    provider = _REGISTRY.get(name)
    if not provider:
        raise ValueError(f"Unknown payment provider: {name!r}. Available: {list(_REGISTRY)}")
    return provider


def register_provider(name: str, provider: BasePaymentProvider) -> None:
    _REGISTRY[name] = provider
