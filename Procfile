web: uvicorn services.seller.main:app --host 0.0.0.0 --port $PORT
agent: uvicorn services.agent.main:app --host 0.0.0.0 --port $PORT
psp: uvicorn services.psp.main:app --host 0.0.0.0 --port $PORT
worker: python -m services.pipeline.worker
