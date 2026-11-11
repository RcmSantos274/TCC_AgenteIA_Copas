"""Mensagens de erro amigáveis, reaproveitadas pela CLI e pela interface Streamlit."""
from openai import APIStatusError


def mensagem_erro_openai(e: APIStatusError) -> str:
    codigo = (e.body or {}).get('code') if isinstance(e.body, dict) else None
    if codigo == 'credit_balance_exhausted' or e.status_code == 429:
        return ('Sem crédito na conta da OpenAI. Adicione um método de pagamento e crédito em '
                'platform.openai.com/settings/organization/billing (a assinatura do ChatGPT não '
                'vale para a API).')
    if e.status_code == 401:
        return 'OPENAI_API_KEY inválida ou revogada. Gere uma nova em platform.openai.com/api-keys.'
    return f'Erro da API da OpenAI ({e.status_code}): {e.message}'
