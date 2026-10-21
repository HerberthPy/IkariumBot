WORLD_NAMES = {
    # Brasil (BR)
    "74": "Atlas",
    "75": "Boreas",
    "76": "Chronos",

    # Reino Unido / Internacional (EN)
    "588": "Asphodel 588",
    "591": "Asphodel 591",
    "595": "Asphodel 595",
}


def get_world_name(server_code):
    """
    Retorna o nome amigável do mundo a partir do seu código.
    Se não encontrar o código no dicionário, retorna 'Mundo <código>'.
    """
    if not server_code:
        return "Desconhecido"

    code_str = str(server_code).strip()
    return WORLD_NAMES.get(code_str, f"Mundo {code_str}")