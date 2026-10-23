# app/main/tasks.py

import json
import urllib.request
from app import db
from app.models import Proxy


def sync_webshare_job(app):
    """Sincroniza manualmente as proxies do Webshare com o Pool Global.
    Disparado exclusivamente ao clicar no botão no painel Admin.
    """
    with app.app_context():
        api_key = app.config.get('WEBSHARE_API_KEY')
        if not api_key:
            print("[Sync Webshare] WEBSHARE_API_KEY não configurada no Config.")
            return

        url = "https://proxy.webshare.io/api/v2/proxy/list/?mode=direct&page=1&page_size=100"
        headers = {
            'Authorization': f'Token {api_key}',
            'User-Agent': 'Mozilla/5.0'
        }

        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=10) as response:
                data = json.loads(response.read().decode('utf-8'))
                results = data.get('results', [])

                active_webshare_addresses = set()

                for p in results:
                    if not p.get('valid', True):
                        continue

                    address = p.get('proxy_address')
                    port = p.get('port')
                    username = p.get('username')
                    password = p.get('password')
                    country_code = p.get('country_code', '').upper()

                    if address and port:
                        port_int = int(port)
                        active_webshare_addresses.add((address, port_int))

                        existing_proxy = Proxy.query.filter_by(
                            address=address,
                            port=port_int
                        ).first()

                        if not existing_proxy:
                            # Nova proxy entra no Pool Global
                            novo_proxy = Proxy(
                                address=address,
                                port=port_int,
                                username=username,
                                country=country_code,
                                status='ATIVO',
                                user_id=None
                            )
                            novo_proxy.set_password(password)
                            db.session.add(novo_proxy)
                        else:
                            # Atualiza credenciais mantendo a atribuição do usuário intacta
                            existing_proxy.status = 'ATIVO'
                            existing_proxy.username = username
                            existing_proxy.country = country_code
                            existing_proxy.set_password(password)

                # Inativa proxies no banco de dados que não existem mais no Webshare
                all_db_proxies = Proxy.query.all()
                for proxy in all_db_proxies:
                    if (proxy.address, proxy.port) not in active_webshare_addresses:
                        proxy.status = 'INATIVO'

                        # Inativa lobbies vinculados a esta proxy inativa
                        for lobby in proxy.lobbies:
                            if lobby.status in ['ATIVO', 'ativo']:
                                lobby.status = 'INATIVO'
                                print(f"[Sync Webshare] Lobby '{lobby.nickname}' inativado pois a Proxy #{proxy.id} foi inativada.")

                db.session.commit()
                print("[Sync Webshare] Proxies sincronizadas com sucesso no Pool Global!")

        except Exception as e:
            db.session.rollback()
            print(f"[Sync Webshare ERRO] Falha na sincronização com Webshare: {e}")