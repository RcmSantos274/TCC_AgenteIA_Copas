import os

from dotenv import load_dotenv

load_dotenv()

# Precisa rodar antes de qualquer import do crewai (por isso agente/__init__.py importa este módulo).
os.environ.setdefault('CREWAI_DISABLE_TELEMETRY', 'true')
os.environ.setdefault('OTEL_SDK_DISABLED', 'true')



LLM_MODEL = os.environ.get('LLM_MODEL', 'gpt-4o-mini')




def criar_llm():
    from crewai import LLM

    if LLM_MODEL.startswith('ollama/'):
        return LLM(model=LLM_MODEL, temperature=0,
                   base_url=os.environ.get('OLLAMA_BASE_URL', 'http://localhost:11434'))

    if not os.environ.get('OPENAI_API_KEY'):
        raise RuntimeError(
            'OPENAI_API_KEY não configurada. Preencha no .env (ou use LLM_MODEL=ollama/<modelo>).'
        )
    return LLM(model=LLM_MODEL, temperature=0)
