from typing import Optional

from .base import AlterResult, BasePaymentProvider, EntryResult, ExecuteResult, ProviderError
from ..services.gmopg import GmoPgError, alter_tran, entry_tran, exec_tran, search_trade


class GmoProvider(BasePaymentProvider):
    name = 'gmo'

    def entry(self, order_id: str, amount: int, currency: str = 'JPY', **kwargs) -> EntryResult:
        try:
            result = entry_tran(order_id=order_id, amount=amount)
        except GmoPgError as e:
            raise ProviderError(str(e), code=e.err_code, raw=e.raw)

        return EntryResult(
            provider_order_id=order_id,
            amount=amount,
            currency=currency,
            client_payload={
                'provider_order_id': order_id,
                'access_id':         result['AccessID'],
                'access_pass':       result['AccessPass'],
                'amount':            amount,
                'currency':          currency,
            },
        )

    def execute(self, provider_order_id: str, **kwargs) -> ExecuteResult:
        try:
            result = exec_tran(
                access_id=kwargs['access_id'],
                access_pass=kwargs['access_pass'],
                order_id=provider_order_id,
                token=kwargs['token'],
                method=kwargs.get('method', '1'),
                pay_times=kwargs.get('pay_times'),
                client_field1=kwargs.get('client_field1', ''),
            )
        except GmoPgError as e:
            raise ProviderError(str(e), code=e.err_code, raw=e.raw)

        return ExecuteResult(
            transaction_id=result.get('TranID', ''),
            auth_status='auth_complete',
            raw=result,
        )

    def capture(self, pg_txn) -> AlterResult:
        try:
            result = alter_tran(
                access_id=pg_txn.gmo_access_id,
                access_pass=pg_txn.gmo_access_pass,
                job_cd='SALES',
                amount=pg_txn.amount_jpy,
            )
        except GmoPgError as e:
            raise ProviderError(str(e), code=e.err_code, raw=e.raw)
        return AlterResult(auth_status='captured', raw=result)

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
            'job_cd':            result.get('JobCd', ''),
            'amount':            result.get('Amount', ''),
            'process_date':      result.get('ProcessDate', ''),
            'transaction_id':    result.get('TranID', ''),
            'approve':           result.get('Approve', ''),
            'forward':           result.get('Forward', ''),
            'card_no':           result.get('CardNo', ''),
        }
