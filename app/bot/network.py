# app/bot/network.py

class NetworkInterceptor:
    @staticmethod
    def listen_accounts_api(page, captured_accounts_list):
        """
        Escuta e captura a API JSON da Gameforge extraindo o Mundo (Atlas, Asphodel, etc.) e o País.
        """

        def handle_response(response):
            if ("/api/users/me/accounts" in response.url or "/accounts" in response.url) and response.status == 200:
                try:
                    if "application/json" in response.headers.get("content-type", ""):
                        data = response.json()
                        if isinstance(data, list) and len(data) > 0:
                            captured_accounts_list.clear()

                            for acc in data:
                                server_info = acc.get("server") or {}

                                # 1. Extração precisa do NOME DO MUNDO (Atlas, Asphodel 595, etc.)
                                mundo_nome = None
                                if isinstance(server_info, dict):
                                    mundo_nome = (
                                            server_info.get("name")
                                            or server_info.get("worldName")
                                            or acc.get("targetServerName")
                                            or acc.get("worldName")
                                            or acc.get("serverName")
                                    )

                                # Fallback se veio apenas string no objeto server ou chave genérica
                                if not mundo_nome or mundo_nome.lower() in ['br', 'en', 'pt', 'es', 'none']:
                                    server_number = (
                                                        server_info.get("number") if isinstance(server_info,
                                                                                                dict) else None
                                                    ) or acc.get("serverId") or acc.get("id")

                                    # Tenta pegar o nome direto do dicionário do servidor se disponível
                                    mundo_nome = acc.get("serverName") or f"{server_number}"

                                # 2. Extração do CÓDIGO DO PAÍS (br, en, pt, etc.)
                                pais_code = "pt"
                                if isinstance(server_info, dict):
                                    pais_code = server_info.get("language") or acc.get("language") or "pt"
                                else:
                                    pais_code = acc.get("language") or "pt"

                                captured_accounts_list.append({
                                    "gameforge_account_id": str(acc.get("id", "")),
                                    "servidor": mundo_nome,  # Salva o Mundo (Ex: Atlas, Asphodel 595)
                                    "pais": pais_code,  # Salva o País (Ex: br, en)
                                    "nome_usuario": acc.get("name") or "Sem Nome",
                                    "ativo": not acc.get("blocked", False)
                                })

                            print(f"[Network] {len(captured_accounts_list)} conta(s) e mundo(s) capturados via JSON!")
                except Exception as e:
                    print(f"[Network ERRO] Falha ao ler resposta da API: {e}")

        page.on("response", handle_response)