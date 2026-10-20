from app import create_app

# Instancia a aplicação Flask utilizando a fábrica
app = create_app()

if __name__ == '__main__':
    # use_reloader=False evita que o APScheduler execute jobs duplicados em modo debug
    app.run(debug=True, use_reloader=False)