from app import create_app

# Instacia a aplicação Flask utilizando a fábrica
app = create_app()

if __name__ == '__main__':
    # Executa o servidor em modo de desenvolvimento (debug=True atualiza o servidor ao salvar arquivos)
    app.run(debug=True)