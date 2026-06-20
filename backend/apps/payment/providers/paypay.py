from typing import Optional

from .base import AlterResult, BasePaymentProvider, EntryResult, ExecuteResult, ProviderError
from ..services.gmopg import GmoPgError, alter_tran, search_trade
from ..services.paypay import entry_tran_paypay, exec_tran_paypay


class PayPayProvider(BasePaymentProvider):
    name = 'gmo_paypay'

    def entry(self, order_id: str, amount: int, currency: str = 'JPY', **kwargs) -> EntryResult:
        return_url = kwargs.get('return_url', '')
        try:
            result = entry_tran_paypay(
                order_id=order_id,
                amount=amount,
                return_url=return_url,
            )
        except GmoPgError as e:
            raise ProviderError(str(e), code=e.err_code, raw=e.raw)

        return EntryResult(
            provider_order_id=order_id,
            amount=amount,
            currency=currency,
            client_payload={
                'provider_order_id': order_id,
                'access_id':         result.get('AccessID', ''),
                'access_pass':       result.get('AccessPass', ''),
                'qr_url':            result.get('StartURL', ''),
                'amount':            amount,
                'currency':          currency,
            },
        )

    def execute(self, provider_order_id: str, **kwargs) -> ExecuteResult:
        try:
            result = exec_tran_paypay(
                access_id=kwargs['access_id'],
                access_pass=kwargs['access_pass'],
                order_id=provider_order_id,
            )
        except GmoPgError as e:
            raise ProviderError(str(e), code=e.err_code, raw=e.raw)

        return ExecuteResult(
            transaction_id=result.get('TranID', ''),
            auth_status='captured',
            raw=result,
        )

    def capture(self, pg_txn) -> AlterResult:
        raise NotImplementedError("PayPay uses CAPTURE job at entry — separate capture not supported")

    def cancel(self, pg_txn) -> AlterResult:
        try:
            result = alter_tran(
                access_id=pg_txn.gmo_access_id,
                access_pass=pg_txn.gmo_access_pass,
                job_cd='CANCEL',
            )
        except GmoPgError as e:
            raise ProviderError(str(e), code=e.err_code, raw=e.raw)
        return AlterResult(auth_status='cancelled', raw=result)

    def refund(self, pg_txn, amount: Optional[int] = None) -> AlterResult:
        try:
            result = alter_tran(
                access_id=pg_txn.gmo_access_id,
                access_pass=pg_txn.gmo_access_pass,
                job_cd='RETURN',
                amount=amount,
            )
        except GmoPgError as e:
            raise ProviderError(str(e), code=e.err_code, raw=e.raw)
        return AlterResult(auth_status='refunded', raw=result)

    def get_status(self, provider_order_id: str) -> dict:
        try:
            result = search_trade(provider_order_id)
        except GmoPgError as e:
            raise ProviderError(str(e), code=e.err_code, raw=e.raw)
        return {
            'provider_order_id': provider_order_id,
            'status':            result.get('Status', ''),
            'amount':            result.get('Amount', ''),
            'transaction_id':    result.get('TranID', ''),
            'forward':           result.get('Forward', ''),
        }
