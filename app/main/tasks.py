import json
import urllib.request
from app import db
from app.models import Proxy, User


def sync_webshare_job(app):
    """Job executado automaticamente a cada 10 minutos (600s) pelo APScheduler."""
    with app.app_context():
        # Busca a chave configurada no Config
        api_key = app.config.get('WEBSHARE_API_KEY')
        if not api_key:
            print("[APScheduler] WEBSHARE_API_KEY não configurada no Config.")
            return

        users = User.query.filter_by(is_active=True).all()
        if not users:
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

                for user in users:
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
                                port=port_int,
                                user_id=user.id
                            ).first()

                            if not existing_proxy:
                                novo_proxy = Proxy(
                                    address=address,
                                    port=port_int,
                                    username=username,
                                    country=country_code,
                                    capacity=1,
                                    status='ATIVO',
                                    user_id=user.id
                                )
                                novo_proxy.set_password(password)
                                db.session.add(novo_proxy)
                            else:
                                existing_proxy.status = 'ATIVO'
                                existing_proxy.username = username
                                existing_proxy.country = country_code
                                existing_proxy.set_password(password)

                    ## Inativa proxies do usuário que sumiram do Webshare
                    db_proxies = Proxy.query.filter_by(user_id=user.id).all()
                    for proxy in db_proxies:
                        if (proxy.address, proxy.port) not in active_webshare_addresses:
                            proxy.status = 'INATIVO'

                            # Inativa automaticamente todos os lobbies associados a este proxy ---
                            for lobby in proxy.lobbies:
                                if lobby.status == 'ATIVO':
                                    lobby.status = 'INATIVO'
                                    print(f"[APScheduler] Lobby '{lobby.nickname}' inativado pois o Proxy foi inativado.")

                db.session.commit()
                print("[APScheduler] Proxies sincronizados com sucesso!")

        except Exception as e:
            db.session.rollback()
            print(f"[APScheduler ERRO] Falha na sincronização: {e}")