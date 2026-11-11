"""Matriz experimental compartilhada pela aplicação e pelo benchmark."""

CONFIGURACOES_EXPERIMENTAIS = (
    {"id": "C1", "nome": "C1 · 1.000 elementos · 2 camadas · 720p", "elementos": 1_000, "camadas": 2, "largura": 1280, "altura": 720},
    {"id": "C2", "nome": "C2 · 10.000 elementos · 2 camadas · 720p", "elementos": 10_000, "camadas": 2, "largura": 1280, "altura": 720},
    {"id": "C3", "nome": "C3 · 50.000 elementos · 4 camadas · 720p", "elementos": 50_000, "camadas": 4, "largura": 1280, "altura": 720},
    {"id": "C4", "nome": "C4 · 100.000 elementos · 4 camadas · 1080p", "elementos": 100_000, "camadas": 4, "largura": 1920, "altura": 1080},
)


def validar_configuracao(config):
    """Valida também configurações personalizadas, sem alterar o objeto recebido."""
    copia = dict(config)
    if not isinstance(copia.get("id"), str) or not copia["id"].strip():
        raise ValueError("A configuração precisa de um identificador não vazio.")
    for chave in ("elementos", "camadas", "largura", "altura"):
        valor = copia.get(chave)
        minimo = 0 if chave == "elementos" else 1
        if isinstance(valor, bool) or not isinstance(valor, int) or valor < minimo:
            raise ValueError(f"{chave} deve ser inteiro >= {minimo}.")
    if copia["camadas"] not in (2, 4):
        raise ValueError("A interface suporta configurações com 2 ou 4 camadas.")
    copia.setdefault("nome", copia["id"])
    return copia


def obter_configuracoes(ids=None):
    """Retorna cópias independentes dos presets, na ordem solicitada."""
    if ids is None:
        return [dict(config) for config in CONFIGURACOES_EXPERIMENTAIS]
    if isinstance(ids, str):
        ids = [ids]
    por_id = {config["id"]: config for config in CONFIGURACOES_EXPERIMENTAIS}
    resultado = []
    for identificador in ids:
        chave = str(identificador).upper()
        if chave not in por_id:
            raise ValueError(f"Configuração desconhecida: {identificador}. Use C1, C2, C3 ou C4.")
        if chave in {item["id"] for item in resultado}:
            raise ValueError(f"Configuração repetida: {chave}.")
        resultado.append(dict(por_id[chave]))
    if not resultado:
        raise ValueError("Escolha pelo menos uma configuração.")
    return resultado
