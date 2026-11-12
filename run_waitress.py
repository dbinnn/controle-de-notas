"""
Ponto de entrada de produção — roda o site com Waitress (não é o
servidor de desenvolvimento do Flask, não tem o console de debug
exposto). É o que o iniciar.bat chama.
"""
from waitress import serve
import config
from app import app

if __name__ == "__main__":
    print(f"Controle de Notas rodando em http://localhost:{config.PORT}")
    print("Pra parar: feche esta janela ou aperte Ctrl+C.")
    serve(app, host="0.0.0.0", port=config.PORT)
