from app import create_app  # Importa a factory da sua aplicação Flask
from app.models import VPN
from app.automation.proton_vpn import login_proton_vpn

def iniciar_automacao_conta(vpn_account_id):
    vpn = VPN.query.get(vpn_account_id)

    if not vpn:
        print("[-] Conta VPN não encontrada.")
        return

    senha_descriptografada = vpn.get_password()

    print(f"[*] Iniciando automação para a VPN: {vpn.email}")
    login_proton_vpn(email=vpn.email, password=senha_descriptografada, headless=False)


if __name__ == "__main__":
    # Inicializa o contexto da aplicação para o SQLAlchemy conseguir acessar o app.db
    app = create_app()
    with app.app_context():
        # Substitua o '1' pelo ID de uma VPN que existe no seu banco de dados
        iniciar_automacao_conta(vpn_account_id=1)